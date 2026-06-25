"""
Reconcile billable leads by vendor/source (read-only, GET + JSON body).

Run on your Mac:
    cd ~/Documents/TLDDASHBOARD
    python3 archive/probe_billables.py

The leads endpoint only carries vendor_id (no name), so we map ids -> names
via the /vendors endpoint, then show billable leads per source for today and
this month. Look for the row that matches your 534.
"""

# --- make src/ importable no matter where this script is run from ---
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import config
import tldcrm_client as t

config.require_creds()

# vendor_id -> name map (request the id explicitly; default cols omit it)
vmap = {}
for v in (config.egress_get("vendors", {"columns": ["vendor_id", "name"], "limit": 500}) or []):
    if isinstance(v, dict):
        vmap[str(v.get("vendor_id"))] = v.get("name")
print(f"loaded {len(vmap)} vendor names")


def by_vendor(rk):
    s, e = t.date_range_for(rk)
    rows = config.egress_get("leads", {"billable": 1, "date_created": t._us(s), "date_created_end": t._us(e),
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
