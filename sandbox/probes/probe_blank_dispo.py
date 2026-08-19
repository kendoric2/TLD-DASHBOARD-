#!/usr/bin/env python3
"""
Why are 43% of dispositions blank? (READ-ONLY)

The Call Dispositions tile shows "(blank)" as the largest category. Two candidate causes:

  A. `status_name` is a lookup that fails for some codes — the raw `status` code is present
     but has no name mapping, so we display nothing. That's OUR bug, and the fix is to fall
     back to the raw code.
  B. Those calls genuinely aren't dispositioned yet — in flight, or on today's partial day.
     Then blanks should be concentrated in the most recent hours and near-zero on finished
     days.

This distinguishes them: it shows the blank rate PER DAY and PER HOUR, and for the blank
rows it dumps what the raw `status` column actually holds.

Usage:
  python3 sandbox/probes/probe_blank_dispo.py [DAYS]      # default 4 (ending today)
"""
import os
import sys
import datetime
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

CALL_LOG = "tldialer/tldialer_call_log"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 4
TODAY = datetime.date.today()
START = TODAY - datetime.timedelta(days=DAYS - 1)


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def blank(v):
    return str(v or "").strip() in ("", "None")


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    rows = [r for r in rows_of(config.egress_get(CALL_LOG, {
        "columns": ["call_date", "call_direction", "status", "status_name", "call_type",
                    "agent_name", "vendor_description", "sec_talk", "duration_call",
                    "call_answered", "call_end", "billable"],
        "limit": 200000, "call_direction": "INBOUND",
        "call_date": f"{START} 00:00:00", "call_date_end": f"{TODAY} 23:59:59"},
        timeout=300)) if isinstance(r, dict)]
    if not rows:
        print("No inbound calls in that window.")
        return

    blanks = [r for r in rows if blank(r.get("status_name"))]
    print(f"\nBLANK DISPOSITIONS   {START} .. {TODAY}\n" + "=" * 70)
    print(f"  inbound calls : {len(rows):,}")
    print(f"  blank status_name: {len(blanks):,}  ({len(blanks)/len(rows)*100:.1f}%)")

    # ---- A. is the raw `status` code present when the name is blank? ----------------
    print("\nA. When status_name is blank, what's in the raw `status` column?\n" + "-" * 70)
    raw = Counter(str(r.get("status") or "(also blank)") for r in blanks)
    for k, v in raw.most_common(15):
        print(f"   status = {k:<26}{v:>8,}")
    have_code = sum(v for k, v in raw.items() if k != "(also blank)")
    if have_code:
        print(f"\n   -> {have_code:,} of {len(blanks):,} blanks DO have a raw status code.")
        print("      That's a display gap on our side: fall back to the code.")
        # do those codes ever have a name elsewhere?
        named = {}
        for r in rows:
            if not blank(r.get("status_name")) and r.get("status"):
                named.setdefault(str(r["status"]), str(r["status_name"]))
        overlap = {k: named[k] for k in raw if k in named}
        print(f"      codes that DO have a name on other rows: "
              f"{overlap if overlap else 'none — these codes have no name anywhere'}")
    else:
        print("\n   -> the raw status is empty too; these calls simply aren't dispositioned yet.")

    # ---- B. are blanks concentrated in recent time? ---------------------------------
    print("\nB. Blank rate per day (a finished day should be near zero if it's 'not yet set')\n" + "-" * 70)
    per_day = defaultdict(lambda: [0, 0])
    for r in rows:
        d = str(r.get("call_date") or "")[:10]
        per_day[d][0] += 1
        if blank(r.get("status_name")):
            per_day[d][1] += 1
    for d in sorted(per_day):
        tot, bl = per_day[d]
        tag = "  <- today (partial)" if d == TODAY.isoformat() else ""
        print(f"   {d}   {tot:>7,} calls   {bl:>7,} blank   {bl/tot*100:5.1f}%{tag}")

    print("\n   blank rate by hour, today only:")
    today_rows = [r for r in rows if str(r.get("call_date") or "").startswith(TODAY.isoformat())]
    per_hr = defaultdict(lambda: [0, 0])
    for r in today_rows:
        h = str(r.get("call_date") or "")[11:13]
        per_hr[h][0] += 1
        if blank(r.get("status_name")):
            per_hr[h][1] += 1
    for h in sorted(per_hr):
        tot, bl = per_hr[h]
        print(f"      {h}:00   {tot:>6,} calls   {bl:>6,} blank   {bl/tot*100:5.1f}%")

    # ---- what do blank calls look like? ---------------------------------------------
    print("\nC. What are these calls?\n" + "-" * 70)
    for field in ("call_type", "agent_name", "vendor_description"):
        c = Counter(str(r.get(field) or "(blank)") for r in blanks)
        print(f"   {field}: {dict(c.most_common(5))}")
    answered = sum(1 for r in blanks if not blank(r.get("call_answered")))
    ended = sum(1 for r in blanks if not blank(r.get("call_end")))
    billed = sum(1 for r in blanks if str(r.get("billable")).strip() in ("1", "1.0", "True"))
    talk = sum(1 for r in blanks if float(r.get("sec_talk") or 0) > 0)
    print(f"   answered: {answered:,}   ended: {ended:,}   had talk time: {talk:,}   "
          f"BILLABLE: {billed:,}")
    if billed:
        print(f"   !! {billed:,} blank-disposition calls were BILLED — worth knowing what they were.")

    print("\n" + "=" * 70)
    print("Read it like this:")
    print("  • raw codes present  -> our display bug; show the code (easy fix)")
    print("  • blanks only today  -> not yet dispositioned; label them 'in progress'")
    print("  • blanks on finished days too -> ask TLD what an empty status means\n")


if __name__ == "__main__":
    main()
