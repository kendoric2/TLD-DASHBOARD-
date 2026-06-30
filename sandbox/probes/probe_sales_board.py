#!/usr/bin/env python3
"""
Sales-board data check (READ-ONLY).

Pulls the deals for a date range and builds ONE combined leaderboard of everyone —
closers (agents) and enrollers (fronters) together — so we can confirm the numbers
line up with TLD before building the board UI.

Per person:
  CLOSED   = deals where they were the agent (closer)
  ENROLLED = deals where they were the fronter (enroller)
  TOTAL    = closed + enrolled (deals they touched)
Plus each top closer's deals broken down by carrier.

Everything is deduped on policy_id -> lead_id and limited to stage = sale (same basis
as the rest of the dashboard).

Usage:
  python3 sandbox/probes/probe_sales_board.py [START] [END]
  # defaults to today; pass dates for a wider window, e.g. 2025-09-01 2025-09-30
"""
import os
import sys
import datetime
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config                                       # noqa: E402
from tldcrm_client import TLDCRMClient, _dedupe_rows  # noqa: E402

TODAY = datetime.date.today().isoformat()
START = sys.argv[1] if len(sys.argv) > 1 else TODAY
END   = sys.argv[2] if len(sys.argv) > 2 else TODAY


def pull(c, start, end):
    s0, e1 = f"{start} 00:00:00", f"{end} 23:59:59"
    body = {
        "columns": ["policy_id", "lead_id", "carrier_name", "stage", "agent_name", "fronter_name"],
        "limit": 200000,
        "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1,
    }
    return config.egress_get("policies", body, timeout=120)


def main():
    if not config.have_creds():
        print("No credentials found. Run this on the machine where .env is configured.")
        return

    c = TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)
    rows = _dedupe_rows(pull(c, START, END))         # deduped, stage = sale

    print(f"\nSALES BOARD  {START} .. {END}\n" + "=" * 66)
    print(f"Deduped sale deals: {len(rows):,}\n")

    closed   = defaultdict(int)                       # person -> deals closed (as agent)
    enrolled = defaultdict(int)                       # person -> deals enrolled (as fronter)
    carriers = defaultdict(lambda: defaultdict(int))  # person -> carrier -> closed count
    people   = set()
    for r in rows:
        a = (r.get("agent_name") or "").strip()
        f = (r.get("fronter_name") or "").strip()
        car = (str(r.get("carrier_name") or "").strip() or "—")
        if a:
            closed[a] += 1
            carriers[a][car] += 1
            people.add(a)
        if f:
            enrolled[f] += 1
            people.add(f)

    board = sorted(people, key=lambda p: -(closed[p] + enrolled[p]))
    print(f"{'RANK':<5}{'PERSON':<27}{'CLOSED':>7}{'ENROLLED':>10}{'TOTAL':>7}")
    print("-" * 66)
    for i, p in enumerate(board[:40], 1):
        print(f"{i:<5}{p[:26]:<27}{closed[p]:>7}{enrolled[p]:>10}{closed[p] + enrolled[p]:>7}")
    print("-" * 66)
    print(f"people: {len(people)}   |   total closed: {sum(closed.values()):,}   "
          f"total enrolled: {sum(enrolled.values()):,}\n")

    print("Top closers — deals by carrier:")
    for p in sorted(closed, key=lambda x: -closed[x])[:8]:
        cs = ", ".join(f"{k} {v}" for k, v in sorted(carriers[p].items(), key=lambda x: -x[1]))
        print(f"  {p[:26]:<27} {cs}")
    print()


if __name__ == "__main__":
    main()
