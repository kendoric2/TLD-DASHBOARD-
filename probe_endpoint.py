"""
Generic read-only probe for any egress endpoint: shows its columns and a few
sample rows. GET for the column list, GET-with-JSON-body for the data.

Usage:
    python3 probe_endpoint.py vendors
    python3 probe_endpoint.py vendorperformance
"""
import sys
import json
import config

config.require_creds()

ep = sys.argv[1] if len(sys.argv) > 1 else "vendors"

print(f"=== {ep} columns ===")
try:
    cols = config.egress_get(f"{ep}/docs/columns")
    print(cols if isinstance(cols, list) else json.dumps(cols)[:1200])
except Exception as ex:
    print("FAILED:", ex)

print(f"\n=== {ep} sample (up to 5 rows) ===")
rows = config.egress_get(ep, {"limit": 5})
if isinstance(rows, list):
    print(f"{len(rows)} rows")
    for r in rows[:5]:
        print(json.dumps(r)[:500])
else:
    print(rows)
    print(f"(if 'Not Allowed', make sure /api/egress/{ep} has GET enabled on the key)")

print("\nDone. Paste this back.")
