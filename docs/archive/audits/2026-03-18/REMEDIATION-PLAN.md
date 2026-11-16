# RateShift Audit Remediation Plan — 2026-03-18

**Source**: 20-agent audit sweep, 568 findings (51 P0, 143 P1, 195 P2, 179 P3)
**Target**: Reduce P0 to 0, P1 to <20, within 4 sprints (24 days)
**Approach**: Grouped by risk cluster, not by agent report. Dependencies mapped.

---

## Sprint 0: IMMEDIATE (Day 1 — before any other work)

### Task 0.1: Fix Timing-Unsafe Secret Comparisons
**Files**: `backend/app_factory.py:519`, `workers/api-gateway/src/middleware/rate-limiter.ts:26`
**Reports**: 11-P0-01, 11-P0-02
**Action**:
- Replace `api_key != settings.internal_api_key` with `hmac.compare_digest(api_key.encode(), settings.internal_api_key.encode())`
- Add fail-closed guard: `if not settings.internal_api_key: return JSONResponse(status_code=503, ...)`
- Replace `bypassKey === env.RATE_LIMIT_BYPASS_KEY` with `timingSafeEqual()` (already imported in adjacent file)
**Tests**: Add timing-safe comparison test cases to `test_app_factory.py` and `rate-limiter.test.ts`
**Effort**: 1 hour
**Blocks**: Nothing (independent fix)

### Task 0.2: Rotate Secrets and Delete `backend/.env`
**Files**: `backend/.env` (disk only, not tracked)
**Reports**: 18-P0-01
**Action**:
1. Run `git log --all --oneline -- backend/.env` to confirm never committed
2. Rotate all 4 secrets on Render dashboard: REDIS_URL, JWT_SECRET, INTERNAL_API_KEY, FIELD_ENCRYPTION_KEY
3. For FIELD_ENCRYPTION_KEY rotation: run re-encryption migration on Neon (decrypt with old key, encrypt with new key)
4. Update 1Password vault with new values
5. Delete `backend/.env` from disk
6. Add explicit `.gitignore` entry: `backend/.env`
**Effort**: 2 hours (mostly FIELD_ENCRYPTION_KEY rotation)
**Blocks**: Task 0.1 (must update INTERNAL_API_KEY after rotation)

### Task 0.3: Fix Bandit CI Gate
**Files**: `ci.yml:300-307`
**Reports**: 20-P0-04
**Action**: Remove the `|| { echo "::warning::..." }` error swallowing. Let Bandit non-zero exit fail the job.
```yaml
# Before
bandit -r . -f json -o ../bandit-report.json -ll --severity-level high || {
  echo "::warning::Bandit found high-severity issues"
}
# After
bandit -r . -f json -o ../bandit-report.json -ll --severity-level high
```
**Effort**: 15 minutes
**Blocks**: May need to fix existing Bandit findings first (check current count)

---

## Sprint 1: Infrastructure & Billing Correctness (Days 2-7)

### Task 1.1: Consolidate Dockerfiles — Switch to `backend/Dockerfile`
**Files**: `render.yaml:5`, `Dockerfile`, `backend/Dockerfile`
**Reports**: 20-P0-02, 19-P0-01
**Action**:
- Update `render.yaml` dockerfilePath to `backend/Dockerfile` with `dockerContext: ./backend`
- Set workers to 2 (not 4) for 512MB Render free tier (~240MB each with `--preload`)
- Verify `backend/Dockerfile` production stage builds correctly from root context
- Delete root `Dockerfile` or rename to `Dockerfile.dev`
**Tests**: Local `docker build` + `docker run` smoke test
**Effort**: 2 hours
**Blocks**: Nothing

### Task 1.2: Fix Broken Database Indexes (Migration 054)
**Files**: New file `backend/migrations/054_fix_broken_indexes.sql`
**Reports**: 12-P0-01, 12-P0-02
**Action**:
```sql
-- Drop invalid index on bill_uploads (references non-existent 'status' column)
DROP INDEX IF EXISTS idx_bill_uploads_user_status;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bill_uploads_user_parse_status
    ON bill_uploads (user_id, created_at DESC, parse_status);

-- Drop invalid index on forecast_observations (references non-existent 'utility_type')
DROP INDEX IF EXISTS idx_forecast_observations_region;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_forecast_observations_region_hour
    ON forecast_observations (region, forecast_hour, created_at DESC);
```
**Tests**: Run against Neon `vercel-dev` branch first
**Effort**: 1 hour
**Blocks**: Nothing

