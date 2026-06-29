# Deployment Plan — hosting the dashboard for the team (PARKED)

**Status: parked / not started.** This captures how we plan to take the dashboard from
a local Mac tool to a hosted website for the team. Nothing here is built yet — when
we're ready to move forward, start at *Phased build* below.

## Goal & priorities

- Put the dashboard on a website for the team (**realistically < 10 people**).
- **Stability and efficiency are the #1 goal.** Cohesive, comprehensive, reproducible.
- **Hands-off hosting** — pay a small monthly fee so someone else runs the servers; we
  only manage the code.

## Core principle (the whole reason this design works)

**Decouple TLD API pulls from user traffic.** Today every page load triggers API calls,
so more viewers = more calls = risk of a "too many requests" warning from TLD. The fix:
a background job is the *only* thing that talks to TLD; every user is served from a
shared local store. Then TLD load is constant and tiny no matter how many people are
looking, pages are instant, and if TLD hiccups we keep serving the last good data.

## Target architecture (three layers)

1. **Shared data store** — a day-grain database that holds each day's numbers once and
   composes any range from its days. Shared by all users.
2. **Background refresher** — the only thing that calls TLD. Pulls *today* every ~60s,
   warms the last few days, never re-pulls finalized days. Writes to the store.
3. **Web app** — Flask serving the page + JSON purely from the store, never calling TLD
   on a user request.

## Decided stack

- **Host: managed platform — Render** (Railway is an equally good alternative, same
  model). Connect the GitHub repo → auto-deploys on every push. HTTPS, restarts, scaling
  handled by them.
- **Database: managed Postgres** (Render add-on). Chosen over SQLite specifically because
  the web app and the background refresher are *separate services* that both need the
  store — Postgres lets them share it over the network with no file-sharing headaches.
- **Three Render services, all defined in one `render.yaml` in the repo** (so the entire
  setup is version-controlled and reproducible):
  - Web Service (Flask under **gunicorn**),
  - Background Worker (the refresher),
  - Postgres database.
- **Auth: Google / company SSO via Cloudflare Access** — sign-in at the edge restricted
  to our company domain, so we build/maintain zero login code. Needs a custom domain
  routed through Cloudflare (one-time). *Alternative:* in-app Google OAuth (e.g. Authlib)
  — no Cloudflare, but more code to own.

## Caching / data design (day-grain)

- Each **past day is pulled exactly once, ever**, then stored forever (its numbers can't
  change).
- **Any range = the sum of its days.** "This week" = past days from the store + today
  fresh. A fully-past week/month = 100% from the store, zero API calls. Ratios (CPA,
  blended CPA) are recomputed from summed cost ÷ summed sales.
- **Today is the only day that ever needs a live pull.**
- **Warm the last ~3 days on the first load of the day** to backfill recent days we don't
  have yet (e.g., Friday's finalized numbers on a Monday), pulling only what's missing.
- **Verify-first:** before trusting composition, run a read-only probe to confirm the
  report's daily numbers *sum to* the range value (cost / sales / billable calls are
  per-event and should be additive; range-relative fields like "new"/"first-contact"
  counts would not be — but we don't use those).

## Refresh strategy

- Auto-refresh only while viewing **Today**, at ~60s. Today is the only thing changing
  intra-day.
- **No polling on Week / Month / Last Month** — they barely move; load once, manual
  Refresh if wanted.
- (Today this is "every 30s for everything," which is the main source of call volume —
  the lighter dashboard queries re-run each tick; the heavy report is already throttled
  to ~5 min by its cache.)

## Security guardrail (important during the build)

Until SSO is switched on, the Render URL is publicly reachable. **Real agent/cost data
must never sit on an open URL.** So during the build phase the hosted site stays in
**demo mode (sample data, no real TLD keys on the server)**, or gets a temporary
password. The real TLD keys go in only once the SSO gate is live.

## Cost (approximate — confirm current pricing before committing)

- Render: small Web Service + Background Worker + smallest Postgres ≈ **~$20/month**.
- Cloudflare Access: free at our size.
- Domain: ~$10/year.

## Phased build (each phase leaves it working)

We can **stand up the hosting early (in demo mode) and add the domain + SSO last** — the
layers are independent. Suggested order:

0. **Lock the stack** (done — this document).
1. **Deploy pipeline (can do first, in demo mode):** add a WSGI entry point, gunicorn,
   `render.yaml`, env-based config (all additive — still runs the same locally). Create
   the Render project, connect the repo, deploy to the Render URL in demo mode. From then
   on every `git push` auto-deploys.
2. **Data layer:** day-grain store + range composition. *First step is the additivity
   probe.* Add Postgres.
3. **Refresher:** the background "pull today + warm recent days" job.
4. **Cut over to live data + go-live:** custom domain, Cloudflare Access SSO, real TLD
   keys behind the auth gate.
5. **Polish:** serve last-good data if TLD is down, logging, a health check.

## Who does what

- **Claude (in the code):** prep all deploy config (`render.yaml`, gunicorn, WSGI entry,
  env handling), build the data layer + refresher, and walk through each external click
  step by step.
- **You (accounts / billing / network):** create the Render account, connect billing,
  buy/point the domain, set up Cloudflare Access. (Claude can't log into your accounts.)

## Carries over vs. changes

- **Carries over:** the read-only TLD egress client, the query templates
  (`egress_payloads.json`), the progressive-load split, and the entire front-end.
- **Changes:** the `cache` module becomes a Postgres-backed day-grain store; add the
  background refresher; the web app reads/composes ranges from the store; add gunicorn +
  `render.yaml` + env-based config.

## When we resume — quick checklist

- [ ] Confirm current Render + Postgres pricing.
- [ ] Pick the domain name to use.
- [ ] Confirm Cloudflare Access (edge SSO) vs in-app Google OAuth.
- [ ] Run the additivity probe (daily sums == range) before building composition.
- [ ] Decide demo-mode vs temporary-password for the pre-SSO build window.
