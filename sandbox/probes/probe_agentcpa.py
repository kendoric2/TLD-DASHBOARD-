"""
agentcpa date-parameter HUNT — read-only, aggregates only (no customer PII).

First pass showed agentcpa ignored date params sent in the JSON body. This goes
deeper: it tries dates as URL QUERY-STRING params vs JSON body, ~10 param-name
shapes, both date formats (M/D/YYYY and YYYY-MM-DD), and compares a PAST window
(last_month) against TODAY. If a param actually filters, last_month's totals will
differ from today's -> the line is flagged  *** FILTERS ***.

Run:  python3 sandbox/probes/probe_agentcpa.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import requests
import config
import tldcrm_client as t

config.require_creds()
URL = f"{config.TLD_BASE_URL}/api/egress/agentcpa"

lm_s, lm_e = t.date_range_for("last_month")   # ISO strings
td_s, td_e = t.date_range_for("today")


def val(iso_date, fmt):
    return t._us(iso_date) if fmt == "US" else iso_date


def fetch(mode, params):
    try:
        if mode == "query":
            r = requests.get(URL, headers=config.HEADERS_GET, params=params, timeout=config.TIMEOUT)
        else:
            r = requests.get(URL, headers=config.HEADERS, json=params, timeout=config.TIMEOUT)
        rows = config.unwrap(r.json())
    except Exception as ex:
        return f"ERR {type(ex).__name__}"
    if not isinstance(rows, list):
        return f"HTTP {getattr(r,'status_code','?')}"
    return (len(rows), sum(t._num(x.get("sales")) for x in rows),
            sum(t._num(x.get("policies")) for x in rows),
            round(sum(t._num(x.get("cost")) for x in rows)))


def fmt(tot):
    return tot if isinstance(tot, str) else f"agents={tot[0]:<4} sales={tot[1]:<5} pol={tot[2]:<5} cost={tot[3]:,}"


pairs = [("start_date", "end_date"), ("date_start", "date_end"), ("from", "to"),
         ("date_from", "date_to"), ("report_start", "report_end"),
         ("begin_date", "end_date"), ("group_start_date", "group_end_date")]
singles = ["date", "report_date", "day"]

plan = []
for a, b in pairs:
    plan.append(("query", "US", a, b))
for s in singles:
    plan.append(("query", "US", s, None))
for a, b in pairs[:3]:
    plan.append(("query", "ISO", a, b))
for a, b in pairs[:4]:
    plan.append(("body", "US", a, b))

baseline = fetch("query", {})
print("baseline (no params):", fmt(baseline), "\n")

for mode, f, a, b in plan:
    lm = {a: val(lm_s, f)} if b is None else {a: val(lm_s, f), b: val(lm_e, f)}
    td = {a: val(td_s, f)} if b is None else {a: val(td_s, f), b: val(td_e, f)}
    lm_t, td_t = fetch(mode, lm), fetch(mode, td)
    flag = ""
    if isinstance(lm_t, tuple) and isinstance(td_t, tuple) and lm_t != baseline and lm_t != td_t:
        flag = "   *** FILTERS ***"
    label = f"{a}{('/'+b) if b else ''} [{f}]"
    print(f"[{mode:5}] {label:34} last_month={fmt(lm_t)}")
    print(f"{'':7} {'':34} today     ={fmt(td_t)}{flag}")

print("\nIf nothing is flagged *** FILTERS ***, agentcpa is fixed to today and can't be date-ranged via the API.")
