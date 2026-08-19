#!/usr/bin/env python3
"""
Where are the weekend calls coming from? (READ-ONLY)

Sunday 2026-08-16 took 3,416 inbound calls — more than any weekday that week — and 97%
were never dispositioned because nobody was working. They're logged against "Inbound
Bucket", which is a catch-all, not a real source. No vendor is supposed to send calls at
the weekend, so: who's calling?

The call log identifies the line they dialed IN on (did_description / did_pattern /
call_to) — normally how a marketing source is tracked — plus the caller's own number.
This compares a Sunday against a working day on all of those.

Usage:
  python3 sandbox/probes/probe_weekend_calls.py [SUNDAY] [WEEKDAY]
  # defaults: 2026-08-16 vs 2026-08-18
"""
import os
import sys
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

CALL_LOG = "tldialer/tldialer_call_log"
SUN = sys.argv[1] if len(sys.argv) > 1 else "2026-08-16"
WKD = sys.argv[2] if len(sys.argv) > 2 else "2026-08-18"

COLS = ["call_date", "call_direction", "call_type", "status_name",
        "call_from", "call_to", "phone_number",
        "did_id", "did_pattern", "did_description", "did_extension",
        "campaign_id", "campaign_name", "vendor_id", "vendor_description",
        "agent_name", "billable", "cost", "sec_talk", "lead_vendor_lead_code"]


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def day_rows(day):
    return [r for r in rows_of(config.egress_get(CALL_LOG, {
        "columns": COLS, "limit": 200000, "call_direction": "INBOUND",
        "call_date": f"{day} 00:00:00", "call_date_end": f"{day} 23:59:59"},
        timeout=300)) if isinstance(r, dict)]


def show(title, rows, field, n=12):
    c = Counter(str(r.get(field) or "(blank)") for r in rows)
    print(f"\n   {title} — {field} ({len(c)} distinct)")
    for k, v in c.most_common(n):
        print(f"      {k[:44]:<46}{v:>7,}  ({v/max(len(rows),1)*100:4.1f}%)")


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    sun, wkd = day_rows(SUN), day_rows(WKD)
    sd = datetime.date.fromisoformat(SUN).strftime("%A")
    wd = datetime.date.fromisoformat(WKD).strftime("%A")
    print(f"\nWEEKEND CALL SOURCES\n{'=' * 74}")
    print(f"  {SUN} ({sd}):  {len(sun):,} inbound")
    print(f"  {WKD} ({wd}): {len(wkd):,} inbound")

    # ---- 1. which line did they call in on? ----------------------------------------
    print(f"\n1. WHICH LINE THEY DIALLED — this is the source fingerprint\n" + "-" * 74)
    for field in ("did_description", "did_pattern", "call_to"):
        show(f"{sd}", sun, field)
        show(f"{wd}", wkd, field, 6)

    # ---- 2. campaign / vendor -------------------------------------------------------
    print(f"\n2. CAMPAIGN AND VENDOR\n" + "-" * 74)
    for field in ("campaign_name", "vendor_description"):
        show(f"{sd}", sun, field, 8)
        show(f"{wd}", wkd, field, 8)

    # ---- 3. real people or repeats? -------------------------------------------------
    print(f"\n3. ARE THESE DISTINCT CALLERS?\n" + "-" * 74)
    for label, rows in ((sd, sun), (wd, wkd)):
        froms = [str(r.get("call_from") or "") for r in rows if r.get("call_from")]
        uniq = len(set(froms))
        rep = Counter(froms).most_common(5)
        print(f"   {label}: {len(froms):,} calls from {uniq:,} distinct numbers "
              f"({len(froms)/max(uniq,1):.1f} calls per number)")
        print(f"      most frequent: {rep}")

    # ---- 4. spread through the day, or bunched? -------------------------------------
    print(f"\n4. WHEN DID THEY ARRIVE? (bunched = automated, spread = real people)\n" + "-" * 74)
    for label, rows in ((sd, sun), (wd, wkd)):
        hrs = Counter(str(r.get("call_date") or "")[11:13] for r in rows)
        line = "  ".join(f"{h}:{hrs.get(h,0)}" for h in sorted(hrs) if h)
        print(f"   {label}: {line}")

    # ---- 5. did any cost money? -----------------------------------------------------
    print(f"\n5. DID THE WEEKEND COST ANYTHING?\n" + "-" * 74)
    for label, rows in ((sd, sun), (wd, wkd)):
        billed = [r for r in rows if str(r.get("billable")).strip() in ("1", "1.0", "True")]
        cost = sum(float(str(r.get("cost") or 0) or 0) for r in rows)
        talk = sum(1 for r in rows if float(r.get("sec_talk") or 0) > 0)
        withlead = sum(1 for r in rows if str(r.get("lead_vendor_lead_code") or "").strip())
        print(f"   {label}: billed {len(billed):,}  cost ${cost:,.2f}  "
              f"had talk time {talk:,}  linked to a CRM lead {withlead:,}")

    print(f"\n{'=' * 74}")
    print("Read it like this:")
    print("  • same DID/line on both days -> it's your normal number, people just call anyway")
    print("  • a DID that only rings at weekends -> someone IS sending traffic; that's the source")
    print("  • few distinct numbers + many repeats -> automated retries, not prospects")
    print("  • no CRM lead linked -> these callers aren't in your system at all\n")


if __name__ == "__main__":
    main()
