#!/bin/bash
# ---------------------------------------------------------------
# Push tonight's TLDCRM dashboard work to GitHub.
# Just double-click this file — it opens Terminal and will:
#   1. clear a stale git lock left by the interrupted session
#   2. stage the Falcon refactor + the 5 probe scripts
#   3. commit them
#   4. push to your GitHub repo (origin/main)
# Your .env (API keys) is git-ignored and will NOT be pushed.
# ---------------------------------------------------------------
cd "$(dirname "$0")" || { echo "Could not enter project folder"; exit 1; }
echo "Project: $(pwd)"
echo

# 1) Remove any leftover lock so git can run
rm -f .git/index.lock

# 2) Stage the work (explicit list — won't include this script or .env)
git add egress_payloads.json static/dashboard.js tldcrm_client.py \
        probe_billables.py probe_endpoint.py probe_falcon.py \
        probe_vendors.py verify_numbers.py

echo "These changes will be committed:"
git status -s
echo

# 3) Commit (skips cleanly if there's nothing new)
git commit -m "Falcon billable-lead conversion + probe scripts" \
           -m "Status-based conversion (Active/Sale = converted); add falcon_billable_status query; refresh payload docs; KPI label/notes; add debug probe scripts." \
  || echo "(Nothing new to commit — moving on to push.)"

# 4) Push using your saved GitHub credentials
echo
echo "Pushing to GitHub (origin/main)..."
if git push origin main; then
  echo
  echo "Pushed. Your work is now on GitHub."
else
  echo
  echo "Push did not complete. If it asked for a username/token, run it"
  echo "again, or copy the error message and send it to me."
fi

echo
echo "Press any key to close this window."
read -n 1 -s
echo
