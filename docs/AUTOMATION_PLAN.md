# Automation Workflows — Implementation Plan

> Generated: 2026-03-05
> Status: IN_PROGRESS — Phase 0 DONE, Phase 1 COMPLETE, Phase 2 IN PROGRESS
> Source: Multi-agent brainstorming (5 agents: Designer, Skeptic, Constraint Guardian, User Advocate, Arbiter)

## Executive Summary

9 cross-service automation workflows designed using 16 Composio/Rube MCP connections.
7 approved (5 unconditional, 2 conditional), 2 rejected. 4 prerequisite blockers require ~9-11 hours of development before user-facing workflows can ship.

---

## Prerequisite Blockers (Phase 0) — ALL RESOLVED ✅ (2026-03-05)

### B1: Email Delivery ✅
- **Resolution**: Gmail SMTP fallback added (smtp.gmail.com:587, TLS, App Password). `frontend/lib/email/send.ts` uses Resend primary → nodemailer SMTP fallback. Env vars on Render + Vercel.
- **Note**: Resend domain purchase still recommended for production (custom from address, DKIM/SPF/DMARC). Gmail SMTP unblocks all workflows.

### B2: OneSignal User Binding ✅
- **Resolution**: `loginOneSignal(userId)` / `logoutOneSignal()` added to `frontend/lib/notifications/onesignal.ts`, wired in `useAuth.tsx` post-auth. +4 tests.

### B3: Stripe User ID Resolution ✅
- **Resolution**: `get_by_stripe_customer_id()` added to `user_repository.py`. `apply_webhook_action()` in `stripe_service.py` now resolves user for `payment_failed` events. +6 tests.

### B4: Alert System Wiring ✅
- **Resolution**: `POST /internal/check-alerts` endpoint with full pipeline: load configs → fetch prices → check thresholds → dedup (cooldown: immediate=1h, daily=24h, weekly=7d) → send → record. +8 tests.

---

## Phase 1: Zero-Risk Integrations — COMPLETE ✅ (2026-03-06)

All 3 workflows live via Rube recipes. No application code changes required.

