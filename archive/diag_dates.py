"""
Diagnose how TLDCRM date filtering works on the policies endpoint (read-only).

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 archive/diag_dates.py

Then paste the full output back. This figures out which date column is actually
current and which filter form returns a sane monthly number.
Read-only: only GET requests.
"""

# --- make src/ importable no matter where this script is run from ---
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import requests
import config

config.require_creds()

START, END = "2026-06-01", "2026-06-25"
FIELDS = ["date_sold", "date_created", "date_modified", "date_effective"]


def q(params):
    r = requests.get(f"{config.TLD_BASE_URL}/api/egress/policies",
                     headers=config.HEADERS_GET, params=params, timeout=config.TIMEOUT)
    try:
        return config.unwrap(r.json())
    except Exception:
        return f"HTTP {r.status_code}: {r.text[:120]}"


print("1) Min / max of each candidate date column (all policies):")
for f in FIELDS:
    print(f"   {f:15}", q({"aggregates": "true", "aggregate": "true",
                            "columns": f"tql_min_{f},tql_max_{f}"}))

print("\n2) Total policies, no date filter:")
print("   ", q({"aggregates": "true", "aggregate": "true", "columns": "tql_cnt_policy_id"}))

print(f"\n3) Count per date field for {START} .. {END} (which one drops to a sane number?):")
for f in FIELDS:
    print(f"   {f:15}", q({"aggregates": "true", "aggregate": "true",
                           "columns": "tql_cnt_policy_id",
                           f"{f}_greater_equal": START, f"{f}_less": END}))

print(f"\n4) Count using start_date / end_date = {START} / {END}:")
print("   ", q({"aggregates": "true", "aggregate": "true",
               "columns": "tql_cnt_policy_id", "start_date": START, "end_date": END}))

print("\n5) Newest 5 policies (policy_id desc) with their dates — shows what 'current' looks like:")
print("   ", q({"columns": "policy_id,date_sold,date_created,date_effective,status",
               "order_by": "policy_id", "order": "desc", "limit": 5}))
