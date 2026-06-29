"""
Reconcile the Billable tile (read-only).

The dashboard counts billable LEAD RECORDS (tql_cnt_lead_id) on the leads endpoint,
filtered billable=1, by date_created. Your CRM may be showing billable CALLS instead.
For the chosen day this prints:
  1) a raw sample of billable leads + their 'billable' value  (is it a 0/1 flag, or a
     per-lead count of billable calls?)
  2) the lead COUNT  (= what the dashboard shows today)
  3) the SUM of 'billable' and a couple of call-count columns (likely the CRM's number)

Whichever line equals your CRM's 430 tells us exactly what to point the tile at.

    python3 sandbox/probes/probe_billable_reconcile.py
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

su, eu = t._us(START), t._us(END)
date = {"date_created": su, "date_created_end": eu}

p.hr(f"Billable reconcile   {START} -> {END}")

# 1) Raw sample: what does 'billable' look like per lead?
print("sample billable leads (look at the 'billable' value on each row):")
sample = config.egress_get("leads", {"billable": 1, "columns":
    ["lead_id", "billable", "status_name", "vendor_id", "date_created"], "limit": 10, **date})
p.show_rows(sample, limit=10, fields=["lead_id", "billable", "status_name", "vendor_id", "date_created"])

# 2) Lead COUNT — exactly what the dashboard sums today.
cnt = config.egress_get("leads", {"billable": 1, "aggregates": True, "aggregate": True,
    "columns": ["tql_cnt_lead_id"], **date})
rows, _ = p.as_rows(cnt)
print(f"\nlead COUNT  (tql_cnt_lead_id) = {t._first_num(rows)}   <-- what the dashboard shows")

# 3) Candidate 'billable calls' figures.
print("\ncandidate call-based totals (whichever matches your CRM is the one to use):")
for col in ("tql_sum_billable", "tql_cnt_call_id", "tql_sum_calls", "tql_sum_calls_billable"):
    r = config.egress_get("leads", {"billable": 1, "aggregates": True, "aggregate": True,
        "columns": [col], **date})
    rows, _ = p.as_rows(r)
    val = t._first_num(rows) if rows else r
    print(f"   {col:26} = {val}")

print("\nWhichever line equals your CRM's number is the metric to point the tile at. Paste this back.")