### Workflow 4: Sentry-to-Slack Bridge ✅
- **Recipe**: `rcp_sQ1NKouFdXIe` ([view](https://rube.app/recipe-hub/sentry-to-slack-bridge))
- **Schedule**: Every 15 min (`*/15 * * * *`), ID: `2bbd63bd-0a7f-401b-a0e4-12f8d19c873f`
- **Action**: Fetches unresolved Sentry issues → classifies P0/P1 (critical) vs P2/P3 (digest) → posts to Slack `#incidents` (C0AJPR769H9)
- **Tools**: `SENTRY_LIST_AN_ORGANIZATIONS_ISSUES` (with required `start`/`end` params) + `SLACK_SEND_MESSAGE`
- **Test result**: 0 issues found, "All Clear" posted to #incidents

### Workflow 5: Deploy Notifications ✅
- **Recipe**: `rcp_9f8mVE2Z_DSP` ([view](https://rube.app/recipe-hub/deploy-notifications))
- **Schedule**: Every hour (`0 * * * *`), ID: `06777ec8-c936-4a79-941b-36ed57d449e7`
- **Action**: Checks Render backend + frontend status → posts to Slack `#deployments` (C0AJPR7MQV9) → creates Better Stack incident on failures (status page 239822)
- **Tools**: `RENDER_LIST_SERVICES` + `SLACK_SEND_MESSAGE` + `BETTER_STACK_CREATE_STATUS_PAGE_REPORT`
- **Test result**: Backend OK, Frontend OK, no incident created

### Workflow 9: Notion Roadmap Sync ✅
- **Recipe**: `rcp_73Kc9K65YC5T` ([view](https://rube.app/recipe-hub/github-notion-roadmap-sync))
- **Schedule**: Every 6 hours (`0 */6 * * *`), ID: `8bfb807b-64d3-4694-8f12-6f9bdf569d5a`
- **Action**: Fetches open GitHub issues/PRs via GraphQL → maps labels to priority/category → inserts into Notion roadmap database (24bcbe22-37de-449f-b694-3544f0d864e3)
- **Tools**: `GITHUB_RUN_GRAPH_QL_QUERY` + `NOTION_INSERT_ROW_DATABASE`
- **Test result**: 2/2 issues synced, 0/0 PRs synced

### Infrastructure Created
- Slack `#incidents` channel: C0AJPR769H9
- Slack `#deployments` channel: C0AJPR7MQV9
- Rube session: `drew` (16 active Composio connections)

### API Learnings
- Sentry `SENTRY_LIST_AN_ORGANIZATIONS_ISSUES`: `start` and `end` params are REQUIRED; `sort` must be date|freq|inbox|new|trends|user (NOT "priority")
- Slack: Use `SLACK_SEND_MESSAGE` (not `SLACKBOT_SEND_A_MESSAGE_TO_A_SLACK_CHANNEL`); requires channel ID not name
- Notion `NOTION_INSERT_ROW_DATABASE`: `data` dict with property names as keys; select fields need `{"name": "value"}` format
- Notion `NOTION_UPSERT_ROW_DATABASE`: requires `items[]` with `match`/`create.properties`/`update.properties` (complex format)

---

## Phase 2: Core Workflows (Week 2, after Phase 0 blockers resolved)

### Workflow 1: Schedule Existing Endpoints
- **Weather + Market Research**: Schedule `/internal/fetch-weather` and `/internal/market-research` via GitHub Actions cron
  - Weather: every 6 hours. Fix: add `asyncio.gather()` with `Semaphore(10)` to parallelize 51 API calls (currently sequential)
  - Market research: daily at 2am UTC
- **Rate Scraping**: CANNOT use single HTTP call (37 suppliers × 12s = 25+ min, killed by 30s timeout)
  - Fix option A: Batch into groups of 2 suppliers per invocation (stays within 30s), schedule 19 sequential GitHub Actions jobs
  - Fix option B: Extend `RequestTimeoutMiddleware` to exclude `/internal/*` paths, run as single long-running request
  - Fix option C: Extract scraping to standalone script, run via Render cron or GitHub Actions directly
  - **Recommended**: Option B (simplest, one middleware change)
- **Effort**: 3-4 hours
- **Dependencies**: Middleware exclusion for rate scraping

### Workflow 8: Connection Sync Scheduler
- **Trigger**: Cron (every 2 hours)
- **Action**: Call `get_connections_due_for_sync()` → trigger sync for each due connection
- **Implementation**: New `/internal/sync-connections` endpoint + GitHub Actions cron
- **Effort**: 2 hours
- **Dependencies**: None (sync logic fully implemented)

### Workflow 2: Price Alert Loop
- **Trigger**: Cron (every 15 minutes)
- **Action**: `/internal/check-alerts` → check thresholds → deduplicate → notify via push/email/Slack
- **Implementation**: GitHub Actions cron → internal endpoint (from B4)
- **Notification channels**: Push (OneSignal, from B2) → Email (Resend, from B1) → Slack fallback
- **Effort**: 2 hours (after B1, B2, B4 are resolved)
- **Dependencies**: B1, B2, B4

---

## Phase 3: Revenue Protection (Week 3)

### Workflow 3: Stripe Dunning
- **Trigger**: Stripe webhook `invoice.payment_failed`
- **Action**: Resolve user (from B3) → send empathetic dunning email with payment update link → log attempt
- **Email template**: Acknowledge failure without blame, Stripe Customer Portal link, grace period (7 days), escalation after 3 failures
- **Implementation**: Fix `payment_failed` handler (B3) + dunning email template + retry tracking
- **Effort**: 3 hours (after B1, B3)
- **Dependencies**: B1, B3

### Workflow 6: Nightly KPI Report
- **Trigger**: Cron (daily at 6am UTC)
- **Action**: Aggregate metrics (active users, prices tracked, alerts sent, revenue) → append to Google Sheets → post summary to Slack `#metrics`
- **Implementation**: Rube recipe using `GOOGLEDRIVE_*` + `SLACKBOT_*` + backend API calls
- **Effort**: 2-3 hours
- **Dependencies**: Workflows 1, 2 should be running to provide meaningful data

---

## Phase 4: Deferred / Rejected

### Workflow 7: UptimeRobot Incident Bridge — REJECTED
- **Reason**: Render free tier auto-suspends after 15 minutes of inactivity. UptimeRobot detects auto-suspension as downtime, creating false-positive incidents in Better Stack and noise in Slack.
- **Revisit when**: Project upgrades to paid Render plan (always-on instances)
- **Alternative**: Use Render's built-in health check notifications for now

### Rate Scraping at Full Scale — DEFERRED
- **Reason**: 37 suppliers × 12s rate limit = 444s minimum. Incompatible with current middleware + Rube 4-min timeout.
- **Revisit when**: Middleware exclusion for `/internal/*` is implemented (Workflow 1, Option B)

### In-App Notifications — DEFERRED
- **Reason**: No `notifications` table, no WebSocket/SSE channel, no polling endpoint. Users without push/email have zero notification channels.
- **Revisit when**: After Phase 2 workflows are stable. Design as separate feature (notifications table + SSE endpoint).

---

## Architectural Changes Required

### 1. RequestTimeoutMiddleware Exclusion
**File**: `backend/app_factory.py` (line 84)
**Change**: Add path exclusion for `/internal/*` endpoints. Internal batch jobs have fundamentally different latency profiles than user-facing requests.
```python
# Exclude internal endpoints from timeout
TIMEOUT_EXCLUDED_PATHS = ["/internal/", "/prices/stream"]
```

### 2. NotificationDispatcher (New Service)
**Purpose**: Centralized notification routing with deduplication and frequency enforcement
**Channels** (in fallback order): Push (OneSignal) → Email (Resend) → Log (always)
**Features**: Deduplication key, cooldown window, `notification_frequency` enforcement, channel availability check
**File**: `backend/services/notification_dispatcher.py`

### 3. Redis or PostgreSQL Weight Persistence
**Problem**: `LearningService` silently skips Redis writes. Ensemble weights are ephemeral (lost on restart).
**Option A**: Provision Upstash Redis free tier (10K commands/day)
**Option B**: Create `model_config` table with JSON column for weight persistence (aligns with existing Neon architecture)
**Recommended**: Option B (no new infrastructure dependency)

### 4. GitHub Actions Workflow Files
Create `.github/workflows/` cron jobs for:
- `check-alerts.yml` (every 15 min)
- `fetch-weather.yml` (every 6 hours)
- `market-research.yml` (daily 2am UTC)
- `sync-connections.yml` (every 2 hours)
- `scrape-rates.yml` (daily, batched)

---

## Implementation Timeline

| Week | Phase | Deliverables | Hours |
|------|-------|-------------|-------|
| 1 | 0 + 1 | 4 blockers fixed + 3 zero-risk workflows live | 12-15h |
| 2 | 2 | Scheduled endpoints + connection sync + price alerts live | 7-8h |
| 3 | 3 | Stripe dunning + KPI reports live | 5-6h |
| Total | | 7 workflows live, 2 deferred | ~27h |

---

## Decision Log

| Decision | Alternatives Considered | Objections | Resolution |
|----------|------------------------|------------|------------|
| Use GitHub Actions for cron workflows | Rube recipes, Render cron | Rube 4-min timeout, Render cron less flexible | GitHub Actions: free, reliable, no timeout for jobs under 6h |
| Batch rate scraping (2 per call) | Single call + timeout exclusion, external script | 30s middleware kills single call | Middleware exclusion preferred (Option B), batching as fallback |
| Reject UptimeRobot bridge | 15-min alert threshold, paid Render | False positives erode trust in incident system | Rejected until paid Render plan |
| NotificationDispatcher pattern | Per-workflow notification code | Dedup logic would be duplicated across workflows | Centralized dispatcher with fallback chain |
| PostgreSQL for ML weights | Upstash Redis, no persistence | Redis adds infrastructure; no persistence = invisible degradation | PostgreSQL aligns with existing stack, no new dependency |
| Defer in-app notifications | Build now as part of alert system | Scope creep, separate UX concern | Defer to post-Phase 2; push + email sufficient for MVP |
| Domain purchase as P0 | Wait for more users | All email workflows are non-functional without it | P0: blocks 3 of 7 approved workflows |

---

## Monitoring & Success Metrics

After deployment, track:
- **Alert delivery rate**: % of triggered alerts that reach users (target: >95%)
- **Dunning recovery rate**: % of failed payments recovered within 7 days (target: >60%)
- **Data freshness**: Average age of price data (target: <6 hours)
- **False positive rate**: Spurious alerts per week (target: <2)
- **Notification channel coverage**: % of users with at least one working channel (target: >80%)

---

## Files to Create/Modify

### New Files
- `backend/services/notification_dispatcher.py` — centralized notification routing
- `backend/api/v1/internal_alerts.py` — `/internal/check-alerts` endpoint
- `backend/repositories/user_repository_extensions.py` — `get_by_stripe_customer_id()`
- `.github/workflows/check-alerts.yml`
- `.github/workflows/fetch-weather.yml`
- `.github/workflows/market-research.yml`
- `.github/workflows/sync-connections.yml`
- `.github/workflows/scrape-rates.yml`

### Modified Files
- `backend/app_factory.py` — timeout exclusion for `/internal/*`
- `backend/services/stripe_service.py` — fix `payment_failed` handler user_id resolution
- `backend/services/alert_service.py` — deduplication + frequency enforcement in `check_thresholds()`
- `backend/services/weather_service.py` — parallelize with `asyncio.gather()` + `Semaphore(10)`
- `frontend/lib/notifications/onesignal.ts` — add `OneSignal.login(userId)` post-auth
- `frontend/hooks/useAuth.tsx` or auth callback — trigger OneSignal login after auth
