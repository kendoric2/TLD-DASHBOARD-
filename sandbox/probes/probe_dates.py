"""
Date-column scan across all egress endpoints — read-only, human-readable.

For each endpoint it lists the date fields that ACTUALLY have a value (with an
example), skipping null / "" / 0 / 0000-00-00. Date columns that are always
empty, and endpoints with no date columns, are noted plainly.

Run: python3 sandbox/probes/probe_dates.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config

config.require_creds()

ENDPOINTS = ["policies", "leads", "agentcpa", "vendors", "users",
             "vendorperformance", "report_cpa_agent", "tldialer/report_agentcpa"]

EMPTY = (None, "", "0", "0000-00-00", "0000-00-00 00:00:00", "1969-12-31", "1970-01-01")


def cols_of(ep):
    c = config.egress_get(f"{ep}/docs/columns")
    if isinstance(c, list) and c and isinstance(c[0], dict):
        return list(c[0].keys())
    if isinstance(c, list):
        return [x for x in c if isinstance(x, str)]
    return []


for ep in ENDPOINTS:
    print("\n" + "=" * 64)
    print(ep)
    print("=" * 64)

    try:
        dcols = [c for c in cols_of(ep) if "date" in c.lower()]
    except Exception as ex:
        print(f"  couldn't read columns ({type(ex).__name__})")
        continue

    if not dcols:
        print("  no date columns  ->  this endpoint's date range is a QUERY PARAMETER, not a field")
        continue

    try:
        rows = config.egress_get(ep, {"columns": dcols, "limit": 5}, timeout=60)
    except Exception as ex:
        print(f"  couldn't pull a sample ({type(ex).__name__})")
        continue
    if not isinstance(rows, list) or not rows:
        print(f"  no rows returned ({str(rows)[:80]})")
        continue

    examples = {}
    for c in dcols:
        for r in rows:
            if r.get(c) not in EMPTY:
                examples[c] = r.get(c)
                break

    if not examples:
        print(f"  {len(dcols)} date columns, but all empty in the sample")
        continue

    width = max(len(c) for c in examples)
    print(f"  {len(examples)} of {len(dcols)} date columns are populated:\n")
    for c in sorted(examples):
        print(f"    {c.ljust(width)}   {examples[c]}")
