"""
Diagnose report_cpa_agent across date ranges (read-only).

The dashboard's COST / CPA / Billable Calls / Total Spend / Blended CPA all come from
report_cpa_agent via /api/agent_cpa. If those go blank for This Week / This Month, this
shows why: for each range it reports how long the call took, how many rows came back,
the billable-calls total, and any error the API returned (or a timeout).

We use a generous 180s timeout here ON PURPOSE — if a range succeeds at 180s but the
app (capped at 90s) shows nothing, the culprit is the timeout.

    python3 sandbox/probes/probe_cpa_range.py
"""
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t
import _probe_lib as p

config.require_creds()

COLS = ["agent", "sales", "costs_all", "cpa_cost_calls_all_by_sales", "calls_billable"]

print(f"{'range':12}{'time':>8}  result")
print("-" * 70)
for label in ["today", "this_week", "this_month", "last_month"]:
    s, e = t.date_range_for(label)
    s0, e1 = f"{s} 00:00:00", f"{e} 23:59:59"
    body = {"columns": COLS, "limit": 1000,
            "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1}
    t0 = time.time()
    try:
        resp = config.egress_get("report_cpa_agent", body, timeout=180)
        dt = time.time() - t0
        if isinstance(resp, dict) and resp.get("error"):
            print(f"{label:12}{dt:7.1f}s  API ERROR: {str(resp.get('error'))[:80]}")
            continue
        rows, totals = p.as_rows(resp)
        bc = (totals or {}).get("calls_billable")
        print(f"{label:12}{dt:7.1f}s  rows={len(rows):<4} billable_calls={bc}   ({s}..{e})")
    except Exception as ex:
        dt = time.time() - t0
        print(f"{label:12}{dt:7.1f}s  FAILED: {type(ex).__name__}: {str(ex)[:80]}")

print("-" * 70)
print("If wider ranges show FAILED (a timeout near ~180s) or an API ERROR while Today")
print("works, that's the culprit. Paste this back.")
