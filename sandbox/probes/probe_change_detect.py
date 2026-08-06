#!/usr/bin/env python3
"""
Can we cheaply tell whether a past date range has CHANGED? (READ-ONLY)

A safe cache needs to answer "is my saved copy still correct?" without re-pulling
everything. Policies carry `date_modified`, so the ideal check is:

    "how many policies in this range were modified since I cached it?"   -> 0 means safe

This probe finds out whether TLD actually supports that, and falls back to measuring the
count-only check if it doesn't.

CRITICAL: it doesn't just check that a filter returns rows — it checks the filter is being
HONORED, by asking for an impossible window that must return zero. (TLD has silently
ignored filters before: that's how the bogus "100% MCD" and the lead_id dead end happened.)

Usage:
  python3 sandbox/probes/probe_change_detect.py [START] [END]   # defaults to last month
"""
import os
import sys
import time
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

TODAY = datetime.date.today()
if len(sys.argv) > 2:
    START, END = sys.argv[1], sys.argv[2]
else:
    first_this = TODAY.replace(day=1)
    last_end = first_this - datetime.timedelta(days=1)
    START, END = last_end.replace(day=1).isoformat(), last_end.isoformat()

S0, E1 = f"{START} 00:00:00", f"{END} 23:59:59"
SALE = {"date": S0, "date_end": E1, "date_sold": S0, "date_sold_end": E1}
COUNT = {"aggregates": True, "aggregate": True, "columns": ["tql_cnt_policy_id"]}


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def count_call(label, extra=None, show=True):
    """Run an aggregate count with optional extra filters; return (count, ms)."""
    body = dict(COUNT, **SALE)
    if extra:
        body.update(extra)
    t0 = time.time()
    try:
        resp = config.egress_get("policies", body, timeout=90)
    except Exception as e:
        if show:
            print(f"    {label:<44} FAILED: {type(e).__name__}: {str(e)[:60]}")
        return None, 0
    ms = int((time.time() - t0) * 1000)
    rows = resp if isinstance(resp, list) else (resp.get("results") if isinstance(resp, dict) else [])
    n = 0
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        for v in rows[0].values():
            n = num(v)
            if n:
                break
    if show:
        print(f"    {label:<44} count={n:<9,} ({ms} ms)")
    return n, ms


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    print(f"\nCHANGE-DETECTION PROBE   sale range {START} .. {END}\n" + "=" * 74)

    # ---- 1. Baseline: how many policies are in this range at all? -------------------
    print("\n1. Baseline")
    base, base_ms = count_call("policies sold in range (no extra filter)")
    if not base:
        print("   No policies in this range — pass a range with sales, e.g. 2026-07-01 2026-07-31")
        return

    # ---- 2. Is date_modified honored ALONGSIDE the sale range? ----------------------
    print("\n2. date_modified filter on top of the sale range")
    print("   (if the filter is honored, an impossible window must return 0)")
    all_time, _ = count_call("modified since 2000-01-01  (expect = baseline)",
                             {"date_modified": "2000-01-01 00:00:00",
                              "date_modified_end": "2099-12-31 23:59:59"})
    future, _ = count_call("modified after tomorrow     (expect = 0)",
                           {"date_modified": f"{TODAY + datetime.timedelta(days=1)} 00:00:00",
                            "date_modified_end": "2099-12-31 23:59:59"})
    week, week_ms = count_call("modified in the last 7 days",
                               {"date_modified": f"{TODAY - datetime.timedelta(days=7)} 00:00:00",
                                "date_modified_end": "2099-12-31 23:59:59"})

    honored = (future == 0 and all_time == base and base > 0)
    if honored:
        print("\n   -> date_modified IS honored. This is the exact check we want:")
        print(f"      '{week:,} of the {base:,} policies in {START}..{END} changed in the last 7 days'")
    elif future == base:
        print("\n   -> date_modified is IGNORED (impossible window still returned everything).")
    else:
        print(f"\n   -> inconclusive: baseline={base}, all-time={all_time}, future={future}")

    # ---- 3. Fallback: what does a plain count check cost? ---------------------------
    print("\n3. Fallback — plain count check (catches adds/removes, misses edits)")
    _, ms2 = count_call("re-run baseline count (timing)")
    print(f"    a cache validation would cost ~{(base_ms + ms2) // 2} ms per range")

    # ---- 4. Can we ask 'what changed recently' globally? ----------------------------
    print("\n4. Global 'what changed recently' (date_field override, no sale range)")
    body = {"columns": ["policy_id", "date_sold", "date_modified"],
            "date_field": "date_modified",
            "date_modified": f"{TODAY - datetime.timedelta(days=2)} 00:00:00",
            "date_modified_end": f"{TODAY} 23:59:59", "limit": 50000}
    t0 = time.time()
    try:
        resp = config.egress_get("policies", body, timeout=120)
        rows = resp if isinstance(resp, list) else []
        ms = int((time.time() - t0) * 1000)
        print(f"    policies modified in the last 2 days: {len(rows):,} ({ms} ms)")
        if rows:
            olds = [r for r in rows if isinstance(r, dict)
                    and str(r.get("date_sold") or "")[:10] < START]
            print(f"    of those, {len(olds):,} were SOLD before {START} "
                  f"(= past ranges that would need re-caching)")
            for r in rows[:3]:
                if isinstance(r, dict):
                    print(f"       policy {r.get('policy_id')}  sold {str(r.get('date_sold'))[:10]}"
                          f"  modified {r.get('date_modified')}")
    except Exception as e:
        print(f"    FAILED: {type(e).__name__}: {str(e)[:90]}")

    # ---- verdict -------------------------------------------------------------------
    print("\n" + "=" * 74)
    print("VERDICT")
    if honored:
        print("  BEST: validate a cached range with one fast 'modified since <cache time>'")
        print("  count. Zero means the cache is provably current — catches edits AND")
        print("  adds/removes. Build the cache with this check.")
    else:
        print("  date_modified can't be combined with the sale range. Fall back to the plain")
        print("  count check (fast, catches adds/removes) — and note it would miss a policy")
        print("  that was edited in place, e.g. active -> termed.")
        print("  If section 4 worked, we can ALSO run one global 'what changed lately' call")
        print("  and invalidate any cached range containing those policies.")
    print()


if __name__ == "__main__":
    main()
