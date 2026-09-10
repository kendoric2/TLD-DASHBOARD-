#!/usr/bin/env python3
"""
Live Agents filters — can we tell fronters from agents? (READ-ONLY)

Campaign names hint at it ("Fronters Mixed" vs "Mixed"), but that's a guess. The CRM's
"users" endpoint has a real role_names field (role classification role_names) already used
by tools/agents_by_group.py. This checks whether live dialer agents (by full name) can be
matched against that CRM roster to get a real role, and separately lists the distinct
campaigns currently in use (for the campaign filter, which needs no join at all).

Usage:
  python3 sandbox/probes/probe_live_role_join.py
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import config  # noqa: E402


def rows_of(resp):
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in ("results", "data", "rows", "records"):
            if isinstance(resp.get(k), list):
                return resp[k]
    return []


def main():
    if not config.have_creds():
        print("No credentials found. Run on the machine where .env is configured.")
        return

    print("=" * 78)
    print("1) Live agents right now — campaigns in use")
    print("=" * 78)
    live_resp = config.egress_get("tldialer/tldialer_live_agents", {
        "columns": ["user", "agent_full_name", "live_status", "campaign_id",
                   "campaign_campaign_name"], "limit": 1000}, timeout=60)
    live = [r for r in rows_of(live_resp) if isinstance(r, dict)]
    print(f"{len(live)} agents live right now")
    campaigns = Counter(str(r.get("campaign_campaign_name") or r.get("campaign_id") or "(none)") for r in live)
    print("distinct campaigns:", dict(campaigns))
    fronter_like = {c for c in campaigns if "fronter" in c.lower()}
    print(f"campaign names containing 'fronter': {fronter_like}")

    print("\n" + "=" * 78)
    print("2) CRM users roster — role_names values, and can we join by name?")
    print("=" * 78)
    crm_resp = config.egress_get("users", {
        "columns": ["name", "full_name", "role_names", "group_names", "status"],
        "limit": 5000}, timeout=60)
    crm = [r for r in rows_of(crm_resp) if isinstance(r, dict)]
    print(f"{len(crm)} CRM user rows")
    role_counts = Counter(str(r.get("role_names") or "(blank)") for r in crm)
    print("role_names values (top 20):", dict(role_counts.most_common(20)))

    # try matching live agents to CRM rows by full name (both raw and "First Last" swapped)
    def variants(name):
        name = str(name or "").strip()
        out = {name}
        if "," in name:
            last, first = name.split(",", 1)
            out.add(f"{first.strip()} {last.strip()}")
        else:
            parts = name.split()
            if len(parts) == 2:
                out.add(f"{parts[1]}, {parts[0]}")
        return out

    crm_by_name = {}
    for r in crm:
        for key in ("name", "full_name"):
            v = str(r.get(key) or "").strip()
            if v:
                crm_by_name[v.lower()] = r

    matched, unmatched = 0, []
    for r in live:
        live_name = r.get("agent_full_name")
        hit = None
        for v in variants(live_name):
            hit = crm_by_name.get(v.lower())
            if hit:
                break
        if hit:
            matched += 1
        else:
            unmatched.append(live_name)

    print(f"\nmatched {matched} / {len(live)} live agents to a CRM user row by name")
    print(f"unmatched examples: {unmatched[:10]}")

    print("\nfor matched agents, their role_names + which campaign they're live in:")
    shown = 0
    for r in live:
        live_name = r.get("agent_full_name")
        hit = None
        for v in variants(live_name):
            hit = crm_by_name.get(v.lower())
            if hit:
                break
        if hit and shown < 20:
            print(f"  {live_name:<26} role={hit.get('role_names')!r:<30} "
                  f"campaign={r.get('campaign_campaign_name')}")
            shown += 1


if __name__ == "__main__":
    main()
