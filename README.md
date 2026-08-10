# covenant

**Covenant strength screening for UK commercial tenants, from Companies House.**

A lease has been offered by entity X. Is that covenant real, and if not, where does the actual money sit?

---

## The problem, in one example

Search Companies House for "Pret A Manger" and you get 10,000 results. Two of them sit at the same London address, with nearly the same name:

```
python covenant.py 11391321        python covenant.py 01854213
```

```
  PRET A MANGER LIMITED                    PRET A MANGER (EUROPE) LIMITED
  BAND C — score 55/100                    BAND A — score 100/100
  Weak covenant. Require a guarantee       Strong covenant. Institutionally
  or 6-12 months' rent deposit.            acceptable without extra security.

  • SIC 64209 — holding company.           • Files full accounts — the strongest
    This is not a trading company            disclosure level available
  • Accounts type                          • Trading since 1984 — 42 years
    'audit-exemption-subsidiary'             of history
    — relies on a parent guarantee
    under s479C

  → Identify the trading entity in
    the group and take the covenant,
    or a guarantee, from that.
```

One is a JAB acquisition vehicle incorporated in 2018 that files subsidiary-exemption accounts. The other has been trading since 1984 and files full accounts. **A landlord who signs the first one thinks they have the household name and does not.**

That distinction is free, public, and structured. Almost nobody checks it, because checking it by hand across a rent roll is tedious.

---

## What it checks

Every signal is a structured field in the free Companies House API. Nothing is parsed out of a PDF, nothing is scraped, no credit reference agency is involved.

| Signal | Why a surveyor cares |
|---|---|
| Company status | Liquidation, administration, strike-off — the covenant has already failed |
| **Accounts overdue** | The single best leading indicator of distress, and it is public months before anything else |
| Confirmation statement overdue | The entity is not being actively administered |
| Accounts filing type | Dormant / micro-entity / subsidiary-exemption = thin entity, the covenant is a shell |
| SIC code | 64209, 70100, 68209 and friends mean a holding vehicle, not a trading business |
| Incorporation date | Under two years is no track record |
| Outstanding charges | Secured lenders rank ahead of the landlord |
| **Floating charges** | Captures the very assets you would otherwise distrain against |
| Previous names | Recent rename breaks continuity of trade |
| Registered office in dispute / undeliverable | Companies House cannot reach this company |
| Corporate PSC | Names the parent — your potential guarantor |

Output is a band (A–E), a score, **every finding traced to the filing that caused it**, and a recommended action in the language of the transaction: parent guarantee, rent deposit, assess-the-parent-instead.

The evidence trail is deliberate. A surveyor will not act on a number they cannot trace back to a source.

---

## Use

```bash
pip install requests
export CH_API_KEY=...   # free, instant: developer.company-information.service.gov.uk
```

```bash
python covenant.py "Gail's Bakery"    # list the candidate entities
python covenant.py 01854213           # assess one
python covenant.py 01854213 --json    # for a rent roll pipeline
python covenant.py --selftest         # prove the scoring, no key or network needed
```

`--selftest` runs the scoring against real Companies House payloads captured on 2026-08-10 and asserts the conclusions, including that the trading entity must outrank the holding vehicle.

---

## Area sweeps: `sweep.py`

The REST API answers "tell me about company X". It cannot answer "who is registered *here*". The free monthly [bulk snapshot](https://download.companieshouse.gov.uk/en_output.html) (~470 MB zipped, all 5.7M companies) can. `sweep.py` distils it once into a ~190 MB Parquet, then scores whole postcode areas in under a second:

```bash
python sweep.py --build BasicCompanyDataAsOneFile-2026-08-01.csv   # once
python sweep.py W1S                  # rank every company in an outward code
python sweep.py W1S --csv w1s.csv    # full table for a spreadsheet
python sweep.py --stats W1           # distress league table across an area
```

Real output, snapshot of 2026-08-01:

```
  7,746 companies registered in W1S
  A: 2,113  B: 2,007  C: 2,390  D: 1,008  E: 228
  47% are band C or below — would need a guarantee, deposit,
  or a hard look before going on a lease
```

The sweep uses only bulk-file columns (status, overdue dates, account category, SIC, charge counts). The weakest names it surfaces are then deep-dive candidates for `covenant.py`, which adds PSC, floating-charge detail and insolvency history from the live API.

**Stated caveat:** this sweeps *registered* office addresses, and many companies register at an accountant or agent. It finds the companies anchored to a place, not necessarily the shopfronts on it. Joining the VOA rating list (actual occupiers, floor areas, rateable values) is the roadmap for trading-address truth.

## Roadmap

1. **VOA rating-list join** — map covenant bands onto actual trading occupiers and rateable value: "£Xm of rateable value in W1 sits on band-D covenants."
2. **Covenant watch** — the Companies House streaming API pushes filing events in real time; alert a landlord the day a tenant goes accounts-overdue or grants a floating charge, months before it reaches the trade press.
3. **Rent cover** — parse iXBRL accounts where they exist (many are image PDFs; coverage will be partial and will say so).

## Scope, honestly

- **England, Wales, Scotland and NI**, wherever Companies House registration applies. Not partnerships, sole traders or overseas entities without a UK registration.
- **No financial figures.** Turnover, net assets and rent cover live in iXBRL accounts documents, and many filers still submit image PDFs. This tool deliberately stops where free structured data stops rather than guessing. Rent cover is the obvious next layer.
- **A screen, not an opinion.** It tells you which entities on a rent roll deserve an hour of a surveyor's attention. It does not replace the surveyor, and nothing here is a Red Book valuation or investment advice.

## Licence

MIT.
