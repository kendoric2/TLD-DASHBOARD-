#!/usr/bin/env python3
"""
Clear the dashboard's disk cache (the cache/ folder).

Read-only-safe: it only deletes derived cache files — it never touches the CRM.
After clearing, logs/cache_snapshot.csv is refreshed so it reflects the empty cache.

The in-memory CPA cache lives inside a running server process and can't be cleared
from here; it expires on its own within 5 minutes (or restart the server to drop it).

Run from anywhere:   python3 tools/clear_cache.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import cache  # noqa: E402

removed = cache.clear()
snap = os.path.join("logs", "cache_snapshot.csv")
print(f"Cleared {removed} cache file(s) from cache/.")
print(f"Snapshot refreshed: {snap}")
