"""
Falcon (vendor 14646) billable leads broken down by status — to define and
verify the conversion rate (converted = lead status Active or Sale).
Read-only, GET + JSON body.

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 sandbox/probes/probe_falcon.py
"""

# --- make src/ importable no matter where this script is run from ---
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

import config
import tldcrm_client as t

config.require_creds()

for rk in ["today", "this_month"]:
    s, e = t.date_range_for(rk)
    rows = config.egress_get("leads", {"vendor_id": config.FALCON_VENDOR_ID, "billable": 1,
                             "date_created": t._us(s), "date_created_end": t._us(e),
                             "aggregates": True, "group_by": "status_name",
                             "columns": ["status_name", "tql_cnt_lead_id"],
                             "order_by": "tql_cnt_lead_id", "sort": "DESC", "limit": 100})
    print(f"\n=== Falcon billable by status — {rk} ({t._us(s)} .. {t._us(e)}) ===")
    if not isinstance(rows, list):
        print(rows)
        continue
    total = converted = 0
    for r in rows:
        c = t._num(r.get("tql_cnt_lead_id"))
        total += c
        st = r.get("status_name")
        mark = ""
        if str(st or "").strip().lower() in config.CONVERTED_STATUSES:
            converted += c
            mark = "   <- counts as converted"
        print(f"  {c:>6}  {st}{mark}")
    pct = round(converted / total * 100, 1) if total else 0
    print(f"  total billable: {total}")
    print(f"  converted (Active/Sale): {converted}    conversion: {pct}%")

print("\nDone. Confirm: (1) the status names, (2) a period total matches your 534.")
print("If the converted statuses are named differently, tell me and I'll adjust the list.")
