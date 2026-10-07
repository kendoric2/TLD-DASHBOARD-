"""
Transfer Check — match a DialedIN fronter export against TLD to see which transfers sold.

The fronters work in DialedIN and transfer calls into TLD, but TLD attaches each transfer
to whatever lead already owns that phone (most of these people were bought last AEP under
another vendor), so the transfers never show under the MAPD / Manhattan Life vendors. This
works backwards from DialedIN's own list of transfers instead:

  1. LEADS     every TLD lead for each phone          leads, "phone" takes a list
  2. CALL LOG  the inbound call from that phone,      tldialer_call_log, "phone_number"
               closest to DialedIN's CallDate          takes a list
  3. POLICIES  policies on those leads                 policies, "lead_id" takes a list

A fronter is PAID when one of the phone's leads has a NEW policy created on/after the
transfer day AND on/before the last transfer day in the export, AND a manager has verified
it ("dropped" — TLD's `verified` flag). Old policies (from the previous FMO, set to Unsold)
are ignored because they were created before the transfer; policies created after the
export's last day are ignored because they belong to a later run — the policies lookup is
filtered on lead_id with no date filter, so without that cap any future policy on the
phone's leads would be credited back to this transfer. A new policy not verified yet is
AWAITING VERIFICATION; "Sale Made"
on the call with no new policy yet is PENDING. The export is run weekly on Saturday after
managers have verified the week, so both should be near zero by then.

Every lookup was verified by sandbox/probes/probe_transfer_match.py (560/560 phones found,
97% matched to an inbound call, median 1.7 min from DialedIN's CallDate).

PRIVACY: the export carries MBI, DOB and Medicaid numbers. Only phone, rep, campaign, call
time and TLD lead id are read from it; the file itself is never written to disk, cache or
logs, and results only ever show the phone's last 4 digits.
"""
import csv
import io
import re
import datetime as dt
from collections import Counter, defaultdict

import config

CALL_LOG = "tldialer/tldialer_call_log"

# Paid once per transfer, however many new policies it produced (e.g. MAPD + Manhattan
# Life on the same person). Flip to False to pay per policy — waiting on payroll's answer.
PAY_ONCE_PER_TRANSFER = True

# A call counts as "the transfer" if it's within this long of DialedIN's CallDate.
MATCH_WINDOW = dt.timedelta(hours=3)

# New policies in these statuses don't pay (trash = deleted, quoted = never sold).
UNPAID_STATUSES = {"trash", "quoted", "unsold", "cancelled", "canceled", "declined"}

CHUNK = 100

# ---------------------------------------------------------------------------
# Product line. REPORTING ONLY — it never changes who gets paid. A fronter is paid for
# whatever their transfer sold, so a Manhattan Life policy sold off the MAPD campaign
# still pays the MAPD fronter (4 of the 36 sales in the first real file were exactly
# that). The line is decided by the POLICY'S CARRIER, never by the campaign the fronter
# was dialing, because the two disagree.
LINE_MANHATTAN = "Manhattan Life"
LINE_MAPD = "MAPD"

# Manhattan Life and GTL are tracked together — close enough to the same product.
# Everything else is MAPD, so a new MAPD carrier needs no code change and can't fall
# into an untracked gap.
MANHATTAN_CARRIERS = {"MANHATTAN", "MANHATTAN LIFE", "MANHATTANLIFE", "GTL"}


def carrier_line(name):
    """Carrier name -> product line. '' for a blank carrier."""
    key = re.sub(r"[^A-Z ]", "", str(name or "").upper()).strip()
    if not key:
        return ""
    return LINE_MANHATTAN if key in MANHATTAN_CARRIERS else LINE_MAPD


def campaign_line(name):
    """DialedIN campaign -> the line it was DIALING for. Only used to label transfers that
    produced no sale; a sale is always labelled by its carrier."""
    key = str(name or "").upper()
    if "MANHATTAN" in key:
        return LINE_MANHATTAN
    return LINE_MAPD if "MAPD" in key else ""

