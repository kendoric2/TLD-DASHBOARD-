#!/usr/bin/env python3
"""
Can we resolve TLD lead_id from a live call's phone number? (READ-ONLY)

The live-agents board wants to show lead_id instead of the raw phone number for anyone
INCALL, but tldialer_live_agents doesn't carry lead_id — only call_phone_number. This
checks whether the leads endpoint can be filtered by phone (single value, and an array
of values in one call, to see if we can batch-resolve everyone INCALL in one request
instead of one request per agent).

Usage:
  python3 sandbox/probes/probe_lead_id_by_phone.py
"""
import os
import sys
import json
import time

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
    print("1) Grab a few phone numbers currently INCALL")
    print("=" * 78)
    live_resp = config.egress_get("tldialer/tldialer_live_agents", {
        "columns": ["user", "agent_full_name", "live_status", "call_phone_number"],
        "limit": 1000}, timeout=60)
    live = [r for r in rows_of(live_resp) if isinstance(r, dict)]
    incall = [r for r in live if str(r.get("live_status")).upper() == "INCALL"
             and r.get("call_phone_number")]
    print(f"{len(incall)} agents INCALL with a phone number")
    phones = [r["call_phone_number"] for r in incall[:5]]
    print("sample phones:", phones)

    print("\n" + "=" * 78)
    print("2) Single-phone lookup against leads")
    print("=" * 78)
    if phones:
        t0 = time.time()
        resp = config.egress_get("leads", {"columns": ["lead_id", "phone", "date_created"],
                                 "phone": phones[0], "limit": 5}, timeout=30)
        ms = int((time.time() - t0) * 1000)
        rows = rows_of(resp)
        print(f"phone={phones[0]}  ({ms} ms)  rows: {rows}")

    print("\n" + "=" * 78)
    print("3) Batch lookup — does 'phone' accept a list?")
    print("=" * 78)
    if len(phones) > 1:
        t0 = time.time()
        resp = config.egress_get("leads", {"columns": ["lead_id", "phone"],
                                 "phone": phones, "limit": 50}, timeout=30)
        ms = int((time.time() - t0) * 1000)
        print(f"phones={phones}  ({ms} ms)")
        print(f"response: {json.dumps(resp, default=str)[:500]}")


if __name__ == "__main__":
    main()
