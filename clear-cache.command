#!/bin/bash
# Double-click to clear the dashboard's disk cache (safe — read-only to the CRM).
cd "$(dirname "$0")"
python3 tools/clear_cache.py
echo
read -n 1 -s -r -p "Done. Press any key to close."
echo
