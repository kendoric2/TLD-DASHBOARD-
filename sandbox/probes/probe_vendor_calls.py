"""
Find FALCON's billable CALLS (the CRM's "All Calls" = 290) via report_cpa_agent.

vendorperformance "Billable" (220) is billable LEADS; the CRM's Vendor CPA divides Sales
by billable CALLS. report_cpa_agent has calls_billable (a call count). This checks whether
scoping report_cpa_agent to vendor_id=FALCON yields ~290 billable calls + ~51 sales
(= 17.6%), i.e. matches the CRM.

    python3 sandbox/probes/probe_vendor_calls.py
"""
import os
import sys
import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t
import _probe_lib as p

config.require_creds()

today = datetime.date.today().isoformat()
s0, e1 = f"{today} 00:00:00", f"{today} 23:59:59"
COLS = ["agent", "sales", "calls_all", "calls_billable"]


def total_of(rows, totals, col):
    if isinstance(totals, dict) and totals.get(col) not in (None, ""):
        return t._num(totals.get(col))
    return sum(t._num(r.get(col)) for r in rows if isinstance(r, dict))


print(f"report_cpa_agent — today   (CRM target: FALCON billable calls 290, sales 51, 17.6%)\n")
print(f"{'scope':18}{'calls_billable':>16}{'calls_all':>11}{'sales':>8}  sales/billable_calls")
print("-" * 75)
for label, extra in [("all vendors", {}), (f"vendor {config.FALCON_VENDOR_ID}", {"vendor_id": config.FALCON_VENDOR_ID})]:
    body = {"columns": COLS, "limit": 2000,
            "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1, **extra}
    rows, totals = p.as_rows(config.egress_get("report_cpa_agent", body, timeout=150))
    cb = total_of(rows, totals, "calls_billable")
    ca = total_of(rows, totals, "calls_all")
    s = total_of(rows, totals, "sales")
    conv = f"{s / cb * 100:.1f}%" if cb else "n/a"
    print(f"{label:18}{cb:>16.0f}{ca:>11.0f}{s:>8.0f}  {conv}")

print("\nIf the 'vendor 14646' row shows calls_billable ~290 + sales ~51 (~17.6%), that's")
print("the CRM's number — and I'll point Conversion at report_cpa_agent's calls_billable.")
print("If vendor filtering doesn't change it, report_cpa_agent can't scope by vendor and")
print("we'll hunt the actual Vendor-CPA endpoint instead. Paste this back.")
