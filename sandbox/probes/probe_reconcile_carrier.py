#!/usr/bin/env python3
"""
Reconcile the dashboard's policy numbers against the CRM's own carrier table (READ-ONLY),
and figure out which STATUS filter makes them match.

It pulls the date range once (with the status fields), dedupes on policy_id -> lead_id,
then shows:
  1. The distribution of every candidate status field (status_name / status / active /
     status_id / stage) — so we can SEE what statuses exist and how many of each.
  2. Per-carrier counts ALL statuses vs ACTIVE-only vs your accurate TABLE, so we can see
     whether "active" is the filter that reconciles it.

Edit ACTIVE_FIELD / ACTIVE_VALUES below once we know the right status word.

Usage:
  python3 sandbox/probes/probe_reconcile_carrier.py [START] [END] [calls]
  # defaults to 2024-10-01 .. 2025-10-01
  # add the word "calls" as a 3rd arg to also run the report_cpa_agent (Billable/Conversion) check
"""
import os
import sys
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config                                  # noqa: E402
from tldcrm_client import TLDCRMClient, _dedupe_key, PAYLOADS   # noqa: E402


def dedupe_all(rows):
    """Dedupe WITHOUT the dashboard's stage filter, so the status distributions below
    still show every stage (incl 'redacted'/trash) for diagnosis."""
    seen, out = set(), []
    for r in rows:
        if not isinstance(r, dict):
            continue
        k = _dedupe_key(r)
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out

START = sys.argv[1] if len(sys.argv) > 1 else "2024-10-01"
END   = sys.argv[2] if len(sys.argv) > 2 else "2025-10-01"
RUN_CALLS = "calls" in sys.argv[3:]

# ---- The filter the dashboard now uses (stage = sale). The column below shows it vs table.
ACTIVE_FIELD  = "stage"
ACTIVE_VALUES = {"sale"}

# Your known-accurate CRM carrier table (includes GTL).
EXPECTED = {
    "HUMANA": 17570, "UHC": 16898, "AETNA": 5981, "CIGNA": 1425, "ANTHEM": 1019,
    "WELLCARE": 966, "GTL": 897, "DEVOTED": 822, "MOLINA": 164, "OPTIMUM": 37,
    "ZING": 35, "CLOVER": 18, "CENTENE": 8,
}
EXPECTED_TOTAL = sum(EXPECTED.values())     # 45,840

STATUS_COLS = ["status_name", "status", "active", "status_id", "stage"]


def norm(c):
    return (str(c or "").strip().upper() or "—")


def pull_policies(c, start, end):
    """Direct policies pull including the status fields (canonical dual-date filter)."""
    s0, e1 = f"{start} 00:00:00", f"{end} 23:59:59"
    body = {
        "columns": ["policy_id", "lead_id", "carrier_name"] + STATUS_COLS,
        "limit": 200000,
        "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1,
    }
    return config.egress_get("policies", body, timeout=120)


def is_active(r):
    return str(r.get(ACTIVE_FIELD) or "").strip().lower() in ACTIVE_VALUES


def carrier_counts(rows, predicate=None):
    by = {}
    for r in rows:
        if predicate and not predicate(r):
            continue
        k = norm(r.get("carrier_name"))
        by[k] = by.get(k, 0) + 1
    return by


def main():
    if not config.have_creds():
        print("No credentials found. Run this on the machine where .env is configured.")
        return

    c = TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)
    print(f"\nRange: {START} .. {END}\n" + "=" * 74)

    rows = dedupe_all(pull_policies(c, START, END))
    print(f"policies pulled + deduped : {len(rows):,}   (your table total = {EXPECTED_TOTAL:,})\n")

    # ---- 1. Status distributions ------------------------------------------------------
    print("STATUS field distributions (value : count) — find the one whose 'active' ≈ table\n" + "-" * 74)
    for f in STATUS_COLS:
        dist = Counter((str(r.get(f)).strip().lower() if r.get(f) not in (None, "") else "(blank)") for r in rows)
        shown = dist.most_common(20)
        print(f"  {f}:")
        for val, n in shown:
            print(f"      {val:<22} {n:>8,}")
        if len(dist) > 20:
            print(f"      … (+{len(dist) - 20} more values)")
    print()

    # ---- 2. Per-carrier: ALL statuses vs ACTIVE-only vs TABLE --------------------------
    all_c = carrier_counts(rows)
    act_c = carrier_counts(rows, is_active)
    print(f"Per-carrier  (ACTIVE filter = {ACTIVE_FIELD} in {sorted(ACTIVE_VALUES)})\n" + "-" * 74)
    print(f"{'CARRIER':<12}{'ALL':>10}{'ACTIVE':>10}{'TABLE':>10}{'Δ act-tbl':>11}")
    print("-" * 74)
    carriers = sorted(set(all_c) | set(EXPECTED), key=lambda k: -EXPECTED.get(k, all_c.get(k, 0)))
    for k in carriers:
        exp = EXPECTED.get(k)
        a = act_c.get(k, 0)
        delta = "" if exp is None else f"{a - exp:+,}"
        flag = "   <- not in table" if exp is None and all_c.get(k) else ""
        print(f"{k:<12}{all_c.get(k, 0):>10,}{a:>10,}{(exp if exp is not None else 0):>10,}{delta:>11}{flag}")
    print("-" * 74)
    print(f"{'TOTAL':<12}{sum(all_c.values()):>10,}{sum(act_c.values()):>10,}{EXPECTED_TOTAL:>10,}"
          f"{sum(act_c.values()) - EXPECTED_TOTAL:>+11,}")

    # quick check of the boolean `active` flag as an alternative
    flag_active = sum(1 for r in rows if str(r.get("active") or "").strip() in ("1", "1.0", "true"))
    print(f"\nFor reference, rows with the boolean active flag = 1 : {flag_active:,}")
    print("(Whichever total lands on 45,840 incl GTL / 44,943 excl GTL is the filter we bake in.)\n")

    # ---- 3. Optional: report_cpa_agent calls check ------------------------------------
    if RUN_CALLS:
        print("report_cpa_agent (Billable Calls / Conversion) — year vs months\n" + "=" * 74)
        yr = c.agent_cpa(START, END).get("totals", {})
        print(f"  YEAR : sales={yr.get('sales')}  billable_calls={yr.get('billable_calls')}  conv={yr.get('conversion')}%")
        a = datetime.date.fromisoformat(START); b = datetime.date.fromisoformat(END)
        cur = a.replace(day=1)
        while cur <= b:
            nxt = (cur.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
            s, e = max(a, cur).isoformat(), min(b, nxt - datetime.timedelta(days=1)).isoformat()
            t = c.agent_cpa(s, e).get("totals", {})
            print(f"    {s} .. {e}   billable_calls={t.get('billable_calls')}")
            cur = nxt
        print()


if __name__ == "__main__":
    main()
