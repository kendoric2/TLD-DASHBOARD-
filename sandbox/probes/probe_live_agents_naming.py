#!/usr/bin/env python3
"""
Live agents — is it named vicidial_live_agents or tldialer_live_agents? (READ-ONLY)

tldialer_call_log follows a "tldialer_*" naming pattern, not "vicidial_*" — worth checking
whether the live-status table follows the same convention before concluding it's blocked.

Usage:
  python3 sandbox/probes/probe_live_agents_naming.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

CANDIDATES = [
    "tldialer/tldialer_live_agents",
    "tldialer_live_agents",
    "tldialer/vicidial_live_agents",
    "vicidial_live_agents",
    "tldialer/live_agents",
    "live_agents",
]


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
    for name in CANDIDATES:
        try:
            resp = config.egress_get(name, {"limit": 5}, timeout=30)
        except Exception as e:
            print(f"{name:<32} EXCEPTION {type(e).__name__}: {e}")
            continue
        blocked = isinstance(resp, dict) and set(k.lower() for k in resp.keys()) <= {"error", "message", "status", "code"}
        if blocked:
            print(f"{name:<32} NOT ACCESSIBLE: {json.dumps(resp)}")
            continue
        rows = rows_of(resp)
        if rows and isinstance(rows[0], dict):
            print(f"{name:<32} REACHABLE — {len(rows)} row(s), columns: {sorted(rows[0].keys())}")
            print(f"    sample: {json.dumps(rows[0], default=str)[:300]}")
        else:
            print(f"{name:<32} reachable but 0 rows")


if __name__ == "__main__":
    main()
