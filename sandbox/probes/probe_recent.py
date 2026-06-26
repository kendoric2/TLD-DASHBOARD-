"""
Verify the Recent Sales query (read-only): runs the exact 'recent_sales' egress query
the dashboard uses — including the new Enroller field (fronter_name on the policies
endpoint) — and prints the rows. Confirms the policies endpoint exposes fronter_name
before we rely on it.

    python3 sandbox/probes/probe_recent.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t

config.require_creds()
c = t.TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)

try:
    rows = c.run("recent_sales")
except Exception as ex:
    print(f"recent_sales query FAILED: {type(ex).__name__}: {str(ex)[:160]}")
    print("If it mentions an unknown column 'fronter_name', the policies endpoint uses a")
    print("different field for the enroller — tell me and I'll switch it.")
    raise SystemExit

print(f"recent_sales rows: {len(rows)}\n")
hdr = f"{'date':12}{'agent':22}{'enroller':22}{'carrier':22}"
print(hdr)
print("-" * len(hdr))
filled = 0
for r in rows:
    enr = r.get("fronter_name") or ""
    if enr:
        filled += 1
    print(f"{str(r.get('date_sold'))[:12]:12}"
          f"{str(r.get('agent_name') or '')[:22]:22}"
          f"{str(enr)[:22]:22}"
          f"{str(r.get('carrier_name') or '')[:22]:22}")
print("-" * len(hdr))
print(f"enroller (fronter_name) populated on {filled}/{len(rows)} rows.")
print("If fronter_name appears (even if some rows are blank), the dashboard Enroller column will work.")
