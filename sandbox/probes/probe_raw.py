"""
Raw request inspector — shows EXACTLY what we send and what TLD returns.
No unwrap, no formatting, no helpers. For live debugging of how an endpoint
wants its date range.

Usage:
  python3 sandbox/probes/probe_raw.py report_cpa_agent query   # dates in URL query string (default)
  python3 sandbox/probes/probe_raw.py report_cpa_agent body    # dates in JSON body
  python3 sandbox/probes/probe_raw.py report_cpa_agent query 2026-05-01 2026-05-31
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import json
import requests
import config
import tldcrm_client as t

config.require_creds()
ep = (sys.argv[1] if len(sys.argv) > 1 else "report_cpa_agent").strip("/")
mode = sys.argv[2] if len(sys.argv) > 2 else "query"
start = sys.argv[3] if len(sys.argv) > 3 else t.date_range_for("today")[0]
end = sys.argv[4] if len(sys.argv) > 4 else t.date_range_for("today")[1]

URL = f"{config.TLD_BASE_URL}/api/egress/{ep}"
dates = {"start_date": f"{start} 00:00:00", "end_date": f"{end} 23:59:59"}
safe_headers = {**config.HEADERS, "tld-api-id": "***", "tld-api-key": "***"}

print("=" * 64)
print("REQUEST WE'RE SENDING")
print("=" * 64)
print("method :", "GET")
print("url    :", URL)
print("headers:", safe_headers)
print("mode   :", mode, "(dates in URL query)" if mode == "query" else "(dates in JSON body)")
print("dates  :", dates)

if mode == "query":
    r = requests.get(URL, headers=config.HEADERS_GET, params=dates, timeout=90)
else:
    r = requests.get(URL, headers=config.HEADERS, json=dates, timeout=90)

print("\n" + "=" * 64)
print("WHAT TLD ACTUALLY RECEIVED / RETURNED")
print("=" * 64)
print("final url    :", r.url)              # shows the exact query string that was sent
print("status       :", r.status_code, "/", r.headers.get("content-type"))
print("response size:", len(r.text), "chars")
print("\n--- raw response (first 1800 chars) ---")
print(r.text[:1800])
