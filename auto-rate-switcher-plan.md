# Auto Rate Switcher — Implementation Plan

**Design doc:** `auto-rate-switcher-design.md`
**Research:** `auto-rate-switcher-research.md`

## Goal

Implement the Auto Rate Switcher agent: autonomous electricity plan switching for Business tier, recommend+confirm for Pro tier.

---

## Tasks

### Phase 1: Database & Models

- [ ] **Task 1:** Create migration 066 with all 6 tables (user_plans, available_plans, meter_readings, switch_audit_log, switch_executions, user_agent_settings). Use UUID PKs, IF NOT EXISTS, neondb_owner GRANTs, region_enum. meter_readings partitioned by range(reading_time). Apply to Neon `cold-rice-23455092` production branch.
  - Verify: `mcp__Neon__get_database_tables` shows 64 public tables. All indexes created.

- [ ] **Task 2:** Create SQLAlchemy models in `backend/models/` — one file per table: `user_plan.py`, `available_plan.py`, `meter_reading.py`, `switch_audit_log.py`, `switch_execution.py`, `user_agent_settings.py`. Follow existing patterns (UUID PK, relationship declarations, `to_dict()`).
  - Verify: `.venv/bin/python -c "from backend.models import UserPlan, AvailablePlan, MeterReading, SwitchAuditLog, SwitchExecution, UserAgentSettings"` succeeds.

- [ ] **Task 3:** Update `backend/models/__init__.py` to export all 6 new models. Update `conftest.py` `mock_sqlalchemy_select` fixture if needed.
  - Verify: existing backend tests still pass (`.venv/bin/python -m pytest backend/tests/ -x -q --timeout=30`).

### Phase 2: Core Services

- [ ] **Task 4:** Create `backend/services/arcadia_service.py` — Arcadia Arc API client. Methods: `connect_account(user_id, auth_code)`, `fetch_interval_data(account_id, start, end)`, `fetch_bills(account_id)`, `sync_meter_readings(user_id)`. httpx async client, error handling, retry on 429/503.
  - Verify: `test_arcadia_service.py` — 25 tests covering success, auth failure, rate limit, timeout, data parsing.

- [ ] **Task 5:** Create `backend/services/energybot_service.py` — EnergyBot API client. Methods: `fetch_plans(zip_code, utility_code)`, `get_plan_details(plan_id)`, `create_enrollment(enrollment_request, idempotency_key)`, `check_enrollment_status(enrollment_id)`, `cancel_enrollment(enrollment_id)`. API key auth.
  - Verify: `test_energybot_service.py` — 25 tests covering plan fetch, enrollment create/check/cancel, error handling.

- [ ] **Task 6:** Create `backend/services/switch_executor.py` — SwitchExecutor Protocol + EnergyBotExecutor adapter + AdvisoryOnlyFallback. Protocol defines: `check_plan_available()`, `execute_enrollment()`, `check_enrollment_status()`, `cancel_enrollment()`.
  - Verify: `test_switch_executor_adapters.py` — 20 tests covering adapter pattern, fallback to advisory-only when executor unavailable.

### Phase 3: Decision Engine

- [ ] **Task 7:** Create `backend/services/switch_decision_engine.py` — the brain. `evaluate(user_id) -> SwitchDecision`. Implements all 7 rules in order: kill switch, cooldown, plan comparison, savings floor, ETF guard, contract window, tier gate. Accepts any data source with confidence scoring.
  - Verify: `test_switch_decision_engine.py` — 50 tests: each rule in isolation, combined scenarios, edge cases (no data, expired plan, zero ETF, cooldown active, LOA revoked).

- [ ] **Task 8:** Create `backend/services/plan_scorer.py` — plan-fit scoring. Takes user usage profile (interval or monthly) + plan rate structure → projected monthly cost. Handles TOU, tiered, flat rate structures. Confidence multiplier based on data source.
  - Verify: `test_plan_scorer.py` — 20 tests: flat rate, TOU plan with off-peak user, tiered plan, monthly-only data (lower confidence).

