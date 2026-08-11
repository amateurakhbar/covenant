#!/usr/bin/env python3
"""
Covenant strength screening for UK commercial tenants, from Companies House.

The question this answers: a lease has been offered by entity X. Is that covenant
real, and if not, where does the actual money sit?

Everything here comes from the free Companies House REST API. No accounts parsing,
no paid credit reference agency, no scraping.

    export CH_API_KEY=...   # or COMPANIES_HOUSE_API_KEY. Free: developer.company-information.service.gov.uk
    python covenant.py "Pret A Manger"     # find the entity
    python covenant.py 01854213            # assess it
    python covenant.py --selftest          # prove the scoring, no key needed
"""

import json
import os
import sys
from datetime import date, datetime
from urllib.parse import quote

import requests

API = "https://api.company-information.service.gov.uk"

# SIC codes that mean "this entity does not trade". A lease covenant sitting in one
# of these is a shell unless a trading parent guarantees it.
NON_TRADING_SIC = {
    "64209": "Activities of other holding companies",
    "64205": "Activities of financial services holding companies",
    "64203": "Activities of construction holding companies",
    "64202": "Activities of production holding companies",
    "64204": "Activities of distribution holding companies",
    "70100": "Activities of head offices",
    "68209": "Letting and operating of own or leased real estate",
    "68100": "Buying and selling of own real estate",
    "99999": "Dormant company",
    "74990": "Non-trading company",
}

# Accounts filing type -> (points deducted, what it tells a surveyor)
THIN_ACCOUNTS = {
    "dormant": (45, "dormant accounts; the entity does not trade"),
    "micro-entity": (30, "micro-entity accounts; turnover under £1m, balance sheet under £500k"),
    "total-exemption-full": (12, "small-company exemption; no audit, limited disclosure"),
    "total-exemption-small": (12, "small-company exemption; no audit, limited disclosure"),
    "audit-exemption-subsidiary": (20, "audit exemption as a subsidiary; relies on a parent guarantee (s479C)"),
    "small": (10, "small-company accounts; no P&L disclosure"),
    "initial": (25, "no accounts filed yet; no trading record"),
}


def _today():
    return date.today()


def fetch(path, key=None):
    """GET a Companies House endpoint. Key is the HTTP basic auth username."""
    key = key or os.environ.get("CH_API_KEY") or os.environ.get("COMPANIES_HOUSE_API_KEY")
    if not key:
        sys.exit("Set CH_API_KEY or COMPANIES_HOUSE_API_KEY (free at developer.company-information.service.gov.uk)")
    r = requests.get(API + path, auth=(key, ""), timeout=20)
    if r.status_code == 404:
        return None
    if r.status_code == 401:
        sys.exit("Companies House rejected the key (401). Check CH_API_KEY.")
    r.raise_for_status()
    return r.json()


def _years_since(iso):
    if not iso:
        return None
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return (_today() - d).days / 365.25


