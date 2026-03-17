# RateShift — Launch-Day Monitoring Runbook

> Created: 2026-03-17
> Purpose: Operational reference for the person watching infrastructure on launch day
> Companion to: `docs/CAPACITY_AUDIT.md`, `docs/LAUNCH_CHECKLIST.md`, `docs/MONITORING.md`
> Scenario basis: 500 signups (moderate), 2,000 page views, 200 AI queries

This runbook is a hands-on operational guide, not a project checklist. It tells you what to
watch, what numbers mean trouble, and exactly what to do when something goes wrong. Keep this
open in a browser tab next to your monitoring dashboards on launch day.

---

## Table of Contents

1. [Pre-Launch Checklist](#1-pre-launch-checklist)
2. [Dashboard URLs](#2-dashboard-urls)
3. [Key Metrics and Thresholds](#3-key-metrics-and-thresholds)
4. [Alert Escalation Matrix](#4-alert-escalation-matrix)
5. [Incident Response Playbooks](#5-incident-response-playbooks)
6. [Hourly Check Schedule (First 12 Hours)](#6-hourly-check-schedule-first-12-hours)
7. [Post-Launch Review](#7-post-launch-review)

---

## 1. Pre-Launch Checklist

Work through these gates in order. Do not skip. If a gate fails, stop and fix it before
continuing to the next one.

### T-24 Hours (Day Before)

**Infrastructure upgrades — must be done before Product Hunt goes live.**

- [ ] Upgrade Render to Starter tier ($7/mo)
  - Dashboard: https://dashboard.render.com > Service `srv-d649uhur433s73d557cg` > Settings > Instance Type
  - Why: Free tier auto-sleeps after 15 minutes idle; cold starts take 20-30s and ruin first impressions
  - Verify: Service restarts, then `curl -s https://api.rateshift.app/health | python3 -m json.tool` returns `"status": "healthy"`

- [ ] Upgrade Resend to Starter ($20/mo)
  - Dashboard: https://resend.com/settings/billing
  - Why: Free tier cap is 100 emails/day; 500 welcome emails alone would hit it 5x over
  - Verify: Billing page shows "Starter" plan with 50,000 emails/month

- [ ] Check GitHub Actions minutes remaining for the current billing month
  - URL: https://github.com/JoeyJoziah/electricity-optimizer/settings/billing
  - Action: If more than 1,500 minutes used, purchase a 500-minute block ($4 one-time) as a hotfix buffer
  - Why: GHA minutes exhausted = cannot deploy hotfixes during launch

- [ ] Verify all UptimeRobot monitors are in UP status
  - URL: https://dashboard.uptimerobot.com
  - Expected: Three monitors green — RateShift Frontend, RateShift API Health, RateShift API Prices

- [ ] Bookmark all dashboards from Section 2 (takes ~10 minutes, saves time under pressure)

- [ ] Run end-to-end smoke test
  ```bash
  # Backend health
  curl -s https://api.rateshift.app/health | python3 -m json.tool

  # Frontend reachable
  curl -s -o /dev/null -w "%{http_code}" https://rateshift.app

  # CF Worker gateway health
  curl -s https://api.rateshift.app/api/v1/health | python3 -m json.tool
  ```
  All three must return success responses. If the backend health check returns unhealthy,
  check Render logs before proceeding.

- [ ] Confirm Gmail SMTP fallback credentials are valid
  - In Render env vars (https://dashboard.render.com > Service > Environment), confirm
    `SMTP_HOST`, `SMTP_PORT`, and `SMTP_PASSWORD` are populated
  - Send a test email via the backend's `/internal/test-email` endpoint (if available) or
    manually via Python: `python3 -c "import smtplib; s=smtplib.SMTP_SSL('smtp.gmail.com',465); s.login('user','pass'); print('OK')"`

- [ ] Verify AI agent responds end-to-end
  - Sign in to https://rateshift.app as a test user
  - Navigate to /assistant
  - Send a short query ("What is the current electricity rate in CT?")
  - Confirm a response is returned in under 10 seconds
  - Check Render logs to confirm which provider (Gemini vs Groq) handled the request

- [ ] Optional but recommended: upgrade Neon to Launch plan ($19/mo)
  - Console: https://console.neon.tech > Project `cold-rice-23455092` > Settings > Billing
  - Why: Provides 300 compute-hours (vs 100) and improved connection limits for concurrent load

### T-1 Hour (Launch Morning)

- [ ] Open all monitoring dashboards (see Section 2) and leave them open in separate tabs
- [ ] Confirm Slack `#incidents` channel is visible and notifications are on
- [ ] Confirm Slack `#deployments` channel is visible
- [ ] Run health check one final time: `curl -s https://api.rateshift.app/health | python3 -m json.tool`
- [ ] Verify Render service shows "Live" status (not sleeping or deploying)
  - Dashboard: https://dashboard.render.com > Service `srv-d649uhur433s73d557cg`
- [ ] Pre-warm the backend with 10 requests to prevent any residual cold-start behavior
  ```bash
  for i in $(seq 1 10); do
    curl -s -o /dev/null https://api.rateshift.app/health
    sleep 2
  done
  echo "Pre-warm complete"
  ```
- [ ] Note the current values for each metric in Section 3 as a pre-launch baseline
  - Neon compute-hours used this billing period
  - GHA minutes used this billing month
  - Composio actions used this month
  - Gemini RPD used today (check Google AI Studio)

### T-0 (Launch Moment)

- [ ] Publish the Product Hunt page
- [ ] Confirm first wave of signups is appearing in the database within 5 minutes
  - Check Neon Console > Tables > `users` for new rows, or watch the KPI metric in Grafana
- [ ] Confirm welcome emails are being sent
  - Check Resend Dashboard > Emails for delivery activity
- [ ] Start the hourly check schedule in Section 6

---

## 2. Dashboard URLs

Bookmark every URL in this section before T-24h. Under stress, you do not want to be
searching for login pages.

### Render (Backend)
| Page | URL |
|------|-----|
| Service overview | https://dashboard.render.com/web/srv-d649uhur433s73d557cg |
| Metrics (CPU, RAM, latency) | https://dashboard.render.com/web/srv-d649uhur433s73d557cg/metrics |
| Logs (live tail) | https://dashboard.render.com/web/srv-d649uhur433s73d557cg/logs |
| Environment variables | https://dashboard.render.com/web/srv-d649uhur433s73d557cg/env |

### Vercel (Frontend)
| Page | URL |
|------|-----|
| Project overview | https://vercel.com/dashboard |
| Usage (bandwidth, invocations, build minutes) | https://vercel.com/dashboard > Project > Usage |
| Deployment logs | https://vercel.com/dashboard > Project > Deployments |

### Neon PostgreSQL
| Page | URL |
|------|-----|
| Project console | https://console.neon.tech/app/projects/cold-rice-23455092 |
| Usage (compute-hours, storage, connections) | https://console.neon.tech/app/projects/cold-rice-23455092/usage |
| Query monitoring | https://console.neon.tech/app/projects/cold-rice-23455092/monitoring |
| Branches | https://console.neon.tech/app/projects/cold-rice-23455092/branches |

### Cloudflare Workers
| Page | URL |
|------|-----|
| Account overview | https://dash.cloudflare.com/b41be0d03c76c0b2cc91efccdb7a10df |
| Worker analytics | https://dash.cloudflare.com/b41be0d03c76c0b2cc91efccdb7a10df/workers/services/view/rateshift-api-gateway/production/metrics |
| KV storage usage | https://dash.cloudflare.com/b41be0d03c76c0b2cc91efccdb7a10df/workers/kv/namespaces |
| Zone analytics (zone `ac03dd28616da6d1c4b894c298c1da58`) | https://dash.cloudflare.com/b41be0d03c76c0b2cc91efccdb7a10df/rateshift.app/analytics |

### Resend (Primary Email)
| Page | URL |
|------|-----|
| Email log and delivery stats | https://resend.com/emails |
| Usage and quotas | https://resend.com/overview |
| Domain health (DKIM/SPF/DMARC) | https://resend.com/domains |

### Gemini API (AI Agent Primary)
| Page | URL |
|------|-----|
| Usage dashboard | https://aistudio.google.com/app/apikey (select key, view Usage tab) |
| Google Cloud Console quotas | https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/quotas |

### Groq (AI Agent Fallback)
| Page | URL |
|------|-----|
| Usage dashboard | https://console.groq.com/settings/usage |
| API keys | https://console.groq.com/keys |

### Composio
| Page | URL |
|------|-----|
| Usage dashboard | https://app.composio.dev/settings/billing |
| Active connections | https://app.composio.dev/connections |

### GitHub Actions
| Page | URL |
|------|-----|
| Billing and minute usage | https://github.com/settings/billing/summary |
| Workflow runs | https://github.com/JoeyJoziah/electricity-optimizer/actions |
| Self-healing monitor | https://github.com/JoeyJoziah/electricity-optimizer/actions/workflows/self-healing-monitor.yml |

### UptimeRobot
| Page | URL |
|------|-----|
| Monitor dashboard | https://dashboard.uptimerobot.com |
| Alert contacts | https://dashboard.uptimerobot.com/alertContacts |

### Grafana Cloud (OTel Tracing)
| Page | URL |
|------|-----|
| Grafana instance (ID 1342627) | https://rateshift.grafana.net |
| Explore > Tempo (traces) | https://rateshift.grafana.net/explore (select Tempo datasource) |
| Region: prod-us-east-2 | Credentials in 1Password "RateShift" vault under "Grafana Cloud OTLP" |

### Slack Channels
| Channel | Purpose | Link |
|---------|---------|------|
| `#incidents` (C0AKV2TK257) | UptimeRobot alerts, Sentry errors, GHA failures | https://electricityoptimizer.slack.com/archives/C0AKV2TK257 |
| `#deployments` (C0AKCN6T02Z) | Deploy status, rollback notifications | https://electricityoptimizer.slack.com/archives/C0AKCN6T02Z |
| `#metrics` (C0AKDD7P2HX) | Nightly KPI digest | https://electricityoptimizer.slack.com/archives/C0AKDD7P2HX |

### Quick Health Check (CLI)
Run this any time you need a rapid status snapshot:
```bash
# Full system health check — takes about 10 seconds
echo "=== Backend ===" && curl -s https://api.rateshift.app/health | python3 -m json.tool
echo "=== Frontend ===" && curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" https://rateshift.app
echo "=== CF Gateway ===" && curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" https://api.rateshift.app/api/v1/health
```

---

## 3. Key Metrics and Thresholds

Each service has a normal operating range, a warning threshold that requires active watching,
and a critical threshold that requires immediate action. Check these values on each hourly pass.

### Render — Backend (srv-d649uhur433s73d557cg)

| Metric | Normal | Warning | Critical | Where to check |
|--------|--------|---------|----------|----------------|
| CPU utilization | < 40% | 40-80% | > 80% sustained | Render metrics tab |
| Memory usage | < 350 MB | 350-450 MB | > 450 MB (OOM risk) | Render metrics tab |
| Request latency p95 | < 500ms | 500ms-2s | > 2s | Render metrics tab |
| Error rate (5xx) | < 0.5% | 0.5-2% | > 2% | Render logs + Sentry |
| Service status | Live | Deploying (transient) | Crashed / Sleeping | Render service overview |

Notes:
- Starter tier gives 512 MB RAM and 0.5 shared CPU. The warning thresholds reflect real
  risk levels for these specs.
- A single memory spike above 450 MB will trigger OOM if unaddressed. This is the highest
  risk metric on Render Starter.
- Under viral load (2,000+ signups), upgrade to Render Standard ($25/mo) immediately.

### Neon PostgreSQL (cold-rice-23455092)

| Metric | Normal | Warning | Critical | Where to check |
|--------|--------|---------|----------|----------------|
| Active connections | < 5 | 5-7 | >= 8 (pool exhausted) | Neon Console > Monitoring |
| Compute-hours used (launch day) | 0-6h | 6-12h | > 12h in first 6h | Neon Console > Usage |
| Compute-hours used (month total) | < 60h | 60-85h | > 85h (cap approaching) | Neon Console > Usage |
| Query latency (avg) | < 50ms | 50-200ms | > 200ms | Neon Console > Monitoring |

Notes:
- The connection pool is configured at `pool_size=3, max_overflow=5` (8 max total). At 8
  active connections, new requests queue and then fail. This is the single most dangerous
  bottleneck under concurrent load.
- If compute-hours exceed 12 hours in the first 6 hours of launch, the month budget will
  be exhausted by day 10. Upgrade to Neon Launch ($19/mo) immediately.
- Neon suspends the endpoint when the monthly compute budget is fully exhausted. All API
  calls will return 500 errors until upgraded or until the billing cycle resets.

### Cloudflare Workers (rateshift-api-gateway)

| Metric | Normal | Warning | Critical | Where to check |
|--------|--------|---------|----------|----------------|
| Requests today | < 30K | 30K-70K | > 70K (70% of daily limit) | CF Workers Analytics |
| CPU time per request | < 5ms | 5-9ms | >= 10ms (at limit) | CF Workers Analytics |
| Error rate | < 0.5% | 0.5-2% | > 2% | CF Workers Analytics |
| KV reads today | < 10K | 10K-25K | > 25K | CF KV namespace metrics |

Notes:
- The free tier allows 100K requests/day. The 70K warning threshold gives enough time to
  evaluate whether upgrading to Workers Paid ($5/mo) is warranted before hitting the cap.
- CF Workers return error 1015 when the request limit is exceeded. The frontend circuit
  breaker handles this for public endpoints by falling back to the direct Render URL.

### Resend (Primary Email)

| Metric | Normal | Warning | Critical | Where to check |
|--------|--------|---------|----------|----------------|
| Emails sent today (Starter: 50K/day) | < 10K | 10K-40K | > 40K | Resend overview page |
| Emails sent today (if still on Free: 100/day) | < 50 | 50-80 | > 80 — upgrade NOW | Resend overview page |
| Bounce rate | < 2% | 2-5% | > 5% | Resend analytics |
| Delivery failures | 0 | 1-3 | > 3 in any 15-min window | Resend email log |

Notes:
- If Resend was NOT upgraded before launch and you are still on the free tier, a count
  above 80 requires immediate action (upgrade or fallback to Gmail SMTP).
- A bounce rate above 5% may trigger Resend to rate-limit the domain. Investigate the
  email list for invalid addresses.

### Gemini 3 Flash (AI Agent Primary)

| Metric | Normal | Warning | Critical | Where to check |
|--------|--------|---------|----------|----------------|
| RPD used today | < 150 | 150-225 | > 225 (90% of 250 limit) | Google AI Studio usage |
| RPM at peak minute | < 8 | 8-10 | >= 10 (Groq fallback triggers) | Render logs |
| Gemini error rate | < 5% | 5-15% | > 15% | Render logs (search `gemini_rate_limited`) |

Notes:
- RPM overflow is expected and handled. Groq fallback is automatic. The warning threshold
  for RPD exists to give you advance notice before the daily cap is hit.
- If RPD exceeds 225, enable Gemini pay-as-you-go billing in Google Cloud Console to lift
  the cap. This takes ~10 minutes and removes the 250 RPD ceiling.

### Groq Llama 3.3 70B (AI Agent Fallback)

| Metric | Normal | Warning | Critical | Where to check |
|--------|--------|---------|----------|----------------|
| Requests today | < 100 | 100-500 | > 1,000 (indicates Gemini may be down) | Groq Console |
| RPM at peak | < 10 | 10-25 | > 25 (approaching 30 RPM limit) | Groq Console |

Notes:
- Under normal launch load, Groq should see 20-60 requests/day (Gemini overflow only).
- If Groq usage climbs above 500 requests, Gemini may be returning errors beyond just RPM
  limits. Check Gemini error rate and consider enabling pay-as-you-go.

### Composio

| Metric | Normal | Warning | Critical | Where to check |
|--------|--------|---------|----------|----------------|
| Actions used this month | < 400 | 400-700 | > 700 (70% of 1K monthly limit) | Composio billing page |
| Actions used today | < 50 | 50-200 | > 300 (30% of monthly budget in one day) | Composio billing page |

Notes:
- Composio actions reset monthly, not daily. At 300 actions on launch day alone, the
  remaining monthly budget drops to 700. If that rate continues for 3 more days, the
  monthly cap is exhausted.
- Composio degradation is graceful: the AI agent responds without tool capabilities but
  does not throw errors to users.
- Upgrade to Composio Starter ($29/mo, 5K actions) if the monthly budget drops below 30%.

### GitHub Actions

| Metric | Normal | Warning | Critical | Where to check |
|--------|--------|---------|----------|----------------|
| Minutes used this month | < 1,500 | 1,500-1,800 | > 1,800 (90% of free tier) | GitHub billing page |
| Active/queued workflows | 0 queued | 1-2 queued | Workflows queued and not starting | GitHub Actions tab |

Notes:
- GHA minutes exhausted means no hotfix deploys. `check-alerts` is on CF Worker Cron
  Trigger (unaffected). Weather, sync, and data pipeline crons will stop.
- If minutes are critical, emergency deploy options: Render auto-deploys from git push
  (uses Render's build pipeline, not GHA). CF Worker deploys via `wrangler deploy` locally.

### Vercel (Frontend)

| Metric | Normal | Warning | Critical | Where to check |
|--------|--------|---------|----------|----------------|
| Bandwidth this month | < 5 GB | 5-80 GB | > 80 GB (80% of 100 GB cap) | Vercel Usage page |
| Serverless invocations today | < 20K | 20K-80K | > 80K (80% of 100K/month) | Vercel Usage page |
| Build minutes this month | < 1K | 1K-5K | > 5K (83% of 6K/month) | Vercel Usage page |

Notes:
- Vercel is the lowest-risk service. CDN caching absorbs most traffic. The ISR pages
  (153 cached routes) minimize serverless hits. Auth routes (`/api/auth/*`) are the main
  serverless consumers.

---

## 4. Alert Escalation Matrix

This matrix maps threshold crossings to specific responses. Severity labels:
- P1 (Critical): Production impact. Requires immediate action.
- P2 (High): Degraded user experience or imminent capacity risk. Requires action within 15 minutes.
- P3 (Medium): Monitoring required. Action within 1 hour.
- P4 (Low): Awareness only. Log and review in post-launch retrospective.

| Condition | Severity | Immediate Response | Escalation if unresolved in |
|-----------|----------|-------------------|----------------------------|
| Backend returns > 2% 5xx errors | P1 | Check Render logs. Restart service if hung. If memory OOM, upgrade to Standard ($25/mo). | 5 minutes |
| UptimeRobot reports backend DOWN | P1 | Check Render dashboard. If sleeping, send warmup request. If crashed, review logs and restart. | 5 minutes |
| Neon connections >= 8 (pool exhausted) | P1 | Upgrade to Neon Launch immediately. Identify slow queries in Neon monitoring. | 10 minutes |
| Render memory > 450 MB | P1 | Upgrade to Render Standard ($25/mo). Memory will not recover without a restart or upgrade. | 10 minutes |
| Render CPU > 80% sustained (> 5 min) | P2 | Upgrade to Render Standard ($25/mo) for dedicated CPU. Check for runaway query in Neon. | 15 minutes |
| Resend emails sent > 80% of daily cap | P2 | If on Free tier: upgrade to Starter immediately. If on Starter: monitor; not actionable until near 50K. | 15 minutes |
| GHA minutes remaining < 200 | P2 | Purchase 500-minute block ($4) at github.com settings billing. | 15 minutes |
| Gemini RPD > 225 (90% of 250) | P2 | Enable Gemini pay-as-you-go in Google Cloud Console. Groq is handling overflow but Groq has its own RPM limit. | 15 minutes |
| CF Worker requests today > 70K | P3 | Evaluate bot traffic in CF zone analytics. Upgrade to Workers Paid ($5/mo) if needed. | 1 hour |
| Neon compute-hours > 12h in first 6h | P3 | Upgrade to Neon Launch ($19/mo). Current month budget will be exhausted otherwise. | 1 hour |
| Composio actions today > 300 | P3 | Upgrade to Composio Starter ($29/mo) if launch sustains. Monthly budget will be exhausted in 3 days. | 1 hour |
| Groq requests today > 500 | P3 | Investigate whether Gemini is returning errors beyond RPM throttling. May indicate provider outage. | 1 hour |
| Backend p95 latency 500ms-2s | P3 | Check Neon query times. Check Render CPU. May be transient under burst traffic. | 1 hour |
| Vercel serverless invocations > 80K | P4 | Review auth route traffic. Consider upgrading to Vercel Pro ($20/mo) before end of month. | 24 hours |
| GHA workflow queued but not starting | P2 | Check GHA minutes remaining. If exhausted, purchase minutes. If not exhausted, check GitHub status page. | 15 minutes |
| Sentry error spike > 50 events in 15 min | P2 | Check `#incidents` Slack for Sentry bridge alert. Review Sentry for error type. If new error pattern, open incident. | 15 minutes |

### How to Read an Alert in Slack `#incidents`

Automated alerts from the Sentry-Slack bridge (Rube recipe `rcp_sQ1NKouFdXIe`) post every 15
minutes when unresolved Sentry issues exist. The format is:

```
[CRITICAL] RateShift Incident Alert
Service: backend
Workflow: check-alerts
Error: Unhandled exception in email_service.py: SMTPAuthenticationError
Count: 12 occurrences in last 15 min
Link: https://sentry.io/...
```

Match the `Service` and error type to the escalation matrix above to determine severity.

---

## 5. Incident Response Playbooks

These three scenarios are the most likely launch-day incidents based on the capacity model.
Each playbook uses a standard structure: Detect, Assess, Respond, Verify, Communicate.

---

### Playbook 1 — Email Quota Exhausted (Resend 100/day Free Tier)

**Context**: If Resend was not upgraded before launch, the free tier allows only 100 emails/day.
Even a conservative 100-signup scenario generates 120 emails. This scenario assumes the upgrade
did not happen, or that Resend Starter was depleted through an unexpected spike.

**Detection signals**:
- Sentry errors containing `resend.emails.send` or HTTP 429 from api.resend.com
- Users reporting they did not receive a welcome or verification email
- Resend Dashboard > Emails showing delivery failures or a daily counter at its cap

**Step 1 — Assess scope**

Open Resend Dashboard (https://resend.com/emails) and check:
- Current daily count vs plan limit
- Whether failures are 429 (quota) or another error code (domain/DKIM issue)
- Whether Gmail SMTP fallback is already active (check Render logs for `email_sent_via_smtp`)

**Step 2 — Immediate response (quota exhausted on Free tier)**

Upgrade to Resend Starter immediately. This takes 2 minutes:
1. Navigate to https://resend.com/settings/billing
2. Select Starter ($20/month)
3. Enter payment information
4. New quota (50,000 emails/day) takes effect within 1-2 minutes

**Step 3 — Immediate response (both Resend and Gmail SMTP failing)**

If Resend is upgraded but still failing, or if Gmail SMTP is also returning errors:
1. Check Gmail SMTP credentials in Render env vars (`SMTP_HOST`, `SMTP_PASSWORD`)
2. Confirm Gmail app password is still valid (Google may revoke app passwords on suspicious activity)
3. Temporary workaround: set the backend env var `DISABLE_WELCOME_EMAIL=true` via Render dashboard
   to stop generating new email attempts while you resolve the credential issue. New signups
   still land in the database; send the welcome email batch manually once email is restored.

**Step 4 — Verify resolution**

Trigger a test signup via https://rateshift.app. Within 30 seconds, confirm:
- Render logs show `email_sent_via_resend` or `email_sent_via_smtp`
- Resend Dashboard shows a new email record
- Test email arrives in inbox

**Step 5 — Communicate**

If resolution took > 15 minutes and signups accumulated during the outage, queue a follow-up
welcome email to affected users once email is restored. A partial outage of transactional email
does not require a public status page incident, but document it in the T+24h retrospective.

**Prevention note**: Resend Starter ($20/mo) must be active before the Product Hunt page goes
live. This playbook is a last resort. See Section 1, T-24h checklist.

---

### Playbook 2 — Backend Cold Start Storm

**Context**: Render Starter eliminates auto-sleep but does not eliminate all cold start
scenarios. A cold start storm occurs when multiple users send concurrent requests to a Render
instance that recently restarted (post-deploy, post-OOM-restart, or after a brief outage),
causing all requests to queue while a single process initializes. Even on Starter tier, a
restart causes ~5-10s of unavailability.

On Render Free tier (if not upgraded), the instance sleeps after 15 minutes of idle time and
requires 20-30 seconds to wake. A burst of PH traffic hitting a sleeping backend means the
first 10-20 users all experience a timeout.

**Detection signals**:
- UptimeRobot alert: backend DOWN or response time > 10 seconds
- Users reporting blank screen or "network error" on first load
- Render logs showing process startup messages followed by queued requests
- Grafana traces showing high p95 latency (> 5s) on all endpoints simultaneously

**Step 1 — Assess the scenario**

Open Render logs (https://dashboard.render.com/web/srv-d649uhur433s73d557cg/logs) and look for:
- `Starting uvicorn` or `Application startup complete` — confirms a recent restart
- OOM signals: `Killed`, `MemoryError`, or memory usage at 512 MB just before the crash
- Timeout flood: multiple requests all failing at the same time (correlated timestamps)

**Step 2 — If on Render Free tier (not upgraded): immediate upgrade**

1. Navigate to Render dashboard > Service settings > Instance Type
2. Change from Free to Starter ($7/mo)
3. Service will restart once. This takes 30 seconds.
4. Warmup immediately after restart:
   ```bash
   for i in $(seq 1 5); do curl -s https://api.rateshift.app/health; sleep 1; done
   ```

**Step 3 — If already on Starter and OOM-crashed**

1. The Starter tier (512 MB RAM) can OOM under sustained concurrent load.
2. Immediately upgrade to Render Standard ($25/mo, 2 GB RAM, dedicated CPU):
   - Render dashboard > Service settings > Instance Type > Standard
3. The service restarts. Run the warmup sequence above.
4. If the restart is causing a cascading reconnect storm from clients, the health endpoint
   will return 200 within 10-15 seconds. UptimeRobot will clear the alert automatically.

**Step 4 — If the issue is request queuing, not memory**

A single-process Render instance handles requests sequentially by default. Under burst traffic:
1. Check Render metrics for request queue depth — if requests are completing but slowly,
   this is CPU saturation, not a crash.
2. Upgrade to Render Standard if CPU is above 80% sustained.
3. In the interim, the CF Worker's 2-tier cache (Cache API + KV) absorbs repeated identical
   requests (e.g., price lookups for the same region), reducing origin hits.

**Step 5 — Verify resolution**

```bash
# Check that health is clean and latency is acceptable
curl -s -w "\nTime: %{time_total}s\n" https://api.rateshift.app/health
```
Target: response in under 1 second. If above 3 seconds after restart, the instance is still
warming up under load.

**Step 6 — Communicate**

If the outage lasted more than 5 minutes during peak traffic:
- Post a brief status update in Slack `#incidents`
- If users are asking about the outage on Product Hunt comments, acknowledge it directly and
  share that it has been resolved: "We had a brief backend hiccup during the traffic spike.
  Everything is back up. Thanks for your patience."

---

### Playbook 3 — AI Agent Rate Limited (Gemini 250 RPD)

**Context**: Gemini 3 Flash Preview is the primary AI agent provider. Its free tier allows
250 RPD and 10 RPM. At 200 AI queries during the moderate launch scenario, the system will
consume 80% of the daily budget. If traffic spikes or the launch runs long, the 250 RPD cap
can be hit. When it is hit, the agent service automatically falls back to Groq Llama 3.3 70B.
This playbook documents both the expected automatic fallback and the scenario where both
providers are simultaneously constrained.

**Detection signals (expected — no action required)**:
- Render logs showing `gemini_rate_limited_falling_back_to_groq` — this is normal behavior
- Grafana traces: `agent.query` spans with `provider=groq` instead of `provider=gemini`
- Groq Console usage counter increasing (indicates fallback is active)
- AI agent responses in the /assistant UI are slightly slower (Groq response time vs Gemini)

**Detection signals (action required)**:
- Render logs showing both Gemini AND Groq returning errors
- Users reporting "AI service temporarily unavailable" in the /assistant UI
- Sentry errors in `agent_service.py` for both provider paths

**Step 1 — Assess which provider is failing**

Check Render logs for the following patterns:
```
gemini_rate_limited_falling_back_to_groq   # Expected Gemini RPM throttle — no action
gemini_daily_quota_exceeded                 # Gemini RPD cap hit — enable pay-as-you-go
groq_rate_limited                           # Groq RPM hit — temporary, resolves in 60s
both_providers_failed                       # Full AI outage — take action
```

**Step 2 — Gemini RPD cap hit (most likely scenario)**

Enable pay-as-you-go billing on the Gemini API to remove the 250 RPD ceiling:
1. Navigate to Google Cloud Console: https://console.cloud.google.com
2. Select the project linked to the Gemini API key (check 1Password "RateShift" vault for
   the project name)
3. Navigate to Billing > Link a billing account
4. Add a payment method and enable billing
5. The quota lift takes effect within 1-5 minutes
6. Pricing: $0.10 per 1M input tokens, $0.40 per 1M output tokens. Launch-day cost estimate:
   200 queries x ~2K tokens avg = ~400K tokens total = approximately $0.20 (negligible)

**Step 3 — Both providers failing simultaneously**

If both Gemini and Groq are returning errors, the AI agent returns a graceful degradation
message to users: "AI service temporarily unavailable. Please try again later."

This is not a full production outage — the rest of the application (prices, dashboard,
alerts, billing) continues to function. The /assistant page is affected only.

Options:
1. Wait for Groq RPM window to reset (resets every 60 seconds)
2. Check Groq Console for account-level issues (plan limits, billing)
3. Temporarily reduce the agent rate limit for free users from 3 queries/day to 1 query/day
   by updating `AGENT_FREE_DAILY_LIMIT=1` in Render env vars. This reduces load on both
   providers during peak.

**Step 4 — Verify resolution**

In the /assistant UI, send a test query. Check Render logs for the provider used:
```
agent.query provider=gemini  # Gemini restored (pay-as-you-go enabled)
agent.query provider=groq    # Groq fallback active (expected during Gemini quota exhaustion)
```
Either log line confirms the agent is functioning. The error state is `both_providers_failed`.

**Step 5 — Communicate**

Gemini rate limiting with successful Groq fallback requires no user communication — the
experience degrades slightly (slower responses) but does not produce errors.

If the full AI outage lasted more than 5 minutes (both providers failing), add a note in
the T+24h retrospective but do not post a public incident. The /assistant feature is not
in the core user journey (price checking and switching). A brief AI outage during a
rate-limiting scenario is an expected free-tier constraint, not a service failure.

---

## 6. Hourly Check Schedule (First 12 Hours)

This schedule assumes launch at T=0 (12:01 AM PT, which is 3:01 AM ET / 8:01 AM UTC).
Adjust timestamps if your launch time differs.

For each hourly check, open the following and record any metric that is outside the
"Normal" band from Section 3:

**Quick check sequence (takes 5 minutes per pass)**:
1. UptimeRobot: all three monitors green
2. Render logs: no error spike in the last 60 minutes
3. Resend: email count vs daily limit
4. Neon: active connections and compute-hours
5. Gemini usage: RPD today
6. CF Worker: request count today
7. GHA: no workflows queued unexpectedly
8. Slack `#incidents`: no unacknowledged alerts

---

| Hour | Time (PT) | Time (UTC) | Focus | What to Check |
|------|-----------|------------|-------|---------------|
| H+0 | 12:01 AM | 08:01 | Launch moment | All monitors green. Render live. Email sending. First signups in DB. |
| H+1 | 1:00 AM | 09:00 | First-wave check | Full quick check sequence. Note baseline values. Verify AI agent responding. |
| H+2 | 2:00 AM | 10:00 | Early traffic | Render CPU and memory trend. Resend count. Neon connections at peak. |
| H+3 | 3:00 AM | 11:00 | East Coast wake-up | Expect traffic increase. Watch Render memory. Check CF request count. |
| H+4 | 4:00 AM | 12:00 | Mid-morning check | Gemini RPD — if > 150, consider enabling pay-as-you-go now (proactive). |
| H+5 | 5:00 AM | 13:00 | Approaching peak | All metrics. GHA minutes remaining. Neon compute-hours trend. |
| H+6 | 6:00 AM | 14:00 | Peak traffic begins | West Coast waking up. This is likely the highest-load hour. All metrics. |
| H+7 | 7:00 AM | 15:00 | Peak (continued) | Render p95 latency. Neon connections. Resend count approaching limit? |
| H+8 | 8:00 AM | 16:00 | Peak (continued) | Check Composio action count. If > 300, upgrade to Starter preemptively. |
| H+9 | 9:00 AM | 17:00 | Post-peak plateau | Sentry error count for the day. Any new error patterns emerging? |
| H+10 | 10:00 AM | 18:00 | Mid-day review | Neon monthly compute-hour pace (extrapolate from hours used). |
| H+11 | 11:00 AM | 19:00 | Afternoon check | CF Worker daily request count. Groq usage (should be low if Gemini healthy). |
| H+12 | 12:00 PM | 20:00 | 12-hour summary | Collect all metrics for the T+24h retrospective. See Section 7. |

### Extended Coverage (Hours 12-24)

After the 12-hour active phase, reduce check frequency to every 2 hours. The risk profile
lowers significantly as the initial signup wave subsides. Focus on:
- Neon compute-hours: the day's accumulated compute must stay within safe monthly budget range
- Resend daily count: resets at midnight UTC, watch the H+24h boundary
- GHA minutes: any new commits triggering CI runs after the launch rush

---

## 7. Post-Launch Review

### T+24h Retrospective (Next Day)

Collect the following metrics by querying the respective dashboards. Fill in the table and
share with the team.

**Infrastructure metrics**

| Metric | Target | Actual | Delta |
|--------|--------|--------|-------|
| Backend uptime % | 99.5%+ | | |
| Frontend uptime % | 99.9%+ | | |
| Backend p95 latency (peak hour) | < 500ms | | |
| 5xx error rate | < 0.5% | | |
| Render peak CPU | < 80% | | |
| Render peak memory | < 450 MB | | |
| Neon compute-hours used (day 1) | < 20h | | |
| Neon peak active connections | < 8 | | |
| CF Worker requests (day 1) | < 30K | | |
| CF Worker error rate | < 0.5% | | |

**Quota metrics**

| Service | Limit | Used (day 1) | % of limit | Action needed? |
|---------|-------|-------------|------------|----------------|
| Resend emails | 50K/day (Starter) | | | |
| Gemini RPD | 250 (or unlimited if pay-as-you-go) | | | |
| Groq requests | 14,400/day | | | |
| Composio actions | 1,000/month | | | |
| GHA minutes | 2,000/month | | | |
| CF Worker requests | 100K/day | | | |
| Neon compute (monthly pace) | 100h/month | | | |

**Product metrics**

| Metric | Target | Actual |
|--------|--------|--------|
| New signups (day 1) | 200-500 | |
| AI agent queries | < 250 | |
| Welcome email delivery rate | > 95% | |
| Incidents declared | 0 | |
| Mean time to detect (if incidents) | < 5 min | |
| Mean time to resolve (if incidents) | < 30 min | |

**Incidents and near-misses**

For each incident or near-miss (threshold crossed but no user impact):
1. What was the detection signal?
2. How long from detection to resolution?
3. Was the runbook accurate and sufficient?
4. What change would prevent recurrence?

Document these as concise bullet points. They feed directly into the action items below.

**Runbook quality review**

After the T+24h retrospective, assess this document:
- Were there thresholds that were too conservative (false alarms)?
- Were there gaps (a metric hit critical but had no playbook entry)?
- Were the dashboard URLs correct and bookmarked before launch?
- Were the playbook steps executable under stress?

Update this file with corrections before the next launch or traffic event.

---

### T+48h Review

At 48 hours post-launch, the initial spike has typically subsided. This review focuses on
whether the new steady-state is sustainable on current tier pricing.

**Capacity projection**

| Service | Day 1 usage | Day 2 usage | Projected monthly rate | Monthly budget | Sustainable? |
|---------|------------|------------|----------------------|---------------|-------------|
| Neon compute-hours | | | | 100h (Free) / 300h (Launch) | |
| Resend emails | | | | 3K (Free) / 50K (Starter) | |
| Composio actions | | | | 1K (Free) / 5K (Starter) | |
| GHA minutes | | | | 2K (Free) | |
| CF Worker requests | | | | 100K/day | |

If any service is projecting to exhaust its monthly budget before end of the billing cycle,
schedule the upgrade now rather than waiting for an outage.

**Deferred upgrade decisions**

Based on actual usage from days 1 and 2, make a final decision on the following upgrades:
- Neon Launch ($19/mo): justified if daily compute-hours average > 3h
- Composio Starter ($29/mo): justified if monthly actions pace exceeds 500
- Gemini pay-as-you-go: justified if Gemini RPD regularly exceeds 200
- Render Standard ($25/mo): justified if average CPU exceeds 50% or memory exceeds 400 MB

**KPI digest**

Pull the nightly KPI report from Slack `#metrics` (C0AKDD7P2HX) for both days. The fields
to capture for the retrospective are:
- Active Users (7d)
- Total Users
- Pro Count
- Business Count
- Estimated MRR
- Alerts Sent
- Connections Active

Compare these against the pre-launch baseline you recorded at T-24h.

**Onboarding funnel**

Check Grafana traces for the conversion funnel:
1. Homepage visit -> Signup (`/signup` page load)
2. Signup -> Onboarding complete (`onboarding_completed = true`)
3. Onboarding -> First price forecast viewed
4. First forecast -> Alert created

Any step with a drop-off above 50% is a product issue to address in the first post-launch
sprint. Instrument these funnel steps as named spans in Grafana Tempo if they are not
already traced.

---

## Appendix A — Emergency Contact Reference

| Resource | Location |
|----------|---------|
| All service credentials | 1Password vault "RateShift" |
| Render service ID | `srv-d649uhur433s73d557cg` |
| Neon project ID | `cold-rice-23455092` |
| Neon pooled endpoint | `ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech` |
| CF Account ID | `b41be0d03c76c0b2cc91efccdb7a10df` |
| CF Worker name | `rateshift-api-gateway` |
| Grafana instance ID | `1342627` (region: prod-us-east-2) |
| Slack workspace | `electricityoptimizer.slack.com` (T0AK0AJV5NE) |
| Resend domain ID | `20c95ef2-42f4-4040-be75-2026e97e35c9` |
| GitHub repo | `JoeyJoziah/electricity-optimizer` |

## Appendix B — Upgrade Decision Tree

Use this as a quick reference when a threshold is hit.

```
Render memory > 450 MB or CPU > 80%
  -> Upgrade to Render Standard ($25/mo) immediately

Resend daily count > 80% of plan limit
  -> If on Free tier: upgrade to Starter ($20/mo)
  -> If on Starter: monitor; 50K/day is very hard to exhaust at launch scale

Neon connections >= 8 (pool exhausted)
  -> Upgrade to Neon Launch ($19/mo) immediately
  -> Also check for slow queries holding connections in Neon monitoring

Neon monthly compute pace > 3h/day average
  -> Upgrade to Neon Launch ($19/mo) before end of billing period

Gemini RPD > 225
  -> Enable pay-as-you-go billing in Google Cloud Console (~10 min)
  -> Cost at launch scale: approximately $0.20 total (negligible)

Composio actions today > 300
  -> Upgrade to Composio Starter ($29/mo) if sustained; monthly budget will exhaust in 3 days

GHA minutes remaining < 200
  -> Purchase 500-minute block at github.com settings billing ($4 one-time)

CF Worker requests today > 70K
  -> Evaluate bot traffic in CF analytics
  -> Upgrade to Workers Paid ($5/mo) if legitimate traffic pattern
```

## Appendix C — Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Capacity Audit | `docs/CAPACITY_AUDIT.md` | Free-tier limits, scenario modeling, risk summary |
| General Monitoring | `docs/MONITORING.md` | UptimeRobot, Better Stack, Sentry, SLA policy |
| Launch Checklist | `docs/LAUNCH_CHECKLIST.md` | Product Hunt preparation (marketing, content, network) |
| Redeployment Runbook | `docs/REDEPLOYMENT_RUNBOOK.md` | Full cold-start redeployment procedure for all layers |
| Observability | `docs/OBSERVABILITY.md` | OTel tracing architecture, Grafana Cloud Tempo setup |
| Infrastructure | `docs/INFRASTRUCTURE.md` | CF Worker, GHA workflows, deployment pipeline |
| Cost Analysis | `docs/COST_ANALYSIS.md` | GHA minute optimization, cost reduction analysis |

---

> Last Updated: 2026-03-17
> Author: SRE Engineering
> Review cadence: Update after each significant traffic event or infrastructure change
