#!/usr/bin/env python3
"""
What IS "System Process"? (READ-ONLY) — research aid for the TLD question.

"System Process" (user_id 0) accounts for ~26.5% of all disposition events. The working
theory is that these are leads auto-dispositioned WITHOUT ever reaching an agent. This
pulls the evidence so you can confirm or refute that with TLD.

It compares System Process activity against human agents on:
  • which dispositions it sets      (auto-drops? DNC scrubs? no-answers?)
  • which pages/URLs it comes from  (a dialer screen implies a human was involved)
  • which vendors its leads come from
  • time-of-day pattern             (round-the-clock = automated; business hours = human)

Usage:
  python3 sandbox/probes/probe_system_process.py [DAYS]     # default 1 (yesterday)
"""
import os
import sys
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 1
END = datetime.date.today() - datetime.timedelta(days=1)
START = END - datetime.timedelta(days=DAYS - 1)


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    rows = rows_of(config.egress_get("lead_logs", {
        "columns": ["action_id", "date_created", "lead_id", "lead_status_name",
                    "user_id", "user_full_name", "page", "lead_vendor_id", "result"],
        "action": "status", "limit": 200000,
        "date_created": f"{START} 00:00:00", "date_created_end": f"{END} 23:59:59"},
        timeout=240))
    rows = [r for r in rows if isinstance(r, dict)]
    sysr = [r for r in rows if str(r.get("user_id")) in ("0", "0.0")]
    human = [r for r in rows if str(r.get("user_id")) not in ("0", "0.0")]

    print(f"\nWHAT IS 'SYSTEM PROCESS'?     {START} .. {END}\n" + "=" * 72)
    print(f"  total disposition events : {len(rows):,}")
    print(f"  System Process (user_id 0): {len(sysr):,} ({len(sysr)/max(len(rows),1)*100:.1f}%)")
    print(f"  human agents             : {len(human):,}")

    def compare(field, title, n=10):
        s = Counter(str(r.get(field) or "(blank)") for r in sysr)
        h = Counter(str(r.get(field) or "(blank)") for r in human)
        print(f"\n{title}\n" + "-" * 72)
        print(f"  {'value':<34}{'SYSTEM':>10}{'HUMANS':>10}")
        for k, _ in (s + h).most_common(n):
            print(f"  {k[:33]:<34}{s.get(k,0):>10,}{h.get(k,0):>10,}")

    compare("lead_status_name", "Dispositions set — does the system set different ones?")
    compare("page", "Where it came from — a /dialer/ page implies a human was on the call")
    compare("lead_vendor_id", "Vendor of the lead")

    # Round-the-clock activity is the strongest tell for automation.
    print("\nTime of day — automation runs at 3am, humans don't\n" + "-" * 72)
    sh = Counter(str(r.get("date_created") or "")[11:13] for r in sysr)
    hh = Counter(str(r.get("date_created") or "")[11:13] for r in human)
    print(f"  {'hour':<8}{'SYSTEM':>10}{'HUMANS':>10}")
    for hr in sorted(set(sh) | set(hh)):
        if hr:
            print(f"  {hr+':00':<8}{sh.get(hr,0):>10,}{hh.get(hr,0):>10,}")

    # Do system-touched leads ever get touched by a human too?
    sys_leads = {str(r.get("lead_id")) for r in sysr}
    hum_leads = {str(r.get("lead_id")) for r in human}
    both = sys_leads & hum_leads
    print("\nDid a human ever touch the same lead?\n" + "-" * 72)
    print(f"  leads touched by System Process : {len(sys_leads):,}")
    print(f"  ...also touched by a human      : {len(both):,} ({len(both)/max(len(sys_leads),1)*100:.1f}%)")
    print(f"  ...NEVER touched by a human     : {len(sys_leads - hum_leads):,}")
    print("\n  If most were never touched by a human, that supports the theory that these")
    print("  are leads auto-dispositioned before ever reaching an agent.\n")


if __name__ == "__main__":
    main()
