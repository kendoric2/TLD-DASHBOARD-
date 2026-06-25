"""
Falcon (vendor 14646) billable leads broken down by status — to define and
verify the conversion rate (converted = lead status Active or Sale).
Read-only, GET + JSON body.

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 probe_falcon.py
"""
import os
import requests
from dotenv import load_dotenv
import tldcrm_client as t

load_dotenv()
base = os.getenv("TLD_BASE_URL", "").strip().rstrip("/")
H = {"tld-api-id": os.getenv("TLD_API_ID", "").strip(),
     "tld-api-key": os.getenv("TLD_API_KEY", "").strip(),
     "Content-Type": "application/json", "Accept": "application/json"}

FALCON = 14646
CONVERTED = ("active", "sale")


def unwrap(d):
    if isinstance(d, dict):
        r = d.get("response", d)
        return r.get("results", r) if isinstance(r, dict) else r
    return d


def get(path, body):
    r = requests.get(f"{base}/api/egress/{path}", headers=H, json=body, timeout=40)
    return unwrap(r.json())


for rk in ["today", "this_month"]:
    s, e = t.date_range_for(rk)
    rows = get("leads", {"vendor_id": FALCON, "billable": 1,
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
        if str(st or "").strip().lower() in CONVERTED:
            converted += c
            mark = "   <- counts as converted"
        print(f"  {c:>6}  {st}{mark}")
    pct = round(converted / total * 100, 1) if total else 0
    print(f"  total billable: {total}")
    print(f"  converted (Active/Sale): {converted}    conversion: {pct}%")

print("\nDone. Confirm: (1) the status names, (2) a period total matches your 534.")
print("If the converted statuses are named differently, tell me and I'll adjust the list.")
