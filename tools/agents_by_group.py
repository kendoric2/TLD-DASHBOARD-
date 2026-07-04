#!/usr/bin/env python3
"""
List ACTIVE agents by user group (READ-ONLY) — one column per group, split by a line.
Users with no group are shown under "New Upline". Standalone metrics pull; nothing to do
with the dashboard.

Usage:
  python3 tools/agents_by_group.py            # active only (default)
  python3 tools/agents_by_group.py --all      # include inactive too
  python3 tools/agents_by_group.py --csv      # also write logs/agents_by_group.csv
"""
import os
import sys
import csv
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import config  # noqa: E402

INCLUDE_ALL = "--all" in sys.argv
WRITE_CSV = "--csv" in sys.argv
NO_GROUP = "New Upline"          # bucket name for users with no assigned group (for now)


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    body = {"columns": ["name", "full_name", "status", "group_names", "role_names"], "limit": 5000}
    rows = config.egress_get("users", body, timeout=60)
    if not isinstance(rows, list):
        print("Unexpected response from /users:", str(rows)[:200])
        return

    groups = defaultdict(list)
    flat = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        status = str(r.get("status") or "").strip()
        if not INCLUDE_ALL and status.lower() != "active":
            continue
        role = str(r.get("role_names") or "").lower()
        if "fronter" in role and "agent" not in role:      # drop fronter-only users; role isn't displayed
            continue
        group = str(r.get("group_names") or "").strip() or NO_GROUP
        name = str(r.get("name") or r.get("full_name") or "?").strip()
        groups[group].append(name)
        flat.append((name, group, status))

    # named groups alphabetically first; the "New Upline" (no-group) bucket always last
    order = sorted([g for g in groups if g != NO_GROUP], key=str.lower)
    if NO_GROUP in groups:
        order.append(NO_GROUP)
    for g in order:
        groups[g].sort(key=str.lower)

    total = sum(len(groups[g]) for g in order)
    label = "ALL" if INCLUDE_ALL else "ACTIVE"
    print(f"\n{label} AGENTS BY GROUP  ({total})\n")
    if not order:
        print("(none)\n")
        return

    width = max([len(g) for g in order] + [len(n) for g in order for n in groups[g]])

    def line(cells):
        return " | ".join(c.ljust(width) for c in cells).rstrip()

    print(line(order))
    print("-+-".join("-" * width for _ in order))
    for i in range(max(len(groups[g]) for g in order)):
        print(line([(groups[g][i] if i < len(groups[g]) else "") for g in order]))

    print("\n" + "   ·   ".join(f"{g}: {len(groups[g])}" for g in order))
    print(f"Total: {total}\n")

    if WRITE_CSV:
        path = os.path.join("logs", "agents_by_group.csv")
        os.makedirs("logs", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "group", "status"])
            w.writerows(sorted(flat, key=lambda x: (x[1].lower(), x[0].lower())))
        print(f"Wrote {path}\n")


if __name__ == "__main__":
    main()
