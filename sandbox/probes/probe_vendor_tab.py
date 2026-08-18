#!/usr/bin/env python3
"""
Discovery for the planned VENDORS tab (READ-ONLY).

Answers, in one run, everything we need before committing to a build:

  1. ENDPOINTS   — what's actually enabled on this API key, flagging call/dialer/dispo ones.
                   (Call dispositions live on the CALL record, not the lead. If no call
                   endpoint is enabled, dispo tracking is blocked until you enable one.)
  2. VENDORS     — the catalogue: id, name, price per lead, active flag. Decides how the
                   vendor picker gets populated and whether we can show pricing.
  3. COST        — does vendorperformance's per-vendor spend/sales RECONCILE with
                   report_cpa_agent's org-wide totals? If yes, per-vendor CPA is one fast
                   call; if no, it's a ~30s report per vendor. (Also decides the CPA
                   selector on the Blended CPA tile.)
  4. LEADS       — is vendor_id filtering on leads actually honored, and what do lead
                   statuses look like per vendor?
  5. DISPO       — for any call/dialer endpoint found, dump its columns looking for a
                   disposition field plus vendor + date fields to filter on.

Usage:
  python3 sandbox/probes/probe_vendor_tab.py [START] [END]   # defaults to last month
"""
import os
import re
import sys
import json
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

CALLISH = ("call", "dialer", "dispo", "disposition", "log", "vicidial", "agent_log", "closer")


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records", "endpoints", "vendor"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def clean(v):
    """vendorperformance wraps cell values in HTML links — strip the tags."""
    return re.sub(r"<[^>]+>", "", str(v if v is not None else "")).strip()


def head(n, t):
    print(f"\n{'=' * 74}\n{n}. {t}\n{'=' * 74}")


# ---------------------------------------------------------------- 1. endpoints
def section_endpoints():
    head(1, "ENDPOINTS ENABLED ON THIS KEY")
    try:
        resp = config.egress_get("endpoints", None, timeout=60)
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {str(e)[:120]}")
        return []
    if isinstance(resp, dict) and set(resp.keys()) <= {"error", "message", "status"}:
        print(f"  endpoint listing not available: {json.dumps(resp)[:200]}")
        print("  (we'll probe known call/dialer names directly instead)")
        return []
    rows = rows_of(resp)
    names = []
    for r in rows:
        if isinstance(r, str):
            names.append(r)
        elif isinstance(r, dict):
            for k in ("endpoint", "name", "path", "slug"):
                if r.get(k):
                    names.append(str(r[k]))
                    break
    if not names and isinstance(resp, dict):
        names = [str(k) for k in resp.keys()]
    names = sorted(set(names))
    print(f"  {len(names)} endpoint(s) enabled:\n")
    cands = []
    for n in names:
        mark = ""
        if any(c in n.lower() for c in CALLISH):
            mark = "   <-- CALL/DISPO CANDIDATE"
            cands.append(n)
        print(f"    {n}{mark}")
    if not cands:
        print("\n  !! No call/dialer endpoint enabled. Call DISPOSITIONS are not reachable")
        print("     until one is turned on in TLD (lead status is still available).")
    return cands


# ---------------------------------------------------------------- 2. vendors
def section_vendors():
    head(2, "VENDOR CATALOGUE")
    try:
        rows = rows_of(config.egress_get("vendors", {
            "columns": ["vendor_id", "name", "description", "price", "price_inbound",
                        "status_name", "date_created"], "limit": 500}, timeout=60))
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {str(e)[:120]}")
        return []
    print(f"  {len(rows)} vendor(s) returned")
    if rows and isinstance(rows[0], dict):
        print(f"  columns: {sorted(rows[0].keys())}\n")
        print(f"    {'ID':<9}{'NAME':<26}{'PRICE':>9}{'INBOUND':>9}  STATUS")
        active = 0
        for r in sorted(rows, key=lambda x: str(x.get("name") or "")):
            st = str(r.get("status_name") or "")
            if st.lower() == "active":
                active += 1
            print(f"    {str(r.get('vendor_id') or ''):<9}"
                  f"{str(r.get('name') or '')[:25]:<26}"
                  f"{str(r.get('price') or ''):>9}{str(r.get('price_inbound') or ''):>9}  {st}")
        print(f"\n  {active} of {len(rows)} are active "
              f"(-> the picker should list only these, and only ones with activity)")
    return rows


