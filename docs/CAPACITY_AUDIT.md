# RateShift -- Capacity Audit for Product Hunt Launch

> Created: 2026-03-17
> Purpose: Pre-launch capacity analysis for free-tier services
> Assumptions: 500 signups, 2,000 page views, 200 AI queries on launch day

---

## Table of Contents

1. [Service Inventory](#1-service-inventory)
2. [Launch-Day Scenario Modeling](#2-launch-day-scenario-modeling)
3. [Rate Limiting Inventory](#3-rate-limiting-inventory)
4. [Monitoring Dashboard Checklist](#4-monitoring-dashboard-checklist)
5. [Emergency Playbook](#5-emergency-playbook)
6. [Pre-Launch Action Items](#6-pre-launch-action-items)

---

## 1. Service Inventory

### Gemini 3 Flash Preview (AI Agent -- Primary)

| Attribute | Value |
|-----------|-------|
| **Free-tier limit** | 10 RPM / 250 RPD (requests per day) |
| **Current usage** | ~100-200 calls/month (~5-10/day) |
| **Launch-day projection** | 200 AI queries = **200 RPD** (80% of daily limit) |
| **Risk level** | **HIGH** |
| **Degradation behavior** | Returns HTTP 429 / `RESOURCE_EXHAUSTED`. Agent service catches this and falls back to Groq automatically (`agent_service.py` L205-213). Users see slightly different model output but no error. |
| **Monitoring** | Google AI Studio > API Keys > Usage dashboard |
| **Upgrade path** | Gemini API pay-as-you-go: $0.10/1M input tokens, $0.40/1M output tokens. No fixed monthly cost. Enable billing in Google Cloud Console. |

**Key concern**: The 10 RPM limit is the real bottleneck. If 10+ users send AI queries in the same minute, the 11th will trigger fallback to Groq. This is handled gracefully but worth monitoring.

---

### Groq Llama 3.3 70B (AI Agent -- Fallback)

| Attribute | Value |
|-----------|-------|
| **Free-tier limit** | 30 RPM / 14,400 RPD / 6,000 tokens/min |
| **Current usage** | ~50-100 calls/month (fallback only) |
| **Launch-day projection** | ~20-60 calls (Gemini overflow only) |
| **Risk level** | **Low** |
| **Degradation behavior** | If both Gemini and Groq fail, users see "AI service temporarily unavailable. Please try again later." (`agent_service.py` L216-220) |
| **Monitoring** | Groq Console > Usage |
| **Upgrade path** | Groq paid plans start at usage-based pricing. Free tier is very generous (14.4K RPD). |

**Assessment**: Groq's limits are 57x higher than projected fallback volume. No concern.

---

### Composio (AI Agent Tool Actions)

| Attribute | Value |
|-----------|-------|
| **Free-tier limit** | 1,000 actions/month |
| **Current usage** | ~50-200 actions/month |
| **Launch-day projection** | ~200 AI queries x ~1.5 tool calls avg = **~300 actions** (30% of monthly limit in one day) |
| **Risk level** | **Medium** |
| **Degradation behavior** | Tool initialization fails silently (`agent_service.py` L103-105). Agent responds without tool capabilities -- answers are less actionable but still functional. |
| **Monitoring** | Composio Dashboard > Usage |
| **Upgrade path** | Composio Starter: $29/month for 5,000 actions. Growth: $99/month for 25,000. |

**Key concern**: If launch sustains for multiple days at high volume, the 1K/month limit could be hit by day 3-4. Consider upgrading to Starter before launch.

---

### Resend (Transactional Email)

| Attribute | Value |
|-----------|-------|
| **Free-tier limit** | 100 emails/day, 3,000 emails/month |
| **Current usage** | Low volume (~10-20/day) |
| **Launch-day projection** | 500 signups x 1 welcome email + ~100 alert emails = **~600 emails** |
| **Risk level** | **CRITICAL** |
| **Degradation behavior** | Resend returns HTTP 429. Backend falls back to Gmail SMTP (`smtp_host`/`smtp_password` in settings). Gmail SMTP has 500/day sending limit for workspace accounts. Combined: 600 emails/day capacity. |
| **Monitoring** | Resend Dashboard > Emails > Usage |
| **Upgrade path** | Resend Starter: **$20/month** for 50,000 emails/month (no daily cap). Already noted in CLAUDE.md as planned. |

**CRITICAL**: 500 welcome emails alone would hit the 100/day free cap 5x over. **Must upgrade to Resend Starter ($20/mo) before launch.** The Gmail SMTP fallback provides some buffer (500/day) but is not reliable for transactional email at scale.

---

### Neon PostgreSQL (Database)

| Attribute | Value |
|-----------|-------|
| **Free-tier limit** | 100 compute-hours/month, 0.5 GB storage, 0.25 CU, ~10 connections via PgBouncer |
| **Current usage** | ~25 compute-hours/month, ~100 MB storage |
| **Launch-day projection** | Sustained traffic for 12-16h = ~16h compute. Month projection with sustained post-launch: ~60-80h |
| **Risk level** | **Medium** |
| **Degradation behavior** | When compute hours exhausted, Neon suspends the database. All API calls return 500 errors. Frontend circuit breaker activates for public endpoints. |
| **Monitoring** | Neon Console > Project `cold-rice-23455092` > Usage tab |
| **Upgrade path** | Neon Launch: **$19/month** for 300 compute-hours, 10 GB storage, 1 CU. |

**Key concern**: The DB connection pool (`pool_size=5, max_overflow=10` = 15 max connections) will be the real limit under concurrent load. At 50+ concurrent users, connection exhaustion is possible. Connection pooling via Neon PgBouncer helps but 0.25 CU will be slow under load.

---

### Cloudflare Workers (API Gateway)

| Attribute | Value |
|-----------|-------|
| **Free-tier limit** | 100,000 requests/day, 10ms CPU time/invocation |
| **Current usage** | Well within limits (~1,000-5,000 req/day estimated) |
| **Launch-day projection** | 2,000 page views x ~5 API calls/page = ~10,000 requests. Plus bots/crawlers: ~15,000 total |
| **Risk level** | **Low** |
| **Degradation behavior** | CF returns 1015 "Worker exceeded request limit" error. Frontend receives 502/503 and circuit breaker activates, falling back to direct Render URL for public endpoints. |
| **Monitoring** | CF Dashboard > Workers & Pages > `rateshift-api-gateway` > Analytics |
| **Upgrade path** | Workers Paid: $5/month for 10M requests/month. Pay-as-you-go beyond that. |

**Assessment**: 15K requests is 15% of the 100K daily limit. Even a 10x viral scenario (150K) would only slightly exceed. The 2-tier caching (Cache API + KV) reduces origin hits significantly.

---

### GitHub Actions (CI/CD + Cron Jobs)

| Attribute | Value |
|-----------|-------|
| **Free-tier limit** | 2,000 minutes/month (Linux runners) |
| **Current usage** | ~2,243 min/month (already ~243 min over free tier) |
| **Launch-day projection** | Additional CI runs from hotfixes: +50-100 min. Post-launch crons unchanged. |
| **Risk level** | **HIGH** |
| **Degradation behavior** | Workflows queue but do not execute. Cron jobs stop firing (check-alerts, fetch-weather, sync-connections). CI/CD stops -- cannot deploy hotfixes. |
| **Monitoring** | GitHub > Settings > Billing > Actions |
| **Upgrade path** | GitHub Team: $4/user/month for 3,000 min. Or self-hosted runner (Oracle Cloud free ARM instance) for unlimited minutes at $0. |

**CRITICAL for launch**: If GHA minutes are exhausted mid-launch, you cannot deploy hotfixes. Cron jobs also stop. **Check current month usage before launch day. Consider purchasing additional minutes ($0.008/min) as a buffer.** Note: `check-alerts` already migrated to CF Worker Cron Trigger, reducing GHA load.

---

### Vercel (Frontend Hosting)

| Attribute | Value |
|-----------|-------|
| **Free-tier limit** | 100 GB bandwidth/month, 6,000 build minutes/month, 100K serverless function invocations/month, 10s function duration |
| **Current usage** | Well within all limits |
| **Launch-day projection** | 2,000 page views = ~1-2 GB bandwidth (CDN-cached). ~2,000 ISR revalidations. |
| **Risk level** | **Low** |
| **Degradation behavior** | Bandwidth exceeded: site returns 402 payment required. Build minutes exceeded: deployments fail. Serverless exceeded: API routes (auth) return 502. |
| **Monitoring** | Vercel Dashboard > Usage |
| **Upgrade path** | Vercel Pro: $20/month for 1 TB bandwidth, 24,000 build min, 1M invocations. |

**Assessment**: Even in a viral scenario, Vercel's CDN handles static assets efficiently. The `output: 'standalone'` mode and ISR (153 cached pages) minimize serverless invocations. Auth routes (`/api/auth/*`) are the main serverless consumers.

---

### Render (Backend Hosting)

| Attribute | Value |
|-----------|-------|
| **Free-tier limit** | 750 hours/month, 512 MB RAM, 0.5 CPU (shared), auto-sleeps after 15 min idle |
| **Current usage** | Kept warm via cron wakeups. Single worker. |
| **Launch-day projection** | Sustained load for 12-16h. Cold starts between traffic bursts: 20-30s per cold start. |
| **Risk level** | **CRITICAL** |
| **Degradation behavior** | Cold starts cause 20-30s timeout for the first request after 15 min idle. Users see loading spinner then potential timeout error. Under sustained load, 512 MB RAM and 0.5 CPU will bottleneck at ~50 req/s. |
| **Monitoring** | Render Dashboard > Service > Metrics (CPU, Memory, Request latency) |
| **Upgrade path** | Render Starter: **$7/month** -- eliminates auto-sleep, same specs. Standard: $25/month for 2 GB RAM, 1 dedicated CPU. |

**CRITICAL**: Cold starts will make the Product Hunt experience terrible. First-time visitors hitting a sleeping backend will wait 20-30s. **Must upgrade to Render Starter ($7/mo) before launch.** This is the single highest-impact pre-launch upgrade.

---

### Risk Summary

| Service | Risk | Daily Limit | Launch Projection | Headroom |
|---------|------|------------|-------------------|----------|
| Render | **CRITICAL** | N/A (cold starts) | Sustained load | **None -- upgrade required** |
| Resend | **CRITICAL** | 100 emails/day | ~600 emails | **-500 -- upgrade required** |
| Gemini 3 Flash | HIGH | 250 RPD | 200 RPD | 20% |
| GitHub Actions | HIGH | ~67 min/day avg | ~75 min/day | -12% (already over) |
| Neon PostgreSQL | Medium | ~3.3h compute/day avg | ~16h burst | OK for one day, risk for month |
| Composio | Medium | ~33 actions/day avg | ~300 actions | -800% daily, 70% monthly |
| Cloudflare Workers | Low | 100K req/day | ~15K req | 85% |
| Groq | Low | 14,400 RPD | ~60 | 99.6% |
| Vercel | Low | 100 GB/month | ~2 GB | 98% |

---

## 2. Launch-Day Scenario Modeling

### Scenario A: Conservative (100 signups)

| Metric | Value |
|--------|-------|
| Signups | 100 |
| Page views | 400 |
| AI queries | 40 |
| Emails sent | ~120 (100 welcome + 20 alerts) |

| Service | Usage | Limit | Status |
|---------|-------|-------|--------|
| Gemini | 40 RPD | 250 | OK |
| Groq | ~5 fallback | 14,400 | OK |
| Composio | ~60 actions | 1,000/mo | OK |
| Resend | 120/day | 100/day | **OVER** (Gmail fallback covers) |
| Neon | ~4h compute | 3.3h avg/day | Slightly elevated |
| CF Workers | ~3K req | 100K | OK |
| Render | Sustained 4-6h | N/A | OK if upgraded from Free |
| Vercel | ~0.4 GB | 100 GB/mo | OK |

**Verdict**: Manageable with Render Starter upgrade. Resend slightly over daily free cap but Gmail SMTP fallback absorbs it.

---

### Scenario B: Moderate (500 signups) -- Base Case

| Metric | Value |
|--------|-------|
| Signups | 500 |
| Page views | 2,000 |
| AI queries | 200 |
| Emails sent | ~600 (500 welcome + 100 alerts) |

| Service | Usage | Limit | Status |
|---------|-------|-------|--------|
| Gemini | 200 RPD (peak ~15 RPM) | 250 RPD / 10 RPM | **RPM exceeded** (Groq fallback) |
| Groq | ~50 fallback | 14,400 | OK |
| Composio | ~300 actions | 1,000/mo | 30% monthly budget in 1 day |
| Resend | 600/day | 100/day | **6x OVER** -- upgrade required |
| Neon | ~16h compute | 3.3h avg/day | OK for day, watch monthly |
| CF Workers | ~15K req | 100K | OK |
| Render | Sustained 12-16h | N/A | Must be Starter tier |
| Vercel | ~2 GB | 100 GB/mo | OK |

**Verdict**: Requires Render Starter ($7) and Resend Starter ($20) upgrades. Gemini RPM will trigger Groq fallback during peak minutes -- acceptable. Watch Composio monthly budget.

---

### Scenario C: Viral (2,000+ signups)

| Metric | Value |
|--------|-------|
| Signups | 2,000+ |
| Page views | 10,000+ |
| AI queries | 800+ |
| Emails sent | ~2,200+ (2,000 welcome + 200 alerts) |

| Service | Usage | Limit | Status |
|---------|-------|-------|--------|
| Gemini | 800+ RPD | 250 RPD | **3x OVER** -- heavy Groq fallback |
| Groq | ~550+ fallback | 14,400 | OK (3.8%) |
| Composio | ~1,200 actions | 1,000/mo | **OVER** -- tools degrade |
| Resend | 2,200+/day | 50K/mo (Starter) | OK with Starter plan |
| Neon | ~20h+ compute, 50+ concurrent | 100h/mo, 8 conns | **Connection exhaustion likely** |
| CF Workers | ~75K req | 100K | 75% -- approaching limit |
| Render (Starter) | 512 MB / 0.5 CPU saturated | N/A | **Performance degradation** |
| Vercel | ~10 GB | 100 GB/mo | OK |
| GHA | Cannot afford any downtime | 2K min/mo | **Already over budget** |

**Verdict**: Multiple services under stress. Immediate actions needed:

1. **Render Standard ($25/mo)** -- 2 GB RAM, dedicated CPU
2. **Neon Launch ($19/mo)** -- 300h compute, more connections
3. **Composio Starter ($29/mo)** -- 5,000 actions
4. **Consider**: Gemini pay-as-you-go billing, GHA paid minutes

**Total emergency upgrade cost for viral scenario: ~$100/month**

---

## 3. Rate Limiting Inventory

### Layer 1: Cloudflare Worker (Edge)

Source: `workers/api-gateway/wrangler.toml` and `src/config.ts`

| Tier | Limit | Period | Applied To |
|------|-------|--------|-----------|
| **Standard** | 120 req/min per IP | 60s | Most API routes (prices, suppliers, dashboard) |
| **Strict** | 30 req/min per IP | 60s | Auth endpoints (`/api/v1/auth/*`), feedback, price refresh |
| **Internal** | 600 req/min per IP | 60s | Internal endpoints (`/api/v1/internal/*`) -- requires API key |
| **Bypass** | Unlimited | N/A | Webhooks (`/api/v1/webhooks/*`), health checks |

Implementation: Native CF rate limiting bindings (in-memory at edge PoP, zero KV cost). Fails open on binding error.

### Layer 2: Backend Middleware (Application)

Source: `backend/middleware/rate_limiter.py` and `backend/config/settings.py`

| Limit | Default | Scope | Storage |
|-------|---------|-------|---------|
| **Requests/minute** | 100/min per user/IP | All HTTP routes (except `/health`, `/metrics`) | Redis (atomic Lua sliding window) or in-memory fallback |
| **Requests/hour** | 1,000/hour per user/IP | All HTTP routes | Same |
| **Login attempts** | 5 attempts, 15 min lockout | Auth endpoints | Same |

### Layer 3: Application-Level Limits

| Limit | Value | Scope | Source |
|-------|-------|-------|--------|
| **AI Agent (Free tier)** | 3 queries/day per user | `/agent/query`, `/agent/task` | `settings.agent_free_daily_limit` |
| **AI Agent (Pro tier)** | 20 queries/day per user | Same | `settings.agent_pro_daily_limit` |
| **AI Agent (Business)** | Unlimited | Same | Hardcoded in `agent_service.py` |
| **Community posts** | 10 posts/hour per user | `/community/posts` | `community_service.POSTS_PER_HOUR_LIMIT` |
| **Community reports** | 5 unique reporters auto-hides | Report threshold | `community_service.REPORT_HIDE_THRESHOLD` |
| **Prompt length** | 2,000 characters max | AI agent | `agent_service.MAX_PROMPT_LENGTH` |
| **Query timeout** | 120 seconds | AI agent | `agent_service.QUERY_TIMEOUT_SECONDS` |
| **Moderation timeout** | 5 seconds | Community AI moderation | `community_service.MODERATION_TIMEOUT_SECONDS` |
| **Alerts (free tier)** | 1 alert limit | Alert creation | Tier gating via `require_tier` |

### Launch-Day Rate Limit Capacity

For 500 concurrent users browsing the dashboard:

- **CF Worker Standard**: 120 req/min per IP -- no concern for individual users. Aggregate capacity: effectively unlimited (per-IP, not global).
- **Backend middleware**: 100 req/min per user -- single user cannot overload the backend.
- **AI Agent**: 500 free users x 3 queries/day = 1,500 max agent queries/day. But Gemini limit is 250 RPD. **Mismatch**: user-level limits allow more total queries than the upstream API can handle. Groq fallback absorbs overflow.

---

## 4. Monitoring Dashboard Checklist

Check these dashboards during launch. Bookmark all URLs in advance.

| Service | Where to Check | What to Watch | Alert Threshold |
|---------|---------------|---------------|-----------------|
| **Render** | `dashboard.render.com` > Service metrics | CPU%, Memory%, Request latency, Error rate | CPU > 80%, Memory > 450 MB, p95 > 2s |
| **Neon** | `console.neon.tech` > Project `cold-rice-23455092` > Usage | Compute hours consumed, Active connections, Query latency | Connections > 6, Compute > 5h in first 6h |
| **Cloudflare Workers** | CF Dashboard > Workers > `rateshift-api-gateway` > Analytics | Requests/day, Error rate, CPU time | Errors > 1%, Requests > 50K |
| **Gemini API** | `aistudio.google.com` > API Keys > Usage | RPM, RPD, Error rate | RPD > 200, Errors > 5% |
| **Groq** | `console.groq.com` > Usage | Request count, Token usage | Unexpected spike (means Gemini is down) |
| **Composio** | Composio Dashboard > Usage | Actions consumed this month | Actions > 500 (50% monthly budget) |
| **Resend** | `resend.com/emails` > Analytics | Emails sent today, Bounce rate | Sent > 80% of plan limit |
| **Vercel** | Vercel Dashboard > Usage | Bandwidth, Serverless invocations, Build min | Bandwidth > 10 GB, Invocations > 50K |
| **GitHub Actions** | Repo > Settings > Billing > Actions | Minutes used this month | > 1,800 min (90% of free tier) |
| **Sentry** | `sentry.io` > Settings > Subscription | Error events this month | > 2,500 (50% of 5K free tier) |
| **UptimeRobot** | `uptimerobot.com` > Dashboard | Backend, Frontend, CF Worker status | Any monitor DOWN |
| **Grafana Cloud** | Grafana > Explore > Tempo | Trace volume, Error spans, p95 latency | Error rate > 5% |

### Real-Time Monitoring Script

Run this during launch to poll key metrics:

```bash
# Quick health check (run every 5 min during launch)
curl -s https://api.rateshift.app/health | jq .
curl -s https://rateshift.app/api/v1/health | jq .
```

---

## 5. Emergency Playbook

### CRITICAL: Render Cold Starts / Performance Degradation

**Symptoms**: Users report 20-30s load times, timeout errors, high bounce rate.

**Immediate actions**:
1. Upgrade to Render Starter ($7/mo) in Render Dashboard > Service > Settings > Instance Type
2. Service restarts automatically (30s downtime)
3. Verify health check passes: `curl https://api.rateshift.app/health`
4. If still slow under load, upgrade to Standard ($25/mo) for 2 GB RAM + dedicated CPU

**Prevention**: Upgrade to Starter **before** launch (see Pre-Launch Action Items).

---

### CRITICAL: Resend Email Limit Exhausted

**Symptoms**: Welcome emails not arriving, Sentry errors for `resend.emails.send`, 429 responses from Resend API.

**Immediate actions**:
1. Check Resend Dashboard for current daily/monthly usage
2. If on Free tier: upgrade to Starter ($20/mo) immediately at `resend.com/settings/billing`
3. Verify Gmail SMTP fallback is active -- check backend logs for `email_sent_via_smtp`
4. If both fail: temporarily disable welcome emails (set `RESEND_API_KEY=""` to force SMTP-only)

**Prevention**: Upgrade to Resend Starter **before** launch.

---

### HIGH: Gemini API Rate Limited (10 RPM / 250 RPD)

**Symptoms**: Agent responses slower than usual (Groq is ~2x slower than Gemini). Backend logs show `gemini_rate_limited_falling_back_to_groq`.

**Immediate actions**:
1. This is **handled automatically** -- Groq fallback activates on 429/RESOURCE_EXHAUSTED
2. Monitor Groq usage to ensure fallback is not also exhausting
3. If both providers fail: the agent returns "AI service temporarily unavailable" gracefully
4. To increase capacity: enable Gemini pay-as-you-go billing in Google Cloud Console

**Acceptance**: This is expected behavior under load. No user-visible errors unless both providers fail simultaneously.

---

### HIGH: GitHub Actions Minutes Exhausted

**Symptoms**: Workflows show "Queued" but never start. Cron jobs stop running. Cannot deploy.

**Immediate actions**:
1. Check billing: `github.com/JoeyJoziah/electricity-optimizer/settings/billing`
2. Purchase additional minutes: $0.008/min (Linux), buy 500 min block = $4
3. Critical: `check-alerts` is on CF Worker Cron Trigger (unaffected). But `fetch-weather`, `sync-connections`, `daily-data-pipeline` will stop.
4. For emergency deploys: deploy manually via `wrangler deploy` (CF Worker) or Render auto-deploy from git push (uses Render's build minutes, not GHA)

**Prevention**: Check GHA minutes 3 days before launch. Purchase buffer if above 1,500 min used.

---

### MEDIUM: Neon Compute Hours Exhausted

**Symptoms**: All API calls return 500 errors. Database connection errors in logs.

**Immediate actions**:
1. Check Neon Console > Usage for compute hours consumed
2. Upgrade to Neon Launch ($19/mo) -- takes effect immediately, no downtime
3. If near end of month: compute hours reset on billing cycle date (not calendar month)

**Prevention**: Monitor compute hours daily during launch week.

---

### MEDIUM: Composio Actions Exhausted

**Symptoms**: Agent responses lack tool-powered data (no email sending, no Sheets export). Backend logs show `composio_init_failed` or tool call errors.

**Immediate actions**:
1. Agent continues working without tools -- just no action execution
2. Upgrade to Composio Starter ($29/mo) in Composio Dashboard
3. Alternatively: temporarily disable Composio by clearing `COMPOSIO_API_KEY` env var (agent will answer questions but cannot execute actions)

---

### LOW: Cloudflare Workers Request Limit

**Symptoms**: Users see 1015 errors. Frontend circuit breaker activates and falls back to direct Render URL.

**Immediate actions**:
1. The circuit breaker handles this automatically for public endpoints
2. If sustained: upgrade to Workers Paid ($5/mo) for 10M requests/month
3. Check for bot traffic in CF Analytics -- enable Bot Management if needed

---

## 6. Pre-Launch Action Items

### Must-Do (before Product Hunt post goes live)

| Priority | Action | Cost | Time |
|----------|--------|------|------|
| **P0** | Upgrade Render to Starter | $7/mo | 2 min (dashboard toggle) |
| **P0** | Upgrade Resend to Starter | $20/mo | 5 min (billing page) |
| **P0** | Check GHA minutes remaining -- buy buffer if > 1,500 used | $4 one-time | 2 min |
| **P0** | Bookmark all monitoring dashboards (Section 4) | $0 | 10 min |
| **P1** | Pre-warm Render backend with 10 requests | $0 | 1 min |
| **P1** | Verify Gmail SMTP fallback credentials are current | $0 | 5 min |
| **P1** | Test AI agent end-to-end (verify Gemini + Groq + Composio) | $0 | 5 min |

### Should-Do (if time permits)

| Priority | Action | Cost | Time |
|----------|--------|------|------|
| **P2** | Upgrade Neon to Launch plan | $19/mo | 2 min |
| **P2** | Run load test: `k6 run --env SCENARIO=smoke scripts/load_test.js` | $0 | 15 min |
| **P2** | Set up a Slack alert for Sentry error spikes | $0 | 10 min |
| **P2** | Enable Gemini pay-as-you-go billing (removes 250 RPD cap) | Usage-based | 10 min |
| **P3** | Upgrade Composio to Starter plan | $29/mo | 2 min |

### Total Pre-Launch Upgrade Budget

| Scenario | Monthly Cost |
|----------|-------------|
| **Minimum viable** (Render Starter + Resend Starter) | **$27/mo** |
| **Comfortable** (+ Neon Launch) | **$46/mo** |
| **Full coverage** (+ Composio Starter + GHA buffer) | **$79/mo + $4 one-time** |

---

**Last Updated**: 2026-03-17