### Task 1.3: Implement Webhook Event Idempotency
**Files**: `backend/api/v1/billing.py`, `backend/services/stripe_service.py`, new migration 055
**Reports**: 14-P0-02
**Action**:
- Create `stripe_processed_events` table with `event_id VARCHAR(255) PRIMARY KEY, processed_at TIMESTAMP`
- In webhook handler: `INSERT INTO stripe_processed_events (event_id) VALUES ($1) ON CONFLICT DO NOTHING RETURNING event_id`
- If no row returned, event already processed — return 200 immediately
- Add TTL cleanup: delete events older than 72 hours in `db-maintenance.yml`
**Tests**: Add idempotency test to `test_api_billing.py`
**Effort**: 3 hours
**Blocks**: Nothing

### Task 1.4: Wire `invalidate_tier_cache()` Into Webhook Flow
**Files**: `backend/services/stripe_service.py` (apply_webhook_action)
**Reports**: 14-P0-01, 15-P1-01
**Action**:
- Import `invalidate_tier_cache` from `backend/api/dependencies.py`
- Call `await invalidate_tier_cache(user_id)` after every `subscription_tier` update in `apply_webhook_action()`
- Call in all 3 action methods: `activate_subscription`, `update_subscription`, `deactivate_subscription`
**Tests**: Add cache invalidation assertions to `test_stripe_service.py`
**Effort**: 1 hour
**Blocks**: Nothing

### Task 1.5: Fix Floating-Point Currency
**Files**: `backend/services/stripe_service.py:474`, `backend/services/dunning_service.py`
**Reports**: 14-P0-03
**Action**:
- Replace `amount_due / 100.0` with `Decimal(str(amount_due)) / Decimal("100")`
- Change `amount_owed` type from `Optional[float]` to `Optional[Decimal]`
- Ensure Decimal serializes correctly in email templates (use `f"{amount:.2f}"`)
**Tests**: Add edge-case amounts ($0.10, $0.30) to `test_dunning_service.py`
**Effort**: 2 hours
**Blocks**: Nothing

### Task 1.6: Fix Metrics Endpoint Auth Bypass
**Files**: `backend/app_factory.py:519`
**Reports**: 11-P0-01 (secondary fix — fail-closed when unconfigured)
**Action**: Already covered in Task 0.1 but needs additional validation:
- When `settings.internal_api_key` is empty/None, return 503 (not silently allow access)
- Add test case for unconfigured key scenario
**Effort**: 30 minutes (part of Task 0.1)

### Task 1.7: Database Backup Automation
**Files**: New `.github/workflows/db-backup.yml`
**Reports**: 20-P0-03
**Action**:
- Weekly GHA workflow: `pg_dump` Neon direct endpoint → upload to Cloudflare R2
- Use `neonctl` CLI for branch-based backup: `neonctl branches create --name backup-$(date +%Y%m%d)`
- Verify backup by restoring to ephemeral branch and checking table counts
- Document RTO/RPO in `docs/DISASTER_RECOVERY.md`
**Effort**: 3 hours
**Blocks**: R2 bucket setup (free tier)

### Task 1.8: Docker Image Digest Pinning
**Files**: All 4 Dockerfiles, `docker-compose.yml`
**Reports**: 20-P0-01
**Action**:
- Get current digests: `docker buildx imagetools inspect python:3.12-slim --format '{{.Manifest.Digest}}'`
- Pin all 6 `FROM` directives with `@sha256:...`
- Add `docker` ecosystem to `.github/dependabot.yml` for automated digest updates
- Pin `docker-compose.yml` service images (`prom/prometheus`, `grafana/grafana`, `redis_exporter`)
**Effort**: 1 hour
**Blocks**: Nothing

---

## Sprint 2: ML Pipeline Overhaul + Frontend Bug Fixes (Days 8-13)

