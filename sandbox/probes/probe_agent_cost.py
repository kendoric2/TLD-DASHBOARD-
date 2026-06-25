"""
CPA discovery probe — read-only, AGGREGATES ONLY (no lead PII).

Sums each agent's lead `cost` (leads grouped by agent_name, by date_created)
and lines it up against policies sold per agent (by date_sold) so we can
sanity-check CPA = lead cost / policies before building it into the dashboard.

Run:  python3 sandbox/probes/probe_agent_cost.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t

config.require_creds()
client = t.TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)
s, e = t.date_range_for("this_month")
print(f"Period (this_month): {t._us(s)} .. {t._us(e)}\n")

# 1) lead cost per agent — leads grouped by agent_name, filtered by date_created
cost_rows = config.egress_get("leads", {
    "aggregates": True, "group_by": "agent_name",
    "columns": ["agent_name", "tql_sum_cost", "tql_avg_cost", "tql_cnt_lead_id"],
    "date_created": t._us(s), "date_created_end": t._us(e),
    "order_by": "tql_sum_cost", "sort": "DESC", "limit": 25})
if not isinstance(cost_rows, list):
    print("lead-cost query did NOT return rows:", cost_rows)
    print("(If this says 'Not Allowed' or errors, tql_sum_cost may be wrong — tell me.)")
    raise SystemExit

# 2) policies per agent — reuse the existing query (by date_sold)
pol = {}
for r in client.run("agent_policies", s, e):
    if r.get("agent_name"):
        pol[r["agent_name"]] = t._num(r.get("tql_cnt_policy_id"))

print(f"{'agent':24}{'lead_cost':>12}{'leads':>7}{'avg_cost':>10}{'policies':>10}{'CPA':>12}")
print("-" * 75)
for r in cost_rows:
    a = (r.get("agent_name") or "(none)")[:24]
    cost = t._num(r.get("tql_sum_cost"))
    leads = t._num(r.get("tql_cnt_lead_id"))
    avg = t._num(r.get("tql_avg_cost"))
    p = pol.get(r.get("agent_name"), 0)
    cpa = ("$" + format(cost / p, ",.2f")) if p else "—"
    print(f"{a:24}{cost:>12,.2f}{leads:>7}{avg:>10,.2f}{p:>10}{cpa:>12}")

print("\nSanity check:")
print(" - Does lead_cost look like real spend (not all zero)?")
print(" - Is CPA = lead_cost / policies sensible per agent?")
print(" - If tql_sum_cost is blank/zero, I'll switch to total_cost or paid_sum_vendor.")
