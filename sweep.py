#!/usr/bin/env python3
"""
Sweep every registered company in a UK postcode area and rank covenant strength.

Uses the free Companies House monthly bulk snapshot (all ~5.7M companies), so it
answers the reverse question the REST API cannot: "who is registered HERE, and
which of them would I not want on a lease?"

    python sweep.py --build data/BasicCompanyDataAsOneFile-2026-08-01.csv
    python sweep.py W1S                # one outward code
    python sweep.py W1S --csv out.csv  # full ranked table for a spreadsheet
    python sweep.py --stats W1         # distress statistics for an area

Caveat, stated because it matters: this sweeps REGISTERED office addresses.
Many companies register at an accountant or agent. A registered-address sweep
finds the companies anchored to a place, not necessarily the shopfronts on it —
joining the VOA rating list for trading occupiers is the roadmap.
"""

import argparse
import os
import sys

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
PARQUET = os.path.join(HERE, "data", "companies.parquet")

# Same scoring philosophy as covenant.py, restricted to bulk-file columns.
# Deduction-based; every rule names its column so a finding traces to the register.
SCORE_SQL = """
GREATEST(0, 100
  - CASE WHEN CompanyStatus ILIKE '%liquidat%' OR CompanyStatus ILIKE '%administrat%'
              OR CompanyStatus ILIKE '%receiver%' OR CompanyStatus ILIKE '%insolven%' THEN 85
         WHEN CompanyStatus NOT ILIKE 'active%' THEN 60 ELSE 0 END
  - CASE WHEN AccountsNextDue < CURRENT_DATE THEN 30 ELSE 0 END          -- accounts overdue
  - CASE WHEN ConfStmtNextDue < CURRENT_DATE THEN 12 ELSE 0 END          -- conf stmt overdue
  - CASE WHEN AccountCategory ILIKE '%dormant%' THEN 45
         WHEN AccountCategory ILIKE '%micro%' THEN 30
         WHEN AccountCategory ILIKE 'no accounts%' OR AccountCategory = '' THEN 25
         WHEN AccountCategory ILIKE '%total exemption%' THEN 12
         WHEN AccountCategory ILIKE '%small%' THEN 10 ELSE 0 END         -- thin disclosure
  - CASE WHEN SIC1 LIKE '64209%' OR SIC1 LIKE '64205%' OR SIC1 LIKE '70100%'
              OR SIC1 LIKE '68209%' OR SIC1 LIKE '68100%'
              OR SIC1 ILIKE '%dormant%' OR SIC1 ILIKE '%non-trading%' THEN 25 ELSE 0 END
  - CASE WHEN Incorporated > CURRENT_DATE - INTERVAL 2 YEAR THEN 20
         WHEN Incorporated > CURRENT_DATE - INTERVAL 5 YEAR THEN 8 ELSE 0 END
  - LEAST(ChargesOutstanding * 4, 20)                                    -- secured debt
  - CASE WHEN Renamed THEN 6 ELSE 0 END
)
"""

BAND_SQL = """
CASE WHEN score >= 80 THEN 'A' WHEN score >= 60 THEN 'B'
     WHEN score >= 40 THEN 'C' WHEN score >= 20 THEN 'D' ELSE 'E' END
"""


