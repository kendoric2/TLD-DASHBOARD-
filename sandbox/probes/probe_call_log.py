#!/usr/bin/env python3
"""
The REAL call disposition source: tldialer/tldialer_call_log (READ-ONLY).

TLD pointed us here. We'd been using lead_logs (action='status'), which records LEAD STATUS
changes — a decent stand-in, but not the same thing as per-call dispositions. The call log
is one row per call with the disposition the dialer recorded (e.g. AA = answering machine).

Also confirmed by TLD: "System Process" is a USER, not a disposition — it's the system
dispositioning a call a human never received (auto-dial reaches an answering machine, agents
only get live answers).

This checks whether we can build on it:
  1. columns + a sample row
  2. volume per day (lead_logs is ~22k/day, so this could be much larger)
  3. which filters are HONORED (date, agent, vendor, disposition) — each tested with an
     impossible value that must return zero
  4. the disposition distribution, and how much is System vs human

Usage:
  python3 sandbox/probes/probe_call_log.py [DAYS]      # default 1 (yesterday)
"""
import os
import sys
import json
import time
import datetime
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402

EP = "tldialer/tldialer_call_log"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 1
END = datetime.date.today() - datetime.timedelta(days=1)
START = END - datetime.timedelta(days=DAYS - 1)


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def blocked(resp):
    return isinstance(resp, dict) and set(k.lower() for k in resp.keys()) <= {
        "error", "message", "status", "code"}


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return
    print(f"\nCALL LOG PROBE — {EP}\n{'=' * 74}")

    # ---- 1. is it reachable, and what's in it? --------------------------------------
    print("\n1. Reachable? Columns?")
    try:
        docs = config.egress_get(f"{EP}/docs/columns", None, timeout=60)
    except Exception as e:
        docs = {"error": f"{type(e).__name__}: {e}"}
    cols = [c for c in docs if isinstance(c, str)] if isinstance(docs, list) else []
    if cols:
        print(f"   /docs/columns: {len(cols)} columns")
    else:
        print(f"   /docs/columns unavailable: {json.dumps(docs)[:110] if docs else 'none'}")

    try:
        sample = config.egress_get(EP, {"limit": 1}, timeout=60)
    except Exception as e:
        print(f"   ENDPOINT FAILED: {type(e).__name__}: {str(e)[:90]}")
        return
    if blocked(sample):
        print(f"   NOT ACCESSIBLE: {json.dumps(sample)[:130]}")
        print("   -> ask TLD to enable it (and its /docs/columns) for this key.")
        return
    rows = rows_of(sample)
    if rows and isinstance(rows[0], dict):
        got = sorted(rows[0].keys())
        cols = cols or got
        print(f"   sample row has {len(got)} column(s)")
        want = ("status", "dispo", "user", "agent", "lead", "vendor", "date", "call",
                "length", "talk", "phone", "campaign", "list", "hangup")
        print(f"   relevant: {[c for c in cols if any(w in c.lower() for w in want)][:30]}")
        for c in got:
            print(f"      {c:<32} {str(rows[0].get(c))[:44]}")

    # ---- 2. volume + which date field filters ---------------------------------------
    print("\n2. Volume and date filtering")
    date_fields = [c for c in cols if c.lower().startswith("date") or "date" in c.lower()][:4]
    print(f"   candidate date fields: {date_fields}")

    def pull(label, body, timeout=240):
        t0 = time.time()
        try:
            r = rows_of(config.egress_get(EP, body, timeout=timeout))
        except Exception as e:
            print(f"   {label:<44} FAILED: {str(e)[:50]}")
            return None
        print(f"   {label:<44} {len(r):>8,} rows ({int((time.time()-t0)*1000):,} ms)")
        return r

    base, used_field = None, None
    for f in date_fields or ["call_date", "date_created"]:
        got = pull(f"filter on {f}", {"limit": 200000,
                                      f: f"{START} 00:00:00", f + "_end": f"{END} 23:59:59"})
        if got:
            base, used_field = got, f
            break
    if not base:
        print("   -> could not filter by date; ask TLD which date field to use.")
        return
    print(f"   -> using '{used_field}'  (~{len(base) / max(DAYS,1):,.0f} calls/day, "
          f"~{len(base) / max(DAYS,1) * 30:,.0f}/month)")
    impossible = pull("same field, year 2099 (expect 0)",
                      {"limit": 100, used_field: "2099-01-01 00:00:00",
                       used_field + "_end": "2099-12-31 23:59:59"})
    print(f"   -> date filter: {'HONORED' if impossible is not None and not impossible else 'NOT honored'}")

    # ---- 3. what's in it ------------------------------------------------------------
    print("\n3. Dispositions and who set them")
    first = base[0] if isinstance(base[0], dict) else {}
    dispo_col = next((c for c in ("status", "dispo", "disposition", "status_name")
                      if c in first), None)
    user_col = next((c for c in ("user", "user_full_name", "agent", "user_id") if c in first), None)
    print(f"   disposition column: {dispo_col or '?'}    user column: {user_col or '?'}")
    if dispo_col:
        d = Counter(str(r.get(dispo_col) or "(blank)") for r in base if isinstance(r, dict))
        print(f"\n   {len(d)} distinct dispositions:")
        for k, v in d.most_common(20):
            print(f"      {k[:30]:<32}{v:>8,}  ({v / len(base) * 100:4.1f}%)")
    if user_col:
        u = Counter(str(r.get(user_col) or "(blank)") for r in base if isinstance(r, dict))
        sysn = sum(v for k, v in u.items() if "system" in k.lower() or k in ("0", "0.0"))
        print(f"\n   {len(u)} distinct users; System Process = {sysn:,} "
              f"({sysn / len(base) * 100:.1f}%) — calls no agent received")
        for k, v in u.most_common(6):
            print(f"      {k[:30]:<32}{v:>8,}")

    # ---- 4. can we scope it? --------------------------------------------------------
    print("\n4. Can we filter it down (so a tile doesn't pull the whole log)?")
    for col, val in ((user_col, (base[0] or {}).get(user_col)),
                     ("vendor_id", None), (dispo_col, (base[0] or {}).get(dispo_col))):
        if not col or val in (None, ""):
            continue
        ok = pull(f"{col} = {str(val)[:18]}", {"limit": 200000, col: val,
                                               used_field: f"{START} 00:00:00",
                                               used_field + "_end": f"{END} 23:59:59"})
        bad = pull(f"{col} = 'zzzznope' (expect 0)", {"limit": 100, col: "zzzznope",
                                                     used_field: f"{START} 00:00:00",
                                                     used_field + "_end": f"{END} 23:59:59"})
        state = "HONORED" if (bad is not None and not bad and ok) else "NOT honored"
        print(f"   -> {col} filter: {state}")

    print(f"\n{'=' * 74}\nPaste this back and we'll decide whether to move dispo reporting here.\n")


if __name__ == "__main__":
    main()
