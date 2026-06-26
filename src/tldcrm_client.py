"""
TLDCRM read-only API client (the "egress" layer).

PULL ONLY: queries are sent as GET requests with a JSON body to
/api/egress/* endpoints to READ data. Nothing is ever written back.

Query shapes live in egress_payloads.json. Date filtering uses TLD's explicit
range form in the JSON body: start_date + end_date, and (for date_sold) also
date_sold + date_sold_end — sending both is what makes wide date ranges
reliable (per TLD's own request conventions). Dates are M/D/YYYY.

Auth: API ID and Key are sent as request headers.
"""

import os
import sys
import json
import time
import datetime
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "egress_payloads.json"), "r", encoding="utf-8") as _f:
    PAYLOADS = json.load(_f)["queries"]

# --- CPA cache ---------------------------------------------------------------
# report_cpa_agent is a heavy precomputed report and the slowest call in the
# dashboard. CPA barely moves minute-to-minute, so we cache the result per
# date-range for a few minutes. The 30s auto-refresh then reuses the cached map
# (KPIs stay live) instead of re-running the heavy report on every tick.
_CPA_CACHE = {}                 # {(start, end): (fetched_at_epoch, {name_key: cpa})}
_CPA_CACHE_TTL = 300            # seconds — 5 minutes
_CPA_LOCK = threading.Lock()    # guards _CPA_CACHE across the dashboard's worker threads


def date_range_for(range_key):
    """Return (start, end) as ISO dates (YYYY-MM-DD) for the selected period."""
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


def _us(iso_date):
    """ISO date (YYYY-MM-DD) -> TLD's M/D/YYYY format."""
    d = datetime.date.fromisoformat(iso_date)
    return f"{d.month}/{d.day}/{d.year}"


