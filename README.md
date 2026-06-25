# iHealth Plans — TLDCRM Dashboard

A small, **read-only** web dashboard for TLDCRM / TLDialer. It pulls your sales,
policy, and agent-performance numbers into one page so you don't have to dig
through CRM menus. Nothing is ever written back to the CRM.

Out of the box it runs in **demo mode** with sample data; add your API
credentials to go live.

## Quick start

```bash
# 1. Install dependencies (first time only)
pip install -r requirements.txt

# 2. Run it (from the project root)
python3 src/app.py
```

This starts the server and opens **http://localhost:5050** in your browser.
Keep the terminal open while you use it; press Ctrl+C to stop.

Prefer not to use the terminal? Double-click **`bin/start.command`** (opens a
Terminal window) or **`bin/iHealth Dashboard.app`** (runs in the background, no
Terminal). You'll see a **"SAMPLE DATA"** badge until you add credentials
(see *Going live* below).

## Project structure

```
TLDDASHBOARD/
├── src/                     # all application source
│   ├── app.py               # Flask entry point — run THIS to start the dashboard
│   ├── config.py            # all settings + shared helpers (start here)
│   ├── tldcrm_client.py     # read-only TLDCRM API client + number crunching
│   ├── sample_data.py       # demo data used when no credentials are set
│   └── egress_payloads.json # the API query templates (one per metric)
├── templates/
│   └── dashboard.html       # the page
├── static/
│   ├── dashboard.css        # theme / brand colors
│   └── dashboard.js         # on-screen behavior (charts, 30s auto-refresh, sorting)
├── sandbox/
│   ├── probes/              # read-only diagnostic scripts for poking the live API
│   └── snippets/            # small finished utilities worth keeping
├── tests/                   # live sanity-check scripts
├── bin/                     # double-click launchers (Terminal + macOS app)
├── archive/                 # older/superseded scripts, kept for reference (unused)
├── requirements.txt         # Python dependencies
├── .env                     # YOUR credentials (you create this; never committed)
└── .env.example             # template for .env
```

### What each folder is for
- **`src/`** — all the application code: the `app.py` entry point plus the modules
  it imports (`config`, `tldcrm_client`, `sample_data`) and the query-templates
  JSON. Because `app.py` lives here next to those modules, it imports them
  directly.
- **`templates/` + `static/`** — the web front-end (HTML page + CSS/JS) that Flask
  serves. They sit at the project root; `app.py` points Flask at them explicitly.
- **`sandbox/probes/`** — **read-only** scripts for inspecting the live TLD API
  while building or debugging. See *Probe scripts* below.
- **`sandbox/snippets/`** — finished little utilities you might reuse.
- **`tests/`** — scripts that check the live data looks right.
- **`bin/`** — the double-click launchers.
- **`archive/`** — earlier exploratory versions, kept so the history isn't lost
  but no longer used by the app.

## Key files
- **`src/app.py`** — the web server. Three routes: `/` (the page), `/api/dashboard`
  (the JSON the page fetches), `/health` (reports live vs. demo). Run this file.
- **`src/config.py`** — **the one place for settings.** Loads your credentials
  from `.env` and holds the shared constants (timeouts, the Falcon vendor id, the
  "converted" statuses) and the request helpers every probe uses. Start here to
  change anything.
- **`src/tldcrm_client.py`** — talks to TLDCRM's read-only "egress" endpoints,
  runs the queries defined in `egress_payloads.json`, and aggregates the numbers
  the dashboard shows. Issues only GET requests — it cannot write to your CRM.
- **`src/sample_data.py`** — the placeholder numbers shown in demo mode (before
  credentials are set) so you can see the dashboard immediately.

## Probe scripts — what they are and when to use them
Read-only command-line helpers (in `sandbox/probes/`) for exploring and verifying
the live TLD API. They never change data. Run them from the project root:

```bash
python3 sandbox/probes/probe_falcon.py
```

- **`probe_endpoint.py <endpoint>`** — show any egress endpoint's columns + a few
  sample rows. *Use when:* exploring an endpoint you haven't touched before.
- **`probe_policy_columns.py`** — list every column on the `policies` endpoint.
  *Use when:* you need the exact field name for a query.
- **`probe_policy.py [policy_id]`** — dump every field of a single policy
  (sensitive PII masked). *Use when:* figuring out how a specific field is stored.
- **`probe_vendors.py`** — list all vendors (id → name). *Use when:* you need a
  vendor's id.
- **`probe_falcon.py`** — break Falcon billable leads down by status and show the
  conversion rate. *Use when:* verifying the conversion-rate math.
- **`probe_all_queries.py`** — run every dashboard query once and show the raw
  response. *Use when:* you want a quick end-to-end "is everything wired" check.

Two more, elsewhere:
- **`tests/verify_counts_by_range.py`** — confirms counts grow with the date
  range (today < week < month …), proving the date filter works.
- **`sandbox/snippets/active_users.py`** — prints every active user (status_id = 1).

(`archive/` holds the earlier versions — `probe_users.py`, `probe_billables.py`,
`diag_dates.py` — now superseded.)

## Going live (the `.env` file)
The app runs in demo mode until you create a **`.env`** file in the project root
with your TLDCRM API credentials. `.env` is git-ignored, so your keys are never
committed. Copy `.env.example` to `.env` and fill in:

```
TLD_BASE_URL=https://yourcompany.tldcrm.com   # your TLD instance URL
TLD_API_ID=...                                 # API ID
TLD_API_KEY=...                                # API key
```

Optional:

```
PORT=5050        # change the port (default 5050)
NO_BROWSER=1     # don't auto-open the browser on launch
```

Then restart (`python3 src/app.py`) and visit **http://localhost:5050/health** —
it should report `"live": true`. Create the API key **restricted to the egress
(read) endpoints** so it physically cannot write anything.

## Timeouts (where to change them)
All HTTP requests use a **30-second** timeout, defined in **`src/config.py`** as
`TIMEOUT = 30`. The one exception is `probe_policy.py`, which pulls a single large
joined record and uses **`POLICY_TIMEOUT = 60`** (also in `config.py`). Change
either value in `src/config.py` — it's the single source of truth.

## How the code is wired (good to know)
`app.py` lives in `src/` alongside `config.py`, `tldcrm_client.py`, and
`sample_data.py`, so it imports them directly. It tells Flask where the page lives
with explicit `template_folder` / `static_folder` paths (the project root, one
level up from `src/`).

The probe/test/archive scripts live outside `src/`, so each starts with a two-line
shim that adds `src/` to Python's import path:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
```

That's why you can run a probe from anywhere and it still finds `config` and
`tldcrm_client`. `config.py`'s `.env` loading also walks up to the project root,
so credentials are found no matter your current directory.

## Read-only by design
The client only ever issues **GET** requests to `/api/egress/*` — nothing is
written back to the CRM or dialer. Sensitive PCI/PHI fields are masked in probe
output, and `.env` (your keys) plus `policy_*.txt` (probe dumps) are git-ignored.
