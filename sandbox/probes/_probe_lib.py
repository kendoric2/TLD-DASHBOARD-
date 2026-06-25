"""
Shared helper for the per-endpoint egress probes (read-only).

survey() prints, for one endpoint:
  - the full column list (names only — safe),
  - which common join keys it carries (lead_id, policy_id, agent_id, vendor_id, ...),
  - a PII-safe sample (only the non-sensitive columns we pass in),
  - a date-filter check (does a date range actually change the numbers?).

Used by probe_policies.py, probe_leads.py, probe_vendors.py, probe_users.py,
probe_vendorperformance.py — so each of those stays ~3 lines.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import json
import config
import tldcrm_client as t

JOIN_KEYS = ["lead_id", "linked_lead_id", "policy_id", "agent_id", "fronter_id",
             "owner_id", "assigned_id", "vendor_id", "user", "user_id", "carrier_id"]


def survey(endpoint, sample_cols=None, date_field=None, count_col=None, report_dates=False, sample=3):
    print(f"################  /api/egress/{endpoint}  ################\n")

    cols = config.egress_get(f"{endpoint}/docs/columns")
    cols = cols if isinstance(cols, list) else []
    print(f"=== columns ({len(cols)}) ===")
    print(", ".join(str(c) for c in cols) if cols else "(none / non-list response)")

    present = [k for k in JOIN_KEYS if k in cols]
    print(f"\n=== join keys present ===\n{present or '(none of the usual ids)'}")

    body = {"limit": sample}
    if sample_cols:
        body["columns"] = sample_cols
    rows = config.egress_get(endpoint, body)
    print(f"\n=== sample ({'safe columns' if sample_cols else 'default columns'}) ===")
    if isinstance(rows, list):
        print(f"{len(rows)} rows")
        for r in rows[:sample]:
            print(json.dumps(r)[:700])
    else:
        print(rows)

    if count_col and date_field:
        print(f"\n=== date filter (count via {count_col}, today vs this_month) ===")
        for rk in ("today", "this_month"):
            s, e = t.date_range_for(rk)
            su, eu = t._us(s), t._us(e)
            res = config.egress_get(endpoint, {
                "aggregates": True, "aggregate": True, "columns": [count_col],
                date_field: su, date_field + "_end": eu, "start_date": su, "end_date": eu})
            print(f"  {rk:12} count={t._first_num(res) if isinstance(res, list) else res}")
        print("  (today < this_month  =>  date filtering works on this endpoint)")
    elif report_dates:
        print("\n=== date test (rows today vs this_month via start_date/end_date) ===")
        for rk in ("today", "this_month"):
            s, e = t.date_range_for(rk)
            res = config.egress_get(endpoint, {"start_date": t._us(s), "end_date": t._us(e)})
            print(f"  {rk:12} rows={len(res) if isinstance(res, list) else res}")
        print("  (today != this_month  =>  it honors a date range)")

    print("\nDone. Paste this back.\n")
