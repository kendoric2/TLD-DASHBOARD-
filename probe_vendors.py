"""
Probe the TLDCRM vendors endpoint (read-only) to see what's available.

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 probe_vendors.py

Lists the vendors columns, then pulls every vendor (id + name) and prints one
full record so we can see all fields. Read-only: GET (column list) and
GET-with-JSON-body (data).
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
base = os.getenv("TLD_BASE_URL", "").strip().rstrip("/")
hid = os.getenv("TLD_API_ID", "").strip()
key = os.getenv("TLD_API_KEY", "").strip()
if not (base and hid and key):
    raise SystemExit("Fill TLD_BASE_URL / TLD_API_ID / TLD_API_KEY in .env first.")

H = {"tld-api-id": hid, "tld-api-key": key,
     "Content-Type": "application/json", "Accept": "application/json"}


def unwrap(d):
    if isinstance(d, dict):
        resp = d.get("response", d)
        return resp.get("results", resp) if isinstance(resp, dict) else resp
    return d


def vid(v):
    return v.get("vendor_id") or v.get("id")


def vname(v):
    return v.get("name") or v.get("vendor_name") or v.get("vendor") or "?"


# 1) Column list
print("=== vendors columns ===")
try:
    r = requests.get(f"{base}/api/egress/vendors/docs/columns", headers=H, timeout=40)
    cols = unwrap(r.json())
    print(cols if isinstance(cols, list) else json.dumps(cols)[:900])
except Exception as ex:
    print("FAILED:", ex)

# 2) All vendors (GET with JSON body)
print("\n=== vendors ===")
r = requests.get(f"{base}/api/egress/vendors", headers=H, json={"limit": 500}, timeout=40)
rows = unwrap(r.json())
if isinstance(rows, list):
    print(f"{len(rows)} vendors:")
    for v in rows:
        print(f"  id={vid(v)}  {vname(v)}")
    if rows:
        print("\n=== sample vendor record (all default fields) ===")
        print(json.dumps(rows[0], indent=2)[:1500])
else:
    print(rows)
    print("\nIf this says 'Not Allowed', make sure /api/egress/vendors has GET enabled on the key.")

print("\nDone. Paste this back and we can use vendors for the billable-leads breakdown.")
