#!/usr/bin/env python3
"""
tldialer_live_agents — full shape (READ-ONLY).

Confirmed reachable at tldialer/tldialer_live_agents with a real live_status field. This
pulls everyone currently logged in to see the full set of status values, whether it
covers READY/PAUSED as well as INCALL, and every column available.

Usage:
  python3 sandbox/probes/probe_tldialer_live_agents.py
"""
import os
import sys
import json
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

NAME = "tldialer/tldialer_live_agents"


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

    resp = config.egress_get(NAME, {"limit": 500}, timeout=60)
    rows = [r for r in rows_of(resp) if isinstance(r, dict)]
    print(f"pulled {len(rows)} row(s) total (this should be everyone currently logged in)\n")
    if not rows:
        print("no rows — nobody logged in right now, or needs explicit columns like vicidial_users did")
        resp2 = config.egress_get(NAME, {"columns": ["user", "agent_full_name", "live_status",
                                   "extension", "campaign_id", "last_state_duration"],
                                   "limit": 500}, timeout=60)
        rows = [r for r in rows_of(resp2) if isinstance(r, dict)]
        print(f"with explicit columns: {len(rows)} row(s)")

    if rows:
        print("ALL columns:", sorted(rows[0].keys()))
        print("\nlive_status values:", dict(Counter(str(r.get("live_status") or "(blank)") for r in rows)))
        print("\nfull rows:")
        for r in rows:
            print(f"  user={r.get('user'):<8} {r.get('agent_full_name'):<24} "
                  f"status={r.get('live_status'):<12} dur={r.get('last_state_duration'):<10} "
                  f"campaign={r.get('campaign_campaign_name') or r.get('campaign_id')!s:<20} "
                  f"ext={r.get('extension')} calls_today={r.get('calls_today')} "
                  f"phone={r.get('call_phone_number')}")


if __name__ == "__main__":
    main()
