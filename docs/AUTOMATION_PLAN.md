# Automation Workflows — Implementation Plan

> Generated: 2026-03-05
> Status: REVISE (4 prerequisite blockers must be resolved before user-facing workflows go live)
> Source: Multi-agent brainstorming (5 agents: Designer, Skeptic, Constraint Guardian, User Advocate, Arbiter)

## Executive Summary

9 cross-service automation workflows designed using 16 Composio/Rube MCP connections.
7 approved (5 unconditional, 2 conditional), 2 rejected. 4 prerequisite blockers require ~9-11 hours of development before user-facing workflows can ship.

---

## Prerequisite Blockers (Phase 0)

### B1: Resend Domain Verification
- **Problem**: Currently using `onboarding@resend.dev` (Resend sandbox). Can only deliver to account email (`autodailynewsletterintake@gmail.com`). All real users get no emails.
- **Fix**: Purchase domain, verify in Resend (DKIM/SPF/DMARC DNS records), update `EMAIL_FROM_ADDRESS` in Vercel env + `frontend/lib/email/send.ts` + `backend/config/settings.py`
- **Effort**: 2-4 hours
- **Blocks**: Workflows 2, 3, 6

### B2: OneSignal User Binding
- **Problem**: `frontend/lib/notifications/onesignal.ts` calls `OneSignal.init()` but never `OneSignal.login(userId)`. Backend targets pushes via `include_external_user_ids: [user_id]` — but OneSignal has no mapping from user_id to push subscription.
- **Fix**: After successful authentication (post-login), call `OneSignal.login(userId)`. Best location: `useAuth` hook or auth callback.
- **Effort**: 1 hour
- **Blocks**: Workflows 2, 3

### B3: Stripe User ID Resolution
- **Problem**: `stripe_service.py` `payment_failed` handler extracts `customer_id` from invoice but never resolves `user_id`. No `get_by_stripe_customer_id()` method exists in user repository. `apply_webhook_action()` returns `False` because `user_id` is never set.
- **Fix**:
  1. Add `UserRepository.get_by_stripe_customer_id(customer_id: str) -> Optional[User]`
  2. In `payment_failed` handler, resolve user via `stripe_customer_id` column (indexed in migration 004)
  3. Set `result["user_id"]` before returning
- **Effort**: 2 hours
- **Blocks**: Workflow 3

### B4: Alert System Wiring
- **Problem**: `check_thresholds()` and `send_alerts()` exist in `alert_service.py` but are never called from any endpoint. No deduplication — same breach triggers repeated notifications. `notification_frequency` field on user model is never enforced.
- **Fix**:
  1. Create `/internal/check-alerts` endpoint (API-key-protected)
  2. Wire: load active `price_alert_configs` → fetch current prices → `check_thresholds()` → deduplicate against `alert_history` → `send_alerts()` → `record_triggered_alert()`
  3. Implement cooldown: query `alert_history` for recent alerts of same type/region/user. Minimum 1 hour for `immediate`, respect `notification_frequency` otherwise
- **Effort**: 4 hours
- **Blocks**: Workflow 2

---

## Phase 1: Zero-Risk Integrations (Week 1, parallel with Phase 0)

These require no application code changes. Pure external integrations via Composio/Rube recipes.

### Workflow 4: Sentry-to-Slack Bridge
- **Trigger**: Sentry webhook (new error event)
- **Action**: Format error details → post to Slack `#incidents` channel
- **Implementation**: Rube recipe using `SENTRY_*` + `SLACKBOT_SEND_SLACK_MESSAGE`
- **Routing**: P0/P1 errors to `#incidents`, P2/P3 to weekly digest
- **Effort**: 1 hour
- **Risk**: None

### Workflow 5: Deploy Notifications
- **Trigger**: Render/Vercel deploy webhook (status change)
- **Action**: Post deploy status to Slack `#deployments` + update Better Stack
- **Implementation**: Rube recipe using `RENDER_*` + `VERCEL_*` + `SLACKBOT_*` + `BETTER_STACK_*`
- **Effort**: 1-2 hours
- **Risk**: None

### Workflow 9: Notion Roadmap Sync
- **Trigger**: Cron (every 6 hours) or GitHub webhook (project card change)
- **Action**: Sync GitHub Projects #4 board items to Notion roadmap
- **Implementation**: Existing `.claude/hooks/board-sync/` scripts + Rube recipe wrapper
- **Effort**: 1 hour
- **Risk**: None

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
