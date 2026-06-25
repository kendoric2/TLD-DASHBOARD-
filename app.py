"""
iHealth Plans - TLDCRM Dashboard backend.

Architecture
------------
Python (this file + tldcrm_client.py)  =  API CALLING LAYER
    Talks to TLDCRM egress endpoints (read-only) using the payload templates
    in egress_payloads.json, aggregates with TQL, and serves clean JSON at
    /api/dashboard. The API key never leaves the server.

    Date handling: TLD egress is date-bounded with a start_date + end_date
    range, so each UI period is resolved to concrete dates before querying.

JavaScript (static/dashboard.js)        =  GUI LAYER
    Fetches that JSON and handles all on-screen actions: range switch,
    Refresh button, sorting the agent table, and drawing the charts.

Runs in DEMO mode (sample data) until TLD credentials are filled into .env.
"""

import threading
import webbrowser
from flask import Flask, jsonify, render_template, request

import config
from sample_data import get_sample_dashboard

# date_range_for only reads the JSON template (no credentials needed); used so
# demo responses also report the resolved start/end dates.
try:
    from tldcrm_client import date_range_for
except Exception:
    date_range_for = None

app = Flask(__name__)

RANGE_LABELS = {
    "today": "Today",
    "this_week": "This Week",
    "this_month": "This Month",
    "last_month": "Last Month",
    "this_quarter": "This Quarter",
}


def _client():
    """Return a live client if credentials are configured, else None (demo)."""
    if config.have_creds():
        from tldcrm_client import TLDCRMClient
        return TLDCRMClient(config.TLD_BASE_URL, config.TLD_API_ID, config.TLD_API_KEY)
    return None


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/dashboard")
def api_dashboard():
    range_key = request.args.get("range", "this_month")
    label = RANGE_LABELS.get(range_key, "This Month")

    client = _client()
    if client is None:
        data = get_sample_dashboard(label)               # demo mode
        if date_range_for:
            s, e = date_range_for(range_key)
            data["date_range"] = {"start": s, "end": e}
        return jsonify(data)

    try:
        return jsonify(client.build_dashboard(range_key, label))
    except Exception as e:
        # Never break the UI: fall back to sample data and surface the error
        data = get_sample_dashboard(label)
        data["demo"] = True
        data["error"] = f"Live pull failed, showing sample data: {e}"
        if date_range_for:
            s, e2 = date_range_for(range_key)
            data["date_range"] = {"start": s, "end": e2}
        return jsonify(data)


@app.route("/health")
def health():
    return jsonify({"ok": True, "live": _client() is not None})


if __name__ == "__main__":
    # Default to 5050 — macOS uses port 5000 for AirPlay Receiver, which serves
    # a 403 "Access denied" page. Override anytime with: PORT=8000 python3 app.py
    port = config.PORT
    url = f"http://localhost:{port}"
    print(f"\n  iHealth Plans dashboard  ->  {url}\n  (press CTRL+C to stop)\n")
    # Pop the browser open once the server is up (set NO_BROWSER=1 to disable).
    if not config.NO_BROWSER:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False)