# ---------------------------------------------------------------- 3. cost reconcile
def section_cost():
    head(3, f"PER-VENDOR COST — does vendorperformance reconcile?  ({START}..{END})")
    t0 = time.time()
    try:
        vp = rows_of(config.egress_get("vendorperformance", dict(SALE, limit=200), timeout=120))
    except Exception as e:
        print(f"  vendorperformance FAILED: {type(e).__name__}: {str(e)[:110]}")
        vp = []
    vp_ms = int((time.time() - t0) * 1000)

    print(f"  vendorperformance: {len(vp)} rows in {vp_ms:,} ms")
    tot_spend = tot_sales = 0.0
    if vp:
        print(f"\n    {'VENDOR':<24}{'SPEND':>12}{'SALES':>9}{'LEADS':>9}{'CPA':>10}")
        for r in vp:
            if not isinstance(r, dict):
                continue
            name = clean(r.get("Vendor") or r.get("vendor"))
            spend, sales = num(clean(r.get("Spend"))), num(clean(r.get("Sales")))
            leads = num(clean(r.get("Leads")))
            tot_spend += spend
            tot_sales += sales
            cpa = f"${spend / sales:,.2f}" if sales else "—"
            if spend or sales:
                print(f"    {name[:23]:<24}{spend:>12,.2f}{sales:>9,.0f}{leads:>9,.0f}{cpa:>10}")
        print(f"    {'TOTAL':<24}{tot_spend:>12,.2f}{tot_sales:>9,.0f}")

    def report(label, extra=None):
        t0 = time.time()
        try:
            resp = config.egress_get("report_cpa_agent", dict(
                SALE, columns=["sales", "costs_all", "calls_billable"],
                limit=2000, **(extra or {})), timeout=120)
        except Exception as e:
            print(f"  {label:<34} FAILED: {type(e).__name__}: {str(e)[:70]}")
            return None, None, 0
        ms = int((time.time() - t0) * 1000)
        totals = (resp.get("totals") or {}) if isinstance(resp, dict) else {}
        sp, sa = num(totals.get("costs_all")), num(totals.get("sales"))
        print(f"  {label:<34} spend ${sp:>12,.2f}   sales {sa:>7,.0f}   ({ms:,} ms)")
        return sp, sa, ms

    print()
    r_spend, r_sales, rep_ms = report("report_cpa_agent, ORG-WIDE")

    # Decisive: does ONE vendor agree between the two sources? Comparing totals alone is
    # ambiguous — a per-vendor match tells us whether vendorperformance's Spend is the
    # same quantity as the report's costs_all.
    top = None
    for r in vp:
        if isinstance(r, dict) and num(clean(r.get("Spend"))) > 0:
            top = (clean(r.get("Vendor")), clean(r.get("ID")), num(clean(r.get("Spend"))),
                   num(clean(r.get("Sales"))))
            break
    if top and top[1]:
        name, vid, vp_spend, vp_sales = top
        print(f"\n  Cross-check on the biggest spender ({name}, id {vid}):")
        print(f"  {'vendorperformance says':<34} spend ${vp_spend:>12,.2f}   sales {vp_sales:>7,.0f}")
        v_spend, v_sales, _ = report("report_cpa_agent, vendor-scoped", {"vendor_id": vid})
        if v_spend is not None and vp_spend:
            d = abs(v_spend - vp_spend) / vp_spend * 100
            print(f"  -> spend differs by {d:.1f}%")
            if d < 2:
                print("     SAME quantity. Per-vendor CPA can come from ONE fast")
                print("     vendorperformance call — vendor switching is instant.")
            else:
                print("     DIFFERENT quantities — vendorperformance 'Spend' is not the")
                print(f"     report's costs_all. Use a vendor-scoped report (~{rep_ms // 1000}s),")
                print("     fetched only when a vendor is picked, so tiles stay consistent.")

    if r_spend:
        print(f"\n  vendorperformance total ${tot_spend:,.2f} vs org-wide ${r_spend:,.2f} "
              f"({abs(tot_spend - r_spend) / r_spend * 100:.1f}% apart)")
        print(f"  sales {tot_sales:,.0f} vs {r_sales:,.0f}")


