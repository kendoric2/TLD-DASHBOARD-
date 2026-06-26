"""
Probe the rich CPA report (report_cpa_agent / tldialer/report_agentcpa) — readable.
Read-only, agent-level aggregates (no customer PII).

Requests only key columns, longer timeout, dates as 'YYYY-MM-DD HH:MM:SS', and
compares today vs last month (body + query). Prints a clean per-agent table plus
the report's own TOTALS row, and a date-filter verdict.

Usage:
  python3 sandbox/probes/probe_report_cpa.py report_cpa_agent
  python3 sandbox/probes/probe_report_cpa.py tldialer/report_agentcpa
"""
import sys
import requests
import _probe_lib as p

config, t = p.config, p.t
config.require_creds()

ep = (sys.argv[1] if len(sys.argv) > 1 else "report_cpa_agent").strip("/")
URL = f"{config.TLD_BASE_URL}/api/egress/{ep}"
TIMEOUT = 90

COLS = ["agent_id", "agent", "sales", "policies", "premium", "costs_all",
        "cpa_cost_calls_all_by_sales", "cpa_cost_calls_all_by_policies",
        "cpa_cost_calls_billable_new_by_sales",
        "cpa_cost_calls_billable_new_vendor_by_sales",
        "cpa_cost_calls_billable_new_vendor_by_policies"]


def fetch(mode, dates):
    try:
        if mode == "body":
            return config.egress_get(ep, {"columns": COLS, "limit": 10, **dates}, timeout=TIMEOUT)
        r = requests.get(URL, headers=config.HEADERS_GET,
                         params={"columns": ",".join(COLS), "limit": 10, **dates}, timeout=TIMEOUT)
        return config.unwrap(r.json())
    except Exception as ex:
        return f"ERR {type(ex).__name__}: {str(ex)[:60]}"


def line(r):
    return (f"    {str(r.get('agent'))[:22].ljust(22)} "
            f"sales={t._num(r.get('sales')):<5} pol={t._num(r.get('policies')):<5} "
            f"cost=${t._num(r.get('costs_all')):<9,.0f} "
            f"CPA_all/sale=${t._num(r.get('cpa_cost_calls_all_by_sales')):<8,.2f} "
            f"CPA_falcon/sale=${t._num(r.get('cpa_cost_calls_billable_new_vendor_by_sales')):,.2f}")


def report(label, mode, dates):
    resp = fetch(mode, dates)
    print(f"\n-- {mode}  |  {label} --")
    if isinstance(resp, str):
        print("  ", resp)
        return None
    rows, totals = p.as_rows(resp)
    sales = sum(t._num(r.get("sales")) for r in rows)
    cost = sum(t._num(r.get("costs_all")) for r in rows)
    print(f"  {len(rows)} agents   sales(sum of rows)={sales:,}   cost(sum of rows)=${cost:,.0f}")
    for r in [x for x in rows if t._num(x.get("sales")) > 0][:6]:
        print(line(r))
    if totals:
        print("  TOTALS:")
        print(line(totals))
    return (len(rows), sales)   # compare on rows+sales only; cost drifts live and gives false positives


p.hr(f"/api/egress/{ep}   (CPA report)")
lm = t.date_range_for("last_month")
td = t.date_range_for("today")
for mode in ("body", "query"):
    tdv = report("today", mode, {"start_date": td[0] + " 00:00:00", "end_date": td[1] + " 23:59:59"})
    lmv = report("last_month", mode, {"start_date": lm[0] + " 00:00:00", "end_date": lm[1] + " 23:59:59"})
    if isinstance(tdv, tuple) and isinstance(lmv, tuple):
        verdict = "WORKS (today != last_month)" if tdv != lmv else "no change (identical)"
        print(f"\n  => {mode}: date filter {verdict}")

print("\nDone. Paste this back.")
