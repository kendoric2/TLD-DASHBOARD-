"""
Confirm the 'billable calls' source (read-only).

report_cpa_agent (already enabled, already used for CPA/COST) carries call counts —
calls_billable, calls_all, calls_new_vendor, kpi_billable_inbounds, transfers_qualified.
This pulls today's TOTALS for each, under two date filters, so we can see which one
equals your CRM's 430:
  - canonical: date + date_sold  (what the dashboard already sends)
  - date-only: date              (call activity date, ignoring sale date)

    python3 sandbox/probes/probe_billable_calls.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t
import _probe_lib as p

config.require_creds()

# ===================== CHANGE THESE, THEN RUN =====================
START = "2026-06-26"        # match the CRM window you're comparing (default = today)
END   = "2026-06-26"
# ==================================================================

s0, e1 = f"{START} 00:00:00", f"{END} 23:59:59"
METRICS = ["calls_all", "calls_billable", "calls_new_vendor",
           "kpi_billable_inbounds", "transfers_qualified", "transfers_all"]
COLS = ["agent"] + METRICS

VARIANTS = {
    "canonical (date + date_sold)": {"date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1},
    "date-only (call activity)":    {"date": s0, "date_end": e1},
}

p.hr(f"report_cpa_agent — billable-call totals   {START} -> {END}")
for label, dates in VARIANTS.items():
    body = dict(dates, columns=COLS, limit=1000)
    rows, totals = p.as_rows(config.egress_get("report_cpa_agent", body, timeout=90))
    print(f"\n{label}   ({len(rows)} agents)")
    for m in METRICS:
        # prefer the report's totals row; else sum the agent rows
        val = totals.get(m) if isinstance(totals, dict) and totals.get(m) is not None \
            else sum(t._num(r.get(m)) for r in rows if isinstance(r, dict))
        print(f"   {m:24} = {val}")

print("\nWhichever total equals your CRM's 430 is the metric — and report_cpa_agent is")
print("already wired in, so pointing the tile at it is a one-line change. Paste this back.")
