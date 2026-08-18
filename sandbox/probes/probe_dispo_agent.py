#!/usr/bin/env python3
"""
Can lead_logs filter dispositions by AGENT server-side? (READ-ONLY)

We're adding per-agent dispositions to the Agent Detail tab. The day-cache design works
regardless — pull a day once, slice by agent locally — but if TLD can filter by agent
directly, a single-agent lookup over a long range gets much cheaper.

Tests, in order of usefulness:
  A. user_id filter          (numeric id, most likely to work)
  B. user_full_name filter   (string)
  C. how complete is user_full_name on status rows? (if it's often blank, slicing by
     agent locally would silently under-count)

Every filter is checked with an IMPOSSIBLE value that must return zero — TLD has silently
ignored filters three times now (lead_id, group_by sep, group_by lead_status_name), and
each time the wrong answer looked perfectly plausible.

Usage:
  python3 sandbox/probes/probe_dispo_agent.py [DAYS]     # default 1 (yesterday)
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
DATES = {"date_created": f"{START} 00:00:00", "date_created_end": f"{END} 23:59:59"}
COLS = ["action_id", "lead_status_name", "user_id", "user_full_name", "lead_vendor_id"]


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def pull(label, extra=None, cols=None):
    body = dict({"columns": cols or COLS, "action": "status", "limit": 200000}, **DATES)
    if extra:
        body.update(extra)
    t0 = time.time()
    try:
        rows = rows_of(config.egress_get("lead_logs", body, timeout=240))
    except Exception as e:
        print(f"    {label:<42} FAILED: {type(e).__name__}: {str(e)[:50]}")
        return None
    print(f"    {label:<42} {len(rows):>7,} rows ({int((time.time()-t0)*1000):,} ms)")
    return rows


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nAGENT DISPO PROBE   {START} .. {END}\n" + "=" * 70)

    print("\n0. Baseline — all disposition events in the window")
    base = pull("action='status', all agents")
    if not base:
        print("   nothing to work with; try more days.")
        return

    # who dispositions the most? use them as the test subject
    named = [r for r in base if isinstance(r, dict) and str(r.get("user_full_name") or "").strip()]
    who = Counter(str(r["user_full_name"]) for r in named)
    if not who:
        print("   !! user_full_name is blank on every row — we could not slice by agent locally.")
        return
    top_name, top_n = who.most_common(1)[0]
    top_id = None
    for r in named:
        if str(r.get("user_full_name")) == top_name and r.get("user_id"):
            top_id = r["user_id"]
            break
    print(f"    busiest agent: {top_name} (user_id {top_id}) with {top_n:,} of {len(base):,}")

    # ---- A. numeric user_id filter -------------------------------------------------
    print("\nA. Filter by user_id")
    a1 = pull(f"user_id = {top_id}", {"user_id": top_id})
    a2 = pull("user_id = 99999999 (expect 0)", {"user_id": 99999999})
    a_ok = (a2 is not None and len(a2) == 0 and a1 is not None and 0 < len(a1) < len(base))
    if a1 is not None and a_ok:
        got = {str(r.get("user_full_name")) for r in a1 if isinstance(r, dict)}
        print(f"    -> HONORED. returned only: {list(got)[:3]}")
        print(f"       {len(a1):,} rows vs {top_n:,} counted locally"
              f"{'  (match)' if len(a1) == top_n else '  <-- MISMATCH, do not trust'}")
    else:
        print("    -> NOT honored / inconclusive")

    # ---- B. name filter ------------------------------------------------------------
    print("\nB. Filter by user_full_name")
    b1 = pull(f"user_full_name = '{top_name}'", {"user_full_name": top_name})
    b2 = pull("user_full_name = 'Zzz Nobody' (expect 0)", {"user_full_name": "Zzz Nobody"})
    b_ok = (b2 is not None and len(b2) == 0 and b1 is not None and 0 < len(b1) < len(base))
    print(f"    -> {'HONORED' if b_ok else 'NOT honored / inconclusive'}")

    # ---- C. completeness -----------------------------------------------------------
    print("\nC. Is user_full_name reliable enough to slice locally?")
    blank = len(base) - len(named)
    print(f"    {len(named):,} of {len(base):,} status rows have an agent "
          f"({blank:,} blank, {blank / len(base) * 100:.1f}%)")
    print(f"    {len(who)} distinct agents")
    for n, c in who.most_common(8):
        print(f"        {n:<30}{c:>7,}")

    print("\n" + "=" * 70)
    print("VERDICT")
    if a_ok:
        print("  user_id filtering WORKS -> narrow single-agent lookups can query TLD directly,")
        print("  and the day cache still serves the broad views. Best of both.")
    elif b_ok:
        print("  name filtering works (user_id doesn't) -> usable, but names are less stable")
        print("  than ids; prefer the day cache and treat this as an optimization.")
    else:
        print("  No server-side agent filter. Use the day cache and slice locally —")
        print(f"  which is fine: user_full_name is present on {100 - blank / len(base) * 100:.0f}% of rows.")
    print()


if __name__ == "__main__":
    main()