### Phase 4: Execution & Lifecycle

- [ ] **Task 9:** Create `backend/services/switch_execution_service.py` — orchestrates the full switch lifecycle. Methods: `execute_switch(user_id, decision)`, `check_pending_switches()`, `rollback_switch(execution_id)`, `approve_recommendation(audit_log_id)`. Idempotency key generated and stored BEFORE enrollment API call. State machine transitions with audit logging.
  - Verify: `test_switch_execution_service.py` — 30 tests: full lifecycle (initiate → active), failure handling, rollback (plan available vs retired), idempotency on retry, Pro approve flow.

- [ ] **Task 10:** Create `backend/services/contract_lifecycle_service.py` — tracks contract state per user. Methods: `get_contract_status(user_id)`, `is_in_cooldown(user_id)`, `is_in_rescission(user_id)`, `get_free_switch_window(user_id)`. Rescission period lookup by state (TX=14d, OH=7d, PA=3d).
  - Verify: `test_contract_lifecycle_service.py` — 20 tests: each state, rescission by state, cooldown expiry, free switch window detection.

### Phase 5: Safeguards

- [ ] **Task 11:** Create `backend/services/switch_safeguards.py` — standalone safeguard checks callable from decision engine. `check_savings_floor()`, `check_cooldown()`, `check_etf_guard()`, `check_kill_switch()`, `check_rescission()`. Each returns `(passed: bool, reason: str)`.
  - Verify: `test_safeguards.py` — 30 tests: each safeguard independently, threshold edge cases, paused_until, LOA revocation.

### Phase 6: API Endpoints

- [ ] **Task 12:** Create `backend/api/v1/agent_switcher.py` — all user-facing endpoints. `require_tier("pro")` on all routes. Settings CRUD, LOA sign/revoke, history, activity feed, check-now, rollback, approve. Follow existing FastAPI patterns (Depends, HTTPException, response models).
  - Verify: `test_agent_switcher_api.py` — 40 tests: each endpoint, tier gating (free=403, pro=allowed, business=allowed), LOA flow, rollback validation.

- [ ] **Task 13:** Create internal endpoints in `backend/api/v1/internal.py` (add to existing file): `agent-switcher/scan`, `agent-switcher/sync-plans`, `agent-switcher/cleanup-meter-data`. X-API-Key auth, excluded from RequestTimeoutMiddleware.
  - Verify: `test_internal_agent_switcher.py` — 15 tests: auth required, scan triggers decision engine for enrolled users, sync-plans refreshes cache, cleanup deletes old partitions.

### Phase 7: Frontend

- [ ] **Task 14:** Create `/auto-switcher` page — main dashboard. Components: `AgentStatusCard`, `CurrentPlanCard`, `ActivityFeed`, `ProtectedBanner` (post-switch countdown), `PendingRecommendations` (Pro). Route: `frontend/app/(protected)/auto-switcher/page.tsx` + `loading.tsx` + `error.tsx`.
  - Verify: `AutoSwitcherDashboard.test.tsx` — renders with mock data, shows activity feed, protected banner appears after switch, kill switch toggle works.

- [ ] **Task 15:** Create `/auto-switcher/settings` page — configuration. Components: `SavingsThresholdSlider`, `CooldownSetting`, `KillSwitch`, `LOASigningWizard` (5-step). Route: `frontend/app/(protected)/auto-switcher/settings/page.tsx` + `loading.tsx` + `error.tsx`.
  - Verify: `AgentSettings.test.tsx` + `LOASigningWizard.test.tsx` — slider updates, wizard step progression, LOA sign/revoke flow.

