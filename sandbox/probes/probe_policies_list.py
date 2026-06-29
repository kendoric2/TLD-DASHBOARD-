"""
List today's policies exactly as the dashboard counts them (read-only), so we can find
the one extra vs the CRM.

Pulls the same policies query the dashboard uses (canonical date filter), dedupes by the
canonical key (policy_id -> lead_id), then prints:
  - raw row count vs deduped count (proves whether dupes exist)
  - a breakdown by status (an outlier status is usually the culprit)
  - every counted policy with its status / agent / carrier / date_sold

Compare the list to your CRM's "policies sold today" and tell me what's different about
the extra one (most likely its status) — then I add that filter.

    python3 sandbox/probes/probe_policies_list.py
"""
import os
import sys
import datetime
from collections import Counter, defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import config
import tldcrm_client as t
import _probe_lib as p

config.require_creds()

# ===================== CHANGE THESE, THEN RUN =====================
START = datetime.date.today().isoformat()   # defaults to today; set "YYYY-MM-DD" to look back
END   = datetime.date.today().isoformat()
# ==================================================================

s0, e1 = f"{START} 00:00:00", f"{END} 23:59:59"
COLS = ["policy_id", "lead_id", "date_sold", "status", "agent_name", "carrier_name", "product"]
body = {"columns": COLS, "limit": 50000,
        "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1}

rows, _ = p.as_rows(config.egress_get("policies", body, timeout=90))

# dedupe exactly like the dashboard
seen, deduped = set(), []
for r in rows:
    k = t._dedupe_key(r) if isinstance(r, dict) else None
    if k and k not in seen:
        seen.add(k)
        deduped.append(r)

p.hr(f"Policies counted   {START} -> {END}")
print(f"raw rows: {len(rows)}    deduped (= dashboard count): {len(deduped)}")

print("\nby status:")
for status, n in Counter(str(r.get('status')) for r in deduped).most_common():
    print(f"   {str(status):20} {n}")

print("\nby carrier:")
for car, n in Counter(str(r.get('carrier_name')) for r in deduped).most_common():
    print(f"   {str(car):20} {n}")

# leads with more than one policy today — the CRM may count these as a single sale
by_lead = defaultdict(list)
for r in deduped:
    lid = r.get("lead_id")
    if lid not in (None, "", "0", 0):
        by_lead[str(lid)].append(str(r.get("policy_id")))
multi = {lid: pids for lid, pids in by_lead.items() if len(pids) > 1}
print(f"\nleads with >1 policy today: {len(multi)}")
for lid, pids in multi.items():
    print(f"   lead {lid} -> policies {pids}")

print(f"\n{'policy_id':12}{'lead_id':12}{'date_sold':21}{'status':10}{'agent':20}{'carrier':14}")
print("-" * 95)
for r in sorted(deduped, key=lambda r: str(r.get('date_sold'))):
    print(f"{str(r.get('policy_id')):12}{str(r.get('lead_id')):12}{str(r.get('date_sold')):21}"
          f"{str(r.get('status'))[:9]:10}{str(r.get('agent_name'))[:19]:20}{str(r.get('carrier_name'))[:13]:14}")

print("\n- If a lead shows >1 policy, that's likely the CRM's '1 sale' vs our '2 policies'.")
print("- Else tell me the policy_id your CRM doesn't count and I'll pull its full record.")
