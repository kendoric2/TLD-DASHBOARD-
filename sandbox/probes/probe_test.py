"""
Test ONE column on ONE endpoint — set the values below, run, see what comes back.

    python3 sandbox/probes/probe_test.py

Everything you set is placed into the JSON body sent to the endpoint, and the
script prints that exact JSON so you can see precisely what went out.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import json
import _probe_lib as p                       # shared helpers (request + readable output)

config = p.config                            # credentials + the egress_get() request function
config.require_creds()                       # stop early with a clear message if .env isn't filled

# ======================= CHANGE THESE, THEN RUN =======================
ENDPOINT = "leads"          # <- endpoint name: leads, policies, vendorperformance, report_cpa_agent, ...
COLUMN   = "lead_id"        # <- the exact column you want to test
ROWS     = 5                # <- how many rows to pull back (keep this small)

START    = ""               # <- optional start date "YYYY-MM-DD"  (leave "" for NO date filter)
END      = ""               # <- optional end date   "YYYY-MM-DD"  (both must be set to filter)

MASK_SENSITIVE = True       # <- True hides ssn/dob/card/etc.;  set False to see the raw value
# ======================================================================

# substrings that get hidden when MASK_SENSITIVE is True
MASK = ("ssn", "dob", "cc_number", "cc_cvv", "bank_account", "bank_routing",
        "passport", "drivers_license", "medicare_claim", "medicaid_password", "personal_")

# --- build the JSON body that gets sent to the endpoint ---
body = {"columns": [COLUMN], "limit": ROWS}              # always ask for just this column + a few rows
if START and END:                                        # only add dates if BOTH are filled in
    body["start_date"] = f"{START} 00:00:00"             # start of day  (TLD wants 'YYYY-MM-DD HH:MM:SS')
    body["end_date"]   = f"{END} 23:59:59"               # end of day

p.hr(f"/api/egress/{ENDPOINT}   column: {COLUMN}")       # header
print("JSON body sent:")
print("  " + json.dumps(body))                           # <- shows you the exact payload that went out

cols = p.cols_of(ENDPOINT)                               # the endpoint's published column list
print("\nin column list?  " + ("yes" if COLUMN in cols   # tells you if the column name is recognized
      else "no (could still work if it's a computed/aggregate column)"))

# --- send the request ---
try:
    resp = config.egress_get(ENDPOINT, body, timeout=60)  # GET /api/egress/<ENDPOINT> with the JSON body
except Exception as ex:
    print(f"\nrequest FAILED: {type(ex).__name__}: {str(ex)[:100]}")
    raise SystemExit

rows, _ = p.as_rows(resp)                                # normalize the response to a list of rows
sensitive = MASK_SENSITIVE and any(m in COLUMN.lower() for m in MASK)   # should we hide this column's value?
values = [r.get(COLUMN) for r in rows]                   # pull this column out of each row
nonnull = [v for v in values if v not in p.EMPTY]        # which ones actually had a value

print(f"rows returned:   {len(rows)}")
if nonnull:
    print(f"\n*** DATA CAME BACK ***  ({len(nonnull)} of {len(rows)} rows had a value)")
    for v in values:                                     # print each row's value (or a redaction note)
        print("    ", "(value present — redacted)" if (sensitive and v not in p.EMPTY) else p.fmt(v))
else:
    print("\n*** NOTHING CAME BACK ***  (empty in these rows, or not valid for this endpoint)")
