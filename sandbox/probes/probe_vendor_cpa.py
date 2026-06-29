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
    print("\n=== FALCON (14646) — full row ===")
    for k, v in fal[0].items():
        print(f"   {strip(k):32} = {strip(v)}")

print("\nTell me which fields are All Calls, Sales, and Sales/All Calls % (or I'll just")
print("compute Sales / All Calls from those two). Then I wire Conversion to it.")
