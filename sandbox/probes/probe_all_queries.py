"""
Live diagnostic for the TLDCRM dashboard (read-only, POST + JSON body).

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 sandbox/probes/probe_all_queries.py

Shows the RAW POST response for the policies count (so we confirm the date
range actually filters), then runs each dashboard query. Read-only.
"""

# --- make src/ importable no matter where this script is run from ---
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))


import json
import config
import tldcrm_client as t

print("Base URL:", config.TLD_BASE_URL or "(EMPTY)")
print("API ID  :", config.TLD_API_ID or "(empty)")
print("API key :", "set" if config.TLD_API_KEY else "(empty)")
config.require_creds()

c = t.TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)
s, e = t.date_range_for("this_month")
print(f"\nThis month: {s} .. {e}   (sent as {t._us(s)} .. {t._us(e)})")

# --- RAW GET for the policies count, so we see the filtered envelope ---
endpoint, body = c._payload("policies_count", s, e)
url = f"{config.TLD_BASE_URL}/api/egress/{endpoint}"
print(f"\n=== RAW GET /api/egress/{endpoint} (JSON body) ===")
print("body:", json.dumps(body))
r = c.session.request("GET", url, json=body, timeout=config.TIMEOUT)
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
