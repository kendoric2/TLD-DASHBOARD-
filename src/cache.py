"""
Disk cache for FULLY-PAST date ranges — with proof that the copy is still correct.

The previous version of this file was removed because it was unsafe in two ways, and
both are designed out here:

  1. It saved whatever came back, including empty/failed responses. Because a past range
     was treated as "final, never re-fetch", one bad reply froze COST/Spend/Calls at 0
     forever (July 2026 showed $0 while TLD had $392,560).
     -> Now: an empty result is NEVER stored.

  2. It cached the finished dashboard payload, so every new tile made old files render
     blank, patched by hand-bumping a schema number (it reached v6 and still broke).
     -> Now: we cache the RAW ROWS from TLD and recompute tiles from them. Adding a tile
        can't invalidate anything. The cache key includes the exact column list, so if a
        feature needs a column the cached rows lack, that's an automatic miss.

And the assumption the old design was built on — "a finished month can't change" — is
simply false: a probe found 196 of July's 2,058 policies had been modified within a week
(terms, chargebacks, corrections). So nothing here is trusted blindly. Every hit is
validated against TLD first; see tldcrm_client._range_unchanged_since().

Files live in <project_root>/cache/ (git-ignored — derived data, not source).
Safe to delete the folder at any time; it rebuilds on demand.
"""
import os
import json
import time
import hashlib
import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, "cache")


def is_final(end):
    """True only if the range ENDS BEFORE TODAY. Anything touching today is volatile and
    is never written here — today's numbers are still moving."""
    try:
        return datetime.date.fromisoformat(str(end)[:10]) < datetime.date.today()
    except (ValueError, TypeError):
        return False


def columns_sig(payload):
    """Short hash of the columns/filters a query asked for. Baked into the cache key so a
    query that later needs another column can't be served stale rows missing it."""
    try:
        blob = json.dumps(payload, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = str(payload)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def _path(namespace, start, end, sig):
    name = f"{namespace}__{start}__{end}__{sig}.json".replace("/", "-")
    return os.path.join(CACHE_DIR, name)


def load(namespace, start, end, sig):
    """Return the stored envelope {fetched_at, rows} for a final range, else None.
    The CALLER must still validate freshness before trusting `rows`."""
    if not is_final(end):
        return None
    try:
        with open(_path(namespace, start, end, sig), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("fetched_at"):
        return None
    if not data.get("rows"):          # an empty cached copy is treated as no copy at all
        return None
    return data


def save(namespace, start, end, sig, rows):
    """Persist rows for a final range. Empty results are deliberately not stored."""
    if not is_final(end) or not rows:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = _path(namespace, start, end, sig)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "namespace": namespace, "start": start, "end": end,
                       "rows": rows}, f)
        os.replace(tmp, path)          # atomic: a reader never sees a half-written file
    except OSError:
        pass


def drop(namespace, start, end, sig):
    """Remove a cached copy (used when validation says it's out of date)."""
    try:
        os.remove(_path(namespace, start, end, sig))
    except OSError:
        pass


def clear():
    """Delete every cached file. Returns how many were removed."""
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
    return removed
