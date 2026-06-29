"""
metrics.py — always-on logging of TLD egress activity.

Every real call to TLD, and every cache hit that AVOIDED a call, is appended as a
row to logs/egress.csv so you can see exactly what the dashboard is doing and how
many API calls it's making. Open the CSV in Excel anytime.

Columns: datetime, endpoint, query, range, source, status, ms, count
  source = live | mem-cache | disk-cache
  status = HTTP status for live calls (or ERR); blank for cache hits
  ms     = duration of a live call in milliseconds; blank for cache hits
  count  = cumulative number of LIVE calls so far; blank for cache hits

Writing here is wrapped in try/except — logging must never break the dashboard.
This module imports nothing from the project (no import cycles).
"""
import os
import csv
import threading
import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # src/ -> project root
LOG_DIR = os.path.join(_ROOT, "logs")
LOG_PATH = os.path.join(LOG_DIR, "egress.csv")
HEADER = ["datetime", "endpoint", "query", "range", "source", "status", "ms", "count"]

_LOCK = threading.Lock()
_live_count = None            # lazily seeded from the existing file so counts survive restarts


def _init_count():
    """Seed the cumulative live-call counter from the last live row already on disk."""
    global _live_count
    if _live_count is not None:
        return
    n = 0
    try:
        with open(LOG_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (row.get("source") or "").strip() == "live":
                    c = (row.get("count") or "").strip()
                    if c.isdigit():
                        n = int(c)
    except (OSError, ValueError):
        n = 0
    _live_count = n


def log(endpoint, *, query=None, start=None, end=None, source="live", status=None, ms=None):
    """Append one row. source 'live' increments the cumulative count; cache hits don't."""
    global _live_count
    try:
        with _LOCK:
            _init_count()
            count = ""
            if source == "live":
                _live_count += 1
                count = _live_count
            rng = f"{start}..{end}" if (start and end) else ""
            row = [
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                endpoint or "",
                query or "",
                rng,
                source,
                "" if status is None else status,
                "" if ms is None else ms,
                count,
            ]
            os.makedirs(LOG_DIR, exist_ok=True)
            new = not os.path.exists(LOG_PATH)
            with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(HEADER)
                w.writerow(row)
    except Exception:
        pass   # never let logging raise into the app


def summary():
    """Aggregate the whole log: counts per source + per endpoint for live calls."""
    totals = {"live": 0, "mem-cache": 0, "disk-cache": 0}
    by_endpoint = {}
    try:
        with open(LOG_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                src = (row.get("source") or "").strip()
                totals[src] = totals.get(src, 0) + 1
                if src == "live":
                    ep = row.get("endpoint") or "?"
                    by_endpoint[ep] = by_endpoint.get(ep, 0) + 1
    except OSError:
        pass
    return {"totals": totals, "by_endpoint": by_endpoint}
