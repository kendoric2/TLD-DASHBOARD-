# iHealth Plans — TLDCRM Dashboard

A small, **read-only** web dashboard for TLDCRM / TLDialer. It pulls your sales, policy,
cost, and agent-performance numbers into one page so you don't have to dig through CRM
menus. Nothing is ever written back to the CRM.

Out of the box it runs in **demo mode** with sample data; add your API credentials to go
live.

## What it does

- **Key Numbers** — six headline tiles: Policies Sold · Billable Calls · Conversion Rate ·
  Total Spend · Blended CPA · Avg Premium (GTL).
- **Policies by Carrier** — a vertical bar chart in the carriers' brand colors, with each
  carrier's total labeled on top.
- **Enrollments** — enrollments per enroller (fronter), plus a running total for the day.
- **Recent Sales** — the latest sales: date, agent, enroller, carrier.
- **Agent Performance** — a sortable, scrollable table of each agent's Policies Sold, COST,
  and CPA, with a pinned **Totals** row and the agent count by the title.
- **Date range + auto-refresh** — switch between Today (default), This Week, This Month,
  Last Month, and This Quarter; optional 30-second auto-refresh.

## Quick start

```bash
# 1. Install dependencies (first time only)
pip install -r requirements.txt

# 2. Run it (from the project root)
python3 src/app.py
```

This starts the server and opens **http://localhost:5050** in your browser. Keep the
terminal open while you use it; press Ctrl+C to stop.

Prefer not to use the terminal? Double-click **`bin/start.command`** (opens a Terminal
window) or **`bin/iHealth Dashboard.app`** (runs in the background). You'll see a
**"SAMPLE DATA"** badge until you add credentials.

## Going live

The app runs in demo mode until you create a **`.env`** file in the project root with your
TLDCRM API credentials. `.env` is git-ignored, so your keys are never committed. Copy
`.env.example` to `.env` and fill in:

```
TLD_BASE_URL=https://yourcompany.tldcrm.com   # your TLD instance URL
TLD_API_ID=...                                 # API ID
TLD_API_KEY=...                                # API key
```

Create the API key **restricted to the egress (read) endpoints** so it physically cannot
write anything. Then restart and visit **http://localhost:5050/health** — it should report
`"live": true`.

## Read-only by design

The app only ever issues **GET** requests to TLD's `/api/egress/*` (read) endpoints —
nothing is written back to the CRM or dialer. Your API key stays on the server and never
reaches the browser.

## How it works under the hood

The internals — every TLD-specific rule, the date handling, how each number is computed,
the caching strategy, a file-by-file map, and the gotchas we learned the hard way — live in
the **blueprint** (kept locally in `docs/`, not committed):

- **`docs/BLUEPRINT-ENGINEER.md`** — the full technical reference, with code.
- **`docs/TLD-Dashboard-Overview.docx`** — the same material in plain English, no code.
- **`egress_columns.xlsx`** — the full TLD column dictionary (every endpoint's fields).
