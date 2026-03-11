# Zenith P0 — Implementation Plan

**Track ID:** zenith-p0-fixes_20260312
**Estimated effort:** ~45 minutes across 3 phases
**TDD approach:** Test first for each fix

---

## Phase 1: Session Cache TTL (Fix 1) — ~10 min

### Task 1.1: Write test for reduced TTL
- **File:** `backend/tests/test_neon_auth.py`
- **Action:** Add test that verifies `_SESSION_CACHE_TTL == 60`
- **Verify:** `.venv/bin/python -m pytest backend/tests/test_neon_auth.py -x`

### Task 1.2: Reduce TTL to 60 seconds
- **File:** `backend/auth/neon_auth.py:54`
- **Action:** Change `_SESSION_CACHE_TTL = 300` to `_SESSION_CACHE_TTL = 60`
- **Action:** Add comment: `# 60s TTL balances cache performance vs ban propagation delay (Zenith H-15-01)`
- **Verify:** `.venv/bin/python -m pytest backend/tests/test_neon_auth.py -x`

### Task 1.3: Run full auth test suite
- **Verify:** `.venv/bin/python -m pytest backend/tests/test_neon_auth.py backend/tests/test_auth.py -v`

---

## Phase 2: Backend Circuit Breaker (Fix 2) — ~30 min

### Task 2.1: Write CircuitBreaker tests
- **File:** `backend/tests/test_circuit_breaker.py` (new)
- **Tests to write:**
  - `test_initial_state_is_closed`
  - `test_opens_after_failure_threshold`
  - `test_fast_fails_when_open`
  - `test_transitions_to_half_open_after_recovery_timeout`
  - `test_closes_on_successful_half_open_call`
  - `test_reopens_on_failed_half_open_call`
  - `test_resets_failure_count_on_success`
  - `test_context_manager_usage`
- **Verify:** `.venv/bin/python -m pytest backend/tests/test_circuit_breaker.py -x` (expect failures — TDD red)

### Task 2.2: Implement CircuitBreaker class
- **File:** `backend/lib/circuit_breaker.py` (new)
- **Class:** `CircuitBreaker` with `__init__`, `call()` async context manager, `record_success()`, `record_failure()`, `state` property, `reset()`
- **Parameters:** `failure_threshold=5`, `recovery_timeout=60`, `half_open_max=1`
- **Logging:** `logger.warning()` on state transitions
- **Verify:** `.venv/bin/python -m pytest backend/tests/test_circuit_breaker.py -x` (expect green)

### Task 2.3: Integrate into PricingService
- **File:** `backend/integrations/pricing_apis/service.py`
- **Action:** Add `CircuitBreaker` instance per API client in `PricingService.__init__`
- **Action:** Wrap `_call_client()` or equivalent with circuit breaker check
- **Action:** Report breaker states in `health_check()` response
- **Verify:** `.venv/bin/python -m pytest backend/tests/test_pricing_service.py -x`

### Task 2.4: Integrate into WeatherService
- **File:** `backend/integrations/weather_service.py`
- **Action:** Add `CircuitBreaker` for OpenWeatherMap calls
- **Verify:** `.venv/bin/python -m pytest backend/tests/test_weather_service.py -x`

### Task 2.5: Run integration tests
- **Verify:** `.venv/bin/python -m pytest backend/tests/ -x --timeout=120`

---

## Phase 3: CI Auto-Format Scoping (Fix 3) — ~5 min

### Task 3.1: Fix git add scope in ci.yml
- **File:** `.github/workflows/ci.yml`
- **Action:** Replace `git add -A` with `git add backend/` in the backend-lint job
- **Verify:** Review the diff to confirm only the staging command changed

### Task 3.2: Audit all workflows for git add -A
- **Action:** `grep -r "git add -A\|git add \." .github/workflows/`
- **Action:** Fix any other instances found (scope to relevant directory)

### Task 3.3: Verify CI locally (optional)
- **Action:** If `act` is available, dry-run the backend-lint job
- **Verify:** No other `git add -A` patterns remain

---

## Validation

After all 3 phases:
1. Run full backend test suite: `.venv/bin/python -m pytest backend/tests/ -v --timeout=120`
2. Verify no regressions in auth, pricing, or weather tests
3. Review git diff for completeness
4. Commit with descriptive message referencing Zenith findings

---

## Rollback

Each fix is independent and can be reverted individually:
- **Fix 1:** Change TTL back to 300
- **Fix 2:** Remove circuit breaker imports/usage, delete `lib/circuit_breaker.py`
- **Fix 3:** Change `git add backend/` back to `git add -A`