# ---------------------------------------------------------------- 4. leads by vendor
def section_leads(vendors):
    head(4, "LEADS BY VENDOR — is vendor_id honored, and what are the statuses?")
    vid = None
    for r in vendors:
        if isinstance(r, dict) and (r.get("vendor_id") or r.get("id")):
            vid = r.get("vendor_id") or r.get("id")
            break
    vid = vid or config.FALCON_VENDOR_ID
    lead_dates = {"date_created": S0, "date_created_end": E1}

    def pull(label, extra):
        t0 = time.time()
        try:
            rows = rows_of(config.egress_get("leads", dict(
                {"columns": ["lead_id", "vendor_id", "vendor_name", "status_name",
                             "billable", "converted", "policies_sold"], "limit": 200000},
                **lead_dates, **extra), timeout=180))
        except Exception as e:
            print(f"    {label:<34} FAILED: {str(e)[:60]}")
            return None
        print(f"    {label:<34} {len(rows):>8,} rows ({int((time.time()-t0)*1000):,} ms)")
        return rows

    all_rows = pull("all vendors", {})
    one = pull(f"vendor_id = {vid}", {"vendor_id": vid})
    bogus = pull("vendor_id = 99999999 (expect 0)", {"vendor_id": 99999999})

    honored = (bogus is not None and len(bogus) == 0
               and one is not None and all_rows is not None and len(one) < len(all_rows))
    print(f"\n  -> vendor_id filter on leads: {'HONORED' if honored else 'NOT honored / inconclusive'}")

    src = one if (honored and one) else (all_rows or [])
    if src:
        st = Counter(str(r.get("status_name") or "(blank)") for r in src if isinstance(r, dict))
        print(f"\n  lead STATUS distribution for vendor {vid} ({len(src):,} leads):")
        for k, v in st.most_common(15):
            print(f"      {k:<28}{v:>8,}")
        billable = sum(1 for r in src if isinstance(r, dict) and str(r.get("billable")) in ("1", "1.0", "True"))
        sold = sum(1 for r in src if isinstance(r, dict) and num(r.get("policies_sold")) >= 1)
        print(f"\n      billable: {billable:,}   produced a policy: {sold:,}")


# ---------------------------------------------------------------- 5. dispo hunt
def section_dispo(candidates):
    head(5, "CALL DISPOSITIONS — what's in the call/dialer endpoints?")
    if not candidates:
        print("  No call/dialer endpoint enabled, so there's nothing to inspect.")
        print("  To build dispo tracking you'd enable a call-log endpoint in TLD first.")
        return
    for ep in candidates[:4]:
        print(f"\n  --- {ep}")
        for body in ({"limit": 1}, dict(SALE, limit=1), {"limit": 1, "date": S0, "date_end": E1}):
            try:
                rows = rows_of(config.egress_get(ep, body, timeout=90))
            except Exception as e:
                print(f"      body={json.dumps(body)[:50]} -> FAILED {str(e)[:60]}")
                continue
            if rows and isinstance(rows[0], dict):
                cols = sorted(rows[0].keys())
                print(f"      {len(cols)} columns")
                interesting = [c for c in cols if any(w in c.lower() for w in
                               ("dispo", "status", "vendor", "date", "agent", "lead", "duration", "talk"))]
                print(f"      relevant: {interesting[:24]}")
                for c in cols:
                    if "dispo" in c.lower():
                        print(f"        {c} = {rows[0].get(c)!r}")
                break
            print(f"      body={json.dumps(body)[:50]} -> 0 rows")


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nVENDORS TAB — DISCOVERY PROBE     range {START} .. {END}")
    cands = section_endpoints()
    vendors = section_vendors()
    section_cost()
    section_leads(vendors)
    section_dispo(cands)
    print(f"\n{'=' * 74}\nDone — paste this whole output back.\n")


if __name__ == "__main__":
    main()
