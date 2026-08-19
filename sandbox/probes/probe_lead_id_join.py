#!/usr/bin/env python3
"""
Which call-log column holds the CRM lead_id? (READ-ONLY)

The invoice audit is showing a lead_id like 1249602 (7 digits) when the real CRM lead is
146334758 (9 digits). Almost certainly the call log carries the DIALER's lead id, not the
CRM's — the existence of `lead_dialer_leads` as a join table points the same way.

Rather than guess, this takes REAL CRM lead ids and searches every id-ish column of the
call log for them:

  1. dump all call-log columns, flag anything id-like
  2. pull recent CRM leads (known-good 9-digit ids)
  3. pull recent calls with every id-like column, and see WHICH column contains those ids
  4. check whether lead_dialer_leads maps dialer id -> CRM id

Usage:
  python3 sandbox/probes/probe_lead_id_join.py [DAYS]     # default 1 (yesterday)
"""
import os
import sys
import json
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

CALL_LOG = "tldialer/tldialer_call_log"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 1
END = datetime.date.today() - datetime.timedelta(days=1)
START = END - datetime.timedelta(days=DAYS - 1)
S0, E1 = f"{START} 00:00:00", f"{END} 23:59:59"


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nWHICH COLUMN IS THE CRM LEAD ID?   {START} .. {END}\n" + "=" * 72)

    # ---- 1. every id-like column on the call log -----------------------------------
    try:
        docs = config.egress_get(f"{CALL_LOG}/docs/columns", None, timeout=60)
    except Exception as e:
        docs = None
        print(f"  /docs/columns failed: {type(e).__name__}")
    allcols = [c for c in docs if isinstance(c, str)] if isinstance(docs, list) else []
    idcols = [c for c in allcols if "id" in c.lower() or "lead" in c.lower()]
    print(f"\n1. Call log has {len(allcols)} columns; {len(idcols)} look id/lead related:")
    for i in range(0, len(idcols), 6):
        print("     " + ", ".join(idcols[i:i + 6]))
    if not idcols:
        idcols = ["lead_id", "list_id", "campaign_id", "vendor_id", "call_log_id"]

    # ---- 2. real CRM lead ids -------------------------------------------------------
    crm = rows_of(config.egress_get("leads", {
        "columns": ["lead_id", "vendor_id"], "limit": 400,
        "date_created": S0, "date_created_end": E1}, timeout=120))
    crm_ids = {str(r.get("lead_id")) for r in crm if isinstance(r, dict) and r.get("lead_id")}
    print(f"\n2. Pulled {len(crm_ids):,} real CRM lead ids "
          f"(sample: {list(crm_ids)[:3]})")
    if not crm_ids:
        print("   no CRM leads in this window — try more days.")
        return

    # ---- 3. which call-log column contains them? ------------------------------------
    batch = idcols[:40] + ["call_date"]
    calls = rows_of(config.egress_get(CALL_LOG, {
        "columns": batch, "limit": 200000,
        "call_date": S0, "call_date_end": E1}, timeout=300))
    calls = [c for c in calls if isinstance(c, dict)]
    print(f"\n3. Checking {len(calls):,} calls — which column holds a CRM lead id?\n" + "-" * 72)
    print(f"   {'COLUMN':<30}{'populated':>11}{'MATCHES CRM':>14}{'digits':>9}")
    winner = None
    for col in batch:
        vals = [str(c.get(col)) for c in calls if c.get(col) not in (None, "", "0")]
        if not vals:
            continue
        hits = sum(1 for v in vals if v in crm_ids)
        widths = Counter(len(v) for v in vals[:500])
        common = widths.most_common(1)[0][0] if widths else 0
        mark = "   <-- THIS ONE" if hits > len(vals) * 0.2 else ""
        print(f"   {col:<30}{len(vals):>11,}{hits:>14,}{common:>9}{mark}")
        if hits > (winner[1] if winner else 0):
            winner = (col, hits)

    # ---- 4. the join table ----------------------------------------------------------
    print("\n4. lead_dialer_leads — does it map dialer id -> CRM id?\n" + "-" * 72)
    try:
        jd = rows_of(config.egress_get("lead_dialer_leads", {"limit": 5}, timeout=60))
        if jd and isinstance(jd[0], dict):
            print(f"   columns: {sorted(jd[0].keys())}")
            for r in jd[:3]:
                print("   ", json.dumps(r))
            sample_leads = {str(r.get("lead_id")) for r in jd if isinstance(r, dict)}
            inter = sample_leads & crm_ids
            print(f"   its lead_id looks like a CRM id: {'YES' if inter else 'not in our sample'}")
    except Exception as e:
        print(f"   failed: {type(e).__name__}: {str(e)[:70]}")

    print("\n" + "=" * 72)
    print("VERDICT")
    if winner and winner[1]:
        print(f"  '{winner[0]}' contains real CRM lead ids ({winner[1]:,} matches).")
        print("  -> use that column in the invoice audit instead of lead_id.")
    else:
        print("  No call-log column matched a CRM lead id directly.")
        print("  -> the call log is dialer-side only; we'd join via lead_dialer_leads,")
        print("     or simply drop the Lead ID column from the audit rather than show a")
        print("     number that looks like a CRM id but isn't.")
    print()


if __name__ == "__main__":
    main()
