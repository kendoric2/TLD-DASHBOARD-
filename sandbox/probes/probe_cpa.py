"""
Every agent's CPA for a date range — read-only.

Pulls report_cpa_agent (CPA pre-computed by TLD, no math on our side) for the
range you set, and prints a table of all agents sorted by sales.

Uses the date params the report actually honors (from how TLD's own code calls it):
    date / date_end  AND  date_sold / date_sold_end     (NOT start_date/end_date)

    python3 sandbox/probes/probe_cpa.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import json
import _probe_lib as p

config = p.config
t = p.t
config.require_creds()

# ===================== CHANGE THESE, THEN RUN =====================
START = "2026-06-26"        # <- date range start "YYYY-MM-DD"
END   = "2026-06-26"        # <- date range end   "YYYY-MM-DD"  (same day = one day)
ROWS  = 300                 # <- max agents to pull back
SORT_BY = "sales"           # <- sort agents by this column (sales / policies / costs_all)
# ==================================================================

ENDPOINT = "report_cpa_agent"
# columns to show: identity + the two CPA figures (overall, and Falcon = billable-new-vendor)
COLS = ["agent_id", "agent", "sales", "policies", "costs_all",
        "cpa_cost_calls_all_by_sales", "cpa_cost_calls_billable_new_vendor_by_sales"]

# build the JSON body with the date params the report honors (datetime bounds)
s0, e1 = f"{START} 00:00:00", f"{END} 23:59:59"
body = {
    "columns": COLS,
    "limit": ROWS,
    "date": s0,          "date_end": e1,            # range on lead/dialer activity
    "date_sold": s0,     "date_sold_end": e1,       # range on sales
}

p.hr(f"CPA per agent   {START} -> {END}")
print("JSON body sent:")
print("  " + json.dumps(body))

try:
    resp = config.egress_get(ENDPOINT, body, timeout=90)
except Exception as ex:
    print(f"\nrequest FAILED: {type(ex).__name__}: {str(ex)[:100]}")
    raise SystemExit

rows, totals = p.as_rows(resp)
sellers = sorted((r for r in rows if t._num(r.get("sales")) > 0),
                 key=lambda r: t._num(r.get(SORT_BY)), reverse=True)

print(f"\nagents with sales: {len(sellers)}\n")
hdr = f"{'agent':24}{'sales':>7}{'policies':>9}{'cost':>11}{'CPA all/sale':>14}{'CPA falcon/sale':>17}"
print(hdr)
print("-" * len(hdr))
for r in sellers:
    print(f"{str(r.get('agent'))[:24]:24}"
          f"{t._num(r.get('sales')):>7}"
          f"{t._num(r.get('policies')):>9}"
          f"{'$' + format(t._num(r.get('costs_all')), ',.0f'):>11}"
          f"{'$' + format(t._num(r.get('cpa_cost_calls_all_by_sales')), ',.2f'):>14}"
          f"{'$' + format(t._num(r.get('cpa_cost_calls_billable_new_vendor_by_sales')), ',.2f'):>17}")

if totals:
    print("-" * len(hdr))
    print(f"{'TOTALS':24}"
          f"{t._num(totals.get('sales')):>7}"
          f"{t._num(totals.get('policies')):>9}"
          f"{'$' + format(t._num(totals.get('costs_all')), ',.0f'):>11}"
          f"{'$' + format(t._num(totals.get('cpa_cost_calls_all_by_sales')), ',.2f'):>14}"
          f"{'$' + format(t._num(totals.get('cpa_cost_calls_billable_new_vendor_by_sales')), ',.2f'):>17}")

print("\nSanity check: a one-day range should be FAR smaller than the ~123k all-time total,")
print("and agents who didn't work that day should NOT appear.")