def assess(profile, charges=None, psc=None):
    """Score covenant strength 0-100 from a Companies House company profile.

    Deduction-based and fully evidenced: every point lost names the filing that
    caused it, because a surveyor will not act on a number they cannot trace.
    """
    charges = charges or {}
    psc = psc or {}
    score = 100
    flags = []          # (severity, statement): severity drives the sort order
    actions = set()

    def hit(points, severity, statement):
        nonlocal score
        score -= points
        flags.append((severity, statement, points))

    name = profile.get("company_name", "?")
    number = profile.get("company_number", "?")
    status = profile.get("company_status", "unknown")

    # --- 1. Is it even alive -------------------------------------------------
    if status != "active":
        label = status.replace("-", " ")
        if status in ("liquidation", "administration", "receivership", "insolvency-proceedings"):
            hit(85, 3, f"Company is in {label}: the covenant has failed")
        elif status in ("dissolved", "closed", "converted-closed"):
            hit(100, 3, f"Company is {label}: this entity no longer exists")
        else:
            hit(60, 3, f"Company status is '{label}', not active")
        actions.add("Do not proceed on this entity. Establish who, if anyone, has succeeded to the tenancy.")

    if profile.get("has_insolvency_history"):
        hit(25, 3, "Insolvency history on file")
        actions.add("Read the insolvency filings before pricing the lease.")
    if profile.get("has_been_liquidated"):
        hit(20, 3, "Has previously been liquidated")

    # --- 2. Filing discipline: the leading indicator of distress -------------
    accounts = profile.get("accounts") or {}
    if accounts.get("overdue") or (accounts.get("next_accounts") or {}).get("overdue"):
        due = accounts.get("next_due") or (accounts.get("next_accounts") or {}).get("due_on")
        hit(30, 3, f"Annual accounts are OVERDUE (due {due}): the single best early warning of distress")
        actions.add("Ask why accounts are late, in writing, before exchange.")

    cs = profile.get("confirmation_statement") or {}
    if cs.get("overdue"):
        hit(12, 2, f"Confirmation statement overdue (due {cs.get('next_due')})")
        actions.add("Late confirmation statements suggest the entity is not being actively administered.")

    # --- 3. Thin-entity detection: is there anything behind the name --------
    last = accounts.get("last_accounts") or {}
    acc_type = last.get("type")
    if acc_type in THIN_ACCOUNTS:
        pts, why = THIN_ACCOUNTS[acc_type]
        hit(pts, 2, f"Accounts type '{acc_type}': {why}")
        if acc_type in ("dormant", "micro-entity", "initial"):
            actions.add("Treat as a shell. Require a parent company guarantee or a rent deposit.")
        if acc_type == "audit-exemption-subsidiary":
            actions.add("The parent that gave the s479C guarantee is your real covenant; assess that entity instead.")
    elif acc_type == "full":
        flags.append((0, "Files full accounts: the strongest disclosure level available", 0))

    made_up = last.get("made_up_to")
    if made_up:
        age = _years_since(made_up)
        if age and age > 1.8:
            hit(15, 2, f"Most recent accounts are made up to {made_up}, over {age:.1f} years stale")
            actions.add("Request current management accounts; the filed position is out of date.")

    # --- 4. Is it a trading entity or a holding vehicle ---------------------
    for sic in profile.get("sic_codes") or []:
        if sic in NON_TRADING_SIC:
            hit(25, 3, f"SIC {sic}: {NON_TRADING_SIC[sic]}. This is not a trading company")
            actions.add("Identify the trading entity in the group and take the covenant, or a guarantee, from that.")
            break

    # --- 5. Track record ----------------------------------------------------
    age = _years_since(profile.get("date_of_creation"))
    if age is not None:
        if age < 2:
            hit(20, 2, f"Incorporated {profile.get('date_of_creation')}, under 2 years of trading history")
            actions.add("No meaningful track record. Rent deposit of 6-12 months is the usual response.")
        elif age < 5:
            hit(8, 1, f"Incorporated {profile.get('date_of_creation')}: {age:.0f} years of history, limited record")
        elif age > 15:
            flags.append((0, f"Trading since {profile.get('date_of_creation')}, {age:.0f} years of history", 0))

    # --- 6. Prior-ranking secured debt --------------------------------------
    items = charges.get("items") or []
    outstanding = [c for c in items if c.get("status") == "outstanding"]
    floating = [c for c in outstanding
                if any("floating" in str(p).lower() for p in (c.get("particulars") or {}).values())
                or c.get("particulars", {}).get("floating_charge_covers_all")]
    if outstanding:
        sev = 2 if len(outstanding) > 3 else 1
        hit(min(4 * len(outstanding), 20), sev,
            f"{len(outstanding)} outstanding charge(s) registered: secured lenders rank ahead of you")
        if floating:
            hit(8, 2, f"{len(floating)} of those is a floating charge over the undertaking")
            actions.add("A floating charge captures the assets you would otherwise distrain against.")

    # --- 7. Identity / diligence flags --------------------------------------
    prev = profile.get("previous_company_names") or []
    if prev:
        recent = [p for p in prev if (_years_since(p.get("ceased_on")) or 99) < 5]
        if recent:
            hit(6, 1, f"Renamed within 5 years (was '{recent[0].get('name')}'); check for continuity of trade")
    if profile.get("registered_office_is_in_dispute"):
        hit(15, 3, "Registered office address is in dispute")
    if profile.get("undeliverable_registered_office_address"):
        hit(15, 3, "Registered office address is undeliverable: Companies House cannot reach this company")

    # --- 8. Who actually controls it ----------------------------------------
    parents = [p for p in (psc.get("items") or [])
               if "corporate" in (p.get("kind") or "") and not p.get("ceased_on")]
    if parents:
        p = parents[0]
        flags.append((0, f"Controlled by {p.get('name')}, a potential guarantor", 0))
        actions.add(f"Assess {p.get('name')} as the guarantor covenant.")

    score = max(0, min(100, score))
    band, verdict = _band(score)
    flags.sort(key=lambda f: -f[0])

    return {
        "company": name,
        "company_number": number,
        "status": status,
        "score": score,
        "band": band,
        "verdict": verdict,
        "findings": [f[1] for f in flags],
        "deductions": [{"finding": f[1], "points": f[2]} for f in flags],
        "recommended_actions": sorted(actions),
        "source": f"https://find-and-update.company-information.service.gov.uk/company/{number}",
    }


