# Automation Workflows — Implementation Plan

> Generated: 2026-03-05
> Status: COMPLETE — Phase 0 DONE, Phase 1 COMPLETE, Phase 2 COMPLETE, Phase 3 COMPLETE, Self-Healing CI/CD COMPLETE
> Source: Multi-agent brainstorming (5 agents: Designer, Skeptic, Constraint Guardian, User Advocate, Arbiter)

## Executive Summary

9 cross-service automation workflows designed using 16 Composio/Rube MCP connections.
7 approved (5 unconditional, 2 conditional), 2 rejected. All 4 prerequisite blockers resolved. All 7 approved workflows implemented and deployed (~27 hours total). Self-Healing CI/CD system added: auto-format, retry-curl, notify-slack, validate-migrations, self-healing-monitor, E2E resilience. 3 items remain for future work: NotificationDispatcher, ML weight persistence, and in-app notifications.

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
- **Action**: Fetches open GitHub issues/PRs via GraphQL → maps labels to priority/category → inserts into Notion Project Tracker database (31bb9fc9-1d9d-81ed-815a-d6fb35ec0d3f)
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

## Phase 2: Core Workflows — COMPLETE ✅ (2026-03-06)

### Infrastructure Changes ✅
- **RequestTimeoutMiddleware**: `/api/v1/internal/` paths now excluded from 30s timeout (Option B implemented)
- **Weather parallelization**: `asyncio.gather()` + `Semaphore(10)` replaces sequential loop (~5x faster for 51 regions)
- **Scrape-rates auto-discovery**: Endpoint now auto-discovers active suppliers with websites when called with empty body

### Workflow 1: Schedule Existing Endpoints ✅
- **Weather**: `.github/workflows/fetch-weather.yml` — every 6 hours, all 51 US regions
- **Market research**: `.github/workflows/market-research.yml` — daily at 2am UTC, top 10 regions
- **Rate scraping**: `.github/workflows/scrape-rates.yml` — daily at 3am UTC, auto-discovers suppliers
- **Status**: GHA files merged to main, schedules active

### Workflow 8: Connection Sync Scheduler ✅
- **Endpoint**: `POST /internal/sync-connections` → calls `ConnectionSyncService.sync_all_due()`
- **GHA**: `.github/workflows/sync-connections.yml` — every 2 hours
- **Tests**: 5 tests (happy path, partial failure, empty, error, auth)

### Workflow 2: Price Alert Loop ✅
- **GHA**: `.github/workflows/check-alerts.yml` — every 15 minutes
- **Endpoint**: `POST /internal/check-alerts` (from B4, already tested with 8 tests)
- **Note**: Currently sends email alerts only. Push (OneSignal) and Slack channels to be added via NotificationDispatcher (Phase 2 enhancement)

---

## Phase 3: Revenue Protection — COMPLETE ✅ (2026-03-06)

### Workflow 3: Stripe Dunning ✅
- **Trigger**: Stripe webhook `invoice.payment_failed` + daily cron escalation
- **Action**: Record failure → 24h cooldown check → send empathetic dunning email (soft < 3 attempts, final >= 3) → escalate to free after 3 failures
- **Migration**: `024_payment_retry_history` — UUID PK, retry tracking, email history, escalation audit
- **Service**: `backend/services/dunning_service.py` — DunningService with record/cooldown/email/escalate/orchestrator methods
- **Templates**: `dunning_soft.html` (amber gradient, "Update Payment Method") + `dunning_final.html` (red gradient, grace period warning, downgrade notice)
- **Endpoint**: `POST /internal/dunning-cycle` — daily at 7am UTC, finds overdue accounts (>7 days), sends final email, downgrades
- **GHA**: `.github/workflows/dunning-cycle.yml` — daily 7am UTC
- **Wiring**: `stripe_service.py` `handle_webhook_event()` now extracts `amount_due`, `currency`, `invoice_id`; `apply_webhook_action()` accepts `db` param and calls `DunningService.handle_payment_failure()`; `billing.py` passes `db` through
- **Tests**: 13 dunning service tests + 4 endpoint tests = 17 tests

