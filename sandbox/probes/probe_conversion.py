"""
Confirm the Conversion Rate source = "Sales / All Calls %" (read-only).

The CRM's Vendor CPA screen shows a "Sales / All Calls %" column. In report_cpa_agent
that's rate_sales_by_calls_all (= sales / calls_all). There's also a sales_dialer
variant. This pulls today's TOTALS so you can see which one matches the CRM number.

    python3 sandbox/probes/probe_conversion.py
"""
import os
import datetime
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t
import _probe_lib as p

config.require_creds()

# ===================== CHANGE THESE, THEN RUN =====================
START = datetime.date.today().isoformat()   # defaults to today; set "YYYY-MM-DD" to look back
END   = datetime.date.today().isoformat()
# ==================================================================

s0, e1 = f"{START} 00:00:00", f"{END} 23:59:59"
COLS = ["agent", "sales", "sales_dialer", "calls_all",
        "rate_sales_by_calls_all", "rate_sales_dialer_by_calls_all"]
body = {"columns": COLS, "limit": 1000,
        "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1}

resp = config.egress_get("report_cpa_agent", body, timeout=120)
if isinstance(resp, dict) and resp.get("error"):
    print("API ERROR:", resp.get("error"))
    raise SystemExit

rows, totals = p.as_rows(resp)
totals = totals or {}
sales   = t._num(totals.get("sales"))
salesd  = t._num(totals.get("sales_dialer"))
calls   = t._num(totals.get("calls_all"))

p.hr(f"Conversion = Sales / All Calls   {START} -> {END}   ({len(rows)} agents)")
print(f"  total sales            = {sales}")
print(f"  total sales_dialer     = {salesd}")
print(f"  total calls_all        = {calls}")
print()
print(f"  report  rate_sales_by_calls_all        = {totals.get('rate_sales_by_calls_all')}")
print(f"  computed sales / calls_all             = {(sales/calls*100):.2f}%" if calls else "  computed sales / calls_all = n/a")
print(f"  report  rate_sales_dialer_by_calls_all = {totals.get('rate_sales_dialer_by_calls_all')}")
print(f"  computed sales_dialer / calls_all      = {(salesd/calls*100):.2f}%" if calls else "  computed sales_dialer / calls_all = n/a")
print()
print("Compare these to the CRM's Vendor CPA 'Sales / All Calls %'. Tell me which line")
print("matches and I'll wire the Conversion Rate tile to it (we already fetch this report).")
