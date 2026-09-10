#!/usr/bin/env python3
"""
Live Agents board — round 2 (READ-ONLY).

Round 1 found 4 of 5 candidate tables reachable. This digs into the ones we'd actually
need to assemble a live board:
  - vicidial_agent_log: what status/sub_status values show up, and can we get "current
    status per agent" by taking each agent's most recent row?
  - vicidial_auto_calls: full columns for whatever's active right now — does it carry an
    agent identity directly, or only extension/channel info we'd have to join?
  - vicidial_users: full column list, specifically hunting for a phone extension / login
    field that could join to vicidial_auto_calls.

Usage:
  python3 sandbox/probes/probe_live_agents_detail.py
"""
import os
import sys
import json
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402


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

    print("=" * 78)
    print("1) vicidial_agent_log — recent activity, status values, latest-per-agent")
    print("=" * 78)
    resp = config.egress_get("tldialer/vicidial_agent_log", {"limit": 500}, timeout=60)
    rows = [r for r in rows_of(resp) if isinstance(r, dict)]
    print(f"pulled {len(rows)} rows (most recent {min(len(rows), 500)})")
    if rows:
        print("columns:", sorted(rows[0].keys()))
        status_counts = Counter(str(r.get("status") or "(blank)") for r in rows)
        sub_counts = Counter(str(r.get("sub_status") or "(blank)") for r in rows)
        print("status values:", dict(status_counts))
        print("sub_status values:", dict(sub_counts))

        latest = {}
        for r in rows:
            u = r.get("user")
            t = str(r.get("event_time") or "")
            if u and (u not in latest or t > latest[u]["event_time"]):
                latest[u] = r
        print(f"\ndistinct agents (user id) seen in this pull: {len(latest)}")
        print("most recent event per agent (up to 15 shown):")
        for u, r in list(sorted(latest.items(), key=lambda kv: kv[1]["event_time"], reverse=True))[:15]:
            print(f"  user={u:<8} time={r.get('event_time')}  status={r.get('status')}  "
                  f"sub_status={r.get('sub_status')}  campaign={r.get('campaign_id')}  "
                  f"lead_id={r.get('lead_id')}  comments={r.get('comments')}")

    print("\n" + "=" * 78)
    print("2) vicidial_auto_calls — everything active right now, full columns")
    print("=" * 78)
    resp = config.egress_get("tldialer/vicidial_auto_calls", {"limit": 50}, timeout=60)
    rows = [r for r in rows_of(resp) if isinstance(r, dict)]
    print(f"pulled {len(rows)} row(s) (this is basically 'calls happening right now')")
    for r in rows:
        print(json.dumps(r, indent=2, default=str))

    print("\n" + "=" * 78)
    print("3) vicidial_users — full column list + a few sample rows (hunting for an")
    print("   extension / phone_login field to join against vicidial_auto_calls)")
    print("=" * 78)
    resp = config.egress_get("tldialer/vicidial_users", {"limit": 500}, timeout=60)
    rows = [r for r in rows_of(resp) if isinstance(r, dict)]
    print(f"pulled {len(rows)} agent rows")
    if rows:
        print("ALL columns:", sorted(rows[0].keys()))
        ext_cols = [c for c in rows[0].keys() if any(w in c.lower() for w in
                    ("phone", "ext", "sip", "login", "voip"))]
        print("\nphone/extension-ish columns:", ext_cols)
        print("\nsample of those columns for first 10 users:")
        for r in rows[:10]:
            print(f"  user={r.get('user_id')} ({r.get('full_name')}): " +
                  ", ".join(f"{c}={r.get(c)!r}" for c in ext_cols))


if __name__ == "__main__":
    main()
