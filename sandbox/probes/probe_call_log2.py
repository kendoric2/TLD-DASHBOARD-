#!/usr/bin/env python3
"""
Call log, round 2 — correct date field, working filter tests, and invoice reconciliation.
(READ-ONLY)

Round 1 found the endpoint works (213 columns, 27 real call dispositions, ~70% answering
machines) but had two flaws of mine: it filtered on `modify_date` (when the record was last
touched) instead of `call_date` (when the call happened), and the filter section silently
skipped because of a hardcoded None.

This run answers what we actually need:

  1. call_date filtering + true volume
  2. Can we scope by vendor / agent / disposition, so a tile isn't pulling a million rows?
  3. THE BIG ONE: the log has `billable`, `cost` and `sale` per call. Do those reconcile
     with report_cpa_agent (9,814 billable calls / $392,560 for July 2026)? If they do,
     a vendor invoice becomes auditable call by call.

Every filter is checked with an impossible value that must return zero.

Usage:
  python3 sandbox/probes/probe_call_log2.py [DAYS]     # default 1 (yesterday)
"""
import os
import sys
import time
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

EP = "tldialer/tldialer_call_log"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 1
END = datetime.date.today() - datetime.timedelta(days=1)
START = END - datetime.timedelta(days=DAYS - 1)
S0, E1 = f"{START} 00:00:00", f"{END} 23:59:59"

COLS = ["call_date", "call_direction", "call_type", "status_name", "agent_name",
        "vendor_id", "vendor_description", "lead_id", "billable", "cost", "sale",
        "duration_call", "sec_talk"]


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
        return float(str(v).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def pull(label, extra=None, cols=None, quiet=False):
    body = {"columns": cols or COLS, "limit": 200000,
            "call_date": S0, "call_date_end": E1}
    if extra:
        body.update(extra)
    t0 = time.time()
    try:
        rows = rows_of(config.egress_get(EP, body, timeout=300))
    except Exception as e:
        if not quiet:
            print(f"   {label:<44} FAILED: {type(e).__name__}: {str(e)[:45]}")
        return None
    if not quiet:
        print(f"   {label:<44} {len(rows):>8,} rows ({int((time.time()-t0)*1000):,} ms)")
    return rows


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nCALL LOG ROUND 2   call_date {START} .. {END}\n" + "=" * 74)

    # ---- 1. correct date field ------------------------------------------------------
    print("\n1. Filtering on call_date (the time of the call)")
    base = pull("call_date window")
    if base is None:
        print("   -> call_date not usable; ask TLD which date field to filter on.")
        return
    bad = pull("call_date in 2099 (expect 0)",
               {"call_date": "2099-01-01 00:00:00", "call_date_end": "2099-12-31 23:59:59"})
    print(f"   -> call_date filter: {'HONORED' if bad is not None and not bad else 'NOT honored'}")
    if base:
        print(f"   -> ~{len(base)/max(DAYS,1):,.0f} calls/day, ~{len(base)/max(DAYS,1)*30:,.0f}/month")

    if not base:
        return
    first = next((r for r in base if isinstance(r, dict)), {})

    # ---- 2. can we scope it? --------------------------------------------------------
    print("\n2. Scoping filters (so a tile needn't pull the whole log)")
    for col in ("vendor_id", "agent_name", "status_name", "call_direction"):
        val = first.get(col)
        if val in (None, ""):
            vals = [r.get(col) for r in base if isinstance(r, dict) and r.get(col) not in (None, "")]
            val = vals[0] if vals else None
        if val is None:
            print(f"   {col:<44} no sample value, skipped")
            continue
        ok = pull(f"{col} = {str(val)[:22]}", {col: val})
        bogus = pull(f"{col} = 'zzzznope' (expect 0)", {col: "zzzznope"}, quiet=True)
        honored = bogus is not None and not bogus and ok is not None and 0 < len(ok) <= len(base)
        print(f"      -> {col}: {'HONORED' if honored else 'not honored / inconclusive'}")

    # ---- 3. invoice reconciliation --------------------------------------------------
    print("\n3. Does the call log reconcile with the billing report?")
    billable = [r for r in base if isinstance(r, dict)
                and str(r.get("billable")).strip() in ("1", "1.0", "True", "true")]
    cost_sum = sum(num(r.get("cost")) for r in base if isinstance(r, dict))
    sales = sum(1 for r in base if isinstance(r, dict)
                and str(r.get("sale")).strip() in ("1", "1.0", "True", "true"))
    filled_cost = sum(1 for r in base if isinstance(r, dict) and num(r.get("cost")) > 0)
    filled_bill = sum(1 for r in base if isinstance(r, dict)
                      and str(r.get("billable")).strip() not in ("", "None"))
    print(f"   calls in window        : {len(base):,}")
    print(f"   billable flag populated: {filled_bill:,}   marked billable: {len(billable):,}")
    print(f"   cost populated         : {filled_cost:,}   sum of cost: ${cost_sum:,.2f}")
    print(f"   marked as a sale       : {sales:,}")

    try:
        resp = config.egress_get("report_cpa_agent", {
            "columns": ["sales", "costs_all", "calls_billable"], "limit": 2000,
            "date": S0, "date_end": E1, "date_sold": S0, "date_sold_end": E1}, timeout=180)
        tot = (resp.get("totals") or {}) if isinstance(resp, dict) else {}
        r_calls, r_cost, r_sales = (num(tot.get("calls_billable")), num(tot.get("costs_all")),
                                    num(tot.get("sales")))
        print(f"\n   report_cpa_agent same window: billable calls {r_calls:,.0f}   "
              f"spend ${r_cost:,.2f}   sales {r_sales:,.0f}")
        if r_calls:
            d = abs(len(billable) - r_calls) / r_calls * 100
            print(f"   billable calls: log {len(billable):,} vs report {r_calls:,.0f}  ({d:.1f}% apart)")
            print("   -> RECONCILES: invoices can be audited call by call." if d < 2
                  else "   -> differs; the log's 'billable' is not the report's calls_billable.")
        if r_cost and cost_sum:
            d = abs(cost_sum - r_cost) / r_cost * 100
            print(f"   spend: log ${cost_sum:,.2f} vs report ${r_cost:,.2f}  ({d:.1f}% apart)")
    except Exception as e:
        print(f"   report_cpa_agent comparison failed: {str(e)[:70]}")

    # ---- 4. shape of the data -------------------------------------------------------
    print("\n4. What the calls look like")
    for col, title in (("status_name", "disposition"), ("call_direction", "direction"),
                       ("vendor_description", "vendor"), ("agent_name", "agent")):
        c = Counter(str(r.get(col) or "(blank)") for r in base if isinstance(r, dict))
        print(f"\n   {title} ({len(c)} distinct)")
        for k, v in c.most_common(8):
            print(f"      {k[:36]:<38}{v:>8,}  ({v/len(base)*100:4.1f}%)")

    print(f"\n{'=' * 74}\nPaste this back.\n")


if __name__ == "__main__":
    main()
