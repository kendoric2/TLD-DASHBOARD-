"""
Probe TLDCRM users and find those with an Active status (read-only).

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 archive/probe_users.py

Read-only: GET for the column list, POST (JSON body) for the queries.
It lists the users columns, tries the likely "active" filters (showing how many
each returns + sample names), and prints one full user record so we can see
exactly how status is stored. Paste the output back.
"""

# --- make src/ importable no matter where this script is run from ---
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import json
import requests
import config

config.require_creds()


def post(body):
    r = requests.get(f"{config.TLD_BASE_URL}/api/egress/users",
                     headers=config.HEADERS, json=body, timeout=config.TIMEOUT)
    try:
        return config.unwrap(r.json())
    except Exception:
        return f"HTTP {r.status_code}: {r.text[:150]}"


def name_of(u):
    return (u.get("full_name") or u.get("name")
            or (str(u.get("first_name", "")) + " " + str(u.get("last_name", ""))).strip()
            or u.get("username") or "?")


# 1) Column list for the users endpoint
print("=== users columns ===")
try:
    r = requests.get(f"{config.TLD_BASE_URL}/api/egress/users/docs/columns",
                     headers=config.HEADERS_GET, timeout=config.TIMEOUT)
    cols = config.unwrap(r.json())
    print(cols if isinstance(cols, list) else json.dumps(cols)[:900])
except Exception as ex:
    print("FAILED:", ex)

# 2) Total users (no filter)
allu = post({"limit": 2000})
print("\n=== total users (no filter):", len(allu) if isinstance(allu, list) else allu, "===")

# 3) Candidate "active" filters — which one returns a sane subset?
print("\n=== active-status candidates ===")
for filt in ({"status": "Active"}, {"status_id": 1}, {"active": 1}):
    rows = post({**filt, "limit": 2000})
    if isinstance(rows, list):
        names = ", ".join(name_of(u) for u in rows[:5])
        print(f"{filt} -> {len(rows)} users   e.g. {names}")
    else:
        print(f"{filt} -> {rows}")

# 4) One full sample user record, to see exactly how status is stored
if isinstance(allu, list) and allu:
    print("\n=== sample user record (all default fields) ===")
    print(json.dumps(allu[0], indent=2)[:1500])

print("\nDone. Paste this back and I'll lock in the exact active filter.")