### Task 2.1: Fix ML Data Leakage — Scaler + Fill
**Files**: `ml/data/feature_engineering.py`, `ml/training/train_forecaster.py`
**Reports**: 13-P0-ML-01, 13-P0-ML-02
**Action**:
1. Split raw DataFrame before calling `fit()`:
   ```python
   split_idx = int(len(df) * 0.7)
   df_train = df.iloc[:split_idx]
   feature_engine.fit(df_train)
   df_all = feature_engine.transform(df)
   ```
2. Replace `.ffill().bfill()` with per-split fill:
   ```python
   df_train = df_train.ffill().bfill()
   df_val = df_val.ffill()  # forward-fill only from training tail
   df_test = df_test.ffill()  # forward-fill only from val tail
   ```
**Tests**: Add leakage detection test (verify scaler mean/std computed from train only)
**Effort**: 4 hours
**Blocks**: Nothing

### Task 2.2: Fix Multi-Step Inference Strategy
**Files**: `ml/inference/predictor.py:299-319`
**Reports**: 13-P0-ML-03
**Action**:
- Replace recursive strategy with direct (MIMO) approach: train H separate models for H horizon steps
- Or: implement proper feature propagation — update temporal features (hour, day_of_week) for each step
- Remove hardcoded column[0] assumption; use named feature columns
**Tests**: Validate multi-step predictions against known time series
**Effort**: 8 hours
**Blocks**: Task 2.1 (need correct training data first)

### Task 2.3: Fix Confidence Intervals
**Files**: `ml/training/cnn_lstm_trainer.py:104-110`
**Reports**: 13-P0-ML-05
**Action**:
- Replace `target ± 10%` with quantile regression (predict 10th/90th percentile)
- Or: implement conformal prediction for distribution-free intervals
- Label the intervals honestly in the API response
**Tests**: Verify coverage (should contain ~80% of actuals at 80% CI)
**Effort**: 6 hours
**Blocks**: Task 2.1

### Task 2.4: Fix torch.load Security
**Files**: `ml/inference/predictor.py:138-144`
**Reports**: 13-P0-ML-04
**Action**:
- Set `weights_only=True` and explicitly list allowed classes via `torch.serialization.add_safe_globals()`
- Or: switch to `safetensors` format for model storage
- Remove `# noqa: S614` suppression
- Make hash verification fail-closed (reject on hash mismatch, not just warn)
**Tests**: Add test for loading tampered model file
**Effort**: 3 hours
**Blocks**: Nothing

### Task 2.5: Fix Ensemble Weight Keys + Country Code
**Files**: `ml/services/learning_service.py:147-154`, `ml/data/feature_engineering.py:55,88`
**Reports**: 13-P1-ML-01, 13-P1-ML-07
**Action**:
- Change weight storage keys from version strings to component names ("cnn_lstm", "xgboost", "lightgbm")
- Set default country code to "US" in FeatureConfig and Engine defaults
- Add US holiday calendar
**Tests**: Verify adaptive learning updates correct weights after nightly run
**Effort**: 3 hours
**Blocks**: Nothing

### Task 2.6: Fix Frontend Data Bugs
**Files**: Multiple frontend files
**Reports**: 17-BUG-003, 17-BUG-006, 17-BUG-008, 17-BUG-013, 17-BUG-015
**Action**:
- Replace `Date.now().toString()` with `crypto.randomUUID()` in PricesContent.tsx:47, optimize/page.tsx:99,119
- Add null guard before `parseFloat()` in DashboardContent.tsx:106
- Fix `int(0.25)` → use `max(1, round(duration_hours))` or float in recommendations.py:58
- Fix array-index-as-hour in DashboardContent.tsx:113 — use actual hour values from data
- Fix `parseInt('7d')` in PricesContent.tsx:58 — parse the numeric prefix and multiply by 24 for days
**Tests**: Add unit tests for each transformation function
**Effort**: 4 hours
**Blocks**: Nothing

