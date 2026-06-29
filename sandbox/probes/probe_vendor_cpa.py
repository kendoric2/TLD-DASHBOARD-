"""
Read the Vendor CPA report (read-only).

vendorperformance returns {"vendor": [ {row}, ... ]} with values wrapped in HTML links
and UI-style column names. This unwraps it, strips the HTML, prints the exact column
names, and dumps every vendor (highlighting FALCON 14646) so we can see which fields
are All Calls / Sales / Sales-per-All-Calls %.

    python3 sandbox/probes/probe_vendor_cpa.py
"""
import os
import datetime
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config

config.require_creds()

EP = "vendorperformance"

# ===================== CHANGE THESE, THEN RUN =====================
START = datetime.date.today().isoformat()   # defaults to today; set "YYYY-MM-DD" to look back
END   = datetime.date.today().isoformat()
# ==================================================================

s0, e1 = f"{START} 00:00:00", f"{END} 23:59:59"


def strip(v):
    """Remove HTML tags and surrounding whitespace from a cell value."""
    return re.sub(r"<[^>]+>", "", str(v)).strip()


resp = config.egress_get(
    EP, {"date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1, "limit": 200}, timeout=90)
vendors = resp.get("vendor") if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])

print(f"vendors returned: {len(vendors)}   ({START}..{END})\n")
if not vendors:
    print("raw:", repr(resp)[:300])
    raise SystemExit

print("column names (exact):")
for k in vendors[0].keys():
    print(f"   {k!r}")

print("\n--- every vendor (HTML stripped) ---")
for r in vendors:
    print("  " + " | ".join(f"{strip(k)}={strip(v)}" for k, v in r.items()))

fal = [r for r in vendors
       if "14646" in strip(r.get("ID", "")) or "FALCON" in strip(r.get("Vendor", "")).upper()]
if fal:
    f = fal[0]
    print("\n=== FALCON (14646) — full row ===")
    for k, v in f.items():
        print(f"   {strip(k):32} = {strip(v)}")

    def num(v):
        d = re.sub(r"[^0-9.]", "", strip(v))
        return float(d) if d else 0.0
    s, b, l = num(f.get("Sales")), num(f.get("Billable")), num(f.get("Leads"))
    print("\n--- conversion candidates for FALCON ---")
    print(f"   Sales={s:.0f}   Billable={b:.0f}   Leads={l:.0f}")
    if b:
        print(f"   Sales / Billable = {s/b*100:.1f}%   <- what the dashboard shows now")
    if l:
        print(f"   Sales / Leads    = {s/l*100:.1f}%")

print("\nNow tell me what your CRM's Vendor CPA shows for FALCON RIGHT NOW:")
print("   Sales, All Calls, Billable Calls, and the Sales / All Calls %.")
print("With both sides side by side I can match the exact numerator/denominator.")
