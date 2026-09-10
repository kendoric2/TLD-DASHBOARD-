#!/usr/bin/env python3
"""
Live Agents board — round 3 (READ-ONLY).

Round 2 found vicidial_users returning only 1 row (the system dialer account) despite
limit=500 — likely needs an explicit "columns" list like other TLD tables. Also checks
whether an active call's lead_id can be joined back to an agent via vicidial_agent_log,
since vicidial_auto_calls itself carries no agent/user field.

Usage:
  python3 sandbox/probes/probe_live_agents_round3.py
"""
import os
import sys
import json

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
    print("1) vicidial_users WITH explicit columns")
    print("=" * 78)
    body = {"columns": ["user_id", "full_name", "user_group", "phone_login",
                        "user_level", "active", "last_login_date"], "limit": 500}
    resp = config.egress_get("tldialer/vicidial_users", body, timeout=60)
    rows = [r for r in rows_of(resp) if isinstance(r, dict)]
    print(f"pulled {len(rows)} rows")
    active = [r for r in rows if str(r.get("active", "")).upper() not in ("N", "0")]
    print(f"  active: {len(active)}   inactive/other: {len(rows) - len(active)}")
    for r in rows[:15]:
        print(f"  {r}")

    print("\n" + "=" * 78)
    print("2) vicidial_auto_calls right now (again, to see if it's still that 1 call")
    print("   or a different one), then hunt vicidial_agent_log for its lead_id")
    print("=" * 78)
    resp = config.egress_get("tldialer/vicidial_auto_calls", {"limit": 50}, timeout=60)
    calls = [r for r in rows_of(resp) if isinstance(r, dict)]
    print(f"active right now: {len(calls)}")
    for c in calls:
        lead_id = c.get("lead_id")
        print(f"\n  auto_call lead_id={lead_id} status={c.get('status')} "
              f"campaign={c.get('campaign_id')} call_time={c.get('call_time')}")
        if not lead_id:
            continue
        log_resp = config.egress_get("tldialer/vicidial_agent_log",
                                     {"lead_id": lead_id, "limit": 20}, timeout=60)
        log_rows = [r for r in rows_of(log_resp) if isinstance(r, dict)]
        print(f"  matching vicidial_agent_log rows for this lead_id: {len(log_rows)}")
        for r in sorted(log_rows, key=lambda r: str(r.get("event_time") or ""), reverse=True)[:5]:
            print(f"    user={r.get('user')} time={r.get('event_time')} "
                  f"status={r.get('status')} sub_status={r.get('sub_status')}")

    print("\n" + "=" * 78)
    print("3) vicidial_agent_log filtered to sub_status=GRABCL in the last 30 min")
    print("   (agents who most recently grabbed a call — best proxy for 'on a call now')")
    print("=" * 78)
    import datetime
    now = datetime.datetime.now()
    since = (now - datetime.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    resp = config.egress_get("tldialer/vicidial_agent_log",
                             {"limit": 500, "event_time": since}, timeout=60)
    rows = [r for r in rows_of(resp) if isinstance(r, dict)]
    print(f"rows in the last 30 min: {len(rows)}")
    grabs = [r for r in rows if r.get("sub_status") == "GRABCL"]
    print(f"GRABCL events: {len(grabs)}")
    for r in grabs[:15]:
        print(f"  user={r.get('user')} time={r.get('event_time')} lead_id={r.get('lead_id')} "
              f"campaign={r.get('campaign_id')}")


if __name__ == "__main__":
    main()
