"""
CPA discovery (policy side) — read-only, AGGREGATES ONLY (no PII).

The lead's agent != the selling agent, so we check whether the *policies*
endpoint exposes the originating lead's cost. If it does, summing it per
selling agent gives a clean CPA = acquisition cost / policies on the closer.

Run:  python3 sandbox/probes/probe_policy_cost.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t

config.require_creds()
s, e = t.date_range_for("this_month")
us_s, us_e = t._us(s), t._us(e)
print(f"Period (this_month): {us_s} .. {us_e}\n")

# 1) Which policy columns even mention "cost"?
cols = config.egress_get("policies/docs/columns")
costish = [c for c in cols if isinstance(c, str) and "cost" in c.lower()] if isinstance(cols, list) else cols
print("policy columns containing 'cost':", costish, "\n")

# 2) Try summing the lead cost per SELLING agent (policies grouped by agent_name)
body = {
    "aggregates": True, "group_by": "agent_name",
    "columns": ["agent_name", "tql_cnt_policy_id", "tql_sum_cost", "tql_avg_cost"],
    "order_by": "tql_cnt_policy_id", "sort": "DESC", "limit": 25,
    "date_sold": us_s, "date_sold_end": us_e, "start_date": us_s, "end_date": us_e,
}
rows = config.egress_get("policies", body)
if not isinstance(rows, list):
    print("aggregate did NOT return rows:", rows)
    print("(Tell me the 'cost' column names printed above and I'll point the query at the right one.)")
    raise SystemExit

print(f"{'agent':24}{'policies':>9}{'lead_cost':>13}{'avg_cost':>10}{'CPA':>12}")
print("-" * 68)
for r in rows:
    a = (r.get("agent_name") or "(none)")[:24]
    p = t._num(r.get("tql_cnt_policy_id"))
    cost = t._num(r.get("tql_sum_cost"))
    avg = t._num(r.get("tql_avg_cost"))
    cpa = ("$" + format(cost / p, ",.2f")) if p else "—"
    print(f"{a:24}{p:>9}{cost:>13,.2f}{avg:>10,.2f}{cpa:>12}")

print("\nIf lead_cost / CPA are populated, cost rides on the policy -> clean per-closer CPA.")
print("If tql_sum_cost errored or is all zero, send me the 'cost' column names above.")
