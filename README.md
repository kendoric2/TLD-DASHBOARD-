# iHealth Plans — TLDCRM Dashboard

A read-only dashboard for TLDCRM / TLDialer. Pulls your sales, policy, and
agent-performance numbers into one view so you don't have to dig through menus.

## How it's built

| Layer | Tech | Job |
|-------|------|-----|
| **API layer** | Python (`app.py`, `tldcrm_client.py`) | Calls TLDCRM **egress** endpoints (read-only) using TQL, aggregates the numbers, serves clean JSON at `/api/dashboard`. **Your API key stays here on the server — never in the browser.** |
| **GUI layer** | JavaScript (`static/dashboard.js`) | Fetches that JSON and handles all on-screen actions: date-range switch, Refresh button, sorting, and drawing the charts. |
| **Look** | HTML + CSS (`templates/`, `static/`) | The page and theme. Brand colors live at the top of `dashboard.css`. |

**Read-only by design:** the client only ever issues `GET` requests to
`/api/egress/*`. Nothing is ever written back to the CRM or dialer.

## Egress payloads & date ranges

All egress request shapes live in **`egress_payloads.json`** — one entry per
metric (endpoint, columns, group_by, filters). Keeping them in JSON means you
can tweak a query without touching Python.

TLD requires date-bounded egress to use a **`start_date` + `end_date`** range
(`YYYY-MM-DD`) in the payload — not relative labels. The templates use
`{{start_date}}` / `{{end_date}}` placeholders, and `tldcrm_client.date_range_for()`
resolves the selected period (Today, This Week, This Month, Last Month, This
Quarter) into concrete dates before each request.

## Run it

```bash
cd TLDDASHBOARD
pip install -r requirements.txt
python3 app.py
```

It opens **http://localhost:5050** in your browser automatically. (macOS reserves
port 5000 for AirPlay Receiver, so the app uses 5050 — set `PORT=...` to change it.)

Out of the box it runs in **demo mode** with sample data (you'll see a
"SAMPLE DATA" badge), so you can use it before any keys are added.

## Go live

1. Open the `.env` file (already created, and git-ignored so it's never committed).
2. Fill in the three fields:
   ```
   TLD_BASE_URL=https://yourcompany.tldcrm.com
   TLD_API_ID=...
   TLD_API_KEY=...
   ```
   In TLD, create an API key **restricted to the egress (read) endpoints** — it
   then physically cannot write anything.
3. Restart `python3 app.py`. The badge disappears and real numbers load.
4. Visit `http://localhost:5050/health` to confirm `"live": true`.

## What's on the dashboard

- **KPIs:** Policies Sold · Billable Leads (purchased) · Conversion Rate · Avg Premium (GTL only)
- **Charts:** Policies by Carrier · Policies by Plan Type
- **Tables:** Recent Sales (premium shown only for GTL) · Agent Performance (ranked by policies sold)

## Notes / to confirm on first live connection

A few TLD field names are set as best-guesses from the API docs and are easy to
adjust in `tldcrm_client.py` (top of file):
- the billable-leads filter (`billable`),
- the GTL carrier label, and
- the agent / carrier / plan column names.

Confirm any of them against your instance with, e.g.:
`GET /api/egress/policies/docs/columns`
