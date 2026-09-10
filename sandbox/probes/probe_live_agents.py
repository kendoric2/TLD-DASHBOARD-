#!/usr/bin/env python3
"""
Live Agents board — endpoint hunt (READ-ONLY).

Checks whether the dialer's real-time agent tables are reachable on this API key, the
same way probe_endpoint_hunt.py checked the CRM-side candidates. Tries each name both
bare and under the "tldialer/" namespace (tldialer_call_log needs that prefix — see
CALL_LOG in src/tldcrm_client.py — so a genuine VICIdial table likely does too).

Nothing here writes. An endpoint that isn't enabled just returns an error and we move on.

Usage:
  python3 sandbox/probes/probe_live_agents.py
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

# name -> what it should hold if it's the real VICIdial table
CANDIDATES = [
    ("vicidial_live_agents", "real-time: which agent, which campaign, current status, current lead"),
    ("vicidial_agent_log",   "per-session history: talk/pause/wait time, login/logout"),
    ("vicidial_users",       "agent roster tied to campaigns (closer flag, etc.)"),
    ("vicidial_hopper",      "leads queued to be dialed right now"),
    ("vicidial_auto_calls",  "calls actively connecting via the dialer"),
]

INTERESTING = ("status", "agent", "user", "campaign", "lead_id", "call_id", "channel",
               "extension", "server", "time", "date", "pause", "talk", "wait", "comment")


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def blocked(resp):
    return (isinstance(resp, dict)
            and set(k.lower() for k in resp.keys()) <= {"error", "message", "status", "code"})


def try_one(name):
    for body in ({"limit": 5}, None):
        t0 = time.time()
        try:
            resp = config.egress_get(name, body, timeout=60)
        except Exception as e:
            print(f"   body={json.dumps(body) if body else 'none':<16} EXCEPTION {type(e).__name__}: {e}")
            continue
        ms = int((time.time() - t0) * 1000)
        if blocked(resp):
            print(f"   NOT ACCESSIBLE ({ms} ms): {json.dumps(resp)[:120]}")
            return None
        rows = rows_of(resp)
        if rows and isinstance(rows[0], dict):
            cols = sorted(rows[0].keys())
            print(f"   REACHABLE ({ms} ms, {len(rows)} row(s), {len(cols)} columns)")
            hits = [c for c in cols if any(w in c.lower() for w in INTERESTING)]
            print(f"   relevant columns: {hits}")
            print(f"   sample row: {json.dumps(rows[0], default=str)[:400]}")
            return cols
        print(f"   reachable but 0 rows ({ms} ms, body={json.dumps(body) if body else 'none'})")
    return []


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    print(f"\nLIVE AGENTS — endpoint hunt\n{'=' * 74}")
    found, missing = [], []
    for name, why in CANDIDATES:
        print(f"\n{'-' * 74}\n{name}\n   ({why})")
        for variant in (f"tldialer/{name}", name):
            print(f"  trying: {variant}")
            cols = try_one(variant)
            if cols is not None and cols != []:
                found.append(variant)
                break
        else:
            missing.append(name)

    print(f"\n{'=' * 74}\nSUMMARY")
    print(f"  reachable   : {', '.join(found) if found else '(none)'}")
    print(f"  NOT reachable / empty: {', '.join(missing) if missing else '(none)'}")
    print()


if __name__ == "__main__":
    main()
