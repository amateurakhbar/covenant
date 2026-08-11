# Demo: five steps from a name on a lease to a market-wide view

Everything below is real output, run live on 2026-08-10 against the Companies House
API and the 2026-08-01 bulk snapshot (5,695,465 companies). Every claim traces to a
public filing you can click.

Setup, once:

```bash
pip install -r requirements.txt
export CH_API_KEY=...   # free, instant: developer.company-information.service.gov.uk
```

---

## Step 1: The ambiguity

A lease lands on your desk. The tenant is "Pret A Manger". Which entity is that?

```bash
python covenant.py "Pret A Manger"
```

```
  20 entities match 'Pret A Manger'; the covenant is only as good as the one on the lease:

      11391321  PRET A MANGER LIMITED                     active     inc. 2018-05-31
      10674734  PRET UK LIMITED                           active     inc. 2017-03-16
  ×   03602613  PRET A MANGER LIMITED                     dissolved  inc. 1998-07-17
      01854213  PRET A MANGER (EUROPE) LIMITED            active     inc. 1984-10-10
      04240964  PRET A MANGER (HONG KONG) LIMITED         active     inc. 2001-06-25
      14722221  PRET A MANGER (INTERNATIONAL) LIMITED     active     inc. 2023-03-10
  ×   14204578  PRET A MANGER LOGISTICS LIMITED           dissolved  inc. 2022-06-29
  ×   02762743  PRET A MANGER (G.B.) LIMITED              dissolved  inc. 1992-11-06
      ...
```

Twenty entities. Two of them are *both* named exactly "PRET A MANGER LIMITED": one
live, one dissolved. Which one is on your lease matters enormously.

## Step 2: The trap

Assess the one a landlord would naturally pick: the live company carrying the exact
brand name.

```bash
python covenant.py 11391321
```

```
  PRET A MANGER LIMITED  (11391321)
  ────────────────────────────────────────────────────────────────────
  COVENANT BAND C   score 55/100
  Weak covenant. Require a guarantee or 6-12 months' rent deposit.

  Findings
    • SIC 64209: Activities of other holding companies. This is not a trading company
    • Accounts type 'audit-exemption-subsidiary': relies on a parent guarantee (s479C)
    • Controlled by Pret Holding 2 Ltd, a potential guarantor

  Recommended action
    → Assess Pret Holding 2 Ltd as the guarantor covenant.
    → Identify the trading entity in the group and take the covenant, or a guarantee, from that.
    → The parent that gave the s479C guarantee is your real covenant; assess that entity instead.
```

The famous name is a **holding shell**: incorporated 2018 as JAB (ACQUISITION) LTD,
renamed a year later, SIC code "activities of other holding companies", minimal
subsidiary-exemption accounts. A landlord who signs this entity thinks they have the
sandwich chain. They don't.

## Step 3: The resolution

The tool said the real covenant is elsewhere in the group. Follow it.

```bash
python covenant.py 01854213
```

```
  PRET A MANGER (EUROPE) LIMITED  (01854213)
  ────────────────────────────────────────────────────────────────────
  COVENANT BAND A   score 100/100
  Strong covenant. Institutionally acceptable without additional security.

  Findings
    • Files full accounts: the strongest disclosure level available
    • Trading since 1984-10-10, 42 years of history
    • Controlled by Pret A Manger Limited, a potential guarantor
```

Same brand, same registered address, opposite covenant. The entity with the less
obvious name is the one that has traded since 1984 and files full accounts. **This
distinction is free, public, and structured, and almost nobody checks it, because
checking it by hand across a rent roll is tedious.**

## Step 4: The zoom-out

Individual lookups are the retail view. The bulk snapshot gives the market view:
score every registered company in a postcode area, offline, in under a second.

```bash
python sweep.py W1S
```

```
  7,746 companies registered in W1S
  A: 2,113  B: 2,007  C: 2,390  D: 1,008  E: 228
  47% are band C or below: would need a guarantee, deposit,
  or a hard look before going on a lease

  Weakest covenants (deep-dive candidates for covenant.py):
  band score  number     name                                      why (register says)
  E    0      11867480   12 RAYS LIMITED                           Liquidation, accounts OVERDUE, dormant
  E    0      16043531   354 OXFORD STREET LIMITED                 accounts OVERDUE, no accounts filed, 1 charge(s)
  E    0      02259267   ANTLOW ENTERPRISES LIMITED                Live but Receiver Manager on at least one charge
  E    0      16064310   BGO EUROPE IV LOGISTICS UK DIDCOT PROPCO  accounts OVERDUE, no accounts filed
  ...
```

Or a distress league table across all of W1 (`python sweep.py --stats W1`): W1C is
the weakest outward code at 61% band C-or-below; W1F the strongest at 39%.

## Step 5: The loop closes

Take a name the sweep flagged and deep-dive it with the live API.

```bash
python covenant.py 16043531
```

```
  354 OXFORD STREET LIMITED  (16043531)
  ────────────────────────────────────────────────────────────────────
  COVENANT BAND D   score 25/100
  Poor covenant. Do not rely on this entity's own strength.

  Findings
    • Annual accounts are OVERDUE (due 2026-07-28): the single best early warning of distress
    • SIC 68209: Letting and operating of own or leased real estate. This is not a trading company
    • Incorporated 2024-10-28, under 2 years of trading history
    • Controlled by Clas Puma Limited, a potential guarantor

  Recommended action
    → Ask why accounts are late, in writing, before exchange.
    → Assess Clas Puma Limited as the guarantor covenant.
    → No meaningful track record. Rent deposit of 6-12 months is the usual response.
```

A 2024 propco on one of the most famous retail addresses in Britain, whose first
accounts went overdue two weeks before this demo was run, with a registered charge:
surfaced by a free sweep and confirmed by a free API call.

---

## The shape of the pipeline

```
bulk snapshot (5.7M companies, monthly, free)
      │  sweep.py · offline, ~0.6s per postcode area
      ▼
ranked area table → weakest names flagged
      │  covenant.py · live API: PSC parent, floating charges, insolvency
      ▼
banded verdict + findings traced to filings + actions in transaction language
```

The scoring itself is provable without a key or network: `python covenant.py
--selftest` runs the rules against captured real payloads and asserts, among other
things, that the Pret trading entity must outrank the holding vehicle.

*Nothing here is investment advice or a substitute for professional judgement: it is
a screen that tells you which entities deserve an hour of a surveyor's attention.*
