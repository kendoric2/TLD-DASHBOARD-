"""
Probe a TLD report endpoint — readable. Columns + sample + a date-filter hunt
(tries a few param names, body vs query, dates as 'YYYY-MM-DD HH:MM:SS').

Usage:
  python3 sandbox/probes/probe_report.py report_cpa_agent
  python3 sandbox/probes/probe_report.py tldialer/report_agentcpa
"""
import sys
import requests
import _probe_lib as p

config = p.config
t = p.t
config.require_creds()

ep = (sys.argv[1] if len(sys.argv) > 1 else "agentcpa").strip("/")
URL = f"{config.TLD_BASE_URL}/api/egress/{ep}"

p.hr(f"/api/egress/{ep}")
p.show_columns(p.cols_of(ep))
print("\nsample:")
p.show_rows(p.pull(ep, 3), 3)


def summ(resp):
    if isinstance(resp, str):
        return resp[:50]
    rows, _ = p.as_rows(resp)
    return (f"rows={len(rows):<4} sales={sum(t._num(x.get('sales')) for x in rows):<5} "
            f"cost={sum(t._num(x.get('cost')) for x in rows):,.0f}")


def fetch(mode, params):
    try:
        if mode == "query":
            r = requests.get(URL, headers=config.HEADERS_GET, params=params, timeout=60)
        else:
            r = requests.get(URL, headers=config.HEADERS, json=params, timeout=60)
        return config.unwrap(r.json())
    except Exception as ex:
        return f"ERR {type(ex).__name__}"


print("\ndate-filter hunt (last_month vs today):")
lm = t.date_range_for("last_month")
td = t.date_range_for("today")
for a, b in [("start_date", "end_date"), ("date_start", "date_end"), ("start", "end")]:
    for mode in ("body", "query"):
        lmv = fetch(mode, {a: lm[0] + " 00:00:00", b: lm[1] + " 23:59:59"})
        tdv = fetch(mode, {a: td[0] + " 00:00:00", b: td[1] + " 23:59:59"})
        flag = ""
        if isinstance(lmv, list) and isinstance(tdv, list) and summ(lmv) != summ(tdv):
            flag = "   *** FILTERS ***"
        print(f"  [{mode:5}] {(a + '/' + b).ljust(20)} last_month {summ(lmv)}")
        print(f"          {''.ljust(20)} today      {summ(tdv)}{flag}")

print("\nDone. Paste this back.")
