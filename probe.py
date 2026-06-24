"""
Quick LIVE connectivity + field check for TLDCRM (read-only).

Run this on a machine that can reach your TLD instance (e.g. your Mac):
    python3 probe.py

It hits a handful of egress endpoints and prints the raw responses so we can
confirm the endpoints and column names are right before trusting the dashboard.
Read-only: only GET requests, nothing is written back.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()
import tldcrm_client as t

base = os.getenv("TLD_BASE_URL", "").strip()
print("Base URL:", base or "(EMPTY - set TLD_BASE_URL in .env)")
print("API ID  :", os.getenv("TLD_API_ID", "").strip() or "(empty)")
print("API key :", "set" if os.getenv("TLD_API_KEY", "").strip() else "(empty)")

if not (base and os.getenv("TLD_API_ID", "").strip() and os.getenv("TLD_API_KEY", "").strip()):
    raise SystemExit("\nFill all three values in .env first, then re-run.")

c = t.TLDCRMClient(base, os.getenv("TLD_API_ID"), os.getenv("TLD_API_KEY"), timeout=15)
s, e = t.date_range_for("this_month")
print(f"\nDate range: {s} -> {e}\n")

checks = ["policies_count", "billable_leads_count", "avg_gtl_premium",
          "policies_by_carrier", "agent_policies", "recent_sales"]

for q in checks:
    try:
        rows = c.run(q) if q == "recent_sales" else c.run(q, s, e)
        preview = rows[:2] if isinstance(rows, list) else rows
        print(f"[OK]   {q}: {json.dumps(preview)[:320]}")
    except Exception as ex:
        print(f"[FAIL] {q}: {type(ex).__name__}: {str(ex)[:220]}")

print("\nDone. Paste this output back and I'll fix any field names that are off.")