def _band(score):
    if score >= 80:
        return "A", "Strong covenant. Institutionally acceptable without additional security."
    if score >= 60:
        return "B", "Acceptable covenant. Standard rent deposit is prudent."
    if score >= 40:
        return "C", "Weak covenant. Require a guarantee or 6-12 months' rent deposit."
    if score >= 20:
        return "D", "Poor covenant. Do not rely on this entity's own strength."
    return "E", "Failed or shell entity. The covenant is worthless as it stands."


def screen(company_number, key=None):
    """Full assessment: profile + charges + PSC."""
    cn = company_number.zfill(8) if company_number.isdigit() else company_number.upper()
    profile = fetch(f"/company/{cn}", key)
    if not profile:
        sys.exit(f"No company found with number {cn}")
    charges = fetch(f"/company/{cn}/charges", key) if profile.get("has_charges") else {}
    psc = fetch(f"/company/{cn}/persons-with-significant-control", key) or {}
    return assess(profile, charges, psc)


def search(query, key=None):
    res = fetch(f"/search/companies?q={quote(query)}&items_per_page=20", key) or {}
    return res.get("items", [])


def render(r):
    out = [
        "",
        f"  {r['company']}  ({r['company_number']})",
        f"  {'─' * 68}",
        f"  COVENANT BAND {r['band']}   score {r['score']}/100",
        f"  {r['verdict']}",
        "",
    ]
    if r["findings"]:
        out.append("  Findings")
        out += [f"    • {f}" for f in r["findings"]]
        out.append("")
    if r["recommended_actions"]:
        out.append("  Recommended action")
        out += [f"    → {a}" for a in r["recommended_actions"]]
        out.append("")
    out.append(f"  Source: {r['source']}")
    out.append("")
    return "\n".join(out)


# --- self-check ------------------------------------------------------------
# Real Companies House payloads, pulled 2026-08-10. The point of the fixtures is
# that the scoring is provable without a key and without the network.

PRET_HOLDCO = {
    "company_name": "PRET A MANGER LIMITED",
    "company_number": "11391321",
    "company_status": "active",
    "date_of_creation": "2018-05-31",
    "sic_codes": ["64209"],
    "has_charges": False,
    "has_insolvency_history": False,
    "accounts": {
        "last_accounts": {"made_up_to": "2026-01-01", "type": "audit-exemption-subsidiary"},
        "next_accounts": {"due_on": "2027-09-30", "overdue": False},
        "overdue": False,
    },
    "confirmation_statement": {"next_due": "2027-06-13", "overdue": False},
    "previous_company_names": [{"name": "JAB (ACQUISITION) LTD", "ceased_on": "2019-12-20"}],
}