def build(csv_path):
    """One-time: distil the 2.6GB snapshot CSV into a ~300MB scoring parquet."""
    if not os.path.exists(csv_path):
        sys.exit(f"Not found: {csv_path}\nDownload from download.companieshouse.gov.uk/en_output.html")
    con = duckdb.connect()
    con.execute(f"""
        COPY (
          SELECT
            "CompanyName"                          AS Name,
            "CompanyNumber"                       AS Number,
            trim("RegAddress.AddressLine1")        AS Address,
            trim("RegAddress.PostTown")            AS PostTown,
            upper(trim("RegAddress.PostCode"))     AS PostCode,
            upper(split_part(trim("RegAddress.PostCode"), ' ', 1)) AS Outward,
            "CompanyStatus"                        AS CompanyStatus,
            try_cast(strptime(nullif("IncorporationDate",''), '%d/%m/%Y') AS DATE) AS Incorporated,
            try_cast(strptime(nullif("Accounts.NextDueDate",''), '%d/%m/%Y') AS DATE) AS AccountsNextDue,
            try_cast(strptime(nullif("ConfStmtNextDueDate",''), '%d/%m/%Y') AS DATE) AS ConfStmtNextDue,
            trim("Accounts.AccountCategory")       AS AccountCategory,
            trim("SICCode.SicText_1")              AS SIC1,
            coalesce(try_cast("Mortgages.NumMortOutstanding" AS INT), 0) AS ChargesOutstanding,
            ("PreviousName_1.CompanyName" IS NOT NULL AND trim("PreviousName_1.CompanyName") != '') AS Renamed
          FROM read_csv_auto('{csv_path}', header=true, all_varchar=true)
        ) TO '{PARQUET}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n = con.execute(f"SELECT count(*) FROM '{PARQUET}'").fetchone()[0]
    mb = os.path.getsize(PARQUET) / 1e6
    print(f"Built {PARQUET}: {n:,} companies, {mb:.0f} MB.")
    print(f"The source CSV can now be deleted.")


def _query(where, params):
    con = duckdb.connect()
    return con.execute(f"""
        WITH scored AS (
          SELECT *, {SCORE_SQL} AS score FROM '{PARQUET}' WHERE {where}
        )
        SELECT Number, Name, Address, PostCode, CompanyStatus, AccountCategory,
               Incorporated, ChargesOutstanding,
               (AccountsNextDue < CURRENT_DATE) AS AccountsOverdue,
               score, {BAND_SQL} AS band
        FROM scored ORDER BY score ASC, Name
    """, params)


def sweep(outward, csv_out=None, limit=25):
    if not os.path.exists(PARQUET):
        sys.exit("No local snapshot. Run:  python sweep.py --build <snapshot.csv>")
    res = _query("Outward = ?", [outward.upper()])
    rows = res.fetchall()
    cols = [d[0] for d in res.description]
    if not rows:
        print(f"No companies registered in {outward.upper()}.")
        return

    if csv_out:
        import csv as _csv
        with open(csv_out, "w", newline="") as f:
            w = _csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"Wrote {len(rows):,} companies to {csv_out}")

    bands = {}
    for r in rows:
        bands[r[-1]] = bands.get(r[-1], 0) + 1
    total = len(rows)
    print(f"\n  {total:,} companies registered in {outward.upper()}")
    print("  " + "  ".join(f"{b}: {bands.get(b, 0):,}" for b in "ABCDE"))
    weak = sum(bands.get(b, 0) for b in "CDE")
    print(f"  {weak / total:.0%} are band C or below — "
          f"would need a guarantee, deposit, or a hard look before going on a lease\n")

    print(f"  Weakest {min(limit, total)} covenants (deep-dive candidates for covenant.py):")
    print(f"  {'band':<5}{'score':<7}{'number':<11}{'name':<42}{'why (register says)'}")
    for r in rows[:limit]:
        (num, name, _addr, _pc, status, acct, _inc, charges, overdue, score, band) = r
        why = []
        if not str(status).lower().startswith("active"):
            why.append(status)
        if overdue:
            why.append("accounts OVERDUE")
        if acct and ("DORMANT" in acct.upper() or "MICRO" in acct.upper() or "NO ACCOUNTS" in acct.upper()):
            why.append(acct.lower())
        if charges:
            why.append(f"{charges} charge(s)")
        print(f"  {band:<5}{score:<7.0f}{num:<11}{(name or '')[:40]:<42}{', '.join(why)[:48]}")
    print()


def stats(prefix):
    if not os.path.exists(PARQUET):
        sys.exit("No local snapshot. Run:  python sweep.py --build <snapshot.csv>")
    con = duckdb.connect()
    rows = con.execute(f"""
        WITH scored AS (
          SELECT Outward, {SCORE_SQL} AS score FROM '{PARQUET}'
          WHERE Outward LIKE ? AND CompanyStatus ILIKE 'active%'
        )
        SELECT Outward, count(*) AS n, round(avg(score),1) AS avg_score,
               round(100.0 * count(*) FILTER (WHERE score < 60) / count(*), 1) AS pct_weak
        FROM scored GROUP BY Outward HAVING count(*) >= 50 ORDER BY pct_weak DESC
    """, [prefix.upper() + "%"]).fetchall()
    print(f"\n  Active companies by outward code ({prefix.upper()}*), % scoring below band B:\n")
    print(f"  {'code':<8}{'companies':>10}{'avg score':>11}{'% band C-E':>12}")
    for o, n, avg, pct in rows:
        print(f"  {o:<8}{n:>10,}{avg:>11}{pct:>11}%")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outward", nargs="?", help="outward postcode, e.g. W1S")
    ap.add_argument("--build", metavar="CSV", help="build the parquet from a bulk snapshot CSV")
    ap.add_argument("--csv", metavar="OUT", help="write the full ranked table to a CSV")
    ap.add_argument("--stats", metavar="PREFIX", help="distress stats across outward codes")
    ap.add_argument("--top", type=int, default=25, help="rows to print (default 25)")
    a = ap.parse_args()
    if a.build:
        build(a.build)
    elif a.stats:
        stats(a.stats)
    elif a.outward:
        sweep(a.outward, a.csv, a.top)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
