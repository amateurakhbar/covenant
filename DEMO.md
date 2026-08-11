# Demo: five steps from a name on a lease to a market-wide view

Everything below is real output, run live on 2026-08-11 against the Companies House
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

      11391321  PRET A MANGER LIMITED                                active       inc. 2018-05-31
      10674734  PRET UK LIMITED                                      active       inc. 2017-03-16
  ×   03602613  PRET A MANGER LIMITED                                dissolved    inc. 1998-07-17
      01854213  PRET A MANGER (EUROPE) LIMITED                       active       inc. 1984-10-10
      04240964  PRET A MANGER (HONG KONG) LIMITED                    active       inc. 2001-06-25
      14722221  PRET A MANGER (INTERNATIONAL) LIMITED                active       inc. 2023-03-10
      03836164  PRET A MANGER (USA) LIMITED                          active       inc. 1999-08-31
  ×   14204578  PRET A MANGER LOGISTICS LIMITED                      dissolved    inc. 2022-06-29
  ×   14222552  PRET A MANGER (ELEPHANT ROAD) LIMITED                dissolved    inc. 2022-07-08
  ×   02762743  PRET A MANGER (G.B.) LIMITED                         dissolved    inc. 1992-11-06
  ×   04122331  PRET A MANGER HOLDINGS LIMITED                       dissolved    inc. 2000-12-11
  ×   02841749  PRET A MANGER (NETHERLANDS) LIMITED                  dissolved    inc. 1993-08-03
  ×   01903370  PRET A MANGER (U.K.) LIMITED                         dissolved    inc. 1985-04-09
      06324424  MANGERA YVARS ARCHITECTS LIMITED                     active       inc. 2007-07-25
      12662363  BREAD AND MACAROON LTD                               active       inc. 2020-06-11

  Assess one:  python covenant.py <company_number>
```

Twenty entities match; the first fifteen are printed. Two of them are *both* named
exactly "PRET A MANGER LIMITED", one live, one dissolved. Which one is on your lease
matters enormously.

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
    • Accounts type 'audit-exemption-subsidiary': audit exemption as a subsidiary; relies on a parent guarantee (s479C)
    • Controlled by Pret Holding 2 Ltd, a potential guarantor

  Recommended action
    → Assess Pret Holding 2 Ltd as the guarantor covenant.
    → Identify the trading entity in the group and take the covenant, or a guarantee, from that.
    → The parent that gave the s479C guarantee is your real covenant; assess that entity instead.

  Source: https://find-and-update.company-information.service.gov.uk/company/11391321
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

  Recommended action
    → Assess Pret A Manger Limited as the guarantor covenant.

  Source: https://find-and-update.company-information.service.gov.uk/company/01854213
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
  A: 2,111  B: 2,007  C: 2,392  D: 1,007  E: 229
  47% are band C or below: would need a guarantee, deposit, or a hard look before going on a lease

  Weakest 25 covenants (deep-dive candidates for covenant.py):
  band score  number     name                                      why (register says)
  E    0      11867480   12 RAYS LIMITED                           Liquidation, accounts OVERDUE, dormant
  E    0      16043531   354 OXFORD STREET LIMITED                 accounts OVERDUE, no accounts filed, 1 charge(s)
  E    0      13232356   AL SANA GROUP GLOBAL LTD                  Liquidation, accounts OVERDUE, micro entity
  E    0      02259267   ANTLOW ENTERPRISES LIMITED                Live but Receiver Manager on at least one charge
  E    0      02597451   ARCHEUS FINE ART LIMITED                  Live but Receiver Manager on at least one charge
  E    0      13472527   ASTORIA PALACE LTD                        Liquidation, accounts OVERDUE
  E    0      16064310   BGO EUROPE IV LOGISTICS UK DIDCOT PROPCO  accounts OVERDUE, no accounts filed
  E    0      10819120   BLUFX LTD                                 Liquidation, accounts OVERDUE, micro entity
  E    0      00594365   BMMGS ENGINEERING LIMITED                 accounts OVERDUE, dormant
  E    0      14155693   BOGT LTD                                  accounts OVERDUE, dormant
  E    0      03363043   CALDER PEEL PARTNERSHIP LIMITED           In Administration, accounts OVERDUE, 2 charge(s)
  E    0      15973722   CALVETON TEXAS LIMITED                    accounts OVERDUE, no accounts filed
  E    0      05041414   CASTLE INDEPENDENT MORTGAGES LIMITED      Liquidation, accounts OVERDUE
  E    0      08674668   CHANTERSLEUR COTTAGE LTD                  Live but Receiver Manager on at least one charge
  E    0      15997581   CLAS INVESTMENT HOLDCO LIMITED            accounts OVERDUE, no accounts filed
  E    0      15887424   CLAS INVESTMENT LIMITED                   accounts OVERDUE, no accounts filed, 6 charge(s)
  E    0      15924795   CLEAR SUMMER 2 LIMITED                    accounts OVERDUE, no accounts filed
  E    0      08359840   COLLECTIVE REBEL DESIGN STUDIO LTD        Liquidation, accounts OVERDUE
  E    0      07808446   CONSTRUCT CORP LIMITED                    Liquidation, accounts OVERDUE
  E    0      01916131   DENZA INTERNATIONAL LIMITED               Liquidation, accounts OVERDUE, 1 charge(s)
  E    0      14941328   DH PETERBOROUGH LTD                       Liquidation, accounts OVERDUE
  E    0      10296150   DIGITAL EDUCATIONAL PUBLICATIONS LTD      Liquidation, accounts OVERDUE, micro entity
  E    0      05641999   DPIF (CREWE) LIMITED                      Liquidation, accounts OVERDUE, 2 charge(s)
  E    0      05642008   DPIF (DARIN COURT MK) LIMITED             Liquidation, accounts OVERDUE, 2 charge(s)
  E    0      14976125   EARTH HOLDINGS LTD                        accounts OVERDUE, dormant
```

Or a distress league table across all of W1 (`python sweep.py --stats W1`): W1C is
the weakest outward code at 61.1% band C-or-below; W1F the strongest at 38.8%.

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
    → Identify the trading entity in the group and take the covenant, or a guarantee, from that.
    → No meaningful track record. Rent deposit of 6-12 months is the usual response.

  Source: https://find-and-update.company-information.service.gov.uk/company/16043531
```

A 2024 propco on one of the most famous retail addresses in Britain, whose first
accounts went overdue two weeks before this demo was run, with a registered charge,
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

*Nothing here is investment advice or a substitute for professional judgement. It is
a screen that tells you which entities deserve an hour of a surveyor's attention.*
