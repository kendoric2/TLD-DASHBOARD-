"""
TLDCRM read-only API client (the "egress" layer).

PULL ONLY: queries are sent as GET requests with a JSON body to
/api/egress/* endpoints to READ data. Nothing is ever written back.

Query shapes live in egress_payloads.json. Date filtering follows TLD's canonical
rule: the JSON body carries BOTH date/date_end AND date_sold/date_sold_end,
full-day bounds, formatted 'YYYY-MM-DD HH:MM:SS'. That holds for the policies
endpoint and the CPA report. The raw leads endpoint is the exception — it ignores
date/date_sold and is filtered on date_created instead (see _payload's date_field
override).

Auth: API ID and Key are sent as request headers.
"""

import os
import re
import sys
import json
import time
import datetime
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import cache
import metrics

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "egress_payloads.json"), "r", encoding="utf-8") as _f:
    PAYLOADS = json.load(_f)["queries"]

# --- CPA cache ---------------------------------------------------------------
# report_cpa_agent is a heavy precomputed report and the slowest call in the
# dashboard. CPA barely moves minute-to-minute, so we cache the result per
# date-range for a few minutes. The 30s auto-refresh then reuses the cached map
# (KPIs stay live) instead of re-running the heavy report on every tick.
_CPA_CACHE = {}                 # {(start, end): (fetched_at_epoch, {"by_agent":..., "totals":...})}
_CPA_CACHE_TTL = 300            # seconds — 5 minutes
_CPA_LOCK = threading.Lock()    # guards _CPA_CACHE / _CPA_INFLIGHT across worker threads
_CPA_INFLIGHT = {}              # {(start, end): Event} — dedupes concurrent fetches of the same range


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
        """Return (endpoint, json_body). Date-bounded queries get TLD's canonical
        date filter — BOTH date/date_end AND date_sold/date_sold_end, full-day
        bounds, 'YYYY-MM-DD HH:MM:SS' — which the policies endpoint and the CPA
        report honor. The raw leads endpoint is the exception: it ignores
        date/date_sold and must be filtered on date_created, so such a query sets
        'date_field' to override with <field>/<field>_end. (Proven by
        probe_migrate_check.py: canonical on leads returned the whole unfiltered
        table; date_created returns the correct in-range count.)"""
        cfg = PAYLOADS[query_name]
        body = dict(cfg["payload"])
        if cfg.get("date_bounded") and start and end:
            s0, e1 = f"{start} 00:00:00", f"{end} 23:59:59"   # full-day bounds, YYYY-MM-DD HH:MM:SS
            df = cfg.get("date_field")
            if df:                         # endpoint-specific override (leads -> date_created)
                body[df] = s0
                body[df + "_end"] = e1
            else:                          # canonical default (policies endpoint, CPA report)
                body["date"] = s0
                body["date_end"] = e1
                body["date_sold"] = s0
                body["date_sold_end"] = e1
        if cfg.get("falcon_vendor"):       # inject the Falcon vendor id from config (single source of truth)
            body["vendor_id"] = config.FALCON_VENDOR_ID
        return cfg["endpoint"], body

    def run(self, query_name, start=None, end=None):
        endpoint, body = self._payload(query_name, start, end)
        url = f"{self.base_url}/api/egress/{endpoint.lstrip('/')}"
        # GET with a JSON body — egress is read-only and the API key allows GET.
        t0 = time.time()
        try:
            resp = self.session.request("GET", url, json=body, timeout=self.timeout)
        except Exception:
            metrics.log(endpoint, query=query_name, start=start, end=end,
                        source="live", status="ERR", ms=int((time.time() - t0) * 1000))
            raise
        metrics.log(endpoint, query=query_name, start=start, end=end,
                    source="live", status=resp.status_code, ms=int((time.time() - t0) * 1000))
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

    def policies_sold(self, start, end):
        """Count of policies sold — deduped (policy_id -> lead_id) with GTL excluded.
        See _kept_policies (shared basis with the enrollment tracker)."""
        return len(_kept_policies(self.run("policies_ids", start, end)))

    def agent_performance(self, start, end):
        agents = []
        for row in self.run("agent_policies", start, end):
            name = row.get("agent_name")
            if not name:                 # skip the unassigned / null-agent bucket
                continue
            agents.append({
                "name": name,
                "policies": _num(row.get("tql_cnt_policy_id")),
            })
        return agents

    def sales_board(self, start, end, carrier=None):
        """Combined leaderboard (agents + fronters) for a date range, optionally filtered to a
        single carrier. Returns {"board": [...], "carriers": [every carrier in the range]} so
        the header dropdown can offer the full list. Disk-cached per (range, carrier)."""
        ns = "sales_board" if not carrier else "sales_board__" + re.sub(r"[^A-Za-z0-9]+", "_", carrier)
        cached = cache.load(ns, start, end)
        if cached is not None:
            return cached
        rows = _dedupe_rows(self.run("policies_ids", start, end))
        carriers = sorted({(str(r.get("carrier_name") or "").strip() or "—") for r in rows})
        if carrier:
            rows = [r for r in rows if (str(r.get("carrier_name") or "").strip() or "—") == carrier]
        data = {"board": _sales_board(rows), "carriers": carriers}
        cache.save(ns, start, end, data)
        return data

    def vendor_performance(self, start, end):
        """Per-vendor numbers from the Vendor CPA report (vendorperformance) for the date
        range. Returns a list of {vendor_id, vendor, leads, billable, sales, policies,
        spend}. This is the CRM's UI report: rows arrive under a "vendor" key with values
        wrapped in HTML links, so we strip the tags to get raw numbers. Note: TLD computes
        this report on a delay, so it can trail the live CRM by a few minutes (the ratio
        Sales/Billable stays accurate as of its last refresh)."""
        s0, e1 = f"{start} 00:00:00", f"{end} 23:59:59"
        body = {"date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1, "limit": 200}
        resp = config.egress_get("vendorperformance", body, timeout=max(self.timeout, 60))
        rows = resp.get("vendor") if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            out.append({
                "vendor_id": _strip_tags(r.get("ID")),
                "vendor":    _strip_tags(r.get("Vendor")),
                "leads":     _clean_num(r.get("Leads")),
                "billable":  _clean_num(r.get("Billable")),   # "All Calls" on the Vendor CPA screen
                "sales":     _clean_num(r.get("Sales")),
                "policies":  _clean_num(r.get("Policies")),
                "spend":     _clean_num(r.get("Spend")),
            })
        return out

    def agent_cpa(self, start, end):
        """Per-agent CPA + COST plus period totals from report_cpa_agent for the date
        range. Returns {"by_agent": {name_key: {"cpa":..., "cost":...}},
        "totals": {"cost":..., "sales":..., "cpa":...}}.

        Cached per (start, end) for _CPA_CACHE_TTL seconds. Concurrent callers for the
        same range share ONE fetch (so startup warming + the page's lazy load never
        double-hit this heavy report) — the first caller fetches, the rest wait."""
        cache_key = (start, end)
        now = time.time()
        with _CPA_LOCK:
            hit = _CPA_CACHE.get(cache_key)
            if hit and now - hit[0] < _CPA_CACHE_TTL:    # fresh in-memory copy
                metrics.log("agent_cpa", start=start, end=end, source="mem-cache")
                return hit[1]

        # Disk cache: a range that ended before today is FINAL — its numbers never
        # change, so serve it from cache/ forever and never re-hit the API.
        disk = cache.load("agent_cpa", start, end)
        if disk is not None:
            with _CPA_LOCK:
                _CPA_CACHE[cache_key] = (now, disk)
            return disk

        with _CPA_LOCK:
            ev = _CPA_INFLIGHT.get(cache_key)
            leader = ev is None
            if leader:                                   # we own the fetch for this range
                ev = threading.Event()
                _CPA_INFLIGHT[cache_key] = ev

        if not leader:                                   # someone else is already fetching — wait for it
            ev.wait(timeout=120)
            with _CPA_LOCK:
                hit = _CPA_CACHE.get(cache_key)
            return hit[1] if hit else {"by_agent": {}, "totals": {}}

        try:
            result = self._fetch_agent_cpa(start, end)
            cache.save("agent_cpa", start, end, result)  # persist if the range is final
            with _CPA_LOCK:
                _CPA_CACHE[cache_key] = (time.time(), result)
            return result
        finally:
            with _CPA_LOCK:
                _CPA_INFLIGHT.pop(cache_key, None)
            ev.set()                                     # release any waiters

    def _fetch_agent_cpa(self, start, end):
        """The actual report_cpa_agent call + parse (no caching). Honors
        date/date_end + date_sold/date_sold_end (NOT start_date/end_date)."""
        s0, e1 = f"{start} 00:00:00", f"{end} 23:59:59"
        body = {
            "columns": ["agent", "agent_id", "sales", "costs_all",
                        "cpa_cost_calls_all_by_sales", "calls_billable"],
            "limit": 1000,                           # cover the full roster (matches agent_policies)
            "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1,
        }
        # Use the same proven request+unwrap path the working probe uses.
        resp = config.egress_get("report_cpa_agent", body, timeout=max(self.timeout, 90))

        # report_cpa_agent returns {data|results|rows: [...], totals: {...}} (sometimes
        # wrapped in "response", which egress_get already peels). Pull out rows + totals.
        rows = resp if isinstance(resp, list) else []
        totals = {}
        if isinstance(resp, dict):
            for k in ("results", "data", "rows", "report", "records", "agents"):
                if isinstance(resp.get(k), list):
                    rows = resp[k]
                    break
            if isinstance(resp.get("totals"), dict):
                totals = resp["totals"]

        out = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            full, loose = _name_keys(r.get("agent"))
            if not full:
                continue
            rec = {"cpa":  _num(r.get("cpa_cost_calls_all_by_sales")),
                   "cost": _num(r.get("costs_all"))}
            out[full] = rec
            out.setdefault(loose, rec)               # loose alias (drops middle name) as a fallback match

        # Period totals: prefer the report's own totals row; else sum the rows.
        if totals:
            tot = {"cost":  _num(totals.get("costs_all")),
                   "sales": _num(totals.get("sales")),
                   "cpa":   _num(totals.get("cpa_cost_calls_all_by_sales")),
                   "billable_calls": _num(totals.get("calls_billable"))}
        else:
            tcost = sum(_num(r.get("costs_all")) for r in rows if isinstance(r, dict))
            tsales = sum(_num(r.get("sales")) for r in rows if isinstance(r, dict))
            tcalls = sum(_num(r.get("calls_billable")) for r in rows if isinstance(r, dict))
            tot = {"cost": tcost, "sales": tsales,
                   "cpa": round(tcost / tsales, 2) if tsales else 0,
                   "billable_calls": tcalls}

        # Conversion = FALCON Sales / billable calls (the CRM 'Sales / All Calls %').
        # Isolated so a hiccup here never wipes the COST/CPA tiles.
        try:
            tot["conversion"] = self._falcon_conversion(start, end)
        except Exception:
            tot["conversion"] = 0.0

        # One-line diagnostic to the terminal (stderr) — does NOT touch the JSON the browser sees.
        print(f"[agent_cpa] {start}->{end}: {len(rows)} report rows; "
              f"sample agents={[r.get('agent') for r in rows[:5] if isinstance(r, dict)]}",
              file=sys.stderr)

        return {"by_agent": out, "totals": tot}

    def _falcon_conversion(self, start, end):
        """Conversion = Sales / billable CALLS for FALCON, from report_cpa_agent scoped to
        the Falcon vendor — matches the CRM Vendor CPA 'Sales / All Calls %' (whose 'All
        Calls' column is the billable-call count, = calls_billable). Note: vendorperformance
        'Billable' counts billable LEADS, not calls, which is why it ran high."""
        s0, e1 = f"{start} 00:00:00", f"{end} 23:59:59"
        body = {"columns": ["sales", "calls_billable"], "vendor_id": config.FALCON_VENDOR_ID,
                "limit": 2000, "date": s0, "date_end": e1, "date_sold": s0, "date_sold_end": e1}
        resp = config.egress_get("report_cpa_agent", body, timeout=max(self.timeout, 90))
        rows, totals = [], {}
        if isinstance(resp, dict):
            for k in ("results", "data", "rows", "report", "records", "agents"):
                if isinstance(resp.get(k), list):
                    rows = resp[k]
                    break
            if isinstance(resp.get("totals"), dict):
                totals = resp["totals"]
        elif isinstance(resp, list):
            rows = resp

        def _t(col):
            if totals.get(col) not in (None, ""):
                return _num(totals.get(col))
            return sum(_num(r.get(col)) for r in rows if isinstance(r, dict))

        sales, calls = _t("sales"), _t("calls_billable")
        return round(sales / calls * 100, 1) if calls else 0.0

    def build_dashboard(self, start, end, range_label):
        # start/end are resolved ISO dates (preset or custom) — see app._resolve_range.

        # Disk cache: a fully-past range is final, so reuse the saved result and skip
        # every API call. Ranges that include today fall through and load live.
        cached = cache.load("dashboard", start, end)
        if cached is not None:
            cached["range_label"] = range_label
            return cached

        # All queries are independent and filtered server-side, so run them
        # concurrently — the dashboard loads in ~one round-trip instead of seven.
        jobs = {
            "policy_rows": lambda: self.run("policies_ids", start, end),
            "avg_gtl":    lambda: _first_num(self.run("avg_gtl_premium", start, end)),
            "recent":     lambda: self.run("recent_sales"),
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

        # One policies pull, deduped ONCE, then sliced so the numbers can't disagree:
        #   • Policies by Carrier: deduped, ALL carriers (incl GTL) -> matches the CRM table
        #   • Policies Sold + enrollments: deduped AND GTL-excluded (separate product line)
        deduped_all = _dedupe_rows(results.get("policy_rows") or [])
        excluded = config.EXCLUDED_POLICY_CARRIERS
        kept_policies = [r for r in deduped_all
                         if str(r.get("carrier_name") or "").strip().upper() not in excluded]
        policies = len(kept_policies)
        enrollments = enrollment_tracker(kept_policies)
        by_carrier = _carrier_breakdown(deduped_all)     # all carriers incl GTL -> matches table
        active_by_carrier = _active_by_carrier(deduped_all)  # active vs sold per carrier (retention)
        by_state = _state_breakdown(kept_policies)       # deals per customer state (GTL-excluded)
        agents = _agent_breakdown(kept_policies)         # GTL-excluded -> agent total = Policies Sold

        recent = [{
            "date_sold": r.get("date_sold"),
            "lead_id": r.get("lead_id"),
            "agent": r.get("agent_name") or r.get("agent"),
            "agent_commission": _num(r.get("commission_paid")),
            "enroller": r.get("fronter_name") or r.get("fronter"),
            "fronter_commission": _num(r.get("commission_paid_fronter")),
            "carrier": r.get("carrier_name") or r.get("carrier"),
        } for r in (results.get("recent") or [])]

        # Agent rows carry name + policies only here (deduped, stage=sale, GTL-excluded, so
        # the table's policy total equals Policies Sold). COST/CPA + the Total Spend / Blended
        # CPA tiles load separately via GET /api/agent_cpa, so the heavy report never blocks paint.

        data = {
            "demo": False,
            "range_label": range_label,
            "date_range": {"start": start, "end": end},
            "kpis": {
                "policies_sold": policies,
                "avg_gtl_premium": results.get("avg_gtl") or 0,
                # conversion_rate loads in phase 2 (it needs the heavy report) — see /api/agent_cpa
            },
            "by_carrier": by_carrier,
            "active_by_carrier": active_by_carrier,
            "by_state": by_state,
            "recent_sales": recent,
            "agents": agents,
            "enrollments": enrollments,
        }
        if errors:
            data["error"] = "Some metrics didn't load: " + "; ".join(errors)
        else:
            cache.save("dashboard", start, end, data)   # persist clean results for final ranges
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


def _strip_tags(v):
    """Drop HTML tags — the vendor report wraps cell values in <a> links."""
    return re.sub(r"<[^>]+>", "", str(v if v is not None else "")).strip()


def _clean_num(v):
    """Parse a number from a possibly HTML/$/comma/%-wrapped cell -> int/float, else 0."""
    s = re.sub(r"<[^>]+>", "", str(v if v is not None else ""))
    s = s.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        f = float(s)
    except ValueError:
        return 0
    return int(f) if f.is_integer() else f


# The dedupe key is ALWAYS canonical: policy_id first, then lead_id. Every other id
# (id, *_id) is NOT part of the key — it only rides along to differentiate records on
# inspection. We use another id as the key ONLY if a record has neither canonical id
# (absolutely necessary, so the row still dedupes instead of being dropped).
CANONICAL_IDS = ["policy_id", "lead_id"]
_EMPTY_IDS = (None, "", "0", 0)


def _dedupe_key(rec):
    """Unique key: policy_id, else lead_id — the canonical keys, in that order. Only if
    BOTH are absent does it fall back to any other *_id / id, so a record without a
    canonical id still dedupes rather than vanishing. Namespaced (field:value) so id
    spaces never collide. None / "" / "0" / 0 count as 'no id'."""
    for field in CANONICAL_IDS:                      # always: policy_id -> lead_id
        v = rec.get(field)
        if v not in _EMPTY_IDS:
            return f"{field}:{v}"
    for field in sorted(rec):                        # last resort only (no canonical id)
        if (field == "id" or field.endswith("_id")) and rec.get(field) not in _EMPTY_IDS:
            return f"{field}:{rec[field]}"
    return None


def dedupe_ids(records):
    """Fold records into a SET of unique keys (policy_id-else-lead_id). The same policy
    (or lead) only ever lands once, so len() can't double-count — across one pull or many.
    A lead with two policies yields two keys; the same lead with no policy yields one."""
    keys = set()
    for r in records:
        if isinstance(r, dict):
            k = _dedupe_key(r)
            if k:
                keys.add(k)
    return keys


def _dedupe_rows(rows):
    """Deduped, SALE-stage policy rows (canonical key policy_id -> lead_id, first row per
    key). Policies whose stage isn't in config.POLICY_STAGE_INCLUDE (e.g. "redacted"/trash)
    are dropped HERE, so every downstream count — carrier chart, Policies Sold, enrollments,
    and the agent table — counts the same real sales and matches the CRM's carrier table.
    No carrier filtering here (the carrier chart needs all carriers incl GTL)."""
    include = config.POLICY_STAGE_INCLUDE
    seen, kept = set(), []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if str(r.get("stage") or "").strip().lower() not in include:
            continue
        k = _dedupe_key(r)
        if k and k not in seen:
            seen.add(k)
            kept.append(r)
    return kept


def _kept_policies(rows):
    """Deduped + GTL-excluded policy rows — the basis for Policies Sold and the
    enrollment tracker (GTL is a separate product line)."""
    excluded = config.EXCLUDED_POLICY_CARRIERS
    return [r for r in _dedupe_rows(rows)
            if str(r.get("carrier_name") or "").strip().upper() not in excluded]


def _carrier_breakdown(deduped_rows):
    """Per-carrier metrics from already-deduped rows — ALL carriers, INCLUDING GTL, so the
    chart reconciles to the CRM's own carrier table. Each entry is {label, count, enrolled},
    where 'enrolled' = how many of that carrier's deals have a fronter (an enroller).
    Sorted high to low by count."""
    by = {}
    for r in deduped_rows:
        label = (str(r.get("carrier_name") or "").strip() or "—")
        g = by.setdefault(label, {"label": label, "count": 0, "enrolled": 0})
        g["count"] += 1
        if str(r.get("fronter_id") or "").strip() not in ("", "0"):
            g["enrolled"] += 1
    out = list(by.values())
    out.sort(key=lambda x: -x["count"])
    return out


def _active_by_carrier(deduped_rows):
    """Active-policy breakdown per carrier from already-deduped, stage=sale rows (ALL
    carriers incl GTL). Per carrier: sold (all stage=sale), active (status = active), and a
    per-state split (states:[{state, active, sold}]) so clicking a carrier can show its
    active policies by state. Sorted by active count, high to low."""
    by = {}
    for r in deduped_rows:
        car = str(r.get("carrier_name") or "").strip() or "—"
        c = by.setdefault(car, {"carrier": car, "sold": 0, "active": 0, "_st": {}})
        c["sold"] += 1
        is_active = str(r.get("status_name") or "").strip().lower() == "active"
        if is_active:
            c["active"] += 1
        state = str(r.get("lead_state") or "").strip().upper()
        if state:
            s = c["_st"].setdefault(state, {"state": state, "active": 0, "sold": 0})
            s["sold"] += 1
            if is_active:
                s["active"] += 1
    out = []
    for c in by.values():
        states = sorted(c["_st"].values(), key=lambda x: -x["active"])
        out.append({"carrier": c["carrier"], "sold": c["sold"], "active": c["active"], "states": states})
    out.sort(key=lambda x: -x["active"])
    return out


def _state_breakdown(rows):
    """Per customer-state (lead_state) breakdown from already-deduped, GTL-excluded rows, so
    state totals reconcile with Policies Sold. Each entry has the deal count plus everything
    needed for a click-through: {state, count, enrolled, carriers:[{label,count}],
    agents:[{name,count}]}. Sorted high to low by count."""
    st = {}
    for r in rows:
        state = str(r.get("lead_state") or "").strip().upper()
        if not state:
            continue
        s = st.setdefault(state, {"state": state, "count": 0, "enrolled": 0, "_car": {}, "_ag": {}})
        s["count"] += 1
        if str(r.get("fronter_id") or "").strip() not in ("", "0"):
            s["enrolled"] += 1
        car = str(r.get("carrier_name") or "").strip() or "—"
        s["_car"][car] = s["_car"].get(car, 0) + 1
        ag = str(r.get("agent_name") or "").strip()
        if ag:
            s["_ag"][ag] = s["_ag"].get(ag, 0) + 1
    out = []
    for s in st.values():
        carriers = sorted(({"label": k, "count": v} for k, v in s["_car"].items()), key=lambda x: -x["count"])
        agents = sorted(({"name": k, "count": v} for k, v in s["_ag"].items()), key=lambda x: -x["count"])
        out.append({"state": s["state"], "count": s["count"], "enrolled": s["enrolled"],
                    "carriers": carriers, "agents": agents})
    out.sort(key=lambda x: -x["count"])
    return out


def _agent_breakdown(rows):
    """Policy count per agent from already-deduped, GTL-excluded rows — drives the Agent
    Performance table so its policy total equals Policies Sold. Skips the unassigned /
    null-agent bucket. Sorted high to low."""
    by = {}
    for r in rows:
        name = str(r.get("agent_name") or "").strip()
        if not name:
            continue
        by[name] = by.get(name, 0) + 1
    out = [{"name": k, "policies": v} for k, v in by.items()]
    out.sort(key=lambda x: -x["policies"])
    return out


def _sales_board(deduped_rows):
    """One row per person — agents (closers) and fronters (enrollers) together. Each entry:
    closed (deals as agent), enrolled (deals as fronter), total, and a by-carrier breakdown
    of their closed deals. Sorted by total, then closed, then name."""
    people = {}
    for r in deduped_rows:
        a = str(r.get("agent_name") or "").strip()
        f = str(r.get("fronter_name") or "").strip()
        car = str(r.get("carrier_name") or "").strip() or "—"
        if a:
            p = people.setdefault(a, {"name": a, "closed": 0, "enrolled": 0, "commission": 0, "_car": {}})
            p["closed"] += 1
            p["commission"] += _num(r.get("commission_paid"))            # agent's cut on a sale
            p["_car"][car] = p["_car"].get(car, 0) + 1
        if f:
            p = people.setdefault(f, {"name": f, "closed": 0, "enrolled": 0, "commission": 0, "_car": {}})
            p["enrolled"] += 1
            p["commission"] += _num(r.get("commission_paid_fronter"))     # enroller's cut on an enrollment
    out = []
    for p in people.values():
        carriers = sorted(({"label": k, "count": v} for k, v in p["_car"].items()), key=lambda x: -x["count"])
        out.append({"name": p["name"], "closed": p["closed"], "enrolled": p["enrolled"],
                    "total": p["closed"] + p["enrolled"], "commission": round(p["commission"], 2),
                    "carriers": carriers})
    out.sort(key=lambda x: (-x["total"], -x["closed"], x["name"]))
    return out


def enrollment_tracker(kept_rows):
    """Group already-deduped, GTL-excluded policy rows by fronter (the enroller). Returns
    {"total": N, "by_enroller": [{fronter_id, name, count} sorted desc], "no_enroller": M}.
    Rows with no fronter (self-generated) are counted under no_enroller, not attributed."""
    by, no_enroller = {}, 0
    for r in kept_rows:
        fid = str(r.get("fronter_id") or "").strip()
        if fid in ("", "0"):
            no_enroller += 1
            continue
        g = by.setdefault(fid, {"fronter_id": fid, "name": None, "count": 0, "_detail": {}})
        g["count"] += 1
        g["name"] = r.get("fronter_name") or g["name"]
        agent = str(r.get("agent_name") or "—").strip() or "—"
        carrier = str(r.get("carrier_name") or "—").strip() or "—"
        g["_detail"][(agent, carrier)] = g["_detail"].get((agent, carrier), 0) + 1
    rows = []
    for g in sorted(by.values(), key=lambda g: (-g["count"], str(g["name"] or ""))):
        detail = [{"agent": a, "carrier": c, "count": n} for (a, c), n in g["_detail"].items()]
        detail.sort(key=lambda x: -x["count"])
        rows.append({"fronter_id": g["fronter_id"], "name": g["name"], "count": g["count"], "detail": detail})
    return {"total": sum(g["count"] for g in rows), "by_enroller": rows, "no_enroller": no_enroller}


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
