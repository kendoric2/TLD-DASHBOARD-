"""
Filtered lookup — pull rows from an endpoint, filtered by field(s) + a date range.
Example built in: leads for one agent within a date range.

    python3 sandbox/probes/probe_query.py

Whatever you set goes into the JSON body sent to the endpoint; the script prints
that exact JSON, then shows the matching rows as a table.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import json
import _probe_lib as p

config = p.config
config.require_creds()

# ========================= CHANGE THESE, THEN RUN =========================
ENDPOINT = "leads"                         # <- endpoint to query

FILTERS  = {"agent_id": 44878}             # <- who/what to filter by (field: value).
                                           #    agent (closer) by id:   {"agent_id": 44878}
                                           #    agent by name:          {"agent_name": "Willis, Jarvis"}
                                           #    enroller (fronter):     {"fronter_id": 40067}
                                           #    a vendor:               {"vendor_id": 14646}
                                           #    add more keys to AND them: {"agent_id": 44878, "billable": 1}

COLUMNS  = ["lead_id", "date_created", "status_name", "vendor_id",   # <- columns to show back
            "cost", "billable", "agent_name", "fronter_name"]

DATE_FIELD = "date_created"                # <- which date column the range filters on
                                           #    leads -> date_created (or date_assigned);  policies -> date_sold
START    = "2026-06-25"                    # <- start date "YYYY-MM-DD"   (set both "" for no date filter)
END      = "2026-06-25"                    # <- end date   "YYYY-MM-DD"

ROWS     = 25                              # <- max rows to return
MASK_SENSITIVE = True                      # <- True hides ssn/dob/card/etc.; False shows raw
# ==========================================================================

MASK = ("ssn", "dob", "cc_number", "cc_cvv", "bank_account", "bank_routing",
        "passport", "drivers_license", "medicare_claim", "medicaid_password", "personal_")

# --- build the JSON body ---
body = dict(FILTERS)                       # start with the filters (agent, vendor, etc.)
body["columns"] = COLUMNS                  # which fields to return
body["limit"] = ROWS                       # cap the rows
if START and END:                          # add the date range only if both are set
    body[DATE_FIELD] = f"{START} 00:00:00"            # range start (TLD wants 'YYYY-MM-DD HH:MM:SS')
    body[DATE_FIELD + "_end"] = f"{END} 23:59:59"     # range end

p.hr(f"/api/egress/{ENDPOINT}  (filtered)")
print("JSON body sent:")
print("  " + json.dumps(body))

# --- send it ---
try:
    resp = config.egress_get(ENDPOINT, body, timeout=60)
except Exception as ex:
    print(f"\nrequest FAILED: {type(ex).__name__}: {str(ex)[:100]}")
    raise SystemExit

rows, _ = p.as_rows(resp)
print(f"\nrows returned: {len(rows)}\n")


def cell(col, v):
    if v in p.EMPTY:
        return ""
    if MASK_SENSITIVE and any(m in col.lower() for m in MASK):
        return "***"
    return str(v)[:28]


if rows:                                   # print as an aligned table: header + one line per row
    width = {c: max(len(c), *(len(cell(c, r.get(c))) for r in rows)) for c in COLUMNS}
    print("  ".join(c.ljust(width[c]) for c in COLUMNS))
    print("  ".join("-" * width[c] for c in COLUMNS))
    for r in rows:
        print("  ".join(cell(c, r.get(c)).ljust(width[c]) for c in COLUMNS))
else:
    print("(no rows matched — check the filter values, date range, or column names)")
