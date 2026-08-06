#!/usr/bin/env python3
"""
Can we attach SEP to a set of policies cheaply? (READ-ONLY)

SEP lives on the LEAD (`sep`), not the policy, so the agent-detail view has to join
policy.lead_id -> lead.sep. This probe finds the cheapest join by testing whether the
leads endpoint accepts a lead_id filter — and crucially whether it accepts a BATCH of
ids in one call.

IMPORTANT: it doesn't just check that rows come back — it checks the returned lead_ids
actually MATCH what we asked for. (TLD has silently ignored a filter before and returned
the whole table, which is how the bogus "100% MCD" result happened.)

Usage:
  python3 sandbox/probes/probe_lead_join.py [START] [END]   # defaults to the last 14 days
"""
import os
import sys
import json
import time
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

END = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
START = sys.argv[1] if len(sys.argv) > 1 else (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
S0, E1 = f"{START} 00:00:00", f"{END} 23:59:59"


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def attempt(label, body, want_ids):
    """Run one leads query and report whether the filter was actually honored."""
    print(f"\n--- {label}")
    print(f"    body: {json.dumps(body)[:150]}")
    t0 = time.time()
    try:
        rows = rows_of(config.egress_get("leads", body, timeout=90))
    except Exception as e:
        print(f"    FAILED: {type(e).__name__}: {str(e)[:120]}")
        return False
    ms = int((time.time() - t0) * 1000)
    got = [str(r.get("lead_id")) for r in rows if isinstance(r, dict)]
    want = {str(i) for i in want_ids}
    matched = want.intersection(got)
    print(f"    returned {len(rows)} rows in {ms} ms")
    if not rows:
        print("    -> no rows (filter form probably not supported)")
        return False
    if len(rows) > len(want) * 3:
        print(f"    -> !! FILTER IGNORED — asked for {len(want)} lead(s), got {len(rows)} rows")
        return False
    print(f"    -> matched {len(matched)}/{len(want)} requested ids")
    for r in rows[:5]:
        if isinstance(r, dict):
            print(f"       lead_id={r.get('lead_id')}  sep={r.get('sep')!r}")
    return len(matched) > 0


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    # 1. Grab a few real sold policies to get real lead_ids to test with
    pol = rows_of(config.egress_get("policies", {
        "columns": ["policy_id", "lead_id", "agent_name", "carrier_name"], "sold": 1,
        "date": S0, "date_end": E1, "date_sold": S0, "date_sold_end": E1, "limit": 8}, timeout=90))
    ids = [r.get("lead_id") for r in pol if isinstance(r, dict) and r.get("lead_id")]
    ids = list(dict.fromkeys(ids))[:5]
    print(f"\nSEP JOIN PROBE   {START} .. {END}\n" + "=" * 68)
    print(f"test lead_ids from real policies: {ids}")
    if not ids:
        print("No policies found in this range — try a wider date range.")
        return

    results = {}
    cols = ["lead_id", "sep"]

    # 2. One lead at a time  (worst case: N calls for N policies)
    results["single"] = attempt("A. single lead_id", {"columns": cols, "lead_id": ids[0]}, [ids[0]])

    # 3. A batch as a JSON list  (best case: 1 call for the whole page)
    results["list"] = attempt("B. batch as a list", {"columns": cols, "lead_id": ids}, ids)

    # 4. A batch as a comma string  (some APIs want this instead)
    results["csv"] = attempt("C. batch as comma string",
                             {"columns": cols, "lead_id": ",".join(str(i) for i in ids)}, ids)

    # 5. Fallback: pull the whole lead window and join client-side
    print("\n--- D. fallback: pull all leads by date_created and join in memory")
    t0 = time.time()
    try:
        allrows = rows_of(config.egress_get("leads", {
            "columns": cols, "date_created": S0, "date_created_end": E1, "limit": 200000}, timeout=240))
        ms = int((time.time() - t0) * 1000)
        have = {str(r.get("lead_id")) for r in allrows if isinstance(r, dict)}
        hit = sum(1 for i in ids if str(i) in have)
        print(f"    pulled {len(allrows):,} leads in {ms:,} ms; {hit}/{len(ids)} test ids present")
        print("    (ids missing here = lead created BEFORE this window — the date-window trap)")
        results["fallback"] = hit == len(ids)
    except Exception as e:
        print(f"    FAILED: {type(e).__name__}: {str(e)[:120]}")
        results["fallback"] = False

    print("\n" + "=" * 68)
    print("VERDICT")
    if results.get("list") or results.get("csv"):
        form = "a JSON list" if results.get("list") else "a comma string"
        print(f"  BEST: the leads endpoint accepts a BATCH of lead_ids as {form}.")
        print("  -> one extra call per agent view. SEP column is cheap. Build it.")
    elif results.get("single"):
        print("  Only ONE lead per call works.")
        print("  -> fine for a single agent's page (~50-150 calls, batched a few at a time),")
        print("     but too many for a whole-dashboard SEP view.")
    elif results.get("fallback"):
        print("  No id filter, but pulling the lead window and joining in memory works.")
        print("  -> needs a WIDER lead window than the sale window (a July sale can come")
        print("     from a June lead), so we'd over-pull a bit.")
    else:
        print("  None of the join forms worked — we'd need another route to SEP.")
    print()


if __name__ == "__main__":
    main()
