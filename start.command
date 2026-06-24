#!/bin/bash
#
# iHealth Plans dashboard launcher.
# Double-click this file to start the dashboard. A Terminal window opens and
# your browser follows automatically. Keep that window open while you use the
# dashboard — closing it (or pressing Ctrl+C) stops the server.
#

# Move into the folder this script lives in (works wherever the folder is).
cd "$(dirname "$0")" || exit 1

echo "Starting the iHealth Plans dashboard..."
echo "Your browser will open at http://localhost:5050 in a moment."
echo "Keep this window open while you use it. Close it (or press Ctrl+C) to stop."
echo

# Make sure required packages are installed (only does real work the first time).
python3 -m pip install -r requirements.txt --quiet 2>/dev/null \
  || python3 -m pip install -r requirements.txt --quiet --break-system-packages 2>/dev/null

# Launch the app (it opens the browser for you at http://localhost:5050).
python3 app.py