PRET_OPCO = {
    "company_name": "PRET A MANGER (EUROPE) LIMITED",
    "company_number": "01854213",
    "company_status": "active",
    "date_of_creation": "1984-10-10",
    "sic_codes": ["47110", "47290"],
    "has_charges": False,
    "has_insolvency_history": False,
    "accounts": {
        "last_accounts": {"made_up_to": "2026-01-01", "type": "full"},
        "next_accounts": {"due_on": "2027-09-30", "overdue": False},
        "overdue": False,
    },
    "confirmation_statement": {"next_due": "2027-01-19", "overdue": False},
    "previous_company_names": [{"name": "METYMART LIMITED", "ceased_on": "1985-08-12"}],
}

SHELL = {
    "company_name": "EXAMPLE TRADING LIMITED",
    "company_number": "99999999",
    "company_status": "active",
    "date_of_creation": "2025-06-01",
    "sic_codes": ["56101"],
    "has_charges": True,
    "accounts": {
        "last_accounts": {"made_up_to": "2025-12-31", "type": "dormant"},
        "next_accounts": {"due_on": "2026-03-01", "overdue": True},
        "overdue": True,
    },
    "confirmation_statement": {"next_due": "2026-04-01", "overdue": True},
}

FAILED = {
    "company_name": "GONE LIMITED",
    "company_number": "88888888",
    "company_status": "liquidation",
    "date_of_creation": "2001-01-01",
    "sic_codes": ["47110"],
    "has_insolvency_history": True,
    "accounts": {},
    "confirmation_statement": {},
}


def selftest():
    opco = assess(PRET_OPCO)
    holdco = assess(PRET_HOLDCO)
    shell = assess(SHELL, charges={"items": [
        {"status": "outstanding", "particulars": {"floating_charge_covers_all": True, "description": "floating charge"}},
        {"status": "outstanding", "particulars": {"description": "fixed charge over plant"}},
    ]})
    failed = assess(FAILED)

    # The trading entity must outrank the holding vehicle. This is the whole thesis:
    # two near-identical names at one address, opposite covenant quality.
    assert opco["score"] > holdco["score"], (opco["score"], holdco["score"])
    assert opco["band"] == "A", opco
    assert any("holding" in f.lower() for f in holdco["findings"]), holdco["findings"]

    # A dormant, overdue, newly incorporated entity with floating charges must fail.
    assert shell["band"] in ("D", "E"), shell
    assert any("OVERDUE" in f for f in shell["findings"]), shell["findings"]
    assert any("floating" in f.lower() for f in shell["findings"]), shell["findings"]
    assert any("deposit" in a.lower() or "guarantee" in a.lower()
               for a in shell["recommended_actions"]), shell["recommended_actions"]

    # A company in liquidation is the floor, and must say so first.
    assert failed["score"] == 0, failed
    assert failed["band"] == "E", failed
    assert "liquidation" in failed["findings"][0].lower(), failed["findings"]

    # Bands must be monotonic in score.
    assert [_band(s)[0] for s in (95, 70, 50, 30, 5)] == ["A", "B", "C", "D", "E"]

    print("selftest passed")
    print(render(opco))
    print(render(holdco))
    print(render(shell))


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    if args[0] == "--selftest":
        return selftest()

    q = " ".join(args)
    as_json = False
    if "--json" in args:
        as_json = True
        q = " ".join(a for a in args if a != "--json")

    # A bare company number goes straight to assessment; anything else is a search.
    if q.replace(" ", "").isalnum() and any(c.isdigit() for c in q) and len(q.replace(" ", "")) <= 8:
        r = screen(q.replace(" ", ""))
        print(json.dumps(r, indent=2) if as_json else render(r))
        return

    hits = search(q)
    if not hits:
        print(f"No companies found for '{q}'")
        return
    print(f"\n  {len(hits)} entities match '{q}'; the covenant is only as good as the one on the lease:\n")
    for h in hits[:15]:
        status = h.get("company_status", "?")
        mark = " " if status == "active" else "×"
        print(f"  {mark} {h.get('company_number'):>10}  {h.get('title', '')[:52]:<52} "
              f"{status:<12} inc. {h.get('date_of_creation', '?')}")
    print(f"\n  Assess one:  python covenant.py <company_number>\n")


if __name__ == "__main__":
    main()
