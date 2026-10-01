#!/usr/bin/env python3
"""
Can we match DialedIN fronter transfers to what happened in TLD? (READ-ONLY)

Takes the DialedIN "CampaignLeads" CSV export (one row per transferred lead) and checks:
  1. LEADS     — does each phone exist as a TLD lead? which vendor did it land under?
                 was it a brand-new lead or an existing one (TLD dedupes by phone)?
  2. CALL LOG  — is there an inbound call from that phone near the transfer time?
                 which TLD line (DID) / vendor did it come in on, and which agent took it?
  3. POLICIES  — did that lead turn into a sale? (that's what fronters are paid on)

Prints counts and phone LAST-4 only. The CSV holds PHI (MBI, DOB, Medicaid #) — nothing
from it is written to disk, cache or logs by this script.

Usage:
  python3 sandbox/probes/probe_transfer_match.py ~/Downloads/CampaignLeads_XXXX.csv
"""
import csv
import os
import re
import sys
import time
import datetime as dt
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config  # noqa: E402
import tldcrm_client as t  # noqa: E402

CALL_LOG = t.CALL_LOG
CHUNK = 100
MATCH_WINDOW = dt.timedelta(hours=3)   # call log hit must be within this of the DialedIN CallDate


def phone10(s):
    d = re.sub(r"\D", "", str(s or ""))
    return d[-10:] if len(d) >= 10 else ""


def parse_dt(s):
    s = str(s or "").strip()
    for f in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
              "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def rows_of(resp):
    if isinstance(resp, list):
        return [r for r in resp if isinstance(r, dict)]
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return [r for r in resp[k] if isinstance(r, dict)]
    return []


