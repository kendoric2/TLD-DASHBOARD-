# iHealth Plans — TLDCRM Dashboard

A small, **read-only** web dashboard for TLDCRM / TLDialer. It pulls your sales,
policy, cost, and agent-performance numbers into one page so you don't have to dig
through CRM menus. Nothing is ever written back to the CRM.

Out of the box it runs in **demo mode** with sample data; add your API
credentials to go live.

## What you see on the dashboard

- **Key Numbers** (six tiles): Policies Sold · Billable Calls · Conversion Rate ·
  Total Spend · Blended CPA · Avg Premium (GTL).
- **Charts**: Policies by Carrier (each slice in the carrier's brand color) and
  Policies by Plan Type.
- **Recent Sales**: Date · Agent · Enroller · Carrier.
- **Agent Performance**: Agent · Policies Sold · COST · CPA — sortable (click a
  column), scrollable, with a pinned **Totals** row and the agent count by the title.
- A **date-range selector** (defaults to **Today**) and a **30-second auto-refresh**
  toggle in the header.

## Quick start (Mac / general)

```bash
# 1. Install dependencies (first time only)
pip install -r requirements.txt

# 2. Run it (from the project root)
python3 src/app.py
```

This starts the server and opens **http://localhost:5050** in your browser. Keep
the terminal open while you use it; press Ctrl+C to stop.

Prefer not to use the terminal? Double-click **`bin/start.command`** (opens a
Terminal window) or **`bin/iHealth Dashboard.app`** (runs in the background). You'll
see a **"SAMPLE DATA"** badge until you add credentials (see *Going live* below).

## Working from your Windows PC at home

You have this on your work Mac. Here's how to run it on a home **Windows** PC and
keep both machines in sync through GitHub.

### One-time setup on the Windows PC

1. **Install Python 3** — download from <https://www.python.org/downloads/>, run the
   installer, and **check "Add Python to PATH"** on the first screen. Verify in a new
   Command Prompt or PowerShell window:
   ```bat
   python --version
   ```
2. **Install Git** — <https://git-scm.com/download/win>, default options are fine.
   Verify:
   ```bat
   git --version
   ```
3. **Clone the project** (this downloads the code from GitHub):
   ```bat
   git clone https://github.com/kendoric2/TLD-DASHBOARD-.git
   cd TLD-DASHBOARD-
   ```
4. **(Recommended) create a virtual environment** so dependencies stay tidy:
   ```bat
   python -m venv venv
   venv\Scripts\activate
   ```
5. **Install dependencies:**
   ```bat
   pip install -r requirements.txt
   ```
6. **Add your credentials.** `.env` is git-ignored, so it does **not** come down with
   the clone — you create it once on each machine. Copy the template and edit it:
   ```bat
   copy .env.example .env
   notepad .env
   ```
   Fill in `TLD_BASE_URL`, `TLD_API_ID`, `TLD_API_KEY` (see *Going live* below).

### Run it on Windows

```bat
python src\app.py
```

…then open **http://localhost:5050**. Or just **double-click `bin\start.bat`** — the
Windows launcher I added (it finds your venv automatically if you made one).

### Windows gotchas

- Use **`python`** (not `python3`) and **backslashes** in paths (`src\app.py`).
- If typing `python` opens the Microsoft Store, install from python.org and re-check
  "Add to PATH," or use **`py`** instead (`py src\app.py`).
- If PowerShell blocks `venv\Scripts\activate`, either use **Command Prompt**, or run
  this once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- The first `git push` will prompt you to sign in to GitHub (browser or a personal
  access token) — that's normal.

## Working across two machines (keep Mac + Windows in sync)

Everything syncs through GitHub. The golden rule: **pull before you start, push when
you finish.**

```bash
# Start of a session, on whichever machine you're on:
git pull

# After you've made changes:
git add -A
git commit -m "what you changed"
git push
```

Do that and your work Mac and home Windows PC always have the latest code. Your
**`.env` stays local on each machine** (it's never synced), so you only set
credentials up once per computer. On the Mac you can also use the
**`push_to_github.command`** helper to commit + push with a double-click.

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
│   ├── dashboard.js         # on-screen behavior (charts, auto-refresh, sorting, lazy CPA load)
│   ├── logo.png             # header logo
│   └── favicon.png
├── assets/brand/            # brand source assets (logo, color reference)
├── sandbox/
│   ├── probes/              # read-only diagnostic scripts (each self-documented)
│   └── snippets/            # small finished utilities worth keeping
├── tests/                   # live sanity-check scripts
├── bin/
│   ├── start.command        # macOS: double-click to run
│   ├── start.bat            # Windows: double-click to run
│   └── iHealth Dashboard.app
├── archive/                 # older/superseded scripts, kept for reference (unused)
├── egress_columns.xlsx      # reference: every enabled endpoint's columns + a sample value
├── push_to_github.command   # macOS helper: commit + push with a double-click
├── requirements.txt         # Python dependencies
├── .env.example             # template for .env
└── .env                     # YOUR credentials (you create this per machine; never committed)
```

## Key files

- **`src/app.py`** — the web server. Routes:
  - `/` — the page.
  - `/api/dashboard` — the **fast** JSON the page loads first (policies, charts,
    recent sales, agent names + policy counts).
  - `/api/agent_cpa` — the **heavy** CPA report (COST, CPA, Billable Calls, Total
    Spend, Blended CPA), loaded separately so it never blocks first paint. Cached
    5 minutes and pre-warmed at startup.
  - `/health` — reports live vs. demo.
- **`src/config.py`** — **the one place for settings.** Loads your credentials from
  `.env` and holds the shared constants (timeouts, the Falcon vendor id, the
  "converted" statuses) and the request helpers every probe uses. Start here.
- **`src/tldcrm_client.py`** — talks to TLDCRM's read-only "egress" endpoints, runs
  the queries in `egress_payloads.json`, and aggregates the numbers. Issues only GET
  requests — it cannot write to your CRM.
- **`src/sample_data.py`** — the placeholder numbers shown in demo mode.

## How dates work (the canonical rule)

Date-filtered queries send TLD's **canonical** range in the JSON body — **both**
`date`/`date_end` **and** `date_sold`/`date_sold_end`, formatted
`YYYY-MM-DD HH:MM:SS` with full-day bounds (`00:00:00` … `23:59:59`). Sending both
pairs is what makes ranges reliable. This holds for the **policies** endpoint and
the **CPA report**.

**One proven exception:** the raw **`leads`** endpoint ignores `date`/`date_sold`
and must be filtered on **`date_created`**. Those queries set `"date_field":
"date_created"` in `egress_payloads.json` to override. (`sandbox/probes/
probe_migrate_check.py` is the test that proved this — it compares each query's old
vs. new date form side by side.)

## Performance (why the first load is quick)

The page paints **immediately** from `/api/dashboard`. The slow part —
`report_cpa_agent`, which powers COST, CPA, Billable Calls, Total Spend and Blended
CPA — loads right after via `/api/agent_cpa`, so those fields show a brief "…" then
fill in. That report is **cached for 5 minutes** per date range and **pre-warmed at
startup**, and concurrent requests for the same range share a single fetch, so after
the first view it's effectively instant (the 30-second auto-refresh reuses the cache).

## Probe scripts — what they are and when to use them

Read-only command-line helpers in `sandbox/probes/`. They never change data. **Each
script has a docstring at the top explaining exactly what it does and how to run it.**
Run them from the project root, e.g.:

```bash
python3 sandbox/probes/probe_cpa.py
```

A few of the most useful:

- **`probe_cpa.py`** — every agent's CPA + cost for a date range (the report behind
  the COST/CPA columns).
- **`probe_billable_calls.py`** — today's billable-call totals from `report_cpa_agent`
  (the source of the Billable Calls tile).
- **`probe_migrate_check.py`** — compares each dashboard query's date handling old vs.
  new, so a change can't silently shift a number.
- **`probe_endpoints.py`** — lists every egress endpoint the API exposes and flags the
  call/dialer-grain ones.
- **`probe_recent.py`** — runs the Recent Sales query (incl. the enroller field) and
  shows the rows.
- **`probe_query.py` / `probe_test.py` / `probe_all_columns.py`** — general-purpose
  filtered lookups, single-column tests, and full column dumps.

`_probe_lib.py` is the shared helper (readable output, response normalizing) that the
probes import. `egress_columns.xlsx` is a handy offline reference of every enabled
endpoint's columns and a sample value — check it before adding a new endpoint.

## Going live (the `.env` file)

The app runs in demo mode until you create a **`.env`** file in the project root with
your TLDCRM API credentials. `.env` is git-ignored, so your keys are never committed.
Copy `.env.example` to `.env` and fill in:

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

Then restart (`python3 src/app.py`, or `python src\app.py` on Windows) and visit
**http://localhost:5050/health** — it should report `"live": true`. Create the API
key **restricted to the egress (read) endpoints** so it physically cannot write
anything. Enable only the endpoints you need — this dashboard uses `policies`,
`leads`, and `report_cpa_agent`.

## Read-only by design

The client only ever issues **GET** requests to `/api/egress/*` — nothing is written
back to the CRM or dialer. Sensitive PCI/PHI fields are masked in probe output, and
`.env` (your keys) plus probe dump files are git-ignored.
```