"""
Hunt for the 'billable calls' source (read-only).

Inspects the most likely dialer/vendor endpoints. For each: lists its columns (flagging
billable / call / date fields) and shows a 3-row sample of just those fields, so we can
see the grain (is one row a call? a lead? a vendor?) and what 'billable' looks like.

    python3 sandbox/probes/probe_dialer.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import _probe_lib as p

config.require_creds()

# Curated candidates, best guess first.
CANDS = ["dialer_leads", "lead_dialer_leads", "vendorperformance", "vendor_logs", "agentcpa", "callbacks"]

for e in CANDS:
    p.hr(e)
    try:
        cols = p.cols_of(e)
    except Exception as ex:
        print(f"  /docs/columns failed: {type(ex).__name__}: {str(ex)[:90]}")
        continue
    if not cols:
        print("  (no columns returned)")
        continue
    bill = [c for c in cols if "billable" in str(c).lower()]
    call = [c for c in cols if "call" in str(c).lower()][:8]
    dates = [c for c in cols if "date" in str(c).lower()][:6]
    print(f"  cols: {len(cols)}")
    print(f"  billable: {bill or '(none)'}")
    print(f"  call-ish: {call or '(none)'}")
    print(f"  dates:    {dates or '(none)'}")

    # Show a 3-row sample of just the interesting fields (keeps output small).
    show = (bill + call[:4] + dates[:3]) or cols[:6]
    print("  sample:")
    try:
        p.show_rows(p.pull(e, 3, cols=show), limit=3, fields=show)
    except Exception as ex:
        print(f"    sample failed: {type(ex).__name__}: {str(ex)[:90]}")

print("\nPaste this back — I'll spot the billable + date columns and we'll count today (target ~430).")
