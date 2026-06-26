"""
Migration check (read-only): for each date-bounded query, compares the LEGACY date
form (per-endpoint date_field + M/D/YYYY) against what the client ACTUALLY sends now
(tldcrm_client._payload — canonical date/date_sold for policies + CPA, date_created
for the leads endpoint). Prints them side by side.

If every row says OK, the shipped date logic matches the known-good legacy numbers.

TIP: use a PAST day (not today) so live updates between the two calls don't cause
spurious diffs.

    python3 sandbox/probes/probe_migrate_check.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t
import _probe_lib as p

config.require_creds()

# ===================== CHANGE THESE, THEN RUN =====================
START = "2026-06-25"        # a past day = stable comparison
END   = "2026-06-25"
# ==================================================================

su, eu = t._us(START), t._us(END)
c = t.TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)

# named query, legacy date_field, mode ("count" reads first number, "rows" counts rows)
CHECKS = [
    ("policies_count",       "date_sold",    "count"),
    ("billable_leads_count", "date_created", "count"),
    ("avg_gtl_premium",      "date_sold",    "count"),
    ("agent_policies",       "date_sold",    "rows"),
]


def legacy_payload(qname, df):
    """Reconstruct the pre-migration body for this query."""
    cfg = t.PAYLOADS[qname]
    body = dict(cfg["payload"])
    body[df] = su
    body[df + "_end"] = eu
    if df == "date_sold":                       # legacy added start_date/end_date for sold dates
        body["start_date"] = su
        body["end_date"] = eu
    if cfg.get("falcon_vendor"):
        body["vendor_id"] = config.FALCON_VENDOR_ID
    return cfg["endpoint"], body


def value(ep, body, mode):
    rows, _ = p.as_rows(config.egress_get(ep, body, timeout=60))
    return len(rows) if mode == "rows" else t._first_num(rows)


p.hr(f"Migration check   {START} -> {END}")
print(f"{'query':24}{'LEGACY':>14}{'SHIPPED NOW':>14}   match?")
print("-" * 66)
all_ok = True
for qname, df, mode in CHECKS:
    ep_l, body_l = legacy_payload(qname, df)
    ep_s, body_s = c._payload(qname, START, END)        # exactly what the dashboard sends now
    L = value(ep_l, body_l, mode)
    S = value(ep_s, body_s, mode)
    ok = (L == S)
    all_ok = all_ok and ok
    print(f"{qname:24}{str(L):>14}{str(S):>14}   {'OK' if ok else '*** DIFF ***'}")
print("-" * 66)
print("ALL MATCH — shipped date logic is correct." if all_ok else
      "Some values still differ — paste this output back.")
