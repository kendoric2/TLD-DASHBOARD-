"""
Check that Transfer Check reads both DialedIN export formats correctly (offline, fake data).

Run from the project root:
    python3 tests/verify_transfer_parse.py

Prints OK for each case, or stops at the first one that fails.
"""

# --- make src/ importable no matter where this script is run from ---
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import transfer_check as tc


def csv_bytes(lines):
    return ("\n".join(lines) + "\n").encode("utf-8")


# CallDetails export: every transfer twice — the line's "Blind Transfer" leg (Rep is a
# phone number) and the fronter's "Transferred Call" leg. Lead ID is DialedIN's own id.
call_details = csv_bytes([
    "Date,Rep,Campaign,Phone,Lead ID,Details",
    "10/09/2026 5:00:24 PM,5613630948,Manhattan Life,(555) 010-0001,123456789,Blind Transfer",
    "10/09/2026 5:00:24 PM,jeanr@ihp,Manhattan Life,(555) 010-0001,123456789,Transferred Call",
    "10/08/2026 9:15:00 AM,5613630948,MAPD,555-010-0002,987654321,Blind Transfer",
    "10/08/2026 9:15:00 AM,melf@ihp,MAPD,555-010-0002,987654321,Transferred Call",
])
rows = tc.parse_export(call_details, "CallDetails.csv")
assert len(rows) == 2, f"expected only the 2 fronter legs, got {len(rows)}"
assert [r["rep"] for r in rows] == ["jeanr@ihp", "melf@ihp"], rows
assert all(r["tld_id"] == "" for r in rows), "DialedIN's Lead ID must not be used as a TLD lead id"
assert rows[0]["phone"] == "5550100001" and rows[0]["when"].hour == 17, rows[0]
print("OK  CallDetails: fronter rows only, DialedIN Lead ID ignored")

# Original lead export: one row per transfer, TLD Lead ID is trusted.
lead_export = csv_bytes([
    "PrimaryPhone,CallDate,Rep,Campaign,TLD Lead ID",
    "5550100003,10/07/2026 11:00:00 AM,corap@ihp,Manhattan Life,111222333",
    "5550100004,10/07/2026 12:00:00 PM,dianet@ihp,MAPD,",
])
rows = tc.parse_export(lead_export, "leads.csv")
assert len(rows) == 2, rows
assert rows[0]["tld_id"] == "111222333" and rows[1]["tld_id"] == "", rows
print("OK  lead export: unchanged, TLD Lead ID still used")

# A "Details" column that isn't the CallDetails kind must not throw rows away.
other_details = csv_bytes([
    "PrimaryPhone,CallDate,Rep,Details",
    "5550100005,10/06/2026 10:00:00 AM,genec@ihp,Some note",
])
assert len(tc.parse_export(other_details, "x.csv")) == 1
print("OK  unrelated Details column: rows kept")

# BlindTransfer export: Phone is the transfer LINE (a few numbers), the customer is in
# Caller ID (with a leading 1), Details is blank — one row per transfer.
blind = ["Date,Rep,Campaign,Phone,Caller ID,Lead ID,Details"]
for n in range(25):
    line = "5613630948" if n % 5 else "5617851493"
    blind.append(f"10/16/2026 2:{n:02d}:00 PM,rep{n % 3}@ihp,_MANUAL_CALL_,{line},1555010{n:04d},12345{n:04d},")
rows = tc.parse_export(csv_bytes(blind), "BlindTransfer.csv")
assert len(rows) == 25, len(rows)
assert rows[0]["phone"] == "5550100000" and rows[7]["phone"] == "5550100007", rows[:2]
assert all(r["tld_id"] == "" for r in rows)
print("OK  BlindTransfer: customer read from Caller ID, not the transfer line")

# A Caller ID column next to a real customer Phone column must not take over.
many = ["Date,Rep,Phone,Caller ID"] + [f"10/16/2026 3:{n:02d}:00 PM,rep@ihp,555020{n:04d},5613630948" for n in range(25)]
rows = tc.parse_export(csv_bytes(many), "x.csv")
assert rows[3]["phone"] == "5550200003", rows[3]
print("OK  customer Phone column kept when it varies")

# Matching the TLD call: a late file time picks the call at/before it, not a closer callback.
import datetime as dt
t = {"when": dt.datetime(2026, 10, 16, 14, 30)}
calls = [{"call_date": "2026-10-16 14:00:05", "id": "transfer"},
         {"call_date": "2026-10-16 14:40:00", "id": "callback"}]
assert tc._match_call(t, calls)["id"] == "transfer"
t2 = {"when": dt.datetime(2026, 10, 16, 14, 0, 0)}
assert tc._match_call(t2, [{"call_date": "2026-10-16 14:00:02", "id": "x"}])["id"] == "x"
print("OK  TLD call match: late file time still finds the real transfer call")

print("\nAll Transfer Check parsing checks passed.")
