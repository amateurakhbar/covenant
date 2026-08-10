#!/usr/bin/env python3
"""
Covenant dashboard — the Claude Design front-end wired to the live engines.

    python app.py            # http://localhost:8321

Routes:
    /                        entity search (live Companies House API)
    /company/<number>        assessment certificate (live)
    /company/<a>/vs/<b>      side-by-side comparison (live)
    /sweep/<outward>         postcode sweep (offline bulk snapshot via DuckDB)
    /appendix                edge states and scope
"""

import os
import re
import sys
from datetime import datetime, timezone

import duckdb
from flask import Flask, redirect, render_template, request, url_for

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import covenant
import sweep as sweep_mod

# Pick up the key from a local .env if the environment doesn't have one.
if not (os.environ.get("CH_API_KEY") or os.environ.get("COMPANIES_HOUSE_API_KEY")):
    for envfile in (os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
                    os.path.expanduser("~/Amakor Capital/.env")):
        if os.path.exists(envfile):
            for line in open(envfile):
                if line.startswith(("CH_API_KEY=", "COMPANIES_HOUSE_API_KEY=")):
                    k, _, v = line.strip().partition("=")
                    os.environ[k] = v
            if os.environ.get("CH_API_KEY") or os.environ.get("COMPANIES_HOUSE_API_KEY"):
                break

app = Flask(__name__)

CH_URL = "https://find-and-update.company-information.service.gov.uk/company"
OUTWARD_RE = re.compile(r"^[A-Za-z]{1,2}\d[A-Za-z\d]?$")
NUMBER_RE = re.compile(r"^[A-Za-z]{0,2}\d{6,8}$")

BAND_VERDICTS = dict(A="Strong covenant. Institutionally acceptable without additional security.",
                     B="Acceptable covenant. Standard rent deposit is prudent.",
                     C="Weak covenant. Require a guarantee or 6-12 months' rent deposit.",
                     D="Poor covenant. Do not rely on this entity's own strength.",
                     E="Failed or shell entity. The covenant is worthless as it stands.")


def _now():
    return datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def _source_for(finding, number):
    """Map a finding to the register page that evidences it."""
    f = finding.lower()
    if "psc" in f or "controlled by" in f:
        return ("PSC register", f"{CH_URL}/{number}/persons-with-significant-control")
    if "accounts" in f or "confirmation" in f:
        return ("Filing history", f"{CH_URL}/{number}/filing-history")
    if "charge" in f:
        return ("Charges register", f"{CH_URL}/{number}/charges")
    return ("Company profile", f"{CH_URL}/{number}")


def _facts(profile):
    """The register-facts rows the certificate shows above the findings."""
    acc = (profile.get("accounts") or {}).get("last_accounts") or {}
    cs = profile.get("confirmation_statement") or {}
    prev = profile.get("previous_company_names") or []
    facts = [("Company number", profile.get("company_number", "—")),
             ("Incorporated", profile.get("date_of_creation", "—"))]
    if prev:
        facts.append(("Previous name", f"{prev[0].get('name')} — until {prev[0].get('ceased_on')}"))
    sics = profile.get("sic_codes") or []
    if sics:
        label = ", ".join(sics)
        if sics[0] in covenant.NON_TRADING_SIC:
            label = f"{sics[0]} — {covenant.NON_TRADING_SIC[sics[0]]}"
        facts.append(("SIC code", label))
    if acc.get("made_up_to"):
        facts.append(("Last accounts", f"made up to {acc['made_up_to']} — type '{acc.get('type', '?')}'"))
    else:
        facts.append(("Last accounts", "none filed"))
    if cs.get("next_due"):
        facts.append(("Confirmation stmt",
                      f"next due {cs['next_due']} — {'OVERDUE' if cs.get('overdue') else 'not overdue'}"))
    return facts


def _screen_full(number):
    """Profile + assessment, or None if not found."""
    cn = number.zfill(8) if number.isdigit() else number.upper()
    profile = covenant.fetch(f"/company/{cn}")
    if not profile:
        return None
    charges = covenant.fetch(f"/company/{cn}/charges") if profile.get("has_charges") else {}
    psc = covenant.fetch(f"/company/{cn}/persons-with-significant-control") or {}
    r = covenant.assess(profile, charges, psc)
    r["facts"] = _facts(profile)
    r["deductions"] = [
        {**d, "source": _source_for(d["finding"], r["company_number"])} for d in r["deductions"]
    ]
    r["total_deducted"] = sum(d["points"] for d in r["deductions"])
    r["verdict"] = BAND_VERDICTS[r["band"]]
    r["ch_url"] = f"{CH_URL}/{r['company_number']}"
    return r


@app.route("/")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return render_template("search.html", q="", results=None, now=_now())
    if OUTWARD_RE.match(q):
        return redirect(url_for("sweep_view", outward=q.upper()))
    if NUMBER_RE.match(q.replace(" ", "")):
        return redirect(url_for("certificate", number=q.replace(" ", "").upper()))
    hits = covenant.search(q)
    # Flag duplicate registered names — the trap the demo is built on.
    names = {}
    for h in hits:
        names[h.get("title")] = names.get(h.get("title"), 0) + 1
    for h in hits:
        h["duplicate"] = names.get(h.get("title"), 0) > 1
    return render_template("search.html", q=q, results=hits, now=_now())


