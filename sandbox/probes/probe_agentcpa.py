"""
agentcpa date-filtering test — read-only, human-readable.

Sends start_date/end_date as datetimes ('YYYY-MM-DD HH:MM:SS') in several
combinations (body vs query, full-day vs date-only) and across windows
(today / yesterday / last month). If TODAY and a PAST window come back with
different totals, the date range is being honored. If everything is identical,
agentcpa ignores dates (it's a fixed live-today report).

Run: python3 sandbox/probes/probe_agentcpa.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import datetime
import requests
import _probe_lib as p

config = p.config
t = p.t
config.require_creds()

EP = "agentcpa"
URL = f"{config.TLD_BASE_URL}/api/egress/{EP}"

today = datetime.date.today()
yest = today - datetime.timedelta(days=1)
lm_s, lm_e = t.date_range_for("last_month")


def fetch(mode, params):
    try:
        if mode == "query":
            r = requests.get(URL, headers=config.HEADERS_GET, params=params, timeout=90)
        else:
            r = requests.get(URL, headers=config.HEADERS, json=params, timeout=90)
        rows, _ = p.as_rows(config.unwrap(r.json()))
        return rows
    except Exception as ex:
        return f"ERR {type(ex).__name__}"


def summarize(label, rows):
    if not isinstance(rows, list):
        print(f"  {label:46} {rows}")
        return None
    sales = sum(t._num(x.get("sales")) for x in rows)
    cost = sum(t._num(x.get("cost")) for x in rows)
    agents = sum(1 for x in rows if t._num(x.get("sales")) > 0)
    cpa = round(cost / sales, 2) if sales else 0
    print(f"  {label:46} sales={sales:<5} cost=${cost:<8,.0f} sellers={agents:<3} cpa=${cpa}")
    return (len(rows), sales, cost)


def dt(d, end=False):
    return f"{d.isoformat()} {'23:59:59' if end else '00:00:00'}"


p.hr(f"/api/egress/{EP}  — date-filter combinations")
print(f"today = {today}   yesterday = {yest}   last_month = {lm_s}..{lm_e}\n")

base = summarize("baseline (no date params)", fetch("body", {}))
print()

# combinations, all aiming at TODAY first, then contrast windows
combos = [
    ("today  full-day  body  start_date/end_date", "body",
     {"start_date": dt(today), "end_date": dt(today, True)}),
    ("today  full-day  query start_date/end_date", "query",
     {"start_date": dt(today), "end_date": dt(today, True)}),
    ("today  date-only body  start_date/end_date", "body",
     {"start_date": today.isoformat(), "end_date": today.isoformat()}),
    ("yesterday full-day body", "body",
     {"start_date": dt(yest), "end_date": dt(yest, True)}),
    ("last_month full-day body", "body",
     {"start_date": dt(datetime.date.fromisoformat(lm_s)), "end_date": dt(datetime.date.fromisoformat(lm_e), True)}),
]

sigs = {}
for label, mode, params in combos:
    sigs[label] = summarize(label, fetch(mode, params))

print("\nVERDICT:")
today_sig = sigs.get("today  full-day  body  start_date/end_date")
yest_sig = sigs.get("yesterday full-day body")
lm_sig = sigs.get("last_month full-day body")
if today_sig and (today_sig != yest_sig or today_sig != lm_sig):
    print("  agentcpa DOES honor the date range (today differs from a past window). We can date-filter it.")
elif today_sig and today_sig == base:
    print("  agentcpa IGNORES the date range (every window == baseline). It's a fixed live-today report.")
else:
    print("  inconclusive — compare the rows above.")
