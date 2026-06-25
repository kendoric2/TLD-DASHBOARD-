"""
List the full_name of every user with status_id = 1 (Active).
Read-only POST to /api/egress/users.

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 active_users.py
"""
import config

config.require_creds()

body = {
    "status_id": 1,
    "columns": ["full_name", "status_id"],
    "order_by": "full_name",
    "sort": "ASC",
    "limit": 2000,
}

rows = config.egress_get("users", body)

if not isinstance(rows, list):
    print("Could not read users:", str(rows)[:300])
    print("\nIf this says 'Not Allowed', make sure /api/egress/users has GET enabled on the API key.")
    raise SystemExit

names = [u.get("full_name") for u in rows if u.get("full_name")]
print(f"{len(names)} active users (status_id = 1):\n")
for n in names:
    print(" -", n)
