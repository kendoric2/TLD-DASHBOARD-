#!/usr/bin/env python3
"""
Why don't the sales numbers agree? (READ-ONLY)

There are several "sales" figures in play for a single day and they disagree:

  • invoice audit  — "Sale Made" among BILLABLE calls only
  • call log       — calls with status "Sale Made"
  • call log       — calls with the `sale` flag set
  • report_cpa_agent sales
  • policies sold  — what the dashboard counts (deduped, stage=sale)

Some of the gap is legitimate (a sale can come from a call you weren't billed for), but
some may not be. This lays every number side by side for one day and then does the real
test: join the "Sale Made" calls to actual policies via lead id, and show what doesn't
match in each direction.

Usage:
  python3 sandbox/probes/probe_sales_reconcile.py [DAY]      # default yesterday
"""
import os
import sys
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

CALL_LOG = "tldialer/tldialer_call_log"
DAY = sys.argv[1] if len(sys.argv) > 1 else (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
S0, E1 = f"{DAY} 00:00:00", f"{DAY} 23:59:59"


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


def truthy(v):
    return str(v).strip() in ("1", "1.0", "True", "true")


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nSALES RECONCILIATION   {DAY}\n" + "=" * 74)

    # ---- 1. the call log ------------------------------------------------------------
    calls = [r for r in rows_of(config.egress_get(CALL_LOG, {
        "columns": ["call_date", "call_direction", "status_name", "sale", "billable",
                    "cost", "agent_name", "vendor_description", "lead_vendor_lead_code"],
        "limit": 200000, "call_date": S0, "call_date_end": E1}, timeout=300))
        if isinstance(r, dict)]
    sale_status = [r for r in calls if "sale" in str(r.get("status_name") or "").lower()]
    sale_flag = [r for r in calls if truthy(r.get("sale"))]
    billable = [r for r in calls if truthy(r.get("billable"))]
    sale_and_billable = [r for r in sale_status if truthy(r.get("billable"))]

    print(f"\n1. CALL LOG ({len(calls):,} calls)")
    print(f"   status contains 'Sale'     : {len(sale_status):>6,}")
    print(f"   `sale` flag set            : {len(sale_flag):>6,}")
    print(f"   billable calls             : {len(billable):>6,}")
    print(f"   BOTH sale-status + billable: {len(sale_and_billable):>6,}   <- what the audit shows")

    print("\n   'Sale Made' calls by direction / billable:")
    c = Counter((str(r.get("call_direction")), truthy(r.get("billable"))) for r in sale_status)
    for (d, b), n in sorted(c.items(), key=lambda x: -x[1]):
        print(f"      {d or '(blank)':<10} billable={str(b):<6}{n:>6,}")
    if sale_status:
        print("\n   do the two call-log measures agree with each other?")
        both = sum(1 for r in sale_status if truthy(r.get("sale")))
        print(f"      of {len(sale_status):,} 'Sale Made' calls, {both:,} also have the sale flag")
        onlyflag = sum(1 for r in sale_flag
                       if "sale" not in str(r.get("status_name") or "").lower())
        print(f"      {onlyflag:,} calls have the flag but a different status: "
              f"{Counter(str(r.get('status_name')) for r in sale_flag if 'sale' not in str(r.get('status_name') or '').lower()).most_common(5)}")

    # ---- 2. the CPA report ----------------------------------------------------------
    resp = config.egress_get("report_cpa_agent", {
        "columns": ["sales", "costs_all", "calls_billable"], "limit": 2000,
        "date": S0, "date_end": E1, "date_sold": S0, "date_sold_end": E1}, timeout=180)
    tot = (resp.get("totals") or {}) if isinstance(resp, dict) else {}
    print(f"\n2. REPORT_CPA_AGENT")
    print(f"   sales {num(tot.get('sales')):>6,.0f}   billable calls {num(tot.get('calls_billable')):>6,.0f}"
          f"   spend ${num(tot.get('costs_all')):,.2f}")

    # ---- 3. policies ----------------------------------------------------------------
    pol = [r for r in rows_of(config.egress_get("policies", {
        "columns": ["policy_id", "lead_id", "carrier_name", "stage", "agent_name"],
        "limit": 200000, "date": S0, "date_end": E1,
        "date_sold": S0, "date_sold_end": E1}, timeout=180)) if isinstance(r, dict)]
    sale_stage = [r for r in pol if str(r.get("stage") or "").strip().lower() == "sale"]
    uniq = {str(r.get("policy_id")) for r in sale_stage}
    no_gtl = [r for r in sale_stage
              if str(r.get("carrier_name") or "").strip().upper() != "GTL"]
    print(f"\n3. POLICIES")
    print(f"   rows returned            : {len(pol):>6,}")
    print(f"   stage = sale             : {len(sale_stage):>6,}  ({len(uniq):,} distinct policy ids)")
    print(f"   stage = sale, GTL removed: {len(no_gtl):>6,}   <- the dashboard's Policies Sold")
    leads_with_policy = {str(r.get("lead_id")) for r in no_gtl if r.get("lead_id")}
    print(f"   distinct leads behind them: {len(leads_with_policy):,}"
          f"   (a lead can hold more than one policy)")

    # ---- 4. the real test: do 'Sale Made' calls map to policies? --------------------
    print(f"\n4. DO THE 'SALE MADE' CALLS MATCH ACTUAL POLICIES?\n" + "-" * 74)
    call_leads = {str(r.get("lead_vendor_lead_code")).strip()
                  for r in sale_status if str(r.get("lead_vendor_lead_code") or "").strip()}
    print(f"   'Sale Made' calls with a CRM lead id: {len(call_leads):,} of {len(sale_status):,}")
    matched = call_leads & leads_with_policy
    print(f"   ...that DO have a policy sold today : {len(matched):,}")
    print(f"   ...with NO policy today             : {len(call_leads - leads_with_policy):,}"
          f"   (sale logged on the call, policy dated another day?)")
    print(f"   policies whose lead had NO 'Sale Made' call: "
          f"{len(leads_with_policy - call_leads):,}   (sold without a call dispositioned as a sale)")

    print("\n" + "=" * 74)
    print("SUMMARY — the same day, five ways")
    print(f"   audit (sale + billable)   {len(sale_and_billable):>6,}")
    print(f"   call log 'Sale Made'      {len(sale_status):>6,}")
    print(f"   call log sale flag        {len(sale_flag):>6,}")
    print(f"   report_cpa_agent sales    {num(tot.get('sales')):>6,.0f}")
    print(f"   policies sold (dashboard) {len(no_gtl):>6,}")
    print("\nThe audit number SHOULD be lowest — it only counts sales on calls you were")
    print("billed for. The question is whether the rest of the gap is explained by")
    print("section 4, or whether something is being missed.\n")


if __name__ == "__main__":
    main()
