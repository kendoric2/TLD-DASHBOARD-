#!/bin/bash
#
# iHealth Plans dashboard launcher.
# Double-click this file to start the dashboard. A Terminal window opens and
# your browser follows automatically. Keep that window open while you use the
# dashboard; closing it (or pressing Ctrl+C) stops the server.
#
# Needs Node.js 20+ and the .NET 10 SDK (see README.md).

# Move into the folder this script lives in (works wherever the folder is).
cd "$(dirname "$0")/.." || exit 1

echo "Starting the iHealth Plans dashboard..."
echo "Your browser will open at http://localhost:5050 in a moment."
echo "Keep this window open while you use it. Close it (or press Ctrl+C) to stop."
echo

# First run only: install the packages.
[ -d node_modules ] || npm install --no-audit --no-fund

# Compiles the F#, starts the server and opens the browser.
npm start
