"""
Reconcile billable leads by vendor/source (read-only, GET + JSON body).

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 probe_billables.py

The leads endpoint only carries vendor_id (no name), so we map ids -> names
via the /vendors endpoint, then show billable leads per source for today and
this month. Look for the row that matches your 534.
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


def unwrap(d):
    if isinstance(d, dict):
        r = d.get("response", d)
        return r.get("results", r) if isinstance(r, dict) else r
    return d


def get(path, body=None):
    r = requests.get(f"{base}/api/egress/{path}", headers=H, json=body, timeout=40)
    return unwrap(r.json())


# vendor_id -> name map (request the id explicitly; default cols omit it)
vmap = {}
for v in (get("vendors", {"columns": ["vendor_id", "name"], "limit": 500}) or []):
    if isinstance(v, dict):
        vmap[str(v.get("vendor_id"))] = v.get("name")
print(f"loaded {len(vmap)} vendor names")


def by_vendor(rk):
    s, e = t.date_range_for(rk)
    rows = get("leads", {"billable": 1, "date_created": t._us(s), "date_created_end": t._us(e),
                         "aggregates": True, "group_by": "vendor_id",
                         "columns": ["vendor_id", "tql_cnt_lead_id"],
                         "order_by": "tql_cnt_lead_id", "sort": "DESC", "limit": 100})
    print(f"\n=== billable by source — {rk} ({t._us(s)} .. {t._us(e)}) ===")
    if not isinstance(rows, list):
        print(rows)
        return
    total = 0
    for r in rows:
        c = t._num(r.get("tql_cnt_lead_id"))
        total += c
        vid = str(r.get("vendor_id"))
        print(f"  {c:>6}  {vmap.get(vid) or '(vendor_id ' + vid + ')'}")
    print(f"  --- total: {total} ---")


for rk in ["today", "this_month"]:
    by_vendor(rk)

print("\nDone. Tell me which row/period equals your 534 and I'll lock that definition in.")
