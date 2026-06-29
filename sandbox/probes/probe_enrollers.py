"""
TEST: Enroller (fronter) performance — enrollments grouped by fronter_id (read-only).

The fronter = the enroller. This pulls the date range's policies, dedupes by the canonical
key (policy_id -> lead_id), and groups them by fronter_id (showing fronter_name) to count
enrollments per enroller. Self-generated sales (no fronter) are reported separately, and
GTL is split out so we can decide whether to exclude it (as Policies Sold does).

    python3 sandbox/probes/probe_enrollers.py
"""
import os
import sys
import datetime
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t
import _probe_lib as p

config.require_creds()

# ===================== CHANGE THESE, THEN RUN =====================
START = datetime.date.today().isoformat()   # defaults to today; set "YYYY-MM-DD" to look back
END   = datetime.date.today().isoformat()
# ==================================================================

s0, e1 = f"{START} 00:00:00", f"{END} 23:59:59"
COLS = ["policy_id", "lead_id", "fronter_id", "fronter_name", "agent_name", "carrier_name"]
body = {"columns": COLS, "limit": 50000,
        "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1}

rows, _ = p.as_rows(config.egress_get("policies", body, timeout=90))

# dedupe by the canonical key (same as Policies Sold), keep all carriers for now
seen, kept = set(), []
for r in rows:
    if not isinstance(r, dict):
        continue
    k = t._dedupe_key(r)
    if k and k not in seen:
        seen.add(k)
        kept.append(r)

by_fronter = defaultdict(lambda: {"fid": None, "name": None, "count": 0})
no_fronter = 0
gtl = 0
for r in kept:
    if str(r.get("carrier_name") or "").strip().upper() in config.EXCLUDED_POLICY_CARRIERS:
        gtl += 1
    fid = str(r.get("fronter_id") or "").strip()
    if fid in ("", "0"):
        no_fronter += 1
        continue
    g = by_fronter[fid]
    g["fid"] = fid
    g["count"] += 1
    g["name"] = r.get("fronter_name") or g["name"]

p.hr(f"Enroller (fronter) performance — TEST   {START} -> {END}")
print(f"policies (deduped):            {len(kept)}")
print(f"  with an enroller (fronter):  {len(kept) - no_fronter}")
print(f"  no enroller (self-generated):{no_fronter}")
print(f"  of which GTL:                {gtl}   (excluded from Policies Sold)")

print(f"\n{'fronter_id':12}{'enroller':26}{'enrollments':>12}")
print("-" * 50)
for g in sorted(by_fronter.values(), key=lambda g: g["count"], reverse=True):
    print(f"{g['fid']:12}{str(g['name'])[:25]:26}{g['count']:>12}")

print("\nCompare the per-enroller counts to your CRM. Tell me: include GTL or not, and")
print("whether to show enrollments only or also a sales/conversion column — then I wire it.")
