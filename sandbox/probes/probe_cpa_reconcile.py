"""
CPA reconciliation — read-only, AGGREGATES ONLY (no PII).

agentcpa gives the authoritative per-agent CPA, but only for *today*. To
reproduce it range-aware we must know which lead role TLD charges the Falcon $40
to. This counts TODAY's billable Falcon leads grouped by each candidate role
(agent_id / fronter_id / assigned_id / owner_id), x $40, and compares the total
to agentcpa's own summed cost. The role whose total matches is the attribution
to use — then range-aware CPA = (that role's billable Falcon leads in range x $40) / sales.

Run:  python3 sandbox/probes/probe_cpa_reconcile.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t

config.require_creds()
FALCON = config.FALCON_VENDOR_ID
CPL = 40
s, e = t.date_range_for("today")
su, eu = t._us(s), t._us(e)
print(f"Window: TODAY ({su})   Falcon vendor_id={FALCON}   $/lead={CPL}\n")

acpa = config.egress_get("agentcpa", {})
if isinstance(acpa, list):
    acpa_cost = sum(t._num(r.get("cost")) for r in acpa)
    acpa_sales = sum(t._num(r.get("sales")) for r in acpa)
    print(f"agentcpa (authoritative): total cost=${acpa_cost:,}  "
          f"(= {acpa_cost / CPL:.0f} billable Falcon leads @ ${CPL}),  sales={acpa_sales}\n")
else:
    print("agentcpa returned:", acpa, "\n")
    acpa_cost = None

print("our billable Falcon leads TODAY, grouped by each candidate role:")
for role in ["agent_id", "fronter_id", "assigned_id", "owner_id"]:
    rows = config.egress_get("leads", {
        "vendor_id": FALCON, "billable": 1,
        "date_created": su, "date_created_end": eu,
        "aggregates": True, "group_by": role,
        "columns": [role, "tql_cnt_lead_id"], "limit": 1000})
    if not isinstance(rows, list):
        print(f"  group_by {role:12} -> {rows}")
        continue
    cnt = sum(t._num(r.get("tql_cnt_lead_id")) for r in rows)
    cost = cnt * CPL
    match = ""
    if acpa_cost is not None and cost == acpa_cost:
        match = "   <<< MATCHES agentcpa cost"
    print(f"  group_by {role:12} -> leads={cnt:<5} cost=${cost:,}{match}")

print("\nWhichever role's cost equals agentcpa's total is the attribution TLD uses.")
print("If none match exactly, the closest tells us how it's counted (we'll refine).")