@app.route("/company/<number>")
def certificate(number):
    r = _screen_full(number)
    if r is None:
        return render_template("search.html", q=number, results=[], now=_now()), 404
    # Suggest the demo comparison when looking at either Pret entity.
    other = {"11391321": "01854213", "01854213": "11391321"}.get(r["company_number"])
    return render_template("certificate.html", r=r, compare_with=other, now=_now())


@app.route("/company/<a>/vs/<b>")
def compare(a, b):
    ra, rb = _screen_full(a), _screen_full(b)
    if not ra or not rb:
        return redirect(url_for("certificate", number=a))
    return render_template("compare.html", a=ra, b=rb, now=_now())


@app.route("/sweep/<outward>")
def sweep_view(outward):
    outward = outward.upper()
    if not os.path.exists(sweep_mod.PARQUET):
        return render_template("appendix.html", now=_now(),
                               error="No local snapshot — run sweep.py --build first."), 503
    con = duckdb.connect()
    con.execute("SET memory_limit='300MB'")  # ponytail: fits Render's 512MB free dyno
    rows = con.execute(f"""
        WITH scored AS (SELECT *, {sweep_mod.SCORE_SQL} AS score
                        FROM '{sweep_mod.PARQUET}' WHERE Outward = ?)
        SELECT Number, Name, CompanyStatus, AccountCategory, ChargesOutstanding,
               (AccountsNextDue < CURRENT_DATE) AS AccountsOverdue,
               score, {sweep_mod.BAND_SQL} AS band
        FROM scored ORDER BY score ASC, Name
    """, [outward]).fetchall()
    if not rows:
        return render_template("sweep.html", outward=outward, total=0, now=_now())

    bands = {}
    for r in rows:
        bands[r[-1]] = bands.get(r[-1], 0) + 1
    total = len(rows)
    weak_pct = round(100 * sum(bands.get(b, 0) for b in "CDE") / total)

    weakest = []
    for num, name, status, acct, charges, overdue, score, band in rows[:8]:
        why = []
        if not str(status).lower().startswith("active"):
            why.append(status)
        if overdue:
            why.append("accounts OVERDUE")
        if acct and any(k in acct.upper() for k in ("DORMANT", "MICRO", "NO ACCOUNTS")):
            why.append(acct)
        if charges:
            why.append(f"{charges} charge(s)")
        weakest.append(dict(number=num, name=name, score=int(score), band=band,
                            why=", ".join(why)))

    # Sibling outward codes share the district: W1S's peers are W1 + optional
    # letter (W1C, W1K ...), NOT W10-W14, which are different districts.
    district = re.match(r"^[A-Z]{1,2}\d{1,2}", outward).group()
    league = con.execute(f"""
        WITH scored AS (SELECT Outward, {sweep_mod.SCORE_SQL} AS score
                        FROM '{sweep_mod.PARQUET}'
                        WHERE regexp_full_match(Outward, ?) AND CompanyStatus ILIKE 'active%')
        SELECT Outward, round(100.0 * count(*) FILTER (WHERE score < 60) / count(*), 1)
        FROM scored GROUP BY Outward HAVING count(*) >= 100 ORDER BY 2 DESC
    """, [district + "[A-Z]?"]).fetchall()

    sectors = con.execute(f"""
        WITH scored AS (SELECT SIC1, {sweep_mod.SCORE_SQL} AS score
                        FROM '{sweep_mod.PARQUET}' WHERE Outward = ? AND SIC1 != '')
        SELECT SIC1, count(*), round(100.0 * count(*) FILTER (WHERE score < 60) / count(*))
        FROM scored GROUP BY SIC1 HAVING count(*) >= 100 ORDER BY 3 DESC LIMIT 6
    """, [outward]).fetchall()
    sectors = [(re.sub(r"^\d+ - ", "", s)[:34], n, int(p)) for s, n, p in sectors]

    # Registered-address concentration, for the stated caveat.
    conc = con.execute(f"""
        SELECT round(100.0 * sum(c) / ?, 0) FROM (
          SELECT count(*) c FROM '{sweep_mod.PARQUET}' WHERE Outward = ?
          GROUP BY Address ORDER BY c DESC LIMIT 20)
    """, [total, outward]).fetchone()[0]

    return render_template("sweep.html", outward=outward, total=total, bands=bands,
                           weak_pct=weak_pct, weakest=weakest, league=league,
                           league_max=league[0][1] if league else 100,
                           sectors=sectors, sector_max=sectors[0][2] if sectors else 100,
                           concentration=int(conc or 0), now=_now())


@app.route("/appendix")
def appendix():
    return render_template("appendix.html", now=_now(), error=None)


if __name__ == "__main__":
    app.run(port=8321, debug=True)
