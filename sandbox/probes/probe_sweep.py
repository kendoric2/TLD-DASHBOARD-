#!/usr/bin/env python3
"""
PRE-LAUNCH SWEEP (READ-ONLY) — walk several date ranges and check every tile.

Run this before sharing the dashboard with anyone. For each range it hits the real
endpoints the browser hits and checks:

  • nothing renders blank  — every tile has data when the range has sales
  • the numbers reconcile  — carrier / state / agent / active totals agree with Policies Sold
  • the CPA report answers — Billable Calls / Spend / CPA aren't silently zero
  • the sales board agrees — board totals match the dashboard's

Ranges checked: today, week-to-date, month-to-date, last month, last quarter, last year.

Usage:
  python3 sandbox/probes/probe_sweep.py                 # against a running server (default)
  python3 sandbox/probes/probe_sweep.py --port 5050     # if you changed the port
"""
import sys
import json
import datetime
import urllib.request
import urllib.parse

PORT = 5050
if "--port" in sys.argv:
    PORT = int(sys.argv[sys.argv.index("--port") + 1])
BASE = f"http://localhost:{PORT}"

OK, WARN, BAD = "  ok  ", " WARN ", " FAIL "
issues = []


def get(path, params):
    url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=300) as r:
        return json.loads(r.read().decode())


def ranges():
    t = datetime.date.today()
    som = t.replace(day=1)
    last_month_end = som - datetime.timedelta(days=1)
    q_start = datetime.date(t.year, 3 * ((t.month - 1) // 3) + 1, 1)
    last_q_end = q_start - datetime.timedelta(days=1)
    last_q_start = datetime.date(last_q_end.year, 3 * ((last_q_end.month - 1) // 3) + 1, 1)
    return [
        ("today", t, t),
        ("week-to-date", t - datetime.timedelta(days=t.weekday() + 1 if t.weekday() != 6 else 0), t),
        ("month-to-date", som, t),
        ("last month", last_month_end.replace(day=1), last_month_end),
        ("last quarter", last_q_start, last_q_end),
        ("last year", datetime.date(t.year - 1, 1, 1), datetime.date(t.year - 1, 12, 31)),
    ]


def check(label, cond, msg, level=BAD):
    if cond:
        print(f"    [{OK}] {msg}")
        return True
    print(f"    [{level}] {msg}")
    issues.append(f"{label}: {msg}")
    return False


def sweep(label, start, end):
    s, e = start.isoformat(), end.isoformat()
    print(f"\n{'=' * 70}\n{label.upper()}   {s} .. {e}\n{'=' * 70}")
    p = {"range": "custom", "start": s, "end": e}

    d = get("/api/dashboard", p)
    if d.get("demo"):
        print("    [ WARN ] server is in DEMO mode — start it with .env configured")
        return
    if d.get("error"):
        check(label, False, f"dashboard error: {d['error']}")

    k = d.get("kpis") or {}
    sold = k.get("policies_sold") or 0
    carriers = d.get("by_carrier") or []
    states = d.get("by_state") or []
    agents = d.get("agents") or []
    active = d.get("active_by_carrier") or []
    enroll = d.get("enrollments") or {}
    print(f"    policies sold: {sold:,}   carriers: {len(carriers)}   states: {len(states)}   agents: {len(agents)}")

    if sold == 0:
        print("    (no sales in this range — skipping reconciliation)")
        return

    # every tile populated
    check(label, carriers, "carrier chart has data")
    check(label, states, "state map has data")
    check(label, agents, "agent table has data")
    check(label, active, "active-policies tile has data")
    check(label, enroll.get("by_enroller") is not None, "enrollments tile present")

    # reconciliation: carrier total (incl GTL) >= Policies Sold (which excludes GTL)
    ctot = sum(c.get("count", 0) for c in carriers)
    check(label, ctot >= sold, f"carrier total {ctot:,} >= policies sold {sold:,} (GTL included)")

    # agents sum exactly to Policies Sold (same deduped, GTL-excluded basis)
    atot = sum(a.get("policies", 0) for a in agents)
    check(label, atot == sold, f"agent policies {atot:,} == policies sold {sold:,}",
          level=WARN if abs(atot - sold) <= 2 else BAD)

    # states sum to Policies Sold minus rows with no state
    stot = sum(x.get("count", 0) for x in states)
    check(label, stot <= sold, f"state total {stot:,} <= policies sold {sold:,}")

    # active tile reconciles with the carrier chart
    asold = sum(x.get("sold", 0) for x in active)
    check(label, asold == ctot, f"active-tile sold {asold:,} == carrier total {ctot:,}")

    # CPA report actually answered
    cpa = get("/api/agent_cpa", dict(p, force="1"))
    tot = cpa.get("totals") or {}
    if cpa.get("error"):
        check(label, False, f"agent_cpa error: {cpa['error']}")
    check(label, cpa.get("by_agent"), f"CPA report returned agents ({len(cpa.get('by_agent') or {})})")
    check(label, (tot.get("billable_calls") or 0) > 0,
          f"billable calls = {tot.get('billable_calls', 0):,}", level=WARN)
    check(label, (tot.get("cost") or 0) > 0, f"total spend = ${tot.get('cost', 0):,}", level=WARN)

    # sales board agrees with the dashboard
    b = get("/api/sales_board", p)
    board = b.get("board") or []
    closed = sum(x.get("closed", 0) for x in board)
    check(label, board, f"sales board has {len(board)} people")
    check(label, closed == ctot, f"board closed {closed:,} == carrier total {ctot:,}",
          level=WARN if abs(closed - ctot) <= 2 else BAD)


def main():
    print(f"\nPRE-LAUNCH SWEEP against {BASE}")
    print("(start the dashboard first: python3 src/app.py)")
    try:
        urllib.request.urlopen(f"{BASE}/health", timeout=10)
    except Exception as ex:
        print(f"\nCannot reach {BASE} — is the server running?  ({ex})\n")
        return
    for label, s, e in ranges():
        try:
            sweep(label, s, e)
        except Exception as ex:
            print(f"    [{BAD}] {label} blew up: {type(ex).__name__}: {ex}")
            issues.append(f"{label}: {type(ex).__name__}: {ex}")

    print(f"\n{'=' * 70}")
    if issues:
        print(f"{len(issues)} thing(s) to look at:\n")
        for i in issues:
            print(f"  • {i}")
    else:
        print("ALL CHECKS PASSED — every range populated and reconciled.")
    print()


if __name__ == "__main__":
    main()
