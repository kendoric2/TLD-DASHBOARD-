"""
Find which date filter makes vendorperformance's FALCON Billable match the CRM (read-only).

The CRM Vendor CPA shows FALCON Billable Calls = 290 / Sales 51 / 17.59% today, but our
query (date + date_sold) returns Billable 218 → 23.4%. Billable *calls* are probably
dated by call date, not sale date. This pulls FALCON under several date-param shapes so
we can see which one yields Billable 290 (and keeps Sales 51).

    python3 sandbox/probes/probe_vendor_dateparams.py
"""
import os
import re
import sys
import datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config

config.require_creds()

EP = "vendorperformance"
today = datetime.date.today().isoformat()
s0, e1 = f"{today} 00:00:00", f"{today} 23:59:59"


def strip(v):
    return re.sub(r"<[^>]+>", "", str(v if v is not None else "")).replace(",", "").strip()


def num(v):
    d = re.sub(r"[^0-9.]", "", strip(v))
    return float(d) if d else 0.0


def falcon(resp):
    rows = resp.get("vendor") if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
    for r in rows:
        if isinstance(r, dict) and strip(r.get("ID")) == str(config.FALCON_VENDOR_ID):
            return r
    return {}


variants = {
    "date + date_sold (current)": {"date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1},
    "date only":                  {"date": s0, "date_end": e1},
    "date_sold only":             {"date_sold": s0, "date_sold_end": e1},
    "date_created":               {"date_created": s0, "date_created_end": e1},
    "no date":                    {},
}

print(f"FALCON today — looking for Billable 290 / Sales 51\n")
print(f"{'date params':28}{'Billable':>10}{'Sales':>8}{'Spend':>12}  Sales/Billable")
print("-" * 72)
for label, d in variants.items():
    f = falcon(config.egress_get(EP, {**d, "limit": 200}, timeout=90))
    b, s, sp = num(f.get("Billable")), num(f.get("Sales")), num(f.get("Spend"))
    conv = f"{s / b * 100:.1f}%" if b else "n/a"
    print(f"{label:28}{b:>10.0f}{s:>8.0f}{('$' + format(sp, ',.0f')):>12}  {conv}")

print("\nThe row showing Billable 290 + Sales 51 (~17.6%) is the date filter to use for")
print("the conversion. Paste this back.")
