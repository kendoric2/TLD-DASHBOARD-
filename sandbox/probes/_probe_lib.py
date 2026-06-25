"""
Shared helpers for the egress probes — read-only, HUMAN-READABLE output.

Exposes: hr() header, fmt() null-friendly value, cols_of(), show_columns(),
as_rows() (normalize ANY response -> rows + totals), show_rows() (aligned
field: value, never a raw dump), pull() (fetch a sample), and survey().
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t

JOIN_KEYS = ["lead_id", "linked_lead_id", "policy_id", "agent_id", "fronter_id",
             "owner_id", "assigned_id", "vendor_id", "user", "user_id", "carrier_id"]
EMPTY = (None, "", "0", "0000-00-00", "0000-00-00 00:00:00")


def hr(title):
    bar = "=" * 64
    print(f"\n{bar}\n{title}\n{bar}")


def fmt(v):
    return "(null)" if v in EMPTY else v


def cols_of(ep):
    c = config.egress_get(f"{ep}/docs/columns")
    if isinstance(c, list) and c and isinstance(c[0], dict):
        return list(c[0].keys())
    if isinstance(c, list):
        return [x for x in c if isinstance(x, str)]
    return []


def show_columns(cols):
    jk = [k for k in JOIN_KEYS if k in cols]
    print(f"columns: {len(cols)}     join keys: {', '.join(jk) or '(none)'}")
    if cols:
        more = f"   (+{len(cols) - 24} more)" if len(cols) > 24 else ""
        print(f"  first cols: {', '.join(map(str, cols[:24]))}{more}")


def as_rows(resp):
    """Normalize any egress/report response to (rows_list, totals_dict)."""
    if isinstance(resp, list):
        return resp, None
    if isinstance(resp, dict):
        totals = resp.get("totals") if isinstance(resp.get("totals"), dict) else None
        for k in ("results", "data", "rows", "report", "records", "agents"):
            if isinstance(resp.get(k), list):
                return resp[k], totals
        return [], totals
    return [], None


def _kv_block(label, row, fields, width):
    print(f"  -- {label} --")
    keys = fields if fields else list(row.keys())
    for k in keys:
        if not fields or k in row:
            print(f"    {str(k).ljust(width)}   {fmt(row.get(k))}")


def show_rows(resp, limit=3, fields=None):
    if isinstance(resp, str):
        print("  ", resp[:200])
        return
    rows, totals = as_rows(resp)
    if not rows and not totals:
        print("  (no rows returned)")
        return
    allkeys = fields or (list(rows[0].keys()) if rows else list((totals or {}).keys()))
    width = max((len(str(k)) for k in allkeys), default=0)
    for i, r in enumerate(rows[:limit]):
        _kv_block(f"row {i + 1} of {len(rows)}", r, fields, width)
    if totals:
        _kv_block("totals", totals, fields, width)


def pull(ep, n=5, cols=None, timeout=None):
    body = {"limit": n}
    if cols:
        body["columns"] = cols
    return config.egress_get(ep, body, timeout=timeout or config.TIMEOUT)


def survey(endpoint, sample_cols=None, date_field=None, count_col=None, report_dates=False, sample=3):
    hr(f"/api/egress/{endpoint}")
    show_columns(cols_of(endpoint))
    print("\nsample:")
    show_rows(pull(endpoint, sample, sample_cols), limit=sample)

    if count_col and date_field:
        print("\ndate filter (record count):")
        for rk in ("today", "this_month"):
            s, e = t.date_range_for(rk)
            su, eu = s + " 00:00:00", e + " 23:59:59"
            res = config.egress_get(endpoint, {
                "aggregates": True, "aggregate": True, "columns": [count_col],
                date_field: su, date_field + "_end": eu, "start_date": su, "end_date": eu})
            rows, _ = as_rows(res)
            print(f"    {rk.ljust(12)} {t._first_num(rows) if rows else res}")
        print("    (today < this_month  =>  date filtering works)")
    elif report_dates:
        print("\ndate test (rows: today vs this_month):")
        for rk in ("today", "this_month"):
            s, e = t.date_range_for(rk)
            res = config.egress_get(endpoint, {"start_date": s + " 00:00:00", "end_date": e + " 23:59:59"})
            rows, _ = as_rows(res)
            print(f"    {rk.ljust(12)} rows={len(rows)}")

    print("\nDone. Paste this back.")