### Workflow 6: Nightly KPI Report ✅
- **Trigger**: Cron (daily at 6am UTC)
- **Action**: Aggregate metrics → return JSON (active users 7d, total users, prices tracked, alerts sent today, connection status, subscription breakdown, estimated MRR, data freshness)
- **Service**: `backend/services/kpi_report_service.py` — KPIReportService with `aggregate_metrics()` method, all queries via `sqlalchemy.text()`
- **Endpoint**: `POST /internal/kpi-report` — returns `{status, generated_at, metrics}`
- **GHA**: `.github/workflows/kpi-report.yml` — daily 6am UTC
- **Delivery**: Rube recipe `rcp_wu9mVLIZRM_n` ([view](https://rube.app/recipe-hub/nightly-kpi-report)), scheduled daily 6:05am UTC (schedule ID: `51f1bdd6-b2a3-42a4-b5df-e936637aaf07`). Posts to Slack `#metrics` (C0AKDD7P2HX) + appends to Google Sheet "KPI Dashboard" (`15JGyCAThhP2lUKLvuEsdarRXDBa5TjlWKDwD9mztITA`)
- **Tests**: 7 KPI service tests + 3 endpoint tests = 10 tests

---

## Self-Healing CI/CD System — COMPLETE ✅ (2026-03-06)

Cross-cutting infrastructure upgrade that adds resilience, automatic recovery, and proactive monitoring across all 23 GHA workflows.

### Deliverable 1: CI Auto-Format ✅
- **Modified**: `.github/workflows/ci.yml` — `backend-lint` and `frontend-lint` jobs
- **Behavior**: Runs `black .` + `isort .` in fix mode. If files changed on PR → auto-commit via `github-actions[bot]`. If files changed on push to main → fail (main should be pre-formatted).
- **Safety**: `cancel-in-progress: true` on CI prevents commit loop. `permissions: contents: write` on lint jobs.

### Deliverable 2: Retry-Curl Composite Action ✅
- **Created**: `.github/actions/retry-curl/action.yml`
- **Inputs**: url, method (POST), headers, body ({}), max-retries (3), initial-delay (5s), max-delay (60s), timeout (120s)
- **Logic**: 2xx → success. 4xx (except 429/408) → fail immediately. 5xx/429/408/000 → exponential backoff with jitter, retry.
- **Outputs**: status-code, attempts
- **Applied to**: All 12 cron workflows (check-alerts, fetch-weather, market-research, sync-connections, scrape-rates, dunning-cycle, kpi-report, price-sync, observe-forecasts, nightly-learning, data-retention, data-health-check)

### Deliverable 3: Notify-Slack Composite Action ✅
- **Created**: `.github/actions/notify-slack/action.yml`
- **Inputs**: webhook-url, workflow-name, severity (critical/warning/info), run-url (auto-populated)
- **Severity mapping**: critical → danger color + 🚨, warning → warning color + ⚠️, info → blue + ℹ️
- **Secret**: `SLACK_INCIDENTS_WEBHOOK_URL` (Slack incoming webhook → `#incidents` C0AJPR769H9)
- **Applied to**: All 12 cron workflows + deploy-production rollback

### Deliverable 4: Validate-Migrations Composite Action ✅
- **Created**: `.github/actions/validate-migrations/action.yml`
- **Convention checks**: (1) Sequential numbering (no gaps). (2) `IF NOT EXISTS` on CREATE TABLE. (3) GRANT uses `neondb_owner` role. (4) No SERIAL/BIGSERIAL (UUID PKs only).
- **Added to CI**: `migration-check` job with PostgreSQL 15 service (full SQL application)
- **Added to deploy-production**: `migration-gate` job (convention checks only, no DB)

### Deliverable 5: Self-Healing Monitor ✅
- **Created**: `.github/workflows/self-healing-monitor.yml`
- **Schedule**: Daily 9am UTC (after overnight crons)
- **Logic**: Matrix strategy over 13 monitored workflows. Counts failures in last 24h via `gh run list`. If ≥3 failures → creates GitHub issue with `self-healing` + `automated` labels. If 3 consecutive successes → auto-closes issue.
- **Permissions**: `issues: write`, `actions: read`

### Deliverable 6: E2E Test Resilience ✅
- **Modified**: `.github/workflows/e2e-tests.yml`
- **Changes**: Two-step Playwright install (try → retry with 10s delay). Extended wait-for-service timeout (60s → 120s). After failure → rerun only failed tests with `--last-failed`. `continue-on-error: true` on first run.

### Files Summary
**New (4)**:
- `.github/actions/retry-curl/action.yml` — Curl with exponential backoff
- `.github/actions/notify-slack/action.yml` — Slack failure alerts
- `.github/actions/validate-migrations/action.yml` — Migration convention checks
- `.github/workflows/self-healing-monitor.yml` — Daily failure monitor + auto-issues

**Modified (15)**:
- `.github/workflows/ci.yml` — Auto-format lint, migration-check job
- `.github/workflows/deploy-production.yml` — Migration-gate, Slack rollback alert
- `.github/workflows/e2e-tests.yml` — Retry install, extended waits, rerun failures
- 12 cron workflows — retry-curl + notify-slack added

### New Secrets & Labels
- **Secret**: `SLACK_INCIDENTS_WEBHOOK_URL` — Slack incoming webhook for #incidents channel
- **Labels**: `self-healing`, `automated` — used by self-healing-monitor for issue lifecycle

---

## Phase 4: Deferred / Rejected

### Workflow 7: UptimeRobot Incident Bridge — REJECTED
- **Reason**: Render free tier auto-suspends after 15 minutes of inactivity. UptimeRobot detects auto-suspension as downtime, creating false-positive incidents in Better Stack and noise in Slack.
- **Revisit when**: Project upgrades to paid Render plan (always-on instances)
- **Alternative**: Use Render's built-in health check notifications for now

### Rate Scraping at Full Scale — DEFERRED (UNBLOCKED)
- **Reason**: 37 suppliers × 12s rate limit = 444s minimum. Originally incompatible with middleware + Rube 4-min timeout.
- **Status**: Middleware exclusion for `/api/v1/internal/` is now implemented (Phase 2). Full-scale scraping via GHA cron is now feasible — current `scrape-rates.yml` uses auto-discovery but could be extended to all 37 suppliers since GHA has no 30s timeout.
- **Next step**: Test full 37-supplier run via `workflow_dispatch`, measure duration, adjust if needed

### In-App Notifications — DEFERRED
- **Reason**: No `notifications` table, no WebSocket/SSE channel, no polling endpoint. Users without push/email have zero notification channels.
- **Status**: Phase 2 and 3 workflows are now stable. This is the natural next feature to build.
- **Next step**: Design `notifications` table + SSE/polling endpoint. Build as part of NotificationDispatcher (see Architectural Changes #2).

---

## Architectural Changes Required

### 1. RequestTimeoutMiddleware Exclusion ✅ (2026-03-06)
**File**: `backend/app_factory.py`
**Change**: `TIMEOUT_EXCLUDED_PREFIXES = ("/api/v1/internal/",)` — internal batch jobs bypass 30s timeout.
**Test**: `test_middleware_asgi.py::TestTimeoutASGI::test_internal_paths_excluded_from_timeout`

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

### 4. GitHub Actions Workflow Files ✅ (2026-03-06)
All 12 cron workflows created:
- `check-alerts.yml` (every 15 min) — price alert pipeline
- `fetch-weather.yml` (every 6 hours) — all 51 US regions
- `market-research.yml` (daily 2am UTC) — top 10 regions
- `sync-connections.yml` (every 2 hours) — UtilityAPI sync
- `scrape-rates.yml` (daily 3am UTC) — auto-discover suppliers
- `dunning-cycle.yml` (daily 7am UTC) — overdue payment escalation
- `kpi-report.yml` (daily 6am UTC) — nightly business metrics
- `self-healing-monitor.yml` (daily 9am UTC) — check 13 workflows for failures, auto-manage issues

---

## Implementation Timeline

| Week | Phase | Deliverables | Hours | Status |
|------|-------|-------------|-------|--------|
| 1 | 0 + 1 | 4 blockers fixed + 3 zero-risk workflows live | 12-15h | ✅ DONE |
| 2 | 2 | Scheduled endpoints + connection sync + price alerts | 7-8h | ✅ DONE (code + GHA) |
| 3 | 3 | Stripe dunning + KPI reports live | 5-6h | ✅ DONE |
| 3+ | Self-Healing | Auto-format, retry, notify, validate, monitor, E2E resilience | 6-8h | ✅ DONE |
| Total | | 7 workflows live, 2 deferred | ~33-35h | 7/7 done |

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
- ✅ `.github/workflows/check-alerts.yml` — price alert cron (every 15 min)
- ✅ `.github/workflows/fetch-weather.yml` — weather data cron (every 6h)
- ✅ `.github/workflows/market-research.yml` — market intel cron (daily 2am)
- ✅ `.github/workflows/sync-connections.yml` — connection sync cron (every 2h)
- ✅ `.github/workflows/scrape-rates.yml` — rate scraping cron (daily 3am)
- ✅ `backend/migrations/024_payment_retry_history.sql` — dunning retry tracking table
- ✅ `backend/services/dunning_service.py` — DunningService (record, cooldown, email, escalate)
- ✅ `backend/services/kpi_report_service.py` — KPIReportService (aggregate business metrics)
- ✅ `backend/templates/emails/dunning_soft.html` — soft dunning email (amber, empathetic)
- ✅ `backend/templates/emails/dunning_final.html` — final dunning email (red, grace period warning)
- ✅ `backend/tests/test_dunning_service.py` — 13 dunning service tests
- ✅ `backend/tests/test_kpi_report_service.py` — 7 KPI service tests
- ✅ `.github/workflows/dunning-cycle.yml` — daily 7am UTC dunning cron
- ✅ `.github/workflows/kpi-report.yml` — daily 6am UTC KPI cron
- Pending: `backend/services/notification_dispatcher.py` — centralized notification routing (future)

### Modified Files
- ✅ `backend/app_factory.py` — timeout exclusion for `/api/v1/internal/`
- ✅ `backend/services/stripe_service.py` — fix `payment_failed` handler user_id resolution
- ✅ `backend/services/alert_service.py` — deduplication + frequency enforcement
- ✅ `backend/services/weather_service.py` — parallelize with `asyncio.gather()` + `Semaphore(10)`
- ✅ `backend/api/v1/internal.py` — sync-connections endpoint + scrape-rates auto-discovery
- ✅ `frontend/lib/notifications/onesignal.ts` — `OneSignal.login(userId)` post-auth
- ✅ `frontend/lib/hooks/useAuth.tsx` — trigger OneSignal login/logout

---

## What's Next

All 7 approved workflows are deployed. The remaining work falls into three categories:

### 1. NotificationDispatcher (Architectural Change #2) — HIGH PRIORITY
- **What**: Centralized notification routing with Push (OneSignal) → Email (Resend) → Log fallback chain
- **Why**: Currently alerts only send email. Users with push enabled get no push notifications. Dedup logic would be duplicated if added per-workflow.
- **Effort**: ~4-6 hours
- **File**: `backend/services/notification_dispatcher.py`
- **Dependencies**: None — OneSignal binding (B2) and email (B1) are already working

### 2. ML Weight Persistence (Architectural Change #3) — MEDIUM PRIORITY
- **What**: Persist `LearningService` ensemble weights to PostgreSQL instead of ephemeral Redis
- **Why**: Weights are lost on every restart, silently degrading prediction quality
- **Effort**: ~2-3 hours
- **Approach**: Create `model_config` table with JSON column (Option B — no new infrastructure)
- **Dependencies**: None

### 3. Full-Scale Rate Scraping — LOW PRIORITY
- **What**: Extend `scrape-rates.yml` to run all 37 suppliers (currently auto-discovers subset with websites)
- **Why**: Middleware timeout exclusion is now in place; GHA has no 30s limit
- **Effort**: ~1-2 hours (test full run, adjust concurrency/batching if needed)
- **Dependencies**: None — blocker resolved in Phase 2

### 4. In-App Notifications — LOW PRIORITY
- **What**: `notifications` table + SSE/polling endpoint for users without push/email
- **Why**: Zero notification channels for users who haven't enabled push or provided email
- **Effort**: ~6-8 hours (new feature: schema, API, frontend component)
- **Dependencies**: NotificationDispatcher (#1 above) should be built first

### 5. Custom Email Domain — OPERATIONAL
- **What**: Purchase domain for Resend, configure DKIM/SPF/DMARC, update `EMAIL_FROM_ADDRESS`
- **Why**: Currently using `onboarding@resend.dev` sandbox (only delivers to account email). All email workflows are technically functional but limited to dev delivery.
- **Effort**: ~1 hour (purchase + DNS config) + propagation time
- **Dependencies**: None — purely operational
