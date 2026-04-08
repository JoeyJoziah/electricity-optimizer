# RateShift — Infrastructure Upgrade Runbook
# Product Hunt Launch: Tuesday April 14, 2026

> **Upgrade window**: Monday April 13, 2026, starting no later than 18:00 ET
> **Target go-live**: Tuesday April 14, 2026, 00:01 PT (Product Hunt reset)
> **Owner**: Solo founder (Devin McGrath)
> **Budget impact**: +$27/mo (Render Starter $7 + Resend Starter $20)
> **Companion docs**: `docs/CAPACITY_AUDIT.md`, `docs/launch/MONITORING_RUNBOOK.md`, `docs/SCALING_PLAN.md`

This runbook is executable step-by-step. Work top to bottom. Do not skip sections.
Each upgrade has an explicit verification gate. If a gate fails, follow the rollback
before proceeding.

---

## Table of Contents

1. [Pre-Upgrade Checklist](#1-pre-upgrade-checklist)
2. [Render: Free to Starter Upgrade](#2-render-free-to-starter-upgrade)
3. [Resend: Free to Starter Upgrade](#3-resend-free-to-starter-upgrade)
4. [Post-Upgrade Verification Suite](#4-post-upgrade-verification-suite)
5. [Traffic Capacity Estimates at New Tiers](#5-traffic-capacity-estimates-at-new-tiers)
6. [Launch-Day Monitoring Checklist](#6-launch-day-monitoring-checklist)
7. [Emergency Playbook](#7-emergency-playbook)
8. [Cost Monitoring and Scale-Up Triggers](#8-cost-monitoring-and-scale-up-triggers)

---

## 1. Pre-Upgrade Checklist

Run these gates in order before touching any billing settings. Each gate has a
pass/fail condition. A failure means investigate and fix before continuing.

### 1.1 Access Verification

Confirm you can log into every console you will need during the upgrade window.
Open all tabs now — do not rely on password managers working under pressure.

```
[ ] Render Dashboard         https://dashboard.render.com
      Service ID: srv-d649uhur433s73d557cg
      Expected: Service status "Live", health check green

[ ] Resend Dashboard         https://resend.com/settings/billing
      Expected: Current plan shows "Free"

[ ] Neon Console             https://console.neon.tech/app/projects/cold-rice-23455092
      Expected: Project "energyoptimize" visible, Usage tab accessible

[ ] Cloudflare Dashboard     https://dash.cloudflare.com/b41be0d03c76c0b2cc91efccdb7a10df
      Expected: Zone rateshift.app active, Worker rateshift-api-gateway deployed

[ ] Vercel Dashboard         https://vercel.com/dashboard
      Expected: electricity-optimizer project, most recent deployment "Ready"

[ ] 1Password Vault          RateShift vault
      Expected: Able to retrieve Neon, Render, Resend, Stripe secrets
```

### 1.2 Baseline Health Check

Run this before touching anything. Capture the output — you will compare against
it after the upgrade to confirm no regressions.

```bash
# Backend direct health
curl -s https://api.rateshift.app/health | python3 -m json.tool
# Expected: {"status": "healthy", ...} with HTTP 200

# CF Worker gateway health (proxied)
curl -s https://api.rateshift.app/api/v1/health | python3 -m json.tool
# Expected: {"status": "healthy"} with HTTP 200

# Frontend reachable
curl -s -o /dev/null -w "Frontend HTTP status: %{http_code}\n" https://rateshift.app
# Expected: 200

# Prices endpoint (should be CF-cached, fast)
curl -s -w "\nLatency: %{time_total}s\n" \
  "https://api.rateshift.app/api/v1/prices/current?region=us_ct" \
  | python3 -m json.tool
# Expected: HTTP 200, latency < 500ms (cache hit) or < 3s (cache miss)

# CF Worker gateway stats (verify caching is active)
curl -s -H "X-Internal-API-Key: $INTERNAL_API_KEY" \
  https://api.rateshift.app/api/v1/internal/gateway-stats | python3 -m json.tool
# Expected: cache_hits, cache_misses counters visible
```

Save the output of all five commands to a scratch file. You want a snapshot of
"before" latencies and response shapes.

### 1.3 GitHub Actions Minutes Check

A hotfix deploy requires GHA minutes. If the budget is exhausted you cannot push
a fix during the launch window.

```
[ ] Go to: https://github.com/JoeyJoziah/electricity-optimizer/settings/billing
    Check "Actions" section for current month minute usage.

    If usage > 1,500 min: purchase a 500-minute block at GitHub.com/settings/billing
    Cost: ~$4 one-time. Worth it.

    If usage < 1,500 min: you have enough buffer for ~10-20 CI runs. OK to proceed.
```

### 1.4 Neon Connection Pooling Confirmation

The upgrade runbook instructs you to use the pooler endpoint. Verify it is
already configured in Render.

```
[ ] Go to: https://dashboard.render.com > Service srv-d649uhur433s73d557cg > Environment
    Find: DATABASE_URL
    Verify the hostname contains "-pooler" — it should be:
      ep-withered-morning-pooler.us-east-1.aws.neon.tech

    If it contains "ep-withered-morning.us-east-1.aws.neon.tech" (no -pooler):
      Update the env var to use the pooler endpoint before the Render upgrade.
      The pooler supports more concurrent connections via PgBouncer.
      Render will auto-deploy after the env var change.
```

### 1.5 UptimeRobot Status

All monitors must be green before you start changing billing tiers.

```
[ ] Go to: https://dashboard.uptimerobot.com
    Confirm all three monitors show UP:
      - RateShift Frontend (rateshift.app)
      - RateShift API Health (api.rateshift.app/health)
      - RateShift API Prices (api.rateshift.app/api/v1/prices/current)

    If any monitor is DOWN: investigate and resolve before upgrading.
    A Render restart during an upgrade while the backend is already unhealthy
    will produce confusing results.
```

### 1.6 Record Current Render Instance Type

Screenshot or note the current Render service configuration as your rollback
baseline.

```
[ ] Go to: https://dashboard.render.com > Service > Settings > Instance Type
    Current value should be: "Free"
    Note the current auto-deploy branch: main
    Note the current health check path: /health
```

**Pre-upgrade checklist complete. Proceed to Section 2.**

---

## 2. Render: Free to Starter Upgrade

**Why this upgrade matters**: The Render Free tier auto-sleeps after 15 minutes
of inactivity. A cold start takes 20-30 seconds. The first Product Hunt visitor
who hits a sleeping backend sees a spinner for 30 seconds before getting a
response — enough to cause an immediate bounce and a negative first impression.
Render Starter eliminates auto-sleep entirely for $7/month.

**Specs comparison**:

| | Free | Starter |
|--|--|--|
| RAM | 512 MB | 512 MB |
| CPU | 0.5 shared | 0.5 shared |
| Auto-sleep | Yes (15 min idle) | No |
| Custom domain | No | Yes |
| Price | $0 | $7/mo |

Specs for RAM and CPU are identical. The only change is the elimination of
auto-sleep. This is a billing-tier change, not a configuration change.

**Estimated time**: 5 minutes (2 min dashboard clicks + 3 min service restart)

**Downtime**: Approximately 30 seconds while Render restarts the service after
the tier change. Schedule during low-traffic period (Monday evening is fine).

### 2.1 Execute the Upgrade

1. Go to `https://dashboard.render.com`
2. Click on the backend service (srv-d649uhur433s73d557cg or named "rateshift-api")
3. Click **Settings** in the left sidebar
4. Scroll to **Instance Type**
5. Click **Change** or the dropdown next to "Free"
6. Select **Starter ($7/month)**
7. Click **Save Changes** or **Confirm**
8. Render will display a banner: "Your service is updating..."
9. The service will restart. Monitor the **Logs** tab in real time.

Watch for this sequence in the logs:

```
==> Starting service with 'uvicorn backend.main:app ...'
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
```

When you see "Application startup complete", proceed to the verification step.

### 2.2 Render Upgrade Verification

Run these checks immediately after the service restarts:

```bash
# Gate 1: Basic health (must pass within 60s of service startup)
curl -s https://api.rateshift.app/health
# Expected: {"status": "healthy"} HTTP 200
# If you get connection refused: wait 30s and retry (service still starting)

# Gate 2: Confirm auto-sleep is disabled
# (No programmatic check exists — visual confirmation in Render dashboard)
# Settings > Instance Type should now show "Starter"

# Gate 3: Response latency is consistent (no cold-start penalty)
for i in 1 2 3; do
  curl -s -w "Request $i: %{time_total}s\n" -o /dev/null https://api.rateshift.app/health
  sleep 2
done
# Expected: All three requests complete in < 1s
# A 20-30s request indicates auto-sleep is still active (tier change did not take effect)

# Gate 4: Authenticated endpoint still works (DB connectivity intact)
curl -s https://api.rateshift.app/api/v1/prices/current?region=us_ct
# Expected: JSON price data, HTTP 200

# Gate 5: CF Worker still routing correctly to upgraded backend
curl -s -w "\nCF latency: %{time_total}s\n" \
  "https://api.rateshift.app/api/v1/prices/current?region=us_ct" | python3 -m json.tool
# Expected: Same price data, X-Cache header present
```

All five gates must pass. If any fails, see rollback procedure below.

### 2.3 Render Rollback Procedure

The rollback is reversible at any time with no data loss. The service will restart
again (another ~30 second window).

1. Go to `https://dashboard.render.com` > Service > Settings > Instance Type
2. Change from **Starter** back to **Free**
3. Click **Save Changes**
4. Wait for service restart (watch logs)
5. Run Gate 1 verification above to confirm the service is healthy on Free tier
6. Investigate the failure before retrying the upgrade

**Important**: Rolling back to Free tier re-enables auto-sleep. Do not leave the
service on Free tier overnight before launch day — the first morning visitor will
hit a cold start.

---

## 3. Resend: Free to Starter Upgrade

**Why this upgrade matters**: The Resend Free tier sends a maximum of 100 emails
per day. A moderate Product Hunt launch with 500 signups generates ~600 emails
(500 welcome emails + ~100 price alert notifications). That is 6x the daily cap.
Without this upgrade, welcome emails stop being delivered after the first 100
signups. The Gmail SMTP fallback (500/day limit) provides partial coverage but is
not a reliable substitute for transactional email at launch scale.

**Specs comparison**:

| | Free | Starter |
|--|--|--|
| Daily send limit | 100 emails/day | No daily cap |
| Monthly send limit | 3,000 emails/month | 50,000 emails/month |
| Domains | 1 | 1 |
| Price | $0 | $20/mo |

**Estimated time**: 5 minutes (billing page only — no service restart)

**Downtime**: None. Resend plan upgrades take effect immediately. No API key
changes are needed. Your existing `RESEND_API_KEY` in Render env vars remains valid.

### 3.1 Execute the Upgrade

1. Go to `https://resend.com/settings/billing`
2. Under "Current Plan", click **Upgrade** or **Change Plan**
3. Select **Starter ($20/month)**
4. Enter payment details if not already on file
5. Confirm the upgrade
6. The page should immediately reflect "Starter" as the active plan with:
   - 50,000 emails/month
   - No daily sending cap

### 3.2 Resend Upgrade Verification

```bash
# Gate 1: Send a test email via the Resend API directly
# Replace YOUR_RESEND_API_KEY with the value from Render env vars
curl -s -X POST https://api.resend.com/emails \
  -H "Authorization: Bearer YOUR_RESEND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "from": "RateShift <noreply@rateshift.app>",
    "to": ["your-personal-email@example.com"],
    "subject": "RateShift Upgrade Verification — T-24h",
    "text": "Resend Starter upgrade verified at '"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'."
  }' | python3 -m json.tool
# Expected: {"id": "some-uuid"} HTTP 200
# Check your inbox to confirm delivery

# Gate 2: Confirm plan limits via Resend API
curl -s https://api.resend.com/domains \
  -H "Authorization: Bearer YOUR_RESEND_API_KEY" | python3 -m json.tool
# Expected: rateshift.app domain listed with status "verified"
# (This confirms the API key is valid and domain is active)

# Gate 3: Confirm backend is using Resend (not falling back to SMTP)
# Check Render logs for recent email sends. In Render Dashboard > Logs, search for:
#   "email_sent_via_resend" or "resend" (backend structured log field)
# You should NOT see "email_sent_via_smtp" for normal sends
```

Gate 1 (actual email delivery) is the critical gate. If you receive the test email,
the upgrade is working correctly.

### 3.3 Resend Rollback Procedure

Rollback is not normally needed for this upgrade since it only increases limits.
However, if billing fails or the plan does not activate:

1. Verify payment method in `https://resend.com/settings/billing`
2. The Free tier remains in place until a successful payment is processed
3. If Resend billing is broken: the Gmail SMTP fallback (`SMTP_HOST`, `SMTP_PORT`,
   `SMTP_PASSWORD` in Render env vars) will continue to handle email delivery up to
   500 emails/day. This is sufficient for the first ~400 signups.
4. To force SMTP-only mode as a temporary measure: in Render env vars, rename
   `RESEND_API_KEY` to `RESEND_API_KEY_DISABLED`. The backend will fall through to
   SMTP. Rename it back when Resend billing is resolved.

---

## 4. Post-Upgrade Verification Suite

Run this full suite after both upgrades are complete and before going to sleep
on Monday night. These tests verify the complete request path from the public
internet through to the database.

### 4.1 Layer-by-Layer Health Sweep

```bash
# --- Layer 1: Frontend (Vercel CDN) ---
curl -s -I https://rateshift.app | grep -E "^HTTP|^x-vercel|^cache-control"
# Expected: HTTP/2 200, x-vercel-cache: HIT or MISS (not error), cache-control present

# --- Layer 2: CF Worker Gateway ---
curl -s -I https://api.rateshift.app/api/v1/prices/current?region=us_ct \
  | grep -E "^HTTP|^cf-cache|^x-cache|^cf-ray"
# Expected: HTTP/2 200, CF-Ray header present (confirms passing through CF edge)

# --- Layer 3: Backend (Render Starter) ---
curl -s https://api.rateshift.app/health | python3 -m json.tool
# Expected: {"status": "healthy", "database": "connected", "version": "..."}

# --- Layer 4: Database (Neon via pooler) ---
curl -s https://api.rateshift.app/api/v1/prices/current?region=us_ny | python3 -m json.tool
# Expected: JSON with actual price data — confirms DB is responding
# If you get {"detail": "..."} error, check Neon console for compute status
```

### 4.2 Email End-to-End Test

```bash
# Trigger a test registration to verify welcome email delivery
# Use a real email address you can check
curl -s -X POST https://api.rateshift.app/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "launch-test-'"$(date +%s)"'@yourdomain.com",
    "password": "TestPassword123!",
    "name": "Launch Test"
  }' | python3 -m json.tool
# Expected: {"id": "...", "email": "..."} HTTP 201

# Then check your email inbox within 60 seconds for the welcome email.
# From: RateShift <noreply@rateshift.app>
# Subject: Welcome to RateShift (or similar)
# If it arrives: Resend Starter is working correctly.
# If it does not arrive within 2 minutes: check Resend Dashboard > Emails tab for delivery status.
```

### 4.3 Sustained No-Sleep Verification

This test confirms Render Starter has truly disabled auto-sleep. After a period
of inactivity, the Starter tier should still respond immediately.

```bash
# Wait 20 minutes with no traffic (simulate an idle period)
# Then run:
time curl -s https://api.rateshift.app/health > /dev/null
# Expected: Wall time < 2 seconds
# If wall time is 20-30 seconds: auto-sleep is still active (tier change failed)
```

If you do not want to wait 20 minutes, check Render Dashboard > Metrics. The
"Sleep" indicator should not appear on the Starter tier. On Free tier, you will
see it. This is the fastest visual confirmation.

### 4.4 Rate Limiting Sanity Check

Confirm the CF Worker rate limiting is still functional after the backend upgrade.
The rate limiter runs at the CF edge and is unaffected by Render changes, but
verify it has not been misconfigured.

```bash
# Fire 10 rapid requests — none should be rate-limited at this volume
for i in $(seq 1 10); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "https://api.rateshift.app/api/v1/prices/current?region=us_ct")
  echo "Request $i: HTTP $STATUS"
done
# Expected: All 10 return 200 (well under 120 req/min standard limit)

# Confirm auth endpoint is under strict rate limit (30 req/min)
# Do NOT actually trigger 30 failed auth attempts — just verify the endpoint is reachable
curl -s -X POST https://api.rateshift.app/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "nonexistent@test.com", "password": "wrong"}' \
  -w "\nHTTP status: %{http_code}\n"
# Expected: HTTP 401 (not rate-limited at 1 request)
```

### 4.5 Neon Connection Pool Check

Verify the database can handle concurrent connections at current settings.

```bash
# Fire 5 simultaneous database-hitting requests
for i in $(seq 1 5); do
  curl -s "https://api.rateshift.app/api/v1/prices/current?region=us_ct" \
    -w "Request $i: HTTP %{http_code} in %{time_total}s\n" \
    -o /dev/null &
done
wait
# Expected: All 5 complete with HTTP 200
# Latency variance > 2x between requests may indicate connection pool contention

# Then check Neon console:
# console.neon.tech > Project cold-rice-23455092 > Monitoring
# Look at "Active connections" — should show < 5 after the burst (connections returned to pool)
```

**Verification suite complete. If all gates pass: you are ready for launch.**

---

## 5. Traffic Capacity Estimates at New Tiers

These estimates are based on the scenario modeling in `docs/CAPACITY_AUDIT.md`
and the tier specs confirmed above. They tell you how much headroom you have at
each service before degradation occurs.

### 5.1 Render Starter

| Metric | Capacity | Notes |
|--|--|--|
| Concurrent requests | ~50 req/s sustained | 0.5 shared CPU, 1 Uvicorn worker |
| Memory headroom | ~200 MB usable (of 512 MB) | FastAPI + ML models occupy ~300 MB |
| Cold start penalty | **Eliminated** | Starter tier, always-warm |
| Request timeout risk | Above ~80 req/s sustained | CPU becomes bottleneck, queuing begins |
| Recommended ceiling | 50 concurrent users active | Per load test baseline in LOAD_TESTING.md |

At 500 PH signups spread across a 12-hour window, peak concurrency is roughly
10-20 active users at any given moment. Well within Starter limits.

The danger zone is a sudden burst — all 500 visitors arriving in the first 30
minutes of the PH post going live. At that rate (~17 signups/min), Render Starter
will handle it with elevated but acceptable latency. The CF Worker's 2-tier cache
(5-minute TTL on price data, 2-hour TTL on supplier registry) means most
read-heavy requests never reach the backend.

**Upgrade trigger**: If Render CPU sustains above 80% for more than 5 consecutive
minutes, or p95 response time exceeds 3 seconds, escalate to Render Standard
($25/mo, 2 GB RAM, dedicated CPU). See Section 8.

### 5.2 Resend Starter

| Metric | Capacity | Notes |
|--|--|--|
| Monthly send limit | 50,000 emails/month | No daily cap |
| Welcome email capacity | ~50,000 signups/month | One per signup |
| Alert email capacity | Remaining budget after welcome emails | |
| Bounce rate SLA | < 5% to avoid Resend suspension | Monitor in Resend dashboard |
| Conservative daily ceiling | ~5,000 emails/day | Self-imposed; well under monthly cap |

At 500 signups (base case), you send ~600 emails total on launch day. That is 1.2%
of the monthly budget. Even in a viral scenario with 2,000 signups, you send ~2,200
emails, which is 4.4% of the monthly budget. Resend Starter has enormous headroom.

**No upgrade trigger is needed for Resend** under any realistic PH launch scenario.

### 5.3 Neon PostgreSQL (Free — No Upgrade Planned)

| Metric | Free Tier | Launch Risk |
|--|--|--|
| Compute hours | 100 h/month | Medium |
| Storage | 0.5 GB | Low (currently ~100 MB) |
| Max connections (pooler) | ~10 via PgBouncer | Low (1 worker, pool_size 3+5=8) |
| Compute used in one 16h launch day | ~16 h | 16% of monthly budget |
| Projected compute usage for April | ~40-50 h total | Within 100 h limit |

Neon's free tier is unlikely to exhaust during the launch itself. The risk is
accumulated usage in the days following if post-launch traffic remains elevated.
Watch the compute-hours counter daily for the week after launch. If you are
projected to exceed 100 h before the billing cycle resets, upgrade to Neon Launch
($19/mo, 300 h) immediately.

### 5.4 Cloudflare Worker (Free — No Upgrade Needed)

| Metric | Free Tier | Launch Projection |
|--|--|--|
| Daily request limit | 100,000 req/day | ~15,000 (15%) |
| Cache hit rate (estimated) | ~60-70% | Reduces origin hits |
| Rate limit capacity | 120 req/min/IP (standard) | No single user exceeds this |
| Worst-case (viral, 2K signups) | ~75,000 req/day | 75%, approaching limit |

The CF Worker's 2-tier caching (Cache API + KV with per-region TTLs of 5-120
minutes) dramatically reduces request volume to the backend. The free tier should
handle any realistic PH traffic scenario.

If you somehow approach 80,000 requests in a day (extremely viral), upgrade to
Workers Paid ($5/mo, 10M requests/month) as a precaution. This takes 2 minutes
in the CF dashboard.

### 5.5 Vercel Frontend (Free — No Upgrade Needed)

| Metric | Free Tier | Launch Projection |
|--|--|--|
| Bandwidth | 100 GB/month | ~2 GB for 2,000 page views |
| Serverless invocations | 100,000/month | ~2,000 (auth routes) |
| Build minutes | 6,000/month | ~50 for Monday deploy |

Vercel's CDN handles static assets (JS, CSS, images) with 0 serverless invocations.
Only the auth routes (`/api/auth/*`) hit serverless functions. The free tier has
50x headroom over the base-case launch scenario.

---

## 6. Launch-Day Monitoring Checklist

This is your operational dashboard guide for Tuesday April 14. Open all these
URLs at 11:30 PM ET on Monday night (30 minutes before PH resets at midnight PT
= 3:00 AM ET). Keep them open throughout the launch.

### 6.1 Dashboards to Have Open

```
Tab 1:  Render Metrics        https://dashboard.render.com (Service > Metrics)
Tab 2:  Neon Usage            https://console.neon.tech/app/projects/cold-rice-23455092 > Usage
Tab 3:  CF Worker Analytics   https://dash.cloudflare.com > Workers > rateshift-api-gateway > Analytics
Tab 4:  Resend Email Stats    https://resend.com/emails
Tab 5:  UptimeRobot           https://dashboard.uptimerobot.com
Tab 6:  Sentry Errors         https://sentry.io (your RateShift project)
Tab 7:  Vercel Analytics      https://vercel.com > electricity-optimizer > Analytics
Tab 8:  Gemini API Usage      https://aistudio.google.com > API Keys > Usage
Tab 9:  GitHub Actions        https://github.com/JoeyJoziah/electricity-optimizer/actions
Tab 10: Composio Usage        https://composio.dev/dashboard > Usage
```

### 6.2 Metrics to Watch and Thresholds

Check each of these on a 15-minute cadence for the first 6 hours, then every
30 minutes for the following 6 hours.

#### Render (Backend)

| Metric | Watch For | Concern Threshold | Action |
|--|--|--|--|
| CPU % | Sustained high | > 80% for 5+ min | Section 7.1 |
| Memory | Growing without release | > 450 MB | Section 7.1 |
| Request latency (p95) | Creeping up | > 3,000 ms | Section 7.1 |
| Error rate | Any spike | > 2% of requests | Section 7.2 |
| Service status | "Live" indicator | Any state other than Live | Section 7.2 |

#### Neon PostgreSQL

| Metric | Watch For | Concern Threshold | Action |
|--|--|--|--|
| Active connections | Approaching pool limit | > 8 concurrent | Section 7.3 |
| Compute hours used | Monthly budget burn | > 20 h in first 24h | Section 7.3 |
| Query latency | Slow queries in monitoring | p95 > 500 ms | Section 7.3 |
| Error rate | Connection failures | Any ORM errors in Render logs | Section 7.3 |

#### Cloudflare Worker

| Metric | Watch For | Concern Threshold | Action |
|--|--|--|--|
| Requests/day | Approaching daily limit | > 70,000 | Section 7.4 |
| Error rate | Worker failures | > 1% | Section 7.4 |
| Cache hit rate | Drop in cache effectiveness | < 40% | Investigate, not urgent |
| CPU time/invocation | Approaching 10ms limit | > 8 ms avg | Section 7.4 |

#### Resend

| Metric | Watch For | Concern Threshold | Action |
|--|--|--|--|
| Emails sent today | Volume tracking | > 5,000/day | Verify no loop |
| Bounce rate | Email deliverability | > 5% | Pause, investigate |
| Delivery failures | Any queue errors | > 10 failures/hour | Section 7.5 |

#### Sentry

| Metric | Watch For | Concern Threshold | Action |
|--|--|--|--|
| Error events | Any new error type | New exception class appearing | Triage immediately |
| Error volume | Spike in known errors | > 100 events/hour on any single error | Section 7.2 |
| Monthly events | Budget consumption | > 2,500 (50% of 5K free tier) | Accept errors gracefully |

#### Gemini / Groq (AI Agent)

| Metric | Watch For | Concern Threshold | Action |
|--|--|--|--|
| Gemini RPD | Daily limit approach | > 200 RPD | Normal — Groq fallback active |
| Gemini RPM | Per-minute spike | > 10 RPM | Normal — Groq fallback active |
| Groq requests | Unexpected high volume | > 200 RPD on Groq | Gemini may be down entirely |
| Composio actions | Monthly budget burn | > 500 actions (50%) | Section 7.6 |

### 6.3 Hourly Health Check Script

Run this every 15 minutes during the first 4 hours of the launch. Copy it to your
terminal and run in a loop, or open a second terminal window with it running.

```bash
#!/bin/bash
# Quick launch-day health poll
# Usage: bash launch-health-check.sh

TIMESTAMP=$(date -u +"%H:%M:%S UTC")
echo "=== RateShift Health Check @ $TIMESTAMP ==="

# Backend health
BACKEND=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://api.rateshift.app/health)
echo "Backend health:   HTTP $BACKEND"

# Prices endpoint (CF cached)
PRICES=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
  "https://api.rateshift.app/api/v1/prices/current?region=us_ct")
echo "Prices endpoint:  HTTP $PRICES"

# Frontend
FRONTEND=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://rateshift.app)
echo "Frontend:         HTTP $FRONTEND"

# Response time
LATENCY=$(curl -s -o /dev/null -w "%{time_total}" --max-time 10 https://api.rateshift.app/health)
echo "Backend latency:  ${LATENCY}s"

echo ""
```

A healthy result looks like:
```
=== RateShift Health Check @ 03:15:00 UTC ===
Backend health:   HTTP 200
Prices endpoint:  HTTP 200
Frontend:         HTTP 200
Backend latency:  0.187s
```

If any line shows anything other than HTTP 200, or if latency exceeds 5s:
immediately open the corresponding dashboard and proceed to Section 7.

---

## 7. Emergency Playbook

These are the specific actions to take when a service goes into a degraded state
during the launch. Each scenario is ranked by likelihood based on the capacity
analysis in Section 5.

### 7.1 Render: CPU/Memory Saturation or High Latency

**Symptoms**: CPU > 80% sustained, p95 latency > 3s, 502/504 errors from CF
Worker, users reporting slow load times.

**Likelihood**: Medium at 500+ concurrent users.

**Resolution — 5 minutes**:
1. Open `https://dashboard.render.com` > Service > Settings > Instance Type
2. Change from **Starter ($7/mo)** to **Standard ($25/mo)**
   - Standard gives: 2 GB RAM, 1 dedicated CPU (vs 0.5 shared)
   - The service will restart with a ~30 second downtime
3. After restart, watch Render metrics for CPU to drop below 40%
4. Total additional cost: $18/mo over Starter (you had $27 budget, this adds $18)
5. Verify with: `curl -s https://api.rateshift.app/health`

**If Standard is still insufficient** (viral scenario, 2,000+ signups):
- Upgrade to Render Pro ($85/mo, 4 GB RAM, 2 dedicated CPUs)
- At this point you also likely need Neon Launch (see 7.3) — concurrent upgrades
  are fine; each service restarts independently

**Rollback**: Downgrade back to Starter when traffic normalizes (typically 24-48h
after a PH spike).

### 7.2 Render: Service Down (500 Errors or Crash Loop)

**Symptoms**: All endpoints returning 5xx, UptimeRobot sends DOWN alert, Sentry
floods with errors.

**Immediate actions**:
1. Check Render Dashboard > Service > Logs for the crash cause
2. Look for: OOMKilled (out of memory), uncaught exception, missing env var
3. For OOMKilled: upgrade to Standard immediately (see 7.1)
4. For uncaught exception: look at the stack trace in logs, then check Sentry for
   the full traceback
5. For a bad deploy: go to Render > Service > Deploys, click "Rollback" on the
   last known-good deploy (the one before any Monday pre-launch changes)
6. If you cannot identify the cause in 5 minutes: roll back the deploy first,
   investigate second

**While the backend is down**: The CF Worker's frontend circuit breaker activates
automatically for public endpoints (prices, health, suppliers) and falls back to
direct Render URL if configured. Auth and user-specific endpoints will fail.

**Communication**: If downtime exceeds 5 minutes during the launch window, post a
brief status update to your PH comment thread: "Experiencing elevated load — back
in a few minutes" is better than silence.

### 7.3 Neon: Connection Exhaustion or Compute Hours Depleted

**Symptoms for connection exhaustion**: 500 errors with "too many connections" or
"connection pool timeout" in Render logs. Typically appears as SQLAlchemy
`OperationalError: connection timed out`.

**Symptoms for compute hours depleted**: Database goes offline mid-request. All
API calls return 500. Neon Console shows "Suspended" status.

**Resolution for connection exhaustion — 2 minutes**:
1. Open `https://console.neon.tech/app/projects/cold-rice-23455092`
2. Confirm DATABASE_URL in Render env vars uses the pooler endpoint:
   `ep-withered-morning-pooler.us-east-1.aws.neon.tech`
   (If it does not have `-pooler`, add it — this routes through PgBouncer and
   allows far more concurrent connections)
3. In Render env vars, temporarily reduce DB_MAX_OVERFLOW from 10 to 5 to
   free up pool slots
4. Trigger a Render redeploy (env var change auto-deploys)

**Resolution for compute hours depleted — 2 minutes**:
1. In Neon Console > Project > Settings > Billing
2. Upgrade from **Free** to **Launch ($19/mo)**
   - 300 compute-hours/month (3x more than free)
   - Takes effect immediately — database comes back online within 30 seconds
3. No DATABASE_URL change needed — same endpoint, same credentials
4. Verify: `curl -s https://api.rateshift.app/api/v1/prices/current?region=us_ct`

### 7.4 Cloudflare Worker: Request Limit Approaching or Errors

**Symptoms for request limit**: CF Analytics shows daily requests approaching
80,000-90,000. Frontend circuit breaker may have triggered for some users.

**Symptoms for worker errors**: CF Analytics shows error rate > 1%. Users see
"Something went wrong" or gateway errors.

**Resolution for request limit — 2 minutes**:
1. Go to `https://dash.cloudflare.com` > Workers & Pages > Plans
2. Upgrade to **Workers Paid ($5/month)** for 10 million requests per month
3. No code changes needed. No redeployment needed. Billing change takes effect
   immediately.

**Resolution for worker errors**:
1. Check CF Workers > rateshift-api-gateway > Logs (real-time)
2. Common causes: upstream Render timeout causing CF to return 502, KV read error
3. The worker is designed to fail-open on KV errors (graceful degradation)
4. If errors are from Render timeouts, address at Render level (see 7.1/7.2)
5. Do not redeploy the worker during active launch traffic unless the error is
   definitively a worker bug — a deploy causes a brief re-initialization

**Check for bot traffic**: If CF Analytics shows a sudden request spike with low
cache hit rate, you may be getting crawled. Enable CF Bot Fight Mode in:
Security > Bots > Bot Fight Mode (toggle to ON). This adds bot protection without
code changes.

### 7.5 Resend: Email Delivery Failures

**Symptoms**: Welcome emails not arriving, Sentry errors for email sends, Resend
Dashboard shows high bounce or failure rate.

**For bounce rate > 5%**:
1. Pause email sending temporarily (set RESEND_API_KEY to empty string in Render
   env vars — backend falls to SMTP fallback)
2. Check Resend Dashboard > Emails tab for specific failure reasons
3. Common causes: disposable email addresses, spam trap addresses from launch day
4. Resume Resend after investigating — the DKIM/SPF/DMARC setup on rateshift.app
   is already verified, so legitimate deliverability should be high

**For delivery quota errors** (should not happen on Starter, but if it does):
1. Resend Dashboard > Billing — verify Starter plan is active
2. If somehow reverted to Free tier, re-upgrade (billing issue — check payment method)
3. SMTP fallback (Gmail, 500/day) provides bridge coverage while resolving

**Gmail SMTP fallback verification** (test this now, before launch):
```bash
# Verify SMTP credentials are valid (run from local machine)
python3 -c "
import smtplib, ssl
SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 465
# Get these from Render env vars: SMTP_USER, SMTP_PASSWORD
SMTP_USER = 'your-gmail@gmail.com'
SMTP_PASS = 'your-app-password'
context = ssl.create_default_context()
with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
    server.login(SMTP_USER, SMTP_PASS)
    print('SMTP fallback: OK')
"
```

### 7.6 Composio: AI Tool Actions Exhausted

**Symptoms**: AI agent responses lack action capabilities (no email drafting, no
data export), backend logs show `composio_init_failed` or tool call errors.

**Behavior**: The agent degrades gracefully — it answers questions but cannot
execute actions. Users see slightly less capable responses, not errors.

**Resolution — 2 minutes**:
1. Go to `https://composio.dev/dashboard` > Billing
2. Upgrade from **Free (1,000 actions/month)** to **Starter ($29/mo, 5,000 actions)**
3. Takes effect immediately
4. No env var changes needed — same `COMPOSIO_API_KEY`

**Alternative**: If you want to preserve free tier for now, accept the degraded
mode (answers without actions) for the rest of launch day. The 1,000-action free
tier resets monthly. This is an acceptable trade-off at 500-signup scale.

### 7.7 GitHub Actions: Minutes Exhausted (Cannot Deploy Hotfix)

**Symptoms**: CI workflows show "Queued" but do not start. You cannot push a
hotfix because CI will not pass and auto-deploy will not trigger.

**Immediate workaround for Render** (bypass GHA):
1. In Render Dashboard > Service > Settings > Build & Deploy
2. Render has its own auto-deploy from the GitHub repo — check "Auto-Deploy" is
   enabled. Render pulls from GitHub and builds independently of GHA. A `git push`
   to main will trigger a Render deploy even if GHA is out of minutes.
3. Alternatively: deploy manually via Render Dashboard > Service > Manual Deploy

**Immediate workaround for CF Worker**:
```bash
# Deploy the worker directly from local machine (bypasses GHA entirely)
cd /Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway
wrangler deploy
```

**Resolution for GHA minutes — 5 minutes**:
1. Go to `https://github.com/settings/billing/actions`
2. Purchase additional minutes: click "Add more minutes" or "Buy more"
3. 500 minutes = ~$4 one-time. Purchase immediately.
4. Minutes are available within a few minutes of purchase.

---

## 8. Cost Monitoring and Scale-Up Triggers

This section answers the question: when should you spend more money, and when
should you ride it out?

### 8.1 The Decision Framework

Spend money when:
- A service is actively failing (returning errors to users)
- A service is at > 80% of its hard limit and still growing
- A service failure would cause user data loss or missed revenue

Ride it out when:
- A service is degrading gracefully (slower responses, not errors)
- Traffic is already trending down
- The failure mode is covered by an existing fallback

### 8.2 Service-Specific Scale-Up Triggers

| Service | Current Tier | Cost | Trigger | Next Tier | Cost |
|--|--|--|--|--|--|
| Render | Starter | $7/mo | CPU > 80% for 5+ min OR p95 > 3s | Standard | $25/mo |
| Render | Standard | $25/mo | CPU > 80% on dedicated core | Pro | $85/mo |
| Neon | Free | $0 | Compute hours > 80 h in month OR connection errors | Launch | $19/mo |
| Neon | Launch | $19/mo | Sustained slow queries, storage > 8 GB | Scale | $69/mo |
| CF Worker | Free | $0 | > 80,000 requests/day | Paid | $5/mo |
| Vercel | Free | $0 | > 80 GB bandwidth/month OR > 80K invocations | Pro | $20/mo |
| Composio | Free | $0 | > 800 actions (80% of 1K monthly) | Starter | $29/mo |
| GHA | Free | $0 | > 1,500 min used AND hotfix needed | Paid minutes | $4 one-time |
| Gemini | Free | $0 | > 200 RPD sustained for 3+ days | Pay-as-you-go | Usage-based |

### 8.3 Maximum Spend Scenarios

If the launch goes viral and you trigger all scale-up thresholds simultaneously:

```
Render Standard:     $25/mo
Resend Starter:      $20/mo  (already planned)
Neon Launch:         $19/mo
CF Workers Paid:     $5/mo
Vercel Pro:          $20/mo
Composio Starter:    $29/mo
GHA buffer:          $4 one-time
Gemini usage-based:  ~$5-15/mo (estimated 800 RPD at low token counts)
---
Total emergency:     ~$122-132/mo + $4 one-time
```

This is the "viral PH launch with 2,000+ signups" budget. The base plan of $27/mo
additional cost (Render Starter + Resend Starter) is sufficient for 500 signups.

### 8.4 When NOT to Scale Up

**Do not upgrade Neon during the launch if**:
- You are within the first 8 hours and compute hours are under 10 h
- Latency is acceptable (p95 < 500 ms for DB queries)
- The issue is connection exhaustion, not compute (fix with pooler endpoint instead)

**Do not upgrade Render to Standard if**:
- CPU spike is temporary (< 5 minutes) and has already receded
- The cause was a single large request (ML inference) rather than concurrent load
- Latency is elevated but errors are < 0.5%

**Do not upgrade Vercel if**:
- Bandwidth is under 50 GB (you have 50% headroom)
- The 402 error has not occurred

### 8.5 Post-Launch Cost Review

24 hours after the PH post goes live, review each service and downgrade anything
that was over-provisioned:

- If Render Standard was triggered but traffic has dropped: downgrade to Starter
- If Neon Launch was triggered: keep it for 30 days to cover the post-launch tail
- If Composio Starter was triggered: evaluate monthly action usage before renewing

Typical PH traffic pattern: large spike in first 6 hours, 80% drop by 24 hours,
long tail for 48-72 hours. Most services can be downgraded by Wednesday.

---

## Appendix: Quick Reference Card

Keep this visible during the upgrade window.

```
UPGRADE SEQUENCE (Monday April 13, evening)
==========================================
1. Complete pre-upgrade checklist (Section 1) — ~15 min
2. Render Free → Starter (Section 2) — ~5 min + verify
3. Resend Free → Starter (Section 3) — ~5 min + verify
4. Run full post-upgrade verification suite (Section 4) — ~20 min
5. Sleep. Launch is Tuesday 00:01 PT.

EMERGENCY CONTACTS (during launch)
===================================
Render down:   dashboard.render.com > Logs, then Section 7.2
Neon down:     console.neon.tech > Usage, then Section 7.3
CF errors:     dash.cloudflare.com > Workers > Analytics, then Section 7.4
Email broken:  resend.com/emails, then Section 7.5

KEY ENDPOINTS
=============
Backend health:   https://api.rateshift.app/health
CF health:        https://api.rateshift.app/api/v1/health
Frontend:         https://rateshift.app
Prices (cached):  https://api.rateshift.app/api/v1/prices/current?region=us_ct

RENDER SERVICE ID:    srv-d649uhur433s73d557cg
NEON PROJECT ID:      cold-rice-23455092
NEON POOLER HOST:     ep-withered-morning-pooler.us-east-1.aws.neon.tech
CF ACCOUNT ID:        b41be0d03c76c0b2cc91efccdb7a10df
CF ZONE ID:           ac03dd28616da6d1c4b894c298c1da58
```

---

> Last updated: 2026-04-08
> Author: SRE runbook for RateShift PH launch T-24h upgrade window
> Companion: docs/CAPACITY_AUDIT.md, docs/launch/MONITORING_RUNBOOK.md, docs/SCALING_PLAN.md