def hr(title):
    print("\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78)


def pct(a, b):
    return f"{a / b * 100:5.1f}%" if b else "   -  "


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    path = os.path.expanduser(sys.argv[1])
    src = list(csv.DictReader(open(path, newline="", encoding="utf-8-sig")))
    xfers = []
    for r in src:
        p = phone10(r.get("PrimaryPhone"))
        if not p:
            continue
        xfers.append({"phone": p, "rep": (r.get("Rep") or "").strip(),
                      "campaign": (r.get("Campaign") or "").strip(),
                      "when": parse_dt(r.get("CallDate")),
                      "dialedin_tld_id": (r.get("TLD Lead ID") or "").strip()})
    whens = [x["when"] for x in xfers if x["when"]]
    d0, d1 = min(whens).date(), max(whens).date()
    phones = sorted({x["phone"] for x in xfers})
    hr(f"DialedIN export: {len(xfers)} transfers, {len(phones)} distinct phones, {d0} .. {d1}")
    for c, n in Counter(x["campaign"] for x in xfers).most_common():
        print(f"   {c:<20} {n:>5}")

    # ------------------------------------------------------------------ 1. LEADS
    hr("1. LEADS — look up every phone in TLD (batched, no date filter)")
    names = {}
    try:
        cl = t.TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)
        names = {v["vendor_id"]: v["name"] for v in cl.vendor_catalogue()}
    except Exception as e:
        print("   vendor catalogue unavailable:", e)
        cl = t.TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)

    leads_by_phone = defaultdict(list)
    t0 = time.time()
    for i in range(0, len(phones), CHUNK):
        batch = phones[i:i + CHUNK]
        resp = config.egress_get("leads", {
            "columns": ["lead_id", "phone", "date_created", "vendor_id", "status_name",
                        "policies_sold"],
            "phone": batch, "limit": len(batch) * 50}, timeout=120)
        for r in rows_of(resp):
            p = phone10(r.get("phone"))
            if p:
                leads_by_phone[p].append(r)
    print(f"   {sum(len(v) for v in leads_by_phone.values()):,} lead rows in "
          f"{time.time() - t0:.1f}s")

    found = [p for p in phones if leads_by_phone.get(p)]
    print(f"   phones found as a TLD lead : {len(found):>4} / {len(phones)}  {pct(len(found), len(phones))}")
    multi = sum(1 for p in found if len(leads_by_phone[p]) > 1)
    print(f"   phones with >1 TLD lead     : {multi:>4}")

    window_start = dt.datetime.combine(d0, dt.time.min) - dt.timedelta(days=1)
    new_vs_old = Counter()
    vendor_newest = Counter()
    for p in found:
        rows = sorted(leads_by_phone[p], key=lambda r: str(r.get("date_created") or ""))
        newest = rows[-1]
        created = parse_dt(newest.get("date_created"))
        new_vs_old["created during transfer window" if created and created >= window_start
                   else "already existed before"] += 1
        vid = str(newest.get("vendor_id") or "")
        vendor_newest[names.get(vid) or f"vendor {vid}" if vid else "(none)"] += 1
    print("\n   newest matching lead was ...")
    for k, n in new_vs_old.most_common():
        print(f"      {k:<34} {n:>5}")
    print("\n   vendor of the newest matching lead (where the transfer 'landed')")
    for k, n in vendor_newest.most_common(12):
        print(f"      {k:<34} {n:>5}")

    # does DialedIN's 'TLD Lead ID' agree with what TLD has for the phone?
    with_id = [x for x in xfers if x["dialedin_tld_id"]]
    agree = sum(1 for x in with_id
                if x["dialedin_tld_id"] in {str(r.get("lead_id")) for r in leads_by_phone.get(x["phone"], [])})
    print(f"\n   DialedIN rows carrying a 'TLD Lead ID': {len(with_id)} — "
          f"that id is among TLD's leads for the phone: {agree} {pct(agree, len(with_id))}")

    # ------------------------------------------------------------------ 2. CALL LOG
    hr(f"2. CALL LOG — inbound calls {d0} .. {d1}")
    cols = ["call_date", "call_direction", "phone_number", "call_from", "vendor_id",
            "vendor_description", "did_description", "agent_name", "status_name",
            "lead_vendor_lead_code", "billable"]
    base = {"columns": cols, "call_direction": "INBOUND",
            "call_date": f"{d0} 00:00:00", "call_date_end": f"{d1} 23:59:59"}
    # is a phone_number list filter honoured? (impossible number must return 0)
    t0 = time.time()
    test = rows_of(config.egress_get(CALL_LOG, dict(base, phone_number=["0000000000"], limit=50), timeout=120))
    honoured = len(test) == 0
    print(f"   phone_number filter honoured: {'YES' if honoured else 'NO'} "
          f"({len(test)} rows for a fake number, {int((time.time() - t0) * 1000)} ms)")
    calls = []
    t0 = time.time()
    if honoured:
        for i in range(0, len(phones), CHUNK):
            calls += rows_of(config.egress_get(CALL_LOG, dict(base, phone_number=phones[i:i + CHUNK],
                                                               limit=20000), timeout=300))
    else:
        calls = rows_of(config.egress_get(CALL_LOG, dict(base, limit=200000), timeout=300))
    print(f"   {len(calls):,} inbound call rows in {time.time() - t0:.1f}s")

    calls_by_phone = defaultdict(list)
    for c in calls:
        for k in ("phone_number", "call_from"):
            p = phone10(c.get(k))
            if p in phones:
                calls_by_phone[p].append(c)
                break

    matched, gaps = [], []
    for x in xfers:
        best = None
        for c in calls_by_phone.get(x["phone"], []):
            cd = parse_dt(c.get("call_date"))
            if not (cd and x["when"]):
                continue
            gap = abs(cd - x["when"])
            if gap <= MATCH_WINDOW and (best is None or gap < best[0]):
                best = (gap, c)
        if best:
            matched.append((x, best[1]))
            gaps.append(best[0].total_seconds() / 60)
    print(f"   transfers with an inbound call from the same phone within "
          f"{int(MATCH_WINDOW.total_seconds() // 3600)}h: {len(matched)} / {len(xfers)} {pct(len(matched), len(xfers))}")
    if gaps:
        gaps.sort()
        print(f"   time gap DialedIN CallDate -> TLD call (minutes): "
              f"median {gaps[len(gaps) // 2]:.1f}, 90th pct {gaps[int(len(gaps) * .9)]:.1f}")
    # phones with NO matching inbound call — did TLD see someone else's number at that time?
    print("\n   line the transfers came in on (did_description)")
    for k, n in Counter((c.get("did_description") or "(blank)") for _, c in matched).most_common(10):
        print(f"      {str(k)[:40]:<40} {n:>5}")
    print("\n   vendor TLD stamped on that call")
    for k, n in Counter((c.get("vendor_description") or "(blank)") for _, c in matched).most_common(10):
        print(f"      {str(k)[:40]:<40} {n:>5}")
    print("\n   disposition")
    for k, n in Counter((c.get("status_name") or "(blank)") for _, c in matched).most_common(10):
        print(f"      {str(k)[:40]:<40} {n:>5}")
    has_crm_id = sum(1 for _, c in matched if str(c.get("lead_vendor_lead_code") or "").strip())
    print(f"\n   matched calls carrying a CRM lead id: {has_crm_id} / {len(matched)}")

    # ------------------------------------------------------------------ 3. POLICIES
    hr(f"3. POLICIES sold {d0} .. {dt.date.today()} — did the transferred lead buy?")
    pol = t._dedupe_rows(cl.run("policies_ids", str(d0), str(dt.date.today())))
    sold = {}
    for p in pol:
        lid = str(p.get("lead_id") or "").strip()
        if lid:
            sold[lid] = p
    print(f"   {len(sold):,} sold lead_ids in range")

    sales_by_rep = Counter()
    xfers_by_rep = Counter(x["rep"] for x in xfers)
    sold_xfers = 0
    for x in xfers:
        ids = {str(r.get("lead_id")) for r in leads_by_phone.get(x["phone"], [])}
        if ids & set(sold):
            sold_xfers += 1
            sales_by_rep[x["rep"]] += 1
    print(f"   transfers whose phone has a lead with a sale: {sold_xfers} / {len(xfers)} {pct(sold_xfers, len(xfers))}")
    print("\n   FRONTER            transfers   sales")
    for rep, n in xfers_by_rep.most_common():
        print(f"      {rep:<18} {n:>6}   {sales_by_rep.get(rep, 0):>5}")


if __name__ == "__main__":
    main()
