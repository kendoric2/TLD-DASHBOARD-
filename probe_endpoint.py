"""
Generic read-only probe for any egress endpoint: shows its columns and a few
sample rows. GET for the column list, GET-with-JSON-body for the data.

Usage:
    python3 probe_endpoint.py vendors
    python3 probe_endpoint.py vendorperformance
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()
base = os.getenv("TLD_BASE_URL", "").strip().rstrip("/")
H = {"tld-api-id": os.getenv("TLD_API_ID", "").strip(),
     "tld-api-key": os.getenv("TLD_API_KEY", "").strip(),
     "Content-Type": "application/json", "Accept": "application/json"}

ep = sys.argv[1] if len(sys.argv) > 1 else "vendors"


def unwrap(d):
    if isinstance(d, dict):
        r = d.get("response", d)
        return r.get("results", r) if isinstance(r, dict) else r
    return d


print(f"=== {ep} columns ===")
try:
    cols = unwrap(requests.get(f"{base}/api/egress/{ep}/docs/columns", headers=H, timeout=40).json())
    print(cols if isinstance(cols, list) else json.dumps(cols)[:1200])
except Exception as ex:
    print("FAILED:", ex)

print(f"\n=== {ep} sample (up to 5 rows) ===")
rows = unwrap(requests.get(f"{base}/api/egress/{ep}", headers=H, json={"limit": 5}, timeout=40).json())
if isinstance(rows, list):
    print(f"{len(rows)} rows")
    for r in rows[:5]:
        print(json.dumps(r)[:500])
else:
    print(rows)
    print(f"(if 'Not Allowed', make sure /api/egress/{ep} has GET enabled on the key)")

print("\nDone. Paste this back.")