# DialedIN column names, with fallbacks in case they rename something.
COLS = {
    "phone":    ["PrimaryPhone", "Phone", "Phone Number"],
    "rep":      ["Rep", "Agent", "Fronter"],
    "campaign": ["Campaign"],
    "when":     ["CallDate", "LastUpdated", "Date"],
    "tld_id":   ["TLD Lead ID", "TLD Lead Id", "Lead ID"],
}


def _phone10(s):
    d = re.sub(r"\D", "", str(s or ""))
    return d[-10:] if len(d) >= 10 else ""


def _parse_dt(s):
    s = str(s or "").strip()
    for f in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M:%S",
              "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def _rows(resp):
    if isinstance(resp, list):
        return [r for r in resp if isinstance(r, dict)]
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return [r for r in resp[k] if isinstance(r, dict)]
    return []


def _pick(header, names):
    low = {h.strip().lower(): h for h in header}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def parse_export(data, filename=""):
    """DialedIN export (CSV or .xlsx bytes) -> list of transfers. Raises ValueError if the
    file doesn't look like a DialedIN export."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        it = ws.iter_rows(values_only=True)
        header = [str(h or "").strip() for h in next(it, [])]
        records = [dict(zip(header, ["" if v is None else v for v in row])) for row in it]
    else:
        text = data.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        header = reader.fieldnames or []
        records = list(reader)

    col = {k: _pick(header, v) for k, v in COLS.items()}
    if not col["phone"] or not col["when"]:
        raise ValueError("This doesn't look like a DialedIN export — it needs a "
                         "PrimaryPhone and a CallDate column.")

    out = []
    for r in records:
        phone = _phone10(r.get(col["phone"]))
        if not phone:
            continue
        when = r.get(col["when"])
        when = when if isinstance(when, dt.datetime) else _parse_dt(when)
        out.append({
            "phone": phone,
            "rep": str(r.get(col["rep"]) or "").strip() if col["rep"] else "",
            "campaign": str(r.get(col["campaign"]) or "").strip() if col["campaign"] else "",
            "when": when,
            "tld_id": re.sub(r"\D", "", str(r.get(col["tld_id"]) or "")) if col["tld_id"] else "",
        })
    if not out:
        raise ValueError("No rows with a phone number were found in that file.")
    return out


def _chunks(seq, n=CHUNK):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _leads_by_phone(phones):
    """phone -> [lead_id, …] for every TLD lead on each phone (leads takes a phone list)."""
    out = defaultdict(list)
    for batch in _chunks(phones):
        resp = config.egress_get("leads", {
            "columns": ["lead_id", "phone", "date_created"],
            "phone": batch, "limit": len(batch) * 50}, timeout=180)
        for r in _rows(resp):
            p = _phone10(r.get("phone"))
            if p and r.get("lead_id"):
                out[p].append(str(r["lead_id"]).strip())
    return out


def _policies_by_lead(lead_ids):
    """lead_id -> [policy, …] — every policy ever written on those leads (no date filter)."""
    out = defaultdict(list)
    for batch in _chunks(lead_ids, 50):
        resp = config.egress_get("policies", {
            "columns": ["policy_id", "lead_id", "date_created", "date_sold", "status_name",
                        "carrier_name", "agent_name", "verified", "verifier_name"],
            "lead_id": batch, "limit": 20000}, timeout=180)
        seen = set()
        for r in _rows(resp):
            pid = str(r.get("policy_id") or "")
            if pid and pid in seen:
                continue
            seen.add(pid)
            out[str(r.get("lead_id") or "").strip()].append(r)
    return out


def _is_live(p):
    return str(p.get("status_name") or "").strip().lower() not in UNPAID_STATUSES


def _is_verified(p):
    return str(p.get("verified") or "").strip() in ("1", "1.0", "True", "true")


def _dropped_sales(dropped, d0, d1):
    """Guard for the pay week: do any transfers the range threw away already have a sale?

    Dropped rows aren't scored, so without this a sale whose transfer landed outside the
    week (the 267 Manhattan Life rows of 10/6-10/7, carrying 17 sales) disappears without a
    word. Same rule as a paid sale — a live new policy created on/after the transfer day —
    but with no upper cap, because these belong to some OTHER week's run. Split by side:
    after the week = belongs to the next run; before = should have been in the last one."""
    if not dropped:
        return None
    leads = _leads_by_phone(sorted({t["phone"] for t in dropped}))
    ids = sorted({lid for v in leads.values() for lid in v} | {t["tld_id"] for t in dropped if t["tld_id"]})
    pols = _policies_by_lead(ids)
    side = {"before": [], "after": []}
    for t in dropped:
        lids = set(leads.get(t["phone"], [])) | ({t["tld_id"]} if t["tld_id"] else set())
        sold = [p for lid in lids for p in pols.get(lid, []) if _is_live(p)
                and (_parse_dt(p.get("date_created")) or dt.datetime.min).date() >= t["when"].date()]
        if sold:
            side["before" if t["when"].date() < d0 else "after"].append(
                (t["when"].date(), any(_is_verified(p) for p in sold)))
    out = {}
    for k, hits in side.items():
        if hits:
            days = sorted(h[0] for h in hits)
            out[k] = {"transfers": len(hits), "verified": sum(1 for h in hits if h[1]),
                      "first": days[0].isoformat(), "last": days[-1].isoformat()}
    return {"transfers": sum(v["transfers"] for v in out.values()), **out} if out else {"transfers": 0}


def check(transfers, start=None, end=None):
    """Run the three lookups and score every transfer. Returns the payload the tab shows.

    start/end (datetime.date, optional) bound the run. DialedIN's export range filters on the
    lead's campaign `Date`, but we read `CallDate` (when the transfer happened) — so a 9/28-10/4
    export came back carrying 267 Manhattan Life rows transferred 10/6-10/7. When a range is
    given it wins over the file: rows outside it are dropped, and the credit window closes at
    `end`. With no range given the file's own min/max CallDate is used, which is the old
    behaviour and trusts the export. Dropped rows that already have a sale are reported in
    `dropped_sales`, so paid work can never fall out of a pay week silently.
    """
    whens = [t["when"] for t in transfers if t["when"]]
    if not whens:
        raise ValueError("None of the CallDate values could be read as a date.")
    file_d0, file_d1 = min(whens).date(), max(whens).date()

    dropped, dropped_rows = 0, []
    if start or end:
        d0 = start or file_d0
        d1 = end or file_d1
        if d0 > d1:
            raise ValueError("The start date is after the end date.")
        kept = [t for t in transfers if t["when"] and d0 <= t["when"].date() <= d1]
        dropped_rows = [t for t in transfers if t["when"] and not d0 <= t["when"].date() <= d1]
        dropped = len(transfers) - len(kept)
        if not kept:
            raise ValueError(f"No transfers fall in {d0} to {d1}. This file covers "
                             f"{file_d0} to {file_d1} ({len(transfers)} rows).")
        transfers = kept
    else:
        d0, d1 = file_d0, file_d1

    phones = sorted({t["phone"] for t in transfers})

    # 1. every TLD lead for each phone
    leads_by_phone = _leads_by_phone(phones)

    # 2. inbound calls from those phones (a day of slack each side)
    calls_by_phone = defaultdict(list)
    c0, c1 = d0 - dt.timedelta(days=1), d1 + dt.timedelta(days=1)
    for batch in _chunks(phones):
        resp = config.egress_get(CALL_LOG, {
            "columns": ["call_date", "phone_number", "agent_name", "status_name",
                        "vendor_description", "did_description", "lead_vendor_lead_code"],
            "call_direction": "INBOUND", "phone_number": batch, "limit": 50000,
            "call_date": f"{c0} 00:00:00", "call_date_end": f"{c1} 23:59:59"}, timeout=300)
        for r in _rows(resp):
            p = _phone10(r.get("phone_number"))
            if p:
                calls_by_phone[p].append(r)

    # 3. every policy on every one of those leads
    lead_ids = sorted({lid for ids in leads_by_phone.values() for lid in ids}
                      | {t["tld_id"] for t in transfers if t["tld_id"]})
    policies_by_lead = _policies_by_lead(lead_ids)

    # Same phone transferred more than once: a policy belongs to the LATEST transfer on or
    # before the day it was created, so two fronters can never both be paid for one sale.
    by_phone = defaultdict(list)
    for i, t in enumerate(transfers):
        by_phone[t["phone"]].append(i)
    credited = defaultdict(list)          # transfer index -> its new policies
    for phone, idxs in by_phone.items():
        ids = set(leads_by_phone.get(phone, [])) | {transfers[i]["tld_id"] for i in idxs if transfers[i]["tld_id"]}
        pols = [p for lid in ids for p in policies_by_lead.get(lid, [])]
        for p in pols:
            created = _parse_dt(p.get("date_created"))
            if not created:
                continue
            # Upper bound: the export is a self-contained week, so a policy created after
            # the last transfer day in the file belongs to a later run, not this one.
            # Without this the lookup (filtered on lead_id only, no date filter) credited
            # ANY future policy on the phone's leads to the transfer.
            if created.date() > d1:
                continue
            owners = [i for i in idxs if transfers[i]["when"]
                      and transfers[i]["when"].date() <= created.date()]
            if owners:
                credited[max(owners, key=lambda i: transfers[i]["when"])].append(p)

    rows = []
    for i, t in enumerate(transfers):
        call = None
        if t["when"]:
            best = None
            for c in calls_by_phone.get(t["phone"], []):
                cd = _parse_dt(c.get("call_date"))
                if cd:
                    gap = abs(cd - t["when"])
                    if gap <= MATCH_WINDOW and (best is None or gap < best[0]):
                        best = (gap, c)
            call = best[1] if best else None

        new = sorted(credited.get(i, []), key=lambda p: str(p.get("date_created") or ""))
        live = [p for p in new if _is_live(p)]
        paid_pols = [p for p in live if _is_verified(p)]
        disposition = str(call.get("status_name") or "").strip() if call else ""
        lead_id = (str(call.get("lead_vendor_lead_code") or "").strip() if call else "") \
            or t["tld_id"] or (leads_by_phone.get(t["phone"]) or [""])[-1]

        if paid_pols:
            result = "Paid"
        elif live:
            result = "Awaiting verification"
        elif disposition.lower() == "sale made":
            result = "Pending"
        elif not call:
            result = "Not found"
        else:
            result = "No sale"

        shown = paid_pols or live or new
        # Product line, for reporting. A sale is labelled by its carrier; a transfer that
        # sold nothing falls back to the line its campaign was dialing, so every row can be
        # grouped. NOTE: "line" below is the DID description (which phone line the call came
        # in on) and has nothing to do with this — don't merge the two.
        paid_by_line = Counter(carrier_line(p.get("carrier_name")) for p in paid_pols)
        sale_lines = sorted({carrier_line(p.get("carrier_name")) for p in shown} - {""})
        rows.append({
            "rep": t["rep"] or "(no rep)",
            "campaign": t["campaign"],
            "product_line": ", ".join(sale_lines) or campaign_line(t["campaign"]),
            "sale_lines": ", ".join(sale_lines),
            "pol_manhattan": paid_by_line.get(LINE_MANHATTAN, 0),
            "pol_mapd": paid_by_line.get(LINE_MAPD, 0),
            "phone_last4": t["phone"][-4:],
            "transfer_time": t["when"].strftime("%Y-%m-%d %H:%M:%S") if t["when"] else "",
            "lead_id": lead_id,
            "call_time": str(call.get("call_date") or "") if call else "",
            "agent": str(call.get("agent_name") or "").strip() if call else "",
            "disposition": disposition,
            "landed_vendor": str(call.get("vendor_description") or "").strip() if call else "",
            "line": str(call.get("did_description") or "").strip() if call else "",
            "result": result,
            "policies": len(paid_pols),
            "carrier": ", ".join(sorted({str(p.get("carrier_name") or "").strip() for p in shown} - {""})),
            "verified_by": ", ".join(sorted({str(p.get("verifier_name") or "").strip()
                                             for p in paid_pols} - {"", "None"})),
            "policy_status": ", ".join(sorted({str(p.get("status_name") or "").strip() for p in shown} - {""})),
            "date_sold": min((str(p.get("date_sold") or "")[:10] for p in shown
                              if str(p.get("date_sold") or "")[:4] not in ("", "None", "0000")), default=""),
        })

    reps = {}
    for r in rows:
        f = reps.setdefault(r["rep"], {"rep": r["rep"], "transfers": 0, "found": 0, "paid": 0,
                                       "policies": 0, "awaiting": 0, "pending": 0,
                                       "not_found": 0, "pol_manhattan": 0, "pol_mapd": 0})
        f["transfers"] += 1
        f["found"] += r["result"] != "Not found"
        f["paid"] += r["result"] == "Paid"
        f["policies"] += r["policies"]
        f["awaiting"] += r["result"] == "Awaiting verification"
        f["pending"] += r["result"] == "Pending"
        f["not_found"] += r["result"] == "Not found"
        # Verified policies split by line. These two always sum to `policies`, so the
        # breakdown reconciles with the payable column instead of floating beside it.
        f["pol_manhattan"] += r["pol_manhattan"]
        f["pol_mapd"] += r["pol_mapd"]
    for f in reps.values():
        f["payable"] = f["paid"] if PAY_ONCE_PER_TRANSFER else f["policies"]
    by_rep = sorted(reps.values(), key=lambda f: (-f["payable"], -f["transfers"], f["rep"].lower()))

    keys = ("transfers", "found", "paid", "policies", "awaiting", "pending", "not_found",
            "payable", "pol_manhattan", "pol_mapd")
    totals = {k: sum(f[k] for f in by_rep) for k in keys}

    # Per-line view of the whole run. `transfers` here groups on product_line (sale carrier,
    # or the campaign's line when nothing sold), so it covers every row exactly once.
    lines = {}
    for r in rows:
        key = r["product_line"] or "(unknown)"
        g = lines.setdefault(key, {"line": key, "transfers": 0, "paid": 0, "policies": 0,
                                   "awaiting": 0, "pending": 0, "not_found": 0})
        g["transfers"] += 1
        g["paid"] += r["result"] == "Paid"
        g["policies"] += r["policies"]
        g["awaiting"] += r["result"] == "Awaiting verification"
        g["pending"] += r["result"] == "Pending"
        g["not_found"] += r["result"] == "Not found"
    by_line = sorted(lines.values(), key=lambda g: (-g["policies"], -g["transfers"], g["line"]))
    return {
        "range": {"start": d0.isoformat(), "end": d1.isoformat()},
        # What the file itself covered, and how many rows the range threw away. DialedIN
        # filters its export on the lead's `Date`, but writes `CallDate` as the LAST call
        # attempt, so a file "for" one week routinely carries later transfer activity.
        "file_range": {"start": file_d0.isoformat(), "end": file_d1.isoformat()},
        "dropped": dropped,
        "dropped_sales": _dropped_sales(dropped_rows, d0, d1),
        "pay_once": PAY_ONCE_PER_TRANSFER,
        "totals": totals,
        "by_rep": by_rep,
        "by_line": by_line,
        "rows": sorted(rows, key=lambda r: r["transfer_time"], reverse=True),
    }
