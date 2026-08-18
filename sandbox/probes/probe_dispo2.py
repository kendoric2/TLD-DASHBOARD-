#!/usr/bin/env python3
"""
Can we get disposition COUNTS without pulling the whole log? (READ-ONLY)

lead_logs is ~22,700 rows/day (~680k/month) — far too much to pull on a page load.
All the filters work (date, action, lead_vendor_id), but the ideal is a server-side
aggregate: "count of each lead_status_name" in one small call.

TLD has silently ignored group_by before — on leads.sep it lumped everything into one
bucket and reported 100% MCD. So this doesn't just check that an aggregate comes back:
it VALIDATES the grouped counts against a known row count pulled the slow way. If they
don't add up, the aggregate is a lie and we don't use it.

Usage:
  python3 sandbox/probes/probe_dispo2.py [DAYS]     # default 1 (yesterday)
"""
import os
import sys
import time
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 1
END = datetime.date.today() - datetime.timedelta(days=1)
START = END - datetime.timedelta(days=DAYS - 1)
S0, E1 = f"{START} 00:00:00", f"{END} 23:59:59"
DATES = {"date_created": S0, "date_created_end": E1}


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def num(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def call(label, body, timeout=180):
    t0 = time.time()
    try:
        rows = rows_of(config.egress_get("lead_logs", dict(body, **DATES), timeout=timeout))
    except Exception as e:
        print(f"  {label:<44} FAILED: {type(e).__name__}: {str(e)[:55]}")
        return None, 0
    ms = int((time.time() - t0) * 1000)
    print(f"  {label:<44} {len(rows):>6,} rows ({ms:,} ms)")
    return rows, ms


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nDISPO AGGREGATE PROBE   {START} .. {END}\n" + "=" * 74)

    # ---- ground truth: pull the status rows the slow way and count them ourselves ---
    print("\n1. Ground truth (slow way) — pull action='status' rows and count locally")
    truth_rows, truth_ms = call("action='status', full rows",
                                {"columns": ["action_id", "lead_status_name", "lead_vendor_id"],
                                 "action": "status", "limit": 200000}, timeout=300)
    if truth_rows is None:
        return
    truth = Counter(str(r.get("lead_status_name") or "(blank)")
                    for r in truth_rows if isinstance(r, dict))
    total_truth = sum(truth.values())
    print(f"     {total_truth:,} status events, {len(truth)} distinct dispositions")
    for k, v in truth.most_common(8):
        print(f"        {k:<28}{v:>8,}")

    # ---- the cheap way: ask TLD to group + count -----------------------------------
    print("\n2. Cheap way — server-side group_by on lead_status_name")
    agg, agg_ms = call("aggregate group_by lead_status_name",
                       {"aggregates": True, "aggregate": True,
                        "group_by": "lead_status_name",
                        "columns": ["lead_status_name", "tql_cnt_action_id"],
                        "action": "status",
                        "order_by": "tql_cnt_action_id", "sort": "DESC", "limit": 100})

    if not agg:
        print("     -> no aggregate returned; we'd scope row pulls instead.")
        return

    got = {}
    for r in agg:
        if isinstance(r, dict):
            got[str(r.get("lead_status_name") or "(blank)")] = num(r.get("tql_cnt_action_id"))
    total_agg = sum(got.values())
    print(f"     returned {len(got)} group(s), total {total_agg:,}")
    for k, v in sorted(got.items(), key=lambda x: -x[1])[:8]:
        print(f"        {k:<28}{v:>8,}")

    # ---- validate: do the groups actually match reality? ---------------------------
    print("\n3. Validation — does the aggregate match the ground truth?")
    if len(got) <= 1 and len(truth) > 1:
        print(f"     !! group_by COLLAPSED everything into {len(got)} bucket — IGNORED.")
        print("        (same failure as leads.sep -> the bogus '100% MCD')")
        ok = False
    else:
        ok = True
        for k in sorted(set(truth) | set(got)):
            t, g = truth.get(k, 0), got.get(k, 0)
            mark = "" if t == g else "   <-- MISMATCH"
            if t != g:
                ok = False
            print(f"        {k:<28} truth {t:>7,}   agg {g:>7,}{mark}")
        print(f"        {'TOTAL':<28} truth {total_truth:>7,}   agg {total_agg:>7,}")

    # ---- can we also group per vendor? ---------------------------------------------
    print("\n4. Same aggregate, scoped to one vendor (for the vendor tab)")
    vids = Counter(str(r.get("lead_vendor_id")) for r in truth_rows
                   if isinstance(r, dict) and r.get("lead_vendor_id"))
    if vids:
        vid = vids.most_common(1)[0][0]
        v_agg, _ = call(f"aggregate, lead_vendor_id={vid}",
                        {"aggregates": True, "aggregate": True,
                         "group_by": "lead_status_name",
                         "columns": ["lead_status_name", "tql_cnt_action_id"],
                         "action": "status", "lead_vendor_id": vid, "limit": 100})
        v_truth = sum(1 for r in truth_rows if isinstance(r, dict)
                      and str(r.get("lead_vendor_id")) == vid)
        if v_agg:
            v_tot = sum(num(r.get("tql_cnt_action_id")) for r in v_agg if isinstance(r, dict))
            print(f"     vendor {vid}: aggregate {v_tot:,} vs counted {v_truth:,}"
                  f"{'  OK' if v_tot == v_truth else '   <-- MISMATCH'}")

    print("\n" + "=" * 74)
    print("VERDICT")
    if ok:
        print(f"  Aggregate is TRUSTWORTHY and took {agg_ms:,} ms vs {truth_ms:,} ms for rows.")
        print("  -> dispo tile can be instant, for any range, at any volume.")
    else:
        print("  Aggregate does NOT match — do not use it.")
        print("  -> pull rows instead, always scoped to action='status' + one vendor +")
        print(f"     a short range (a day was {truth_ms:,} ms).")
    print()


if __name__ == "__main__":
    main()
