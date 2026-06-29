"""
Check whether vendorperformance actually honors the date filter (read-only).

The report shows FALCON Sales = 85 for "today," but real sales today are ~18 — so either
the window isn't really today, or "Sales" counts something broader. This pulls FALCON's
Leads / Billable / Sales / Policies for several windows. If "today" == "this month" ==
"no date", the date filter is being ignored (85 isn't today's number).

    python3 sandbox/probes/probe_vendor_dates.py
"""
import os
import re
import sys
import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t

config.require_creds()


def strip(v):
    return re.sub(r"<[^>]+>", "", str(v if v is not None else "")).replace(",", "").strip()


def falcon(resp):
    rows = resp.get("vendor") if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
    for r in rows:
        if isinstance(r, dict) and strip(r.get("ID")) == str(config.FALCON_VENDOR_ID):
            return r
    return {}


today = datetime.date.today()
yest = today - datetime.timedelta(days=1)
wk_s, wk_e = t.date_range_for("this_week")
mo_s, mo_e = t.date_range_for("this_month")
windows = [
    ("today", today.isoformat(), today.isoformat()),
    ("yesterday", yest.isoformat(), yest.isoformat()),
    ("this_week", wk_s, wk_e),
    ("this_month", mo_s, mo_e),
]

print(f"FALCON ({config.FALCON_VENDOR_ID}) per window\n")
print(f"{'window':12}{'Leads':>8}{'Billable':>10}{'Sales':>8}{'Policies':>10}")
print("-" * 48)
for label, s, e in windows:
    s0, e1 = f"{s} 00:00:00", f"{e} 23:59:59"
    body = {"date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1, "limit": 200}
    f = falcon(config.egress_get("vendorperformance", body, timeout=90))
    print(f"{label:12}{strip(f.get('Leads')):>8}{strip(f.get('Billable')):>10}"
          f"{strip(f.get('Sales')):>8}{strip(f.get('Policies')):>10}")

f = falcon(config.egress_get("vendorperformance", {"limit": 200}, timeout=90))
print(f"{'no date':12}{strip(f.get('Leads')):>8}{strip(f.get('Billable')):>10}"
      f"{strip(f.get('Sales')):>8}{strip(f.get('Policies')):>10}")

print("\nIf 'today' ~= 'this month' / 'no date', the date filter is ignored — 85 isn't today.")
print("If today < week < month, dates work and 'Sales' just counts more than your 18.")
