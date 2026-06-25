"""
List the available columns for the TLDCRM policies endpoint (read-only).

Run on a machine that can reach your TLD instance (your Mac):
    cd ~/Documents/TLDDASHBOARD
    python3 list_columns.py

Hits GET /api/egress/policies/docs/columns and prints the column names so we
can lock in the real field names for the dashboard. Read-only — only a GET.
"""
import sys
import json
import requests
import config

config.require_creds()

url = config.TLD_BASE_URL + "/api/egress/policies/docs/columns"
print("GET", url)
r = requests.get(url, headers=config.HEADERS_GET, timeout=config.TIMEOUT)
print("HTTP", r.status_code)

try:
    data = r.json()
except Exception:
    print(r.text[:3000])
    sys.exit()


def find_columns(obj):
    if isinstance(obj, dict):
        for k in ("results", "data", "columns", "response"):
            if k in obj:
                return find_columns(obj[k])
        return list(obj.keys())
    if isinstance(obj, list):
        names = []
        for item in obj:
            if isinstance(item, dict):
                names.append(item.get("name") or item.get("column")
                             or item.get("key") or json.dumps(item)[:60])
            else:
                names.append(str(item))
        return names
    return [str(obj)]


cols = find_columns(data)
print(f"\n{len(cols)} columns:")
for c in cols:
    print(" -", c)

print("\n--- raw (first 2000 chars) ---")
print(json.dumps(data, indent=2)[:2000])
