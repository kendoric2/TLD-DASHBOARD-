"""
Live diagnostic for the TLDCRM dashboard (read-only, POST + JSON body).

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 probe.py

Shows the RAW POST response for the policies count (so we confirm the date
range actually filters), then runs each dashboard query. Read-only.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()
import tldcrm_client as t

base = os.getenv("TLD_BASE_URL", "").strip()
hid = os.getenv("TLD_API_ID", "").strip()
key = os.getenv("TLD_API_KEY", "").strip()
print("Base URL:", base or "(EMPTY)")
print("API ID  :", hid or "(empty)")
print("API key :", "set" if key else "(empty)")
if not (base and hid and key):
    raise SystemExit("\nFill all three values in .env first.")

c = t.TLDCRMClient(base, hid, key, timeout=30)
s, e = t.date_range_for("this_month")
print(f"\nThis month: {s} .. {e}   (sent as {t._us(s)} .. {t._us(e)})")

# --- RAW POST for the policies count, so we see the filtered envelope ---
endpoint, body = c._payload("policies_count", s, e)
url = f"{base.rstrip('/')}/api/egress/{endpoint}"
print(f"\n=== RAW POST /api/egress/{endpoint} ===")
print("body:", json.dumps(body))
r = c.session.post(url, json=body, timeout=30)
print("HTTP", r.status_code)
print(r.text[:1400])

# --- Each dashboard query, parsed ---
print("\n=== Parsed results per query ===")
checks = ["policies_count", "billable_leads_count", "avg_gtl_premium",
          "policies_by_carrier", "policies_by_plan", "agent_policies", "recent_sales"]
for q in checks:
    try:
        rows = c.run(q) if q == "recent_sales" else c.run(q, s, e)
        n = len(rows) if isinstance(rows, list) else "?"
        print(f"\n[{q}] rows={n}")
        print("  " + json.dumps(rows[:3])[:600])
    except Exception as ex:
        print(f"\n[{q}] FAILED: {type(ex).__name__}: {str(ex)[:240]}")

print("\nDone. Paste this whole output back.")
