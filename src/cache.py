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
import json
import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # src/ -> project root
CACHE_DIR = os.path.join(_ROOT, "cache")
SCHEMA_VERSION = 2            # bump this to invalidate every existing cache file at once


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
    except OSError:
        pass
