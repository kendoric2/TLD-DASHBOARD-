"""
Probe the TLDCRM vendors endpoint (read-only) to see what's available.

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 probe_vendors.py

Lists the vendors columns, then pulls every vendor (id + name) and prints one
full record so we can see all fields. Read-only: GET (column list) and
GET-with-JSON-body (data).
"""
import json
import config

config.require_creds()


def vid(v):
    return v.get("vendor_id") or v.get("id")


def vname(v):
    return v.get("name") or v.get("vendor_name") or v.get("vendor") or "?"


# 1) Column list
print("=== vendors columns ===")
try:
    cols = config.egress_get("vendors/docs/columns")
    print(cols if isinstance(cols, list) else json.dumps(cols)[:900])
except Exception as ex:
    print("FAILED:", ex)

# 2) All vendors (GET with JSON body)
print("\n=== vendors ===")
rows = config.egress_get("vendors", {"limit": 500})
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
