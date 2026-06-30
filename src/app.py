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
import os
import datetime
import threading
import webbrowser
from flask import Flask, jsonify, render_template, request

import config
import cache
from sample_data import get_sample_dashboard, get_sample_board

# date_range_for only reads the JSON template (no credentials needed); used so
# demo responses also report the resolved start/end dates.
try:
    from tldcrm_client import date_range_for
except Exception:
    date_range_for = None

# This file lives in src/; templates/ and static/ are at the project root (one level up).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(_ROOT, "templates"),
            static_folder=os.path.join(_ROOT, "static"))

RANGE_LABELS = {
    "today": "Today",
    "this_week": "This Week",
    "this_month": "This Month",
    "last_month": "Last Month",
    "this_quarter": "This Quarter",
}

MAX_RANGE_DAYS = 366   # cap a custom From/To range at ~12 months


def _parse_iso(s):
    """Parse 'YYYY-MM-DD' to a date, or None if blank/invalid."""
    try:
        return datetime.date.fromisoformat((s or "").strip())
    except (ValueError, TypeError, AttributeError):
        return None


def _custom_label(a, b):
    """Readable label for a range, e.g. 'Jun 1 – Jun 15, 2026'. Single days get friendly
    names (Today / Yesterday) so the default view still reads nicely."""
    if a == b:
        today = datetime.date.today()
        if a == today:
            return "Today"
        if a == today - datetime.timedelta(days=1):
            return "Yesterday"
        return f"{a.strftime('%b')} {a.day}, {a.year}"
    if a.year == b.year:
        return f"{a.strftime('%b')} {a.day} – {b.strftime('%b')} {b.day}, {b.year}"
    return f"{a.strftime('%b')} {a.day}, {a.year} – {b.strftime('%b')} {b.day}, {b.year}"


def _resolve_range(args):
    """Resolve request args to (start_iso, end_iso, label). Supports presets
    (range=today…) and a custom From/To range (range=custom&start=&end=).
    Raises ValueError on bad custom input."""
    range_key = args.get("range", "today")
    if range_key == "custom":
        a, b = _parse_iso(args.get("start")), _parse_iso(args.get("end"))
        if not a or not b:
            raise ValueError("Custom range needs a valid start and end date (YYYY-MM-DD).")
        if b < a:
            raise ValueError("End date can't be before the start date.")
        if (b - a).days > MAX_RANGE_DAYS:
            raise ValueError("Custom range can't exceed 12 months.")
        return a.isoformat(), b.isoformat(), _custom_label(a, b)
    if date_range_for is None:
        today = datetime.date.today().isoformat()
        return today, today, RANGE_LABELS.get(range_key, "Today")
    start, end = date_range_for(range_key)
    return start, end, RANGE_LABELS.get(range_key, "Today")


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
    try:
        start, end, label = _resolve_range(request.args)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    client = _client()
    if client is None:
        data = get_sample_dashboard(label)               # demo mode
        data["date_range"] = {"start": start, "end": end}
        return jsonify(data)

    try:
        return jsonify(client.build_dashboard(start, end, label))
    except Exception as e:
        # Never break the UI: fall back to sample data and surface the error
        data = get_sample_dashboard(label)
        data["demo"] = True
        data["error"] = f"Live pull failed, showing sample data: {e}"
        data["date_range"] = {"start": start, "end": end}
        return jsonify(data)


@app.route("/api/agent_cpa")
def api_agent_cpa():
    """Lazy endpoint for the heavy CPA report. The page renders first from /api/dashboard,
    then fetches this to fill COST/CPA + the Total Spend / Blended CPA tiles. Cached
    server-side (5 min), so after the first call it returns instantly."""
    client = _client()
    if client is None:
        return jsonify({"by_agent": {}, "totals": {}})    # demo: sample data already carries CPA/COST
    try:
        start, end, _ = _resolve_range(request.args)
        return jsonify(client.agent_cpa(start, end))
    except ValueError as e:
        return jsonify({"by_agent": {}, "totals": {}, "error": str(e)}), 400
    except Exception as ex:
        return jsonify({"by_agent": {}, "totals": {}, "error": str(ex)})


@app.route("/api/sales_board")
def api_sales_board():
    """Combined sales leaderboard (agents + fronters) for the board's OWN date range."""
    try:
        start, end, label = _resolve_range(request.args)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    client = _client()
    if client is None:
        data = get_sample_board(label)
        data["date_range"] = {"start": start, "end": end}
        return jsonify(data)

    try:
        data = client.sales_board(start, end)
        data["range_label"] = label
        data["date_range"] = {"start": start, "end": end}
        data["demo"] = False
        return jsonify(data)
    except Exception as e:
        data = get_sample_board(label)
        data["demo"] = True
        data["error"] = f"Live pull failed, showing sample data: {e}"
        data["date_range"] = {"start": start, "end": end}
        return jsonify(data)


def _warm_cpa_cache():
    """Prefetch the default range's CPA report at startup so the first page view is warm.
    Runs in a background thread; the dedupe in agent_cpa means the page's own lazy fetch
    will share this one call instead of starting a second."""
    client = _client()
    if client is None or date_range_for is None:
        return
    try:
        s, e = date_range_for("today")
        client.agent_cpa(s, e)
    except Exception:
        pass


@app.route("/health")
def health():
    return jsonify({"ok": True, "live": _client() is not None})


if __name__ == "__main__":
    # Default to 5050 — macOS uses port 5000 for AirPlay Receiver, which serves
    # a 403 "Access denied" page. Override anytime with: PORT=8000 python3 src/app.py
    port = config.PORT
    url = f"http://localhost:{port}"
    print(f"\n  iHealth Plans dashboard  ->  {url}\n  (press CTRL+C to stop)\n")
    # Pop the browser open once the server is up (set NO_BROWSER=1 to disable).
    if not config.NO_BROWSER:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # Warm the heavy CPA report for the default range in the background so the first view is fast.
    if config.have_creds():
        threading.Thread(target=_warm_cpa_cache, daemon=True).start()
    cache.snapshot()   # refresh logs/cache_snapshot.csv to reflect the current cache
    app.run(host="127.0.0.1", port=port, debug=False)
