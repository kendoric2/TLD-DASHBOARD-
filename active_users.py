"""
List the full_name of every user with status_id = 1 (Active).
Read-only POST to /api/egress/users.

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 active_users.py
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

headers = {
    "tld-api-id": hid,
    "tld-api-key": key,
    "Content-Type": "application/json",
    "Accept": "application/json",
}
body = {
    "status_id": 1,
    "columns": ["full_name", "status_id"],
    "order_by": "full_name",
    "sort": "ASC",
    "limit": 2000,
}

r = requests.get(f"{base}/api/egress/users", headers=headers, json=body, timeout=40)
data = r.json()
resp = data.get("response", data)
rows = resp.get("results", resp) if isinstance(resp, dict) else resp

if not isinstance(rows, list):
    print("Could not read users:", json.dumps(data)[:300])
    print("\nIf this says 'Not Allowed', make sure /api/egress/users has GET enabled on the API key.")
    raise SystemExit

names = [u.get("full_name") for u in rows if u.get("full_name")]
print(f"{len(names)} active users (status_id = 1):\n")
for n in names:
    print(" -", n)
