#!/usr/bin/env python3
"""
Which of these endpoints are actually reachable, and what's in them? (READ-ONLY)

The endpoint LISTING is blocked on this key ("This API is Not Allowed to Access this
Endpoint"), so we can't enumerate what's enabled — we have to knock on each door. This
tries the candidates that matter for the Vendors tab (and a few bonuses), reports which
respond, and dumps the columns that look like dispositions / vendor links / dates.

Nothing here writes. An endpoint that isn't enabled just returns an error and we move on.

Usage:
  python3 sandbox/probes/probe_endpoint_hunt.py
"""
import os
import sys
import json
import time
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

TODAY = datetime.date.today()
WEEK_AGO = TODAY - datetime.timedelta(days=7)
S0, E1 = f"{WEEK_AGO} 00:00:00", f"{TODAY} 23:59:59"

# Ordered by how likely they are to hold call dispositions / vendor billing events.
CANDIDATES = [
    ("dialer_leads",       "dialer's own lead record — most likely home of dispo codes"),
    ("lead_logs",          "per-lead event history — status changes over time"),
    ("vendor_logs",        "vendor posting/billing events — why a lead became billable"),
    ("lead_dialer_leads",  "join table: TLD lead <-> dialer lead"),
    ("callbacks",          "scheduled callbacks"),
    ("dnc",                "do-not-call entries"),
    ("change_logs",        "generic change log"),
    ("commission_paid",    "bonus: richer chargeback detail than the policy fields"),
    ("user_groups",        "bonus: proper groups for the agents-by-group tool"),
    ("user_group_members", "bonus: group membership"),
]

# Column names worth calling out if we find them.
INTERESTING = ("dispo", "status", "vendor", "lead_id", "date", "called", "call",
               "billable", "phone", "list_id", "agent", "user", "group", "amount",
               "chargeback", "reason", "code")


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


def try_endpoint(name, why):
    print(f"\n{'-' * 74}\n{name}\n   ({why})")
    # a few body shapes: bare, tiny limit, and a recent date window
    for body in ({"limit": 1},
                 {"limit": 1, "date_created": S0, "date_created_end": E1},
                 {"limit": 1, "date": S0, "date_end": E1},
                 None):
        t0 = time.time()
        try:
            resp = config.egress_get(name, body, timeout=60)
        except Exception as e:
            print(f"   body={json.dumps(body) if body else 'none':<52} EXCEPTION {type(e).__name__}")
            continue
        ms = int((time.time() - t0) * 1000)
        if blocked(resp):
            print(f"   NOT ACCESSIBLE: {json.dumps(resp)[:110]}")
            return None                      # same answer for every body shape
        rows = rows_of(resp)
        if rows and isinstance(rows[0], dict):
            cols = sorted(rows[0].keys())
            print(f"   REACHABLE ({ms} ms, {len(cols)} columns)")
            hits = [c for c in cols if any(w in c.lower() for w in INTERESTING)]
            print(f"   relevant columns: {hits[:28]}")
            for c in cols:
                lc = c.lower()
                if "dispo" in lc or lc in ("status", "status_name"):
                    print(f"      >>> {c} = {rows[0].get(c)!r}")
            return cols
        print(f"   reachable but 0 rows for body={json.dumps(body) if body else 'none'} ({ms} ms)")
    return []


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nENDPOINT HUNT — what's actually enabled on this key?\n{'=' * 74}")
    print(f"(sampling 1 row each; recent window {WEEK_AGO} .. {TODAY})")

    found, missing = [], []
    for name, why in CANDIDATES:
        cols = try_endpoint(name, why)
        (found if cols is not None else missing).append(name)

    print(f"\n{'=' * 74}\nSUMMARY")
    print(f"  reachable    : {', '.join(found) if found else '(none)'}")
    print(f"  NOT allowed  : {', '.join(missing) if missing else '(none)'}")
    if missing:
        print("\n  To use the blocked ones, ask whoever administers TLD to enable them for")
        print("  this API key — they're read-only endpoints, same as the ones we already use.")
    print()


if __name__ == "__main__":
    main()
