"""
Disk cache for FINAL (past) date ranges.

Historical data never changes once the day is over, so a range that ENDS BEFORE TODAY
is "final": we save its result to disk once and reuse it on every later run — no API
call, even after a restart. Ranges that include today are volatile and are never
written here (the short in-memory TTL cache in tldcrm_client handles those, because
today's numbers are still climbing).

Files live in <project_root>/cache/ (git-ignored — this is derived data, not source).
Each file is keyed by namespace + the resolved start/end dates + a schema version, so
bumping SCHEMA_VERSION (or changing the dates) automatically ignores stale files.

Safe to delete the cache/ folder's contents anytime — it just rebuilds on demand.
"""
import os
import sys
import csv
import json
import datetime

import metrics

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # src/ -> project root
CACHE_DIR = os.path.join(_ROOT, "cache")
SNAPSHOT_PATH = os.path.join(metrics.LOG_DIR, "cache_snapshot.csv")
SCHEMA_VERSION = 6            # bump this to invalidate every existing cache file at once
#                              (v6: enrollment detail per enroller; sales_board carriers list)


def is_final_range(end):
    """True if the range ends before today — i.e. its data is done changing."""
    try:
        end_d = datetime.date.fromisoformat(str(end)[:10])
    except (ValueError, TypeError):
        return False
    return end_d < datetime.date.today()


def _path(namespace, start, end):
    name = f"v{SCHEMA_VERSION}__{namespace}__{start}__{end}.json".replace("/", "-")
    return os.path.join(CACHE_DIR, name)


def load(namespace, start, end):
    """Return cached data for a FINAL range, or None (miss / volatile / unreadable)."""
    if not is_final_range(end):
        return None
    try:
        with open(_path(namespace, start, end), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    print(f"[cache] {namespace} {start}..{end} served from disk (no API call)", file=sys.stderr)
    metrics.log(namespace, start=start, end=end, source="disk-cache")
    return data


def save(namespace, start, end, data):
    """Persist data for a FINAL range only. Ranges that include today are skipped."""
    if not is_final_range(end):
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = _path(namespace, start, end)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)            # atomic swap so a reader never sees a half-written file
        snapshot()                       # keep logs/cache_snapshot.csv current
    except OSError:
        pass


def _summarize(path, namespace):
    """A short, best-effort human note about a cache entry's contents."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return ""
    try:
        if namespace == "dashboard" and isinstance(d, dict):
            k = d.get("kpis", {}) or {}
            return f"policies_sold={k.get('policies_sold')}; agents={len(d.get('agents') or [])}"
        if namespace == "agent_cpa" and isinstance(d, dict):
            t = d.get("totals", {}) or {}
            return f"agents={len(d.get('by_agent') or {})}; spend={t.get('cost')}; conv={t.get('conversion')}"
    except Exception:
        return ""
    return ""


def snapshot():
    """(Re)write logs/cache_snapshot.csv from the current disk cache. Returns row count."""
    rows = []
    try:
        files = sorted(f for f in os.listdir(CACHE_DIR) if f.endswith(".json"))
    except OSError:
        files = []
    for name in files:
        path = os.path.join(CACHE_DIR, name)
        parts = name[:-5].split("__")            # v{schema}__{namespace}__{start}__{end}
        schema = parts[0] if len(parts) > 0 else ""
        namespace = parts[1] if len(parts) > 1 else ""
        start = parts[2] if len(parts) > 2 else ""
        end = parts[3] if len(parts) > 3 else ""
        try:
            st = os.stat(path)
            size_kb = round(st.st_size / 1024, 1)
            modified = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            size_kb, modified = "", ""
        rows.append([namespace, start, end, schema, size_kb, modified, _summarize(path, namespace)])
    try:
        os.makedirs(metrics.LOG_DIR, exist_ok=True)
        with open(SNAPSHOT_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["namespace", "start", "end", "schema", "size_kb", "modified", "summary"])
            w.writerows(rows)
    except OSError:
        pass
    return len(rows)


def clear():
    """Delete every cached file and refresh the snapshot. Returns how many were removed."""
    removed = 0
    try:
        for name in os.listdir(CACHE_DIR):
            if name.endswith(".json"):
                try:
                    os.remove(os.path.join(CACHE_DIR, name))
                    removed += 1
                except OSError:
                    pass
    except OSError:
        pass
    snapshot()
    return removed
