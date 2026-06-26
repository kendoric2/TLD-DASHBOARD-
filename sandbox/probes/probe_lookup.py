"""
Interactive column lookup — read-only.

Type a column name (or part of one); it tells you which endpoint(s) have it and
shows a few sample values. Nothing matched? Try another. It's the
"plug it in -> did something come back? -> no, try another -> yes, here's what" loop.

Run:  python3 sandbox/probes/probe_lookup.py

At the  column>  prompt:
  vendor_price                 -> which endpoints have it + sample values
  cost                         -> partial match: every *cost* column + where it lives
  vendorperformance: tql_sum_cost
                               -> test ONE column on ONE endpoint LIVE
                                  (catches computed/aggregate columns not in the docs list)
  (blank, or q)                -> quit
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import _probe_lib as p

config = p.config
config.require_creds()

# ============================ EDIT-ME SETTINGS ============================
ENDPOINTS = ["policies", "leads", "agentcpa", "vendors", "users",
             "vendorperformance", "report_cpa_agent", "tldialer/report_agentcpa"]
SAMPLE_ROWS = 3          # rows pulled to find a sample value
MAX_SHOWN = 25           # max matching columns shown per endpoint
# sensitive substrings -> show a placeholder instead of the real value
MASK = ("ssn", "cc_number", "cc_cvv", "bank_account", "bank_routing", "passport",
        "drivers_license", "medicare_claim", "medicaid_password", "dob", "personal_")
# =========================================================================


def value_of(col, rows):
    cl = col.lower()
    for r in rows:
        v = r.get(col)
        if v in p.EMPTY:
            continue
        if any(m in cl for m in MASK):
            return "*** redacted ***"
        return str(v)[:120]
    return "(empty in sample)"


def pull(ep, cols):
    try:
        rows, _ = p.as_rows(config.egress_get(ep, {"columns": cols, "limit": SAMPLE_ROWS}, timeout=60))
        return rows
    except Exception as ex:
        return f"ERR {type(ex).__name__}"


print("loading endpoint columns (one-time)...")
COLS = {}
for ep in ENDPOINTS:
    try:
        COLS[ep] = p.cols_of(ep)
    except Exception:
        COLS[ep] = []
    print(f"  {ep:28} {len(COLS[ep])} columns")


def lookup(term):
    # "endpoint: column" -> live single-column test (works for tql_* aggregates too)
    if ":" in term:
        ep, col = (x.strip() for x in term.split(":", 1))
        rows = pull(ep, [col])
        if isinstance(rows, str):
            print(f"  {ep}.{col} -> {rows}")
        elif rows:
            vals = [value_of(col, [r]) for r in rows]
            print(f"  {ep}.{col} -> came back: {vals}")
        else:
            print(f"  {ep}.{col} -> nothing came back (empty or invalid column)")
        return

    # plain term -> case-insensitive search across every endpoint's column list
    hits = {ep: [c for c in cols if term.lower() in c.lower()] for ep, cols in COLS.items()}
    hits = {ep: cs for ep, cs in hits.items() if cs}
    if not hits:
        print(f"  nothing matched '{term}'.  (if it's an aggregate like tql_sum_*, try  endpoint: {term})")
        return
    for ep, cs in hits.items():
        shown = cs[:MAX_SHOWN]
        rows = pull(ep, shown)
        extra = f"  (+{len(cs) - len(shown)} more)" if len(cs) > len(shown) else ""
        print(f"  {ep}  ({len(cs)} match{'es' if len(cs) != 1 else ''}){extra}")
        w = max((len(c) for c in shown), default=0)
        for c in shown:
            val = value_of(c, rows) if isinstance(rows, list) else rows
            print(f"      {c.ljust(w)}   {val}")


print("\nType a column name (blank or 'q' to quit).")
while True:
    try:
        term = input("\ncolumn> ").strip()
    except EOFError:
        break
    if term.lower() in ("", "q", "quit", "exit"):
        break
    lookup(term)
print("bye")