### Task 2.7: Fix Fail-Open Moderation
**Files**: `backend/services/community_service.py:97-113`
**Reports**: 17-BUG-002
**Action**:
- On timeout: leave `is_pending_moderation=true` (don't call `_clear_pending_moderation`)
- Schedule background retry task
- Increase timeout from 5s to 30s
- Only fail-open after 3 retry failures with admin notification
**Tests**: Add timeout simulation test
**Effort**: 2 hours
**Blocks**: Nothing

### Task 2.8: Fix Cache Lock Thundering Herd
**Files**: `backend/services/analytics_service.py:52`
**Reports**: 17-BUG-009
**Action**:
- Change `_acquire_cache_lock` to return `False` on Redis exception (fail-closed)
- Add circuit breaker: after 3 consecutive lock failures, fall back to direct DB query with short TTL
**Tests**: Add Redis failure simulation test
**Effort**: 1 hour
**Blocks**: Nothing

### Task 2.9: Fix Race Condition in Retroactive Moderation
**Files**: `backend/services/community_service.py:454-484`
**Reports**: 17-BUG-001
**Action**:
- Replace shared `flagged_ids` list with coroutine return values:
  ```python
  results = await asyncio.gather(*(classify_post(p) for p in posts))
  flagged_ids = [r for r in results if r is not None]
  ```
**Tests**: Concurrent classification test
**Effort**: 30 minutes
**Blocks**: Nothing

---

## Sprint 3: Security Hardening + Test Quality (Days 14-19)

### Task 3.1: Encrypt Redis Session Cache
**Files**: `backend/auth/neon_auth.py:112-125`
**Reports**: 11-P1-01
**Action**: Encrypt `SessionData` JSON with `FIELD_ENCRYPTION_KEY` before storing in Redis. Decrypt on read.
**Effort**: 2 hours

### Task 3.2: Fix Error Detail Leakage in Internal Endpoints
**Files**: Multiple `backend/api/v1/` files
**Reports**: 18-P1-04
**Action**: Replace all `detail=str(e)` with `detail="See server logs"` in production. Log `str(e)` at ERROR level.
**Effort**: 2 hours

### Task 3.3: Fix `JWT_SECRET` Auto-Generate
**Files**: `backend/config/settings.py:59-62`
**Reports**: 18-P1-02
**Action**: Replace `default_factory` with empty string default. Add validator that raises in production.
**Effort**: 30 minutes

### Task 3.4: Complete `insecure_defaults` Blocklist
**Files**: `backend/config/settings.py:243-248`
**Reports**: 18-P1-03
**Action**: Add `test_jwt_secret_key_change_in_production`, `test_secret_key_for_ci_minimum_32_chars`, `generate_a_secure_random_string_at_least_32_chars`.
**Effort**: 15 minutes

### Task 3.5: Fix Empty Stub Security Tests
**Files**: `backend/tests/test_auth_bypass.py:243-261`
**Reports**: 16-P0-01
**Action**: Either implement real test logic or delete the stubs. Do NOT leave `pass` bodies in security tests.
**Effort**: 2 hours

### Task 3.6: Fix `conftest.py` Missing Fields
**Files**: `backend/tests/conftest.py:481-491`
**Reports**: 16-P0-01
**Action**: Add `subscription_tier` and `stripe_customer_id` to `mock_sqlalchemy_select` fixture.
**Effort**: 30 minutes

### Task 3.7: Fix Performance Test Server Dependency
**Files**: `backend/tests/test_api_latency.py`
**Reports**: 16-P0-03
**Action**: Add `pytest.mark.skipif(not is_server_running())` guard. Or refactor to use TestClient.
**Effort**: 1 hour

### Task 3.8: Fix Tautological E2E Assertion
**Files**: `frontend/e2e/accessibility.spec.ts:296`
**Reports**: 16-P1-02
**Action**: Replace `expect(submitFocused || true).toBe(true)` with `expect(submitFocused).toBe(true)`.
**Effort**: 5 minutes

### Task 3.9: Fix Price Analytics Endpoint Auth
**Files**: `backend/routers/predictions.py` — `/statistics`, `/optimal-windows`, `/trends`, `/peak-hours`
**Reports**: 15-P2-05
**Action**: Add `get_current_user` dependency and `require_tier("pro")` to all 4 endpoints.
**Effort**: 1 hour

### Task 3.10: Clean Up Dead Code
**Reports**: 15-P2-01, 15-P2-06, 20-P1-01, 20-P1-02, 20-P1-05
**Action**:
- Remove 3 dead feature flags from `settings.py`
- Delete or implement `FeatureFlagService`
- Delete phantom staging workflow or document as future work
- Remove `keepalive.yml` or retarget to Render origin
- Delete or implement `model-retrain.yml`
**Effort**: 3 hours

### Task 3.11: Add `.gitleaks.toml` Custom Rules
**Files**: `.gitleaks.toml`
**Reports**: 18-P2-01
**Action**: Add regex rules for Upstash connection strings, Neon connection strings, Base64 OTLP headers, Composio API keys.
**Effort**: 1 hour

---

## Sprint 4: Remaining P1s + P2 Backlog (Days 20-25)

### Task 4.1: Fix CSRF Protection
**Reports**: 11-P1-02
**Action**: Verify `SameSite=Strict` on session cookies. If not possible, implement double-submit CSRF token.
**Effort**: 4 hours

### Task 4.2: Fix Dashboard Waterfall
**Reports**: 19-P0-03
**Action**: Implement React Query `suspense` boundaries or `useSuspenseQueries` to batch requests. Add SSE connection delay (2s after mount).
**Effort**: 3 hours

### Task 4.3: Increase DB + Redis Pool Sizes
**Reports**: 19-P1-06
**Action**: `pool_size=5, max_overflow=10` for SQLAlchemy. `max_connections=20` for Redis.
**Effort**: 30 minutes

### Task 4.4: Fix SSE Heartbeat
**Reports**: 19-P2-03
**Action**: Set `heartbeat_interval` < `interval_seconds` (e.g., 15s heartbeat, 30s data interval).
**Effort**: 15 minutes

### Task 4.5: Fix Notification Polling
**Reports**: 19-P1-03
**Action**: Replace 30s polling with SSE (piggyback on existing `/prices/stream` connection) or increase interval to 120s.
**Effort**: 3 hours

### Task 4.6: Fix E2E Migration Coverage
**Reports**: 20-P1-07
**Action**: Run all 53 migrations in E2E database setup, not just first 3.
**Effort**: 1 hour

### Task 4.7: Fix `waitForTimeout()` in E2E Tests
**Reports**: 16-P1-01
**Action**: Replace 50+ `waitForTimeout()` calls with `waitForResponse()` or `waitForSelector()`.
**Effort**: 4 hours (systematic replacement)

### Task 4.8: Fix Load Test
**Reports**: 16-P1-05
**Action**: Update `locustfile.py` to use valid Region enum values and current auth endpoint.
**Effort**: 1 hour

### Task 4.9-4.20: Remaining P2/P3 Items
**Effort**: ~40 hours total across CSS, typing, accessibility, dark mode, etc.
**Priority**: Addressed opportunistically alongside feature work.

---

## Dependency Graph

```
Sprint 0: [0.1] → [0.2] → [0.3]
Sprint 1: [1.1] [1.2] [1.3] [1.4] [1.5] [1.7] [1.8] (all parallel)
Sprint 2: [2.1] → [2.2] → [2.3]
          [2.4] [2.5] [2.6] [2.7] [2.8] [2.9] (parallel with 2.1-2.3)
Sprint 3: All tasks parallel
Sprint 4: All tasks parallel
```

---

## Success Criteria

| Metric | Current | Target (Post-Sprint 2) | Target (Post-Sprint 4) |
|--------|---------|------------------------|------------------------|
| P0 findings | 51 | 0 | 0 |
| P1 findings | 143 | <40 | <20 |
| Backend tests | 2,686 | 2,720+ | 2,750+ |
| Frontend tests | 2,039 | 2,060+ | 2,080+ |
| ML tests | 611 | 640+ | 660+ |
| Bandit CI gate | Warning only | Fail on high | Fail on high |
| Docker images pinned | 0/6 | 6/6 | 6/6 |
| DB backup automation | None | Weekly R2 | Weekly R2 + verify |
| Gunicorn workers | 1 | 2 | 2 |

---

## Effort Summary

| Sprint | Tasks | Effort (hours) | Theme |
|--------|-------|----------------|-------|
| Sprint 0 | 3 | 3.25 | Immediate security |
| Sprint 1 | 8 | 13 | Infrastructure + billing |
| Sprint 2 | 9 | 28.5 | ML overhaul + frontend |
| Sprint 3 | 11 | 13.25 | Security + tests |
| Sprint 4 | 8+ | 17+ | Remaining P1s |
| **TOTAL** | **39+** | **~75 hours** | |
