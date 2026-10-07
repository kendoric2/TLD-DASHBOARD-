#!/usr/bin/env python3
"""
Why is Transfer Check showing dates outside the uploaded range? (READ-ONLY)

Answers three questions, in order, instead of guessing:

  1. Is the running server even using the current code? Prints whether the date cap
     is present in the transfer_check module that Python actually imports.
  2. What range did the FILE define? `check()` derives its range from the CallDate
     values in the export, NOT from the range you asked DialedIN for. One stray row
     moves the end date and re-opens the window. Prints every day found, and flags
     any day outside the range you expected.
  3. Which column is actually out of range? Runs the real check and reports, per row,
     whether transfer_time / call_time / date_sold falls past the range end.

Steps 1-2 are instant and offline. Step 3 hits the API (read-only) and is slow, so
it only runs if you pass --live.

Prints phone LAST-4 only. The export holds PHI (MBI, DOB, Medicaid #) — nothing from
it is written to disk, cache or logs by this script.

Usage:
  python3 sandbox/probes/probe_transfer_range.py ~/Downloads/CampaignLeads_XXXX.csv
  python3 sandbox/probes/probe_transfer_range.py <file> --expect 2026-09-28 2026-10-04
  python3 sandbox/probes/probe_transfer_range.py <file> --expect 2026-09-28 2026-10-04 --live
"""
import os
import sys
import inspect
import datetime as dt
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import transfer_check  # noqa: E402


def main():
    args = [a for a in sys.argv[1:]]
    live = "--live" in args
    args = [a for a in args if a != "--live"]

    expect = None
    if "--expect" in args:
        i = args.index("--expect")
        try:
            expect = (dt.date.fromisoformat(args[i + 1]), dt.date.fromisoformat(args[i + 2]))
        except (IndexError, ValueError):
            sys.exit("--expect needs two dates: --expect 2026-09-28 2026-10-04")
        args = args[:i] + args[i + 3:]

    if not args:
        sys.exit(__doc__)
    path = os.path.expanduser(args[0])
    if not os.path.exists(path):
        sys.exit(f"No such file: {path}")

    # ---- 1. is the code even the new code? -------------------------------------
    print("=" * 78)
    print("1. IS THE FIX LOADED?")
    print("=" * 78)
    src = inspect.getsource(transfer_check.check)
    capped = "created.date() > d1" in src
    print(f"  transfer_check loaded from : {transfer_check.__file__}")
    print(f"  date cap present in check() : {'YES' if capped else 'NO'}")
    if not capped:
        print("  >> This module does NOT have the cap. The file on disk was not updated,")
        print("     or you are running a different copy of the project.")
    else:
        print("  >> Code is current. If the dashboard still shows old behaviour, the Flask")
        print("     server is running the version it imported at startup (debug=False, no")
        print("     reloader): stop it with Ctrl-C and start it again.")
    print()

    # ---- 2. what range did the file define? ------------------------------------
    print("=" * 78)
    print("2. WHAT RANGE DID THE FILE DEFINE?")
    print("=" * 78)
    with open(path, "rb") as fh:
        transfers = transfer_check.parse_export(fh.read(), os.path.basename(path))

    whens = [t["when"] for t in transfers if t["when"]]
    unparsed = len(transfers) - len(whens)
    print(f"  rows with a phone        : {len(transfers)}")
    print(f"  rows with a usable date  : {len(whens)}")
    print(f"  rows with an UNREADABLE date : {unparsed}"
          + ("   << these are dropped from the range entirely" if unparsed else ""))
    if not whens:
        sys.exit("  No readable CallDate values — nothing else to check.")

    d0, d1 = min(whens).date(), max(whens).date()
    print(f"\n  range check() will use   : {d0}  ..  {d1}")
    if expect:
        print(f"  range you expected       : {expect[0]}  ..  {expect[1]}")
        if (d0, d1) != expect:
            print("  >> MISMATCH. check() caps credit at the file's own end date, so if the")
            print("     file reaches past what you asked for, the window is still open.")
        else:
            print("  >> Matches.")

    print("\n  transfers per day:")
    days = Counter(w.date() for w in whens)
    for day in sorted(days):
        out = ""
        if expect and not (expect[0] <= day <= expect[1]):
            out = "   << OUTSIDE the range you expected"
        print(f"    {day}  {days[day]:5d}{out}")

    if expect:
        stray = [t for t in transfers if t["when"] and not (expect[0] <= t["when"].date() <= expect[1])]
        if stray:
            print(f"\n  {len(stray)} stray row(s) — these are what moved the range end:")
            for t in stray[:20]:
                print(f"    {t['when']}  rep={t['rep'][:22]:22s} phone=***{t['phone'][-4:]}"
                      f"  campaign={t['campaign'][:18]}")
            if len(stray) > 20:
                print(f"    … and {len(stray) - 20} more")
    print()

    if not live:
        print("Stopping here. Re-run with --live to see which column is out of range")
        print("(that part calls the API and takes a while).")
        return

    # ---- 3. which column is actually out of range? -----------------------------
    print("=" * 78)
    print("3. WHICH COLUMN IS OUT OF RANGE?")
    print("=" * 78)
    data = transfer_check.check(transfers)
    end = dt.date.fromisoformat(data["range"]["end"])
    print(f"  check() reported range   : {data['range']['start']} .. {data['range']['end']}")
    print(f"  totals                   : {data['totals']}")

    def past(val):
        d = transfer_check._parse_dt(val)
        return d is not None and d.date() > end

    buckets = Counter()
    examples = {}
    for r in data["rows"]:
        for col in ("transfer_time", "call_time", "date_sold"):
            if past(r.get(col)):
                buckets[col] += 1
                examples.setdefault(col, r)

    if not buckets:
        print("\n  >> No row has transfer_time, call_time or date_sold past the range end.")
        print("     The data is clean. If the screen disagrees, it is showing a cached")
        print("     result from before the restart — re-upload the file.")
    else:
        print("\n  rows with a value past the range end:")
        for col, n in buckets.most_common():
            print(f"    {col:16s} {n:5d}")
            r = examples[col]
            print(f"      e.g. rep={r['rep'][:20]:20s} phone=***{r['phone_last4']}"
                  f" result={r['result']}")
            print(f"           transfer_time={r['transfer_time']!r} call_time={r['call_time']!r}"
                  f" date_sold={r['date_sold']!r}")
        print("\n  NOTE: call_time can legitimately sit a few hours past the end date —")
        print("  MATCH_WINDOW is 3h, so a late-night transfer matches a call after midnight.")
        print("  date_sold past the end date means the cap is not working. transfer_time past")
        print("  it is impossible unless the range came from somewhere other than this file.")


if __name__ == "__main__":
    main()
