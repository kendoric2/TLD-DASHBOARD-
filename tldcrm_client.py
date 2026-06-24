"""
TLDCRM read-only API client (the "egress" layer).

PULL ONLY: we only ever issue GET requests against /api/egress/* endpoints.
Nothing is ever written back to the CRM/dialer.

Request payloads are defined in egress_payloads.json so the query shapes live
in one place. IMPORTANT: TLD requires date-bounded egress to use a
start_date + end_date range (YYYY-MM-DD) in the payload — not relative labels.
This client computes that range from the selected period and fills the
{{start_date}} / {{end_date}} placeholders.

Auth: the API ID and Key are sent as request headers. Confirm the header
names and any column names against your instance on first live connection
(e.g. GET /api/egress/policies/docs/columns).
"""

import os
import json
import copy
import datetime
import requests

# --- Auth header names (verify on first live connection) -------------------
API_ID_HEADER = "tld-api-id"
API_KEY_HEADER = "tld-api-key"

# --- Load the egress payload templates -------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "egress_payloads.json"), "r", encoding="utf-8") as _f:
    _DOC = json.load(_f)
PAYLOADS = _DOC["queries"]


def date_range_for(range_key):
    """Return (start_date, end_date) as 'YYYY-MM-DD' strings for a UI range key.

    TLD egress is date-bounded with a start_date + end_date range, so every
    relative period the UI offers is resolved to concrete dates here.
    """
    today = datetime.date.today()
    if range_key == "today":
        start = end = today
    elif range_key == "this_week":
        start = today - datetime.timedelta(days=today.weekday())   # Monday
        end = today
    elif range_key == "last_month":
        first_this = today.replace(day=1)
        end = first_this - datetime.timedelta(days=1)              # last day prev month
        start = end.replace(day=1)
    elif range_key == "this_quarter":
        q_start_month = 3 * ((today.month - 1) // 3) + 1
        start = today.replace(month=q_start_month, day=1)
        end = today
    else:  # this_month (default)
        start = today.replace(day=1)
        end = today
    return start.isoformat(), end.isoformat()


class TLDCRMClient:
    def __init__(self, base_url, api_id, api_key, timeout=20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            API_ID_HEADER: str(api_id),
            API_KEY_HEADER: str(api_key),
            "Accept": "application/json",
        })

    # -- payload + request --------------------------------------------------
    def _params(self, query_name, start=None, end=None):
        """Build the request params from the JSON template, filling the
        start_date / end_date range placeholders."""
        cfg = PAYLOADS[query_name]
        payload = copy.deepcopy(cfg["payload"])
        out = {}
        for key, val in payload.items():
            if val == "{{start_date}}":
                val = start
            elif val == "{{end_date}}":
                val = end
            if isinstance(val, bool):          # TLD expects lowercase true/false
                val = "true" if val else "false"
            out[key] = val
        return cfg["endpoint"], out

    def run(self, query_name, start=None, end=None):
        endpoint, params = self._params(query_name, start, end)
        url = f"{self.base_url}/api/egress/{endpoint.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return self._rows(resp.json())

    @staticmethod
    def _rows(payload):
        """TLD egress responses vary; normalize to a list of dict rows."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("results", "data", "rows", "response"):
                val = payload.get(key)
                if isinstance(val, list):
                    return val
            return [payload]   # single aggregate row
        return []

    # -- metric helpers (all read-only) -------------------------------------
    def _grouped(self, query_name, start, end):
        cfg = PAYLOADS[query_name]
        label_field = cfg.get("label_field", "label")
        out = []
        for row in self.run(query_name, start, end):
            label = row.get(label_field)
            if label:
                out.append({"label": label,
                            "count": _num(row.get("tql_cnt_policy_id"))})
        return out

    def agent_performance(self, start, end):
        sold = self.run("agent_policies", start, end)

        calls = {}
        try:
            for row in self.run("agent_calls", start, end):
                name = row.get("agent") or row.get("user")
                if name:
                    calls[name] = row
        except Exception:
            pass  # call stats optional; policies still render

        agents = []
        for row in sold:
            name = row.get("agent") or "—"
            policies = _num(row.get("tql_cnt_policy_id"))
            leads = _num(row.get("tql_cnu_lead_id"))
            conv = round(policies / leads * 100, 1) if leads else 0.0
            c = calls.get(name, {})
            agents.append({
                "name": name,
                "calls": _num(c.get("calls")) or None,
                "talk_time": c.get("talk_time"),
                "policies": policies,
                "conversion": conv,
            })
        return agents

    # -- assemble the full dashboard ----------------------------------------
    def build_dashboard(self, range_key, range_label):
        start, end = date_range_for(range_key)

        policies = _first_num(self.run("policies_count", start, end))
        leads = _first_num(self.run("billable_leads_count", start, end))
        conv = round(policies / leads * 100, 1) if leads else 0.0

        return {
            "demo": False,
            "range_label": range_label,
            "date_range": {"start": start, "end": end},
            "kpis": {
                "policies_sold": policies,
                "billable_leads": leads,
                "conversion_rate": conv,
                "avg_gtl_premium": _first_num(self.run("avg_gtl_premium", start, end)),
            },
            "by_carrier": self._grouped("policies_by_carrier", start, end),
            "by_plan": self._grouped("policies_by_plan", start, end),
            "recent_sales": self.run("recent_sales"),
            "agents": self.agent_performance(start, end),
        }


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return int(f) if f.is_integer() else f


def _first_num(rows):
    if not rows:
        return 0
    row = rows[0]
    if isinstance(row, dict):
        for v in row.values():
            n = _num(v)
            if n:
                return n
        return 0
    return _num(row)