- [ ] **Task 16:** Create `/auto-switcher/history` page — switch timeline. Components: `SwitchTimeline`, `SwitchCard` (old→new, savings, status badge), `RollbackButton`, `DecisionReasoning` (expandable). Route: `frontend/app/(protected)/auto-switcher/history/page.tsx` + `loading.tsx` + `error.tsx`.
  - Verify: `SwitchHistory.test.tsx` — timeline renders, rollback button visible within 30 days, status badges correct.

- [ ] **Task 17:** Add sidebar item. Add `Auto Switcher` to sidebar nav between Alerts and Assistant. Badge showing pending recommendation count for Pro tier. Update sidebar nav config.
  - Verify: sidebar renders with new item, badge shows count, navigation works.

- [ ] **Task 18:** Create frontend API client functions in `frontend/lib/api/agent-switcher.ts` — typed functions for all endpoints: `getSettings()`, `updateSettings()`, `signLOA()`, `revokeLOA()`, `getHistory()`, `getActivity()`, `checkNow()`, `rollback()`, `approveSwitch()`.
  - Verify: types match backend response models, error handling follows existing patterns.

### Phase 8: Cron Jobs & Integration

- [ ] **Task 19:** Add CF Worker cron trigger or GHA workflow for `agent-switcher-scan` (daily 4am UTC) and `sync-available-plans` (daily 2am UTC). Use existing `retry-curl` + `notify-slack` patterns. Add `cleanup-meter-data` to existing `db-maintenance.yml` (weekly).
  - Verify: workflow files pass `actionlint`. Cron expressions correct. Internal endpoints called with X-API-Key.

- [ ] **Task 20:** Wire notifications — switch confirmations, recommendations, activity summaries through existing OneSignal + Resend pipeline. Create email templates: `switch_confirmation.html`, `switch_recommendation.html`, `contract_expiring.html`.
  - Verify: email templates render correctly. OneSignal push payload formatted.

### Phase 9: E2E Tests

- [ ] **Task 21:** Create Playwright E2E specs: `auto-switcher-pro-flow.spec.ts` (recommend → approve → verify), `auto-switcher-settings.spec.ts` (enable, configure, LOA, disable), `auto-switcher-history.spec.ts` (view, rollback). Use `authenticatedPage` fixture.
  - Verify: all 3 specs pass locally against dev backend with mocked external APIs.

### Phase 10: Verification

- [ ] **Task 22:** Full test suite pass — all existing tests still green + all new tests pass. `.venv/bin/python -m pytest backend/tests/ -x -q` + `cd frontend && npm test` + E2E.
  - Verify: 0 failures across backend (~3,200 tests), frontend (~2,100 tests), E2E.

- [ ] **Task 23:** Update project docs — add Auto Switcher to `CLAUDE.md` architecture section, update table counts (64 tables), update test counts, add new endpoints to API reference. Update `MEMORY.md` with milestone.
  - Verify: CLAUDE.md accurate, no stale counts.

---

## Done When

- [ ] 6 new tables created and migrated to Neon production
- [ ] Decision engine evaluates all 7 rules correctly
- [ ] Business tier auto-switches via EnergyBot API (mocked in tests)
- [ ] Pro tier sends recommendations and processes approvals
- [ ] All 6 safeguards enforce correctly
- [ ] LOA wizard guides users through trust-building flow
- [ ] Agent Activity feed shows all scan results (including holds)
- [ ] Rollback works within 30-day window
- [ ] ~280 new tests pass, 0 regressions
- [ ] Cron jobs configured and operational

## Notes

- External API contracts (Arcadia, EnergyBot) must be in place before Tasks 4-5 can use real endpoints. Mock during development.
- Texas PUCT broker registration is a parallel business/legal task — not blocked by engineering.
- LOA document storage (S3/R2) must be provisioned before Task 15 (LOA wizard).
- Tasks 1-3 can start immediately with no external dependencies.
- Tasks 4-6 can run in parallel.
- Tasks 7-8 can run in parallel.
- Task 9 depends on Tasks 6-8.
- Frontend tasks (14-18) can start after API endpoints (Task 12) are defined.
