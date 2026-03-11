# Zenith P0 — Production Safety Fixes Specification

**Track ID:** zenith-p0-fixes_20260312
**Origin:** Project Zenith Clarity Gate Audit (2026-03-12)
**Priority:** P0 — Production Safety

---

## Fix 1: Session Cache TTL — Ban Propagation Delay

**Finding:** H-15-01 (Section 15: Security)
**File:** `backend/auth/neon_auth.py:54`
**Risk:** A banned user retains API access for up to 5 minutes due to `_SESSION_CACHE_TTL = 300`

### Problem

The `validate_session()` function caches session lookups in Redis with a 5-minute TTL. While `invalidate_session_cache()` exists and is called on explicit logout, admin-initiated bans do not call it. A banned user's cached session remains valid until TTL expiry.

### Solution Options

**Option A (Simple):** Reduce `_SESSION_CACHE_TTL` from 300 to 60 seconds.
- Pro: One-line change, immediately effective
- Con: 5x more Redis lookups to neon_auth tables (still fast — ~1ms per lookup)
- Recommendation: **Use this option** — the 5x increase is negligible at current scale

**Option B (Event-based):** Add a `ban_user()` function that calls `invalidate_session_cache(session_token)` for all active sessions of the banned user.
- Pro: Instant propagation, no TTL increase
- Con: Requires querying all active sessions for a user, more complex

### Acceptance Criteria

- [ ] Session cache TTL reduced to 60 seconds
- [ ] Existing tests pass (no behavior change for valid sessions)
- [ ] New test: verify cache expires within 60s (mock time)
- [ ] Document the TTL change rationale in a code comment

---

## Fix 2: Backend Circuit Breaker for External APIs

**Finding:** H-16-02 (Section 16: External Integrations)
**Files:** `backend/integrations/pricing_apis/service.py`, `backend/integrations/weather_service.py`, `backend/integrations/utilityapi.py`
**Risk:** A consistently failing external API receives requests until timeout, degrading response times for all users

### Problem

Backend integrations have retry logic (via tenacity or custom) but no circuit breaker. When an API is down:
- Each request waits for full retry cycle (3 retries x timeout)
- No fast-fail after repeated failures
- Frontend has a circuit breaker for the CF Worker gateway, but backend lacks one

### Solution

Implement a lightweight `CircuitBreaker` class (matching the frontend's 3-state pattern: CLOSED/OPEN/HALF_OPEN):

```python
class CircuitBreaker:
    """Lightweight circuit breaker for external API resilience."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, half_open_max: int = 1):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # seconds
        self.half_open_max = half_open_max
        self._failure_count = 0
        self._state = "closed"  # closed | open | half_open
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
```

Integration points:
- `PricingService` — wrap each client call
- `WeatherService` — wrap OpenWeatherMap calls
- `UtilityAPI` — wrap sync calls

### Acceptance Criteria

- [ ] `CircuitBreaker` class in `backend/lib/circuit_breaker.py`
- [ ] 3 states: CLOSED (normal), OPEN (fast-fail after 5 failures), HALF_OPEN (probe after 60s)
- [ ] Integrated into `PricingService._call_client()` wrapper
- [ ] Integrated into `WeatherService.fetch_weather()`
- [ ] Integrated into UtilityAPI sync calls
- [ ] Tests: state transitions (closed->open->half_open->closed), fast-fail in open state, recovery
- [ ] Health check endpoint reports circuit breaker states
- [ ] Logging on state transitions (WARNING level)

---

## Fix 3: Scope `git add` in CI Auto-Format

**Finding:** H-14-01 (Section 14: CI/CD)
**File:** `.github/workflows/ci.yml:98`
**Risk:** `git add -A` after Black/isort auto-format could commit untracked files (secrets, build artifacts, etc.)

### Problem

The backend lint step in CI runs Black + isort, then uses `git add -A` to stage formatted changes. If any untracked files exist in the working directory (from prior steps, artifacts, or accidental includes), they get committed along with the formatting fixes.

### Solution

Replace `git add -A` with `git add backend/` to scope staging to only the formatted directory.

### Acceptance Criteria

- [ ] `git add -A` replaced with `git add backend/` in ci.yml backend-lint step
- [ ] Verify the auto-format commit only includes backend Python files
- [ ] No other `git add -A` patterns exist in CI workflows (audit all workflows)

---

## Out of Scope

- P1/P2/P3 findings from Zenith (hook-API integration tests, auth E2E, PricingService typing, etc.)
- New features or migrations
- Frontend changes (all 3 fixes are backend/CI)

## Dependencies

- No migration required
- No new environment variables
- No deployment coordination needed (all changes are backward-compatible)
