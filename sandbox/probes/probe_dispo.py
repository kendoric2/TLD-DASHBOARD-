#!/usr/bin/env python3
"""
Can we build dispo tracking on lead_logs? (READ-ONLY)

lead_logs turned out to be the disposition event log: each row is an action on a lead
(action="status", page="/dialer/status") carrying the resulting lead_status_name, the
agent who set it, the vendor, and a timestamp. dialer_leads is only a join table.

Before building anything we need to know whether it's PRACTICAL:

  1. VOLUME  — how many log rows per day? An event log can be enormous; if a month is
               500k rows we can't pull it on a page load.
  2. FILTERS — are date / action / vendor filters actually HONORED? (Each is tested with
               an impossible value that must return zero — TLD has silently ignored
               filters before, e.g. lead_id and group_by sep.)
  3. SHAPE   — what do `action`, `page` and `lead_status_name` actually contain, so we
               know how to isolate real dialer dispositions from other lead edits.

Usage:
  python3 sandbox/probes/probe_dispo.py [DAYS]     # default 1 (yesterday)
"""
import os
import sys
import time
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 1
END = datetime.date.today() - datetime.timedelta(days=1)      # a full finished day
START = END - datetime.timedelta(days=DAYS - 1)
S0, E1 = f"{START} 00:00:00", f"{END} 23:59:59"

COLS = ["action_id", "date_created", "lead_id", "action", "result", "page",
        "user_full_name", "lead_vendor_id", "lead_status_name"]


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def pull(label, extra=None, limit=200000):
    body = {"columns": COLS, "limit": limit,
            "date_created": S0, "date_created_end": E1}
    if extra:
        body.update(extra)
    t0 = time.time()
    try:
        rows = rows_of(config.egress_get("lead_logs", body, timeout=240))
    except Exception as e:
        print(f"    {label:<40} FAILED: {type(e).__name__}: {str(e)[:60]}")
        return None
    ms = int((time.time() - t0) * 1000)
    flag = "   <-- HIT THE LIMIT" if len(rows) >= limit else ""
    print(f"    {label:<40} {len(rows):>8,} rows ({ms:,} ms){flag}")
    return rows


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nDISPO PROBE — lead_logs    {START} .. {END}  ({DAYS} day(s))\n" + "=" * 72)

    # ---- 1. volume + does the date filter work? ------------------------------------
    print("\n1. Volume and date filtering")
    allrows = pull("everything in the window", None)
    if allrows is None:
        return
    if allrows:
        per_day = len(allrows) / max(DAYS, 1)
        print(f"    ~{per_day:,.0f} rows/day  ->  a month would be ~{per_day * 30:,.0f} rows")

    future = pull("date window in 2099 (expect 0)",
                  {"date_created": "2099-01-01 00:00:00",
                   "date_created_end": "2099-12-31 23:59:59"})
    print(f"    -> date filter: {'HONORED' if future is not None and len(future) == 0 else 'NOT honored'}")

    # ---- 2. can we narrow it server-side? ------------------------------------------
    print("\n2. Can we filter server-side (so we don't pull the whole log)?")
    only_status = pull("action = 'status'", {"action": "status"})
    bogus_act = pull("action = 'zzzznope' (expect 0)", {"action": "zzzznope"})
    act_ok = (bogus_act is not None and len(bogus_act) == 0
              and only_status is not None and 0 < len(only_status) <= len(allrows))
    print(f"    -> action filter: {'HONORED' if act_ok else 'NOT honored / inconclusive'}")

    vend = None
    if allrows:
        vids = Counter(str(r.get("lead_vendor_id")) for r in allrows
                       if isinstance(r, dict) and r.get("lead_vendor_id"))
        if vids:
            top_vid = vids.most_common(1)[0][0]
            vend = pull(f"lead_vendor_id = {top_vid}", {"lead_vendor_id": top_vid})
            bogus_v = pull("lead_vendor_id = 99999999 (expect 0)", {"lead_vendor_id": 99999999})
            v_ok = (bogus_v is not None and len(bogus_v) == 0
                    and vend is not None and 0 < len(vend) <= len(allrows))
            print(f"    -> vendor filter: {'HONORED' if v_ok else 'NOT honored / inconclusive'}")

    # ---- 3. what's actually in it --------------------------------------------------
    print("\n3. What the log contains")
    src = allrows or []
    if not src:
        print("    (no rows to summarize)")
        return

    def dist(field, n=12, label=None):
        c = Counter(str(r.get(field) or "(blank)") for r in src if isinstance(r, dict))
        print(f"\n    {label or field}  ({len(c)} distinct)")
        for k, v in c.most_common(n):
            print(f"        {k[:38]:<40}{v:>8,}  ({v / len(src) * 100:4.1f}%)")

    dist("action", 10, "action — what kind of event")
    dist("page", 10, "page — where it came from (/dialer/status = a dialer dispo)")
    dist("lead_status_name", 18, "lead_status_name — THE DISPOSITION")

    dialer = [r for r in src if isinstance(r, dict)
              and "dialer" in str(r.get("page") or "").lower()]
    print(f"\n    rows from a dialer page: {len(dialer):,} of {len(src):,} "
          f"({len(dialer) / len(src) * 100:.1f}%)")
    if dialer:
        agents = Counter(str(r.get("user_full_name") or "?") for r in dialer)
        print(f"    distinct agents dispositioning: {len(agents)}")
        for k, v in agents.most_common(5):
            print(f"        {k:<34}{v:>7,}")

    print("\n" + "=" * 72)
    print("Read it like this:")
    print("  • volume small (<50k/month) + filters honored -> build dispo straight from lead_logs")
    print("  • volume huge but filters honored             -> pull per-vendor/per-day only")
    print("  • filters ignored                             -> too heavy for a live tile;")
    print("                                                   we'd summarize on a schedule")
    print()


if __name__ == "__main__":
    main()
