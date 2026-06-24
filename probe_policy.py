"""
Probe a single TLDCRM policy and print EVERY available column (read-only).

Usage (on a machine that can reach your TLD instance, e.g. your Mac):
    cd ~/Documents/TLDDASHBOARD
    python3 probe_policy.py 17779643      # or omit the id to use the default

Shows all columns, including empty ones. It requests the full joined column
set via the schema's related tables (leads, products, carriers, plans, users,
vendors). Read-only: only a GET.

Sensitive PCI/PHI (card/bank numbers, CVV, SSN, DOB, Medicare/Medicaid IDs,
passwords) are masked. The full (masked) output is also written to
policy_<id>.txt so you can scroll it / share it easily.
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()
base = os.getenv("TLD_BASE_URL", "").strip().rstrip("/")
hid = os.getenv("TLD_API_ID", "").strip()
key = os.getenv("TLD_API_KEY", "").strip()
if not (base and hid and key):
    sys.exit("Fill TLD_BASE_URL / TLD_API_ID / TLD_API_KEY in .env first.")

policy_id = sys.argv[1] if len(sys.argv) > 1 else "17779643"

# Related tables to join so every available column is returned.
# (Sent as repeated import= params; if your instance wants a comma list
#  instead, set IMPORTS = "leads,products,carriers,plans,users,vendors".)
IMPORTS = ["leads", "products", "carriers", "policy_carriers",
           "product_carriers", "plans", "policy_fields", "users", "vendors"]

url = base + "/api/egress/policies"
params = {"policy_id": policy_id, "limit": 1, "import": IMPORTS}
print("GET", url, "(policy_id=%s)" % policy_id)
r = requests.get(
    url,
    headers={"tld-api-id": hid, "tld-api-key": key, "Accept": "application/json"},
    params=params,
    timeout=60,
)
print("HTTP", r.status_code)
data = r.json()


def extract_rows(d):
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        if isinstance(d.get("response"), dict):
            d = d["response"]
        for k in ("results", "data", "rows"):
            if isinstance(d.get(k), list):
                return d[k]
        return [d]
    return []


rows = extract_rows(data)
if not rows or not isinstance(rows[0], dict):
    print("No usable record returned. Raw response:")
    print(json.dumps(data, indent=2)[:1800])
    sys.exit()

row = rows[0]

# --- mask genuinely sensitive PCI / PHI ---
MASK_SUBSTR = ("ssn", "cc_number", "cc_cvv", "bank_account_number",
               "bank_routing_number", "mothers_maiden", "drivers_license",
               "passport_number", "medicare_claim_number", "medicaid_password",
               "medicaid_username")
MASK_DOB = {"lead_dob", "lead_dob_full", "beneficiary_dob", "contingent_dob"}


def show(k, v):
    kl = k.lower()
    if any(s in kl for s in MASK_SUBSTR):
        return "*** redacted ***"
    if kl in MASK_DOB:
        return "*** redacted (DOB) ***"
    return "" if v is None else v


lines = [f"{k} = {show(k, v)}" for k, v in row.items()]
filled = sum(1 for k, v in row.items() if v not in (None, "", "0", "0000-00-00", "0000-00-00 00:00:00"))
header = f"Policy {policy_id}: {len(row)} columns total, {filled} populated\n"
out = header + "\n" + "\n".join(lines)

print("\n" + out)

fname = f"policy_{policy_id}.txt"
with open(fname, "w") as f:
    f.write(out + "\n")
print(f"\nSaved full output to {fname}")
