#!/usr/bin/env python3
"""
Vendor tab — round 2, settling the three things round 1 left open (READ-ONLY).

  A. Does report_cpa_agent's `costs_all` actually respect vendor_id?
     Round 1 scoped it to FALCON and got spend IDENTICAL to org-wide ($392,560), while
     sales DID change. Either FALCON is ~100% of spend (innocent), or the filter ignores
     costs (fatal for per-vendor CPA). Scoping to INBOUND — 230 sales, $0 spend per
     vendorperformance — tells us which: if spend is still $392,560, it's broken.

  B. Is vendor_id honored on `leads`? Round 1 tested a vendor with no volume, so both the
     real and the bogus id returned 0 rows and the result was a false positive.
     Re-test with FALCON, which definitely has leads.

  C. What do the lead statuses look like PER VENDOR? Round 1 accidentally showed the
     all-vendor mix. Lead status may be the usable stand-in for dispositions, since no
     call endpoint is reachable.

Usage:
  python3 sandbox/probes/probe_vendor_tab2.py [START] [END]   # defaults to last month
"""
import os
import re
import sys
import time
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

TODAY = datetime.date.today()
if len(sys.argv) > 2:
    START, END = sys.argv[1], sys.argv[2]
else:
    first = TODAY.replace(day=1)
    last_end = first - datetime.timedelta(days=1)
    START, END = last_end.replace(day=1).isoformat(), last_end.isoformat()
S0, E1 = f"{START} 00:00:00", f"{END} 23:59:59"
SALE = {"date": S0, "date_end": E1, "date_sold": S0, "date_sold_end": E1}

FALCON, INBOUND, GENERAL = 14646, 12018, 12017


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records", "vendor"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def num(v):
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v)) or 0)
    except (TypeError, ValueError):
        return 0.0


def report(label, vendor_id=None):
    body = dict(SALE, columns=["sales", "costs_all", "calls_billable"], limit=2000)
    if vendor_id:
        body["vendor_id"] = vendor_id
    t0 = time.time()
    try:
        resp = config.egress_get("report_cpa_agent", body, timeout=180)
    except Exception as e:
        print(f"    {label:<30} FAILED: {type(e).__name__}: {str(e)[:60]}")
        return None
    tot = (resp.get("totals") or {}) if isinstance(resp, dict) else {}
    sp, sa, cb = num(tot.get("costs_all")), num(tot.get("sales")), num(tot.get("calls_billable"))
    print(f"    {label:<30} spend ${sp:>11,.2f}   sales {sa:>6,.0f}   calls {cb:>7,.0f}   "
          f"({int((time.time()-t0)*1000):,} ms)")
    return {"spend": sp, "sales": sa, "calls": cb}


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nVENDOR TAB — ROUND 2     {START} .. {END}\n" + "=" * 72)

    # ---- A. is costs_all vendor-aware? ---------------------------------------------
    print("\nA. Does report_cpa_agent's costs_all respect vendor_id?\n" + "-" * 72)
    org = report("ORG-WIDE (no vendor)")
    fal = report(f"vendor {FALCON} (FALCON)", FALCON)
    inb = report(f"vendor {INBOUND} (INBOUND)", INBOUND)
    gen = report(f"vendor {GENERAL} (GENERAL)", GENERAL)

    if org and inb:
        same_spend = abs(inb["spend"] - org["spend"]) < 1
        diff_sales = abs(inb["sales"] - org["sales"]) > 1
        print()
        if same_spend and diff_sales:
            print("  -> BROKEN: INBOUND returns org-wide spend but its own sales.")
            print("     costs_all is NOT vendor-filterable, so per-vendor CPA cannot come")
            print("     from this report. vendorperformance is the only per-vendor spend.")
        elif not same_spend:
            print("  -> WORKS: spend changes per vendor, so per-vendor CPA is real.")
            print("     (FALCON matching org-wide simply means it's ~all of the spend.)")
        else:
            print("  -> inconclusive; compare the rows above by hand.")

    # ---- B. vendor_id on leads, tested with a vendor that HAS volume ----------------
    print("\nB. Is vendor_id honored on `leads`?  (re-test with FALCON)\n" + "-" * 72)
    lead_cols = ["lead_id", "vendor_id", "vendor_name", "status_name", "billable",
                 "converted", "policies_sold", "sep"]
    dates = {"date_created": S0, "date_created_end": E1}

    def leads(label, extra):
        t0 = time.time()
        try:
            rows = rows_of(config.egress_get("leads", dict(
                {"columns": lead_cols, "limit": 200000}, **dates, **extra), timeout=240))
        except Exception as e:
            print(f"    {label:<34} FAILED: {str(e)[:60]}")
            return None
        print(f"    {label:<34} {len(rows):>8,} rows ({int((time.time()-t0)*1000):,} ms)")
        return rows

    all_rows = leads("all vendors", {})
    fal_rows = leads(f"vendor_id = {FALCON} (FALCON)", {"vendor_id": FALCON})
    inb_rows = leads(f"vendor_id = {INBOUND} (INBOUND)", {"vendor_id": INBOUND})
    bogus = leads("vendor_id = 99999999 (expect 0)", {"vendor_id": 99999999})

    honored = (bogus is not None and len(bogus) == 0
               and fal_rows and all_rows and 0 < len(fal_rows) < len(all_rows))
    print(f"\n  -> vendor_id on leads: {'HONORED' if honored else 'NOT honored / inconclusive'}")
    if fal_rows:
        seen = Counter(str(r.get("vendor_name") or "?") for r in fal_rows if isinstance(r, dict))
        print(f"     vendor_name values returned: {dict(list(seen.items())[:4])}")

    # ---- C. per-vendor status mix (the dispo stand-in) ------------------------------
    print("\nC. Lead status mix PER VENDOR (stand-in for dispositions)\n" + "-" * 72)
    for label, rows in (("FALCON", fal_rows), ("INBOUND", inb_rows), ("ALL VENDORS", all_rows)):
        if not rows:
            continue
        st = Counter(str(r.get("status_name") or "(blank)") for r in rows if isinstance(r, dict))
        billable = sum(1 for r in rows if isinstance(r, dict)
                       and str(r.get("billable")) in ("1", "1.0", "True"))
        sold = sum(1 for r in rows if isinstance(r, dict) and num(r.get("policies_sold")) >= 1)
        withsep = sum(1 for r in rows if isinstance(r, dict) and str(r.get("sep") or "").strip())
        print(f"\n  {label}: {len(rows):,} leads   billable {billable:,}   "
              f"sold {sold:,}   with SEP {withsep:,}")
        for k, v in st.most_common(12):
            print(f"      {k:<28}{v:>8,}  ({v / len(rows) * 100:4.1f}%)")

    print("\n" + "=" * 72 + "\nDone — paste this back.\n")


if __name__ == "__main__":
    main()
