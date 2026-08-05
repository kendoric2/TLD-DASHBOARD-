#!/usr/bin/env python3
"""
SEP (Special Enrollment Period) breakdown of SOLD leads (READ-ONLY).

SEP lives on the lead (field `sep`); it only matters for leads that actually became a sale.
The leads endpoint carries `policies_sold` (how many policies the lead produced), so we can
identify sold leads directly — no policy join needed. This pulls the range's leads, keeps
only those with a policy, and counts SEP among them.

Leads are filtered on date_created (TLD's leads exception), so this is "leads CREATED in the
range that produced a sale". If you need it strictly by sale date, we'd join to policies —
ask and I'll switch it.

Usage:
  python3 sandbox/probes/probe_sep.py [START] [END]   # defaults to the last 30 days
"""
import os
import sys
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

END = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
START = sys.argv[1] if len(sys.argv) > 1 else (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
LIMIT = 200000


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    s0, e1 = f"{START} 00:00:00", f"{END} 23:59:59"

    rows = config.egress_get("leads", {
        "columns": ["lead_id", "sep", "policies_sold", "converted"],
        "date_created": s0, "date_created_end": e1, "limit": LIMIT}, timeout=240)
    rows = rows if isinstance(rows, list) else []
    n = len(rows)

    sold = [r for r in rows if isinstance(r, dict) and num(r.get("policies_sold")) >= 1]
    converted = sum(1 for r in rows if isinstance(r, dict)
                    and str(r.get("converted") or "").strip() not in ("", "0", "None"))

    codes = Counter()
    no_sep = 0
    for r in sold:
        sep = str(r.get("sep") or "").strip()
        if sep:
            codes[sep] += 1
        else:
            no_sep += 1
    with_sep = sum(codes.values())
    ns = len(sold)

    print(f"\nSEP breakdown of SOLD leads — {START} .. {END}\n" + "=" * 54)
    print(f"leads pulled            : {n:,}" + ("   <-- HIT ROW CAP, raise LIMIT!" if n == LIMIT else ""))
    print(f"sold leads (policies_sold>=1): {ns:,}")
    print(f"  (leads flagged converted   : {converted:,})")
    print(f"sold leads WITH a SEP   : {with_sep:,}  ({round(with_sep / ns * 100, 1) if ns else 0}% of sold)")
    print(f"sold leads with no SEP  : {no_sep:,}\n")
    print(f"{'SEP':<10}{'sold leads':>12}")
    print("-" * 24)
    for sep, cnt in codes.most_common():
        print(f"{sep:<10}{cnt:>12,}")
    print()


if __name__ == "__main__":
    main()
