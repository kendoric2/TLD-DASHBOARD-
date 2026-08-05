#!/usr/bin/env python3
"""
Diagnose why Billable Calls / Total Spend / Blended CPA read 0 for a range (READ-ONLY).

Those three come from the ORG-WIDE report_cpa_agent call, while Conversion comes from a
separate FALCON-SCOPED call. If conversion works but the other three are 0, the org-wide
call is probably returning no usable rows. This prints the RAW response for both so we can
see exactly what TLD sends back.

It bypasses every cache (calls the endpoint directly), so it always shows live truth.

Usage:
  python3 sandbox/probes/probe_cpa_zero.py [START] [END]
  # defaults to 2026-07-01 .. 2026-07-31
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

START = sys.argv[1] if len(sys.argv) > 1 else "2026-07-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2026-07-31"
S0, E1 = f"{START} 00:00:00", f"{END} 23:59:59"
DATES = {"date": S0, "date_end": E1, "date_sold": S0, "date_sold_end": E1}


def rows_and_totals(resp):
    rows, totals = [], {}
    if isinstance(resp, list):
        rows = resp
    elif isinstance(resp, dict):
        for k in ("results", "data", "rows", "report", "records", "agents"):
            if isinstance(resp.get(k), list):
                rows = resp[k]
                break
        if isinstance(resp.get("totals"), dict):
            totals = resp["totals"]
    return rows, totals


def report(title, body):
    print(f"\n{title}\n" + "=" * 68)
    print("request body:", json.dumps(body))
    try:
        resp = config.egress_get("report_cpa_agent", body, timeout=120)
    except Exception as e:
        print(f"  CALL FAILED: {type(e).__name__}: {e}")
        return
    print("response type:", type(resp).__name__,
          "| top-level keys:", list(resp.keys())[:12] if isinstance(resp, dict) else "(list)")
    rows, totals = rows_and_totals(resp)
    print(f"rows parsed: {len(rows)}")
    if rows:
        print("first row:", json.dumps(rows[0])[:400])
        s = sum(float(r.get("sales") or 0) for r in rows if isinstance(r, dict))
        c = sum(float(r.get("costs_all") or 0) for r in rows if isinstance(r, dict))
        cb = sum(float(r.get("calls_billable") or 0) for r in rows if isinstance(r, dict))
        print(f"summed rows -> sales={s:,.0f}  costs_all={c:,.2f}  calls_billable={cb:,.0f}")
    else:
        print("  !! no rows — this is what makes the tiles show 0")
        print("  raw response (first 600 chars):", json.dumps(resp)[:600] if resp else repr(resp))
    print("totals row:", json.dumps(totals) if totals else "(none)")


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nreport_cpa_agent diagnosis  {START} .. {END}")

    # 1. Exactly what the dashboard asks for org-wide (the suspect call)
    report("1. ORG-WIDE (what powers Billable Calls / Total Spend / Blended CPA)", {
        "columns": ["agent", "agent_id", "sales", "costs_all",
                    "cpa_cost_calls_all_by_sales", "calls_billable"],
        "limit": 1000, **DATES})

    # 2. Falcon-scoped (what powers Conversion — this one works)
    report("2. FALCON-SCOPED (what powers Conversion)", {
        "columns": ["sales", "calls_billable"],
        "vendor_id": config.FALCON_VENDOR_ID, "limit": 2000, **DATES})

    # 3. Org-wide with no column list, in case the column list is the problem
    report("3. ORG-WIDE, no explicit columns (control test)", {"limit": 1000, **DATES})

    # 4. Org-wide with the Falcon column set, to isolate columns vs vendor filter
    report("4. ORG-WIDE with Falcon's column set (isolates columns vs vendor filter)", {
        "columns": ["sales", "calls_billable"], "limit": 2000, **DATES})

    print("\nRead it like this:")
    print("  • If #1 has 0 rows but #2 has rows  -> the report needs a vendor filter (or our")
    print("    column list breaks it); compare #3 and #4 to see which.")
    print("  • If #1 HAS rows with real numbers  -> the live data is fine and the dashboard")
    print("    served a stale cached copy; clearing the cache fixes it.\n")


if __name__ == "__main__":
    main()
