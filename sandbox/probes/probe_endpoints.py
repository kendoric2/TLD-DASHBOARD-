"""
Discover ALL egress endpoints (read-only).

Hits /api/egress/endpoints, prints the full list, flags the call/dialer-grain
candidates (where 'billable calls' — your 430 — would live), and for each candidate
tries /docs/columns to check for a billable flag + a date field.

    python3 sandbox/probes/probe_endpoints.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import _probe_lib as p

config.require_creds()

CALLISH = ("dial", "call", "cdr", "log", "agentcpa", "transfer", "queue", "phone", "recording")

p.hr("/api/egress/endpoints")
raw = config.egress_get("endpoints")

# 1) Show the raw list exactly as returned (handle dict, or list of short key/value pairs).
pairs = []   # (key, value)
if isinstance(raw, dict):
    pairs = [(str(k), v) for k, v in raw.items()]
elif isinstance(raw, list):
    for i, x in enumerate(raw):
        if isinstance(x, dict):
            pairs += [(str(k), v) for k, v in x.items()]
        else:
            pairs.append((str(i), x))
else:
    print("  unexpected shape:", str(raw)[:300])

print(f"{len(pairs)} entries:\n")
for k, v in pairs:
    line = f"  {k:24} {v}"
    if any(c in (str(k) + ' ' + str(v)).lower() for c in CALLISH):
        line += "    <-- call-ish?"
    print(line)

# 2) Inspect the call-ish candidates' columns for a billable flag + a date field.
cands = []
for k, v in pairs:
    blob = (str(k) + " " + str(v)).lower()
    if any(c in blob for c in CALLISH):
        for cand in (v, k):                      # try the value as a path first, then the key
            if isinstance(cand, str) and cand.strip():
                cands.append(cand.strip().strip("/"))
                break
cands = list(dict.fromkeys(cands))[:8]

print(f"\nInspecting {len(cands)} candidate endpoint(s) for billable + date columns:")
for e in cands:
    print(f"\n--- {e} ---")
    try:
        cols = p.cols_of(e)
    except Exception as ex:
        print(f"  /docs/columns failed: {type(ex).__name__}: {str(ex)[:90]}")
        continue
    if not cols:
        print("  (no columns returned — may need the exact path)")
        continue
    bill = [c for c in cols if "billable" in str(c).lower()]
    call = [c for c in cols if "call" in str(c).lower()]
    dates = [c for c in cols if "date" in str(c).lower()][:8]
    print(f"  cols: {len(cols)} | billable: {bill or '(none)'}")
    print(f"  call-ish: {call[:10] or '(none)'}")
    print(f"  dates: {dates or '(none)'}")

print("\nPaste this back — we'll point at the one with a billable flag + a date field and count today (target ~430).")