class TLDCRMClient:
    def __init__(self, base_url, api_id, api_key, timeout=config.TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            config.API_ID_HEADER: str(api_id),
            config.API_KEY_HEADER: str(api_key),
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _payload(self, query_name, start=None, end=None):
        """Return (endpoint, json_body). For date-bounded queries add the TLD
        date range (M/D/YYYY): start_date + end_date always, plus
        date_sold + date_sold_end when the field is date_sold (the reliable dual)."""
        cfg = PAYLOADS[query_name]
        body = dict(cfg["payload"])
        if cfg.get("date_bounded") and start and end:
            su, eu = _us(start), _us(end)
            df = cfg.get("date_field", "date_sold")
            body[df] = su              # range start on this endpoint's date (date_sold / date_created)
            body[df + "_end"] = eu     # range end
            if df == "date_sold":      # start_date/end_date also filter date_sold (the reliable dual)
                body["start_date"] = su
                body["end_date"] = eu
        if cfg.get("falcon_vendor"):   # inject the Falcon vendor id from config (single source of truth)
            body["vendor_id"] = config.FALCON_VENDOR_ID
        return cfg["endpoint"], body

    def run(self, query_name, start=None, end=None):
        endpoint, body = self._payload(query_name, start, end)
        url = f"{self.base_url}/api/egress/{endpoint.lstrip('/')}"
        # GET with a JSON body — egress is read-only and the API key allows GET.
        resp = self.session.request("GET", url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        return self._rows(resp.json())

    @staticmethod
    def _rows(payload):
        """TLD wraps data as {"response": {"results": [...]}}. Unwrap to a list of rows."""
        if isinstance(payload, dict) and isinstance(payload.get("response"), dict):
            payload = payload["response"]
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("results", "data", "rows"):
                val = payload.get(key)
                if isinstance(val, list):
                    return val
            return [payload]
        return []

    def _grouped(self, query_name, start, end):
        cfg = PAYLOADS[query_name]
        label_field = cfg.get("label_field", "label")
        out = []
        for row in self.run(query_name, start, end):
            label = row.get(label_field)
            if label:
                out.append({"label": label, "count": _num(row.get("tql_cnt_policy_id"))})
        return out

    def agent_performance(self, start, end):
        agents = []
        for row in self.run("agent_policies", start, end):
            name = row.get("agent_name")
            if not name:                 # skip the unassigned / null-agent bucket
                continue
            agents.append({
                "name": name,
                "policies": _num(row.get("tql_cnt_policy_id")),
                "leads": _num(row.get("tql_cnu_lead_id")),
            })
        return agents

    def agent_cpa(self, start, end):
        """Per-agent CPA (cpa_cost_calls_all_by_sales) from report_cpa_agent for the
        date range, returned as {name_key: cpa}. This report honors
        date/date_end + date_sold/date_sold_end (NOT start_date/end_date).

        Cached per (start, end) for _CPA_CACHE_TTL seconds so the 30s auto-refresh
        reuses the result instead of re-running this heavy report on every tick."""
        cache_key = (start, end)
        now = time.time()
        with _CPA_LOCK:                                  # serve a fresh cached copy if we have one
            hit = _CPA_CACHE.get(cache_key)
            if hit and now - hit[0] < _CPA_CACHE_TTL:
                return hit[1]

        s0, e1 = f"{start} 00:00:00", f"{end} 23:59:59"
        body = {
            "columns": ["agent", "agent_id", "sales", "cpa_cost_calls_all_by_sales"],
            "limit": 1000,                           # cover the full roster (matches agent_policies)
            "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1,
        }
        # Use the same proven request+unwrap path the working probe uses.
        resp = config.egress_get("report_cpa_agent", body, timeout=max(self.timeout, 90))

        # report_cpa_agent returns {data|results|rows: [...], totals: {...}} (sometimes
        # wrapped in "response", which egress_get already peels). Pull out the row list.
        rows = resp if isinstance(resp, list) else []
        if isinstance(resp, dict):
            for k in ("results", "data", "rows", "report", "records", "agents"):
                if isinstance(resp.get(k), list):
                    rows = resp[k]
                    break

        out = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            full, loose = _name_keys(r.get("agent"))
            if not full:
                continue
            cpa = _num(r.get("cpa_cost_calls_all_by_sales"))
            out[full] = cpa
            out.setdefault(loose, cpa)               # loose alias (drops middle name) as a fallback match

        # One-line diagnostic to the terminal (stderr) — does NOT touch the JSON the
        # browser sees. Lets us confirm row count + the exact name format the report returns.
        print(f"[agent_cpa] {start}->{end}: {len(rows)} report rows; "
              f"sample agents={[r.get('agent') for r in rows[:5] if isinstance(r, dict)]}",
              file=sys.stderr)

        with _CPA_LOCK:
            _CPA_CACHE[cache_key] = (now, out)
        return out

    def build_dashboard(self, range_key, range_label):
        start, end = date_range_for(range_key)

        # All queries are independent and filtered server-side, so run them
        # concurrently — the dashboard loads in ~one round-trip instead of seven.
        jobs = {
            "policies":   lambda: _first_num(self.run("policies_count", start, end)),
            "falcon":     lambda: self.run("falcon_billable_status", start, end),
            "avg_gtl":    lambda: _first_num(self.run("avg_gtl_premium", start, end)),
            "by_carrier": lambda: self._grouped("policies_by_carrier", start, end),
            "by_plan":    lambda: self._grouped("policies_by_plan", start, end),
            "recent":     lambda: self.run("recent_sales"),
            "agents":     lambda: self.agent_performance(start, end),
            "agent_cpa":  lambda: self.agent_cpa(start, end),
        }
        results, errors = {}, []

        def _run(key, fn):
            try:
                return key, fn()
            except Exception as e:
                errors.append(f"{key}: {e}")
                return key, None

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            for fut in as_completed([pool.submit(_run, k, fn) for k, fn in jobs.items()]):
                k, v = fut.result()
                results[k] = v

        policies = results.get("policies") or 0

        # Falcon billable leads + conversion: a billable Falcon lead is
        # "converted" if its status ended in Active or Sale.
        falcon_rows = results.get("falcon") or []
        billable = sum(_num(r.get("tql_cnt_lead_id")) for r in falcon_rows)
        converted = sum(_num(r.get("tql_cnt_lead_id")) for r in falcon_rows
                        if str(r.get("status_name") or "").strip().lower() in config.CONVERTED_STATUSES)
        conv = round(converted / billable * 100, 1) if billable else 0.0

        recent = [{
            "date_sold": r.get("date_sold"),
            "agent": r.get("agent_name") or r.get("agent"),
            "product": r.get("product_name") or r.get("product"),
            "carrier": r.get("carrier_name") or r.get("carrier"),
            "premium": r.get("premium"),
            "status": r.get("status"),
        } for r in (results.get("recent") or [])]

        # Merge per-agent CPA (from report_cpa_agent) into the agent rows, matched by
        # name. Try the full normalized name first, then the loose (first+last) key so
        # a middle name on either side doesn't break the match.
        agents = results.get("agents") or []
        cpa_map = results.get("agent_cpa") or {}
        matched = 0
        for a in agents:
            full, loose = _name_keys(a.get("name"))
            cpa = cpa_map.get(full)
            if cpa is None:
                cpa = cpa_map.get(loose)
            a["cpa"] = cpa
            if cpa is not None:
                matched += 1
        print(f"[cpa merge] matched {matched}/{len(agents)} agents; "
              f"dashboard sample={[a.get('name') for a in agents[:5]]}", file=sys.stderr)

        data = {
            "demo": False,
            "range_label": range_label,
            "date_range": {"start": start, "end": end},
            "kpis": {
                "policies_sold": policies,
                "billable_leads": billable,
                "conversion_rate": conv,
                "avg_gtl_premium": results.get("avg_gtl") or 0,
            },
            "by_carrier": results.get("by_carrier") or [],
            "by_plan": results.get("by_plan") or [],
            "recent_sales": recent,
            "agents": agents,
        }
        if errors:
            data["error"] = "Some metrics didn't load: " + "; ".join(errors)
        return data


def _name_keys(s):
    """Return (full, loose) match keys for an agent name so the two reports line up.

    full  = fully normalized 'first ... last'  ('Willis, Jarvis' -> 'jarvis willis')
    loose = 'first last' only, dropping any middle name/initial, so
            'Andrew M Giesse' still matches 'Andrew Giesse'."""
    s = (s or "").strip().lower()
    if "," in s:                                  # 'Last, First' -> 'First Last'
        last, first = s.split(",", 1)
        s = f"{first.strip()} {last.strip()}"
    toks = s.split()
    full = " ".join(toks)
    loose = f"{toks[0]} {toks[-1]}" if len(toks) >= 2 else full
    return full, loose


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
