# Deployment Guide — putting the dashboard online for the team

**Status: not started.** This is the step-by-step for taking the dashboard from a local Mac
tool to a private website your managers can open. Read it through first; nothing in the
code has been changed for deployment yet.

> Supersedes `DEPLOYMENT-PLAN.md`. That plan centred on a Postgres database plus a
> background worker that pre-stored every day's numbers. We deliberately removed persistent
> storage from this app because stored data kept going stale and blank — so we're **not**
> rebuilding a larger version of it. Start simple; add a database only if TLD actually
> pushes back on call volume.

---

## What we're building

```
Manager's browser
      │  https://dashboard.yourcompany.com
      ▼
Cloudflare Access  ──►  Google sign-in, restricted to your company domain
      │
      ▼
Render web service  ──►  Flask under gunicorn (the app, unchanged)
      │
      ▼
TLDCRM egress API   ──►  read-only, live on every request
```

No database, no background worker, no stored data. Every number is pulled live, exactly
like it works on your Mac today.

**Cost:** roughly **$7–25/month**. Render's Starter web service is ~$7; Cloudflare Access is
free under 50 users; a domain is ~$12/year if you don't already have one.

---

## Before you start

You'll need:

- The **GitHub repo** (already have it).
- A **Render** account — https://render.com, sign in with GitHub.
- A **Cloudflare** account — free tier is fine.
- A **domain name** you can point at Cloudflare (e.g. `dashboard.yourcompany.com`). If your
  company domain is already on Cloudflare, you just add a subdomain.
- Your **TLD credentials** (the three values in your local `.env`).
- Confirmation from whoever owns TLD that a hosted dashboard hitting the egress API is fine.

---

## Step 1 — Code changes (I do these when you say go)

None of this is done yet. When you're ready, I will:

1. **Add gunicorn** to `requirements.txt`. Flask's built-in server prints
   *"This is a development server. Do not use it in a production deployment."* — it's
   single-threaded and not built for real traffic.
2. **Add `render.yaml`** to the repo so the whole setup is version-controlled rather than
   clicked together by hand, and can be rebuilt from scratch.
3. **Add a shared short cache** (~30 seconds) on the dashboard and sales-board responses.
   Right now every viewer triggers their own pull; with 5 managers that's ~2,500 API
   calls/hour. A 30-second shared cache cuts that to roughly one person's worth, and is far
   too short to ever show a meaningfully stale number.
4. **Confirm the app starts correctly under gunicorn** (the browser auto-open and
   `app.run()` only fire under `if __name__ == "__main__"`, so they're skipped — but I'll
   verify rather than assume).

Nothing about how the dashboard works or looks changes.

---

## Step 2 — Create the Render web service

1. Render dashboard → **New** → **Web Service** → connect your GitHub repo.
2. Settings:
   - **Environment:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:**
     ```
     gunicorn --chdir src --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 180 app:app
     ```
   - **Instance type:** **Starter ($7/mo)** — not Free. The free tier spins down when idle,
     so the first person each morning would wait ~50 seconds for a cold start.

**Why `--workers 1 --threads 8`:** each gunicorn *worker* is a separate process with its own
memory cache. Four workers means four separate caches and four times the API calls. One
worker with several threads shares a single cache and still handles everyone comfortably at
this size.

**Why `--timeout 180`:** the CPA report takes ~30 seconds on a month and longer on a year.
The default 30-second timeout would kill those requests.

---

## Step 3 — Environment variables

In Render → your service → **Environment**, add:

| Key | Value |
|---|---|
| `TLD_BASE_URL` | your TLD instance URL |
| `TLD_API_ID` | your egress API ID |
| `TLD_API_KEY` | your egress API key |
| `PYTHON_VERSION` | `3.11.9` |

**Never commit `.env`** — it stays git-ignored. Render holds these secrets; the app reads
them exactly as it reads `.env` locally, so no code change is needed.

Deploy, then open the Render URL (`something.onrender.com`) and check `/health` returns
`{"live": true}`. **At this point the site is public — don't share the link yet.**

---

## Step 4 — Domain

1. Add your domain to Cloudflare (or use the existing company zone).
2. In Render → **Settings → Custom Domain**, add `dashboard.yourcompany.com`.
3. Create the DNS record Render asks for in Cloudflare, **proxied** (orange cloud on) — the
   proxy is what makes Step 5 possible.
4. Wait for HTTPS to go green (usually minutes).

---

## Step 5 — Lock it down with Google SSO  ← do not skip

**The app has no login of its own.** Until this step is done, anyone with the URL can see
every agent's name, commissions, SEPs and chargebacks.

1. Cloudflare dashboard → **Zero Trust** → **Access** → **Applications** → *Add an
   application* → **Self-hosted**.
2. Application domain: `dashboard.yourcompany.com`.
3. **Identity provider:** Google (or Google Workspace). Cloudflare walks you through
   connecting it.
4. **Policy:** Allow → *Emails ending in* `@yourcompany.com`. Tighten to a named list of
   managers if you'd rather be explicit.
5. Save, then open the site in a private window — you should be forced through Google
   sign-in, and a personal Gmail should be refused.

Nobody reaches the app without signing in first, and we maintain zero login code.

---

## Step 6 — Test before sharing

Run through this list on the live site:

- [ ] `/health` reports `"live": true` (real data, not demo)
- [ ] Today's numbers match your Mac
- [ ] A **month** range loads fully — COST/CPA/Spend fill in, no zeros
- [ ] A **year** range loads without timing out ← the one most likely to fail
- [ ] Sales board, Agent Detail, and the **Excel export** all work
- [ ] A private window forces Google sign-in
- [ ] A non-company email is rejected
- [ ] Open it on a phone — is it usable enough for how managers will actually look at it?

Also run the sweep against the live URL before handing it out:

```bash
python3 sandbox/probes/probe_sweep.py
```

---

## Living with it

**Updating:** push to `main` and Render redeploys automatically. That's why we've been
committing everything.

**Watching API volume:** the local `logs/egress.csv` won't exist on Render (its disk is
ephemeral). If you want visibility into hosted call volume, tell me and I'll route the
metrics somewhere that survives restarts.

**If TLD complains about call volume:** raise the auto-refresh from 30s to 2 minutes (a
one-line change, cuts calls ~4×) before considering anything bigger.

**If pages feel slow:** the bottleneck is TLD's CPA report, not the hosting. The next lever
is loading cost data on demand rather than automatically for large ranges.

---

## Known risks

| Risk | Likelihood | What we'd do |
|---|---|---|
| Year-range request times out behind the proxy | Medium | Raise gunicorn timeout; load cost data on demand for big ranges |
| More viewers → more API calls | Medium | The 30s shared cache in Step 1; then slow the auto-refresh |
| Cold starts on the free tier | High if Free chosen | Use the $7 Starter tier |
| Someone shares the URL outside the company | Low | Cloudflare Access blocks them at sign-in |
| TLD credentials leak | Low | They live only in Render's environment; rotate the key if ever exposed |

---

## Rough timeline

About **2–3 hours** end to end for someone doing it the first time:

| Step | Time |
|---|---|
| Code prep (me) | 30 min |
| Render service + deploy | 30 min |
| Domain + DNS | 20 min (plus DNS propagation) |
| Cloudflare Access SSO | 30 min |
| Testing | 30 min |

The domain and SSO steps are the fiddly ones; the deploy itself is quick.
