# Architecture Review — RateShift Backend + Frontend
**Date:** 2026-03-16
**Reviewer:** architect-reviewer agent (claude-sonnet-4-6)
**Scope:** `backend/main.py`, `backend/app_factory.py`, `backend/api/v1/__init__.py`,
`backend/config/settings.py`, `backend/config/database.py`, `backend/middleware/*`,
`backend/lib/*`, `frontend/app/layout.tsx`, `frontend/lib/api/client.ts`,
`frontend/lib/api/circuit-breaker.ts`, `frontend/lib/config/env.ts`,
`frontend/lib/hooks/useAuth.tsx`, `frontend/next.config.js`

---

## Executive Summary

RateShift has a well-structured, production-hardened foundation. The factory pattern
for app construction, pure ASGI middleware chain, structured logging, and dual-layer
circuit breaking (backend + frontend) all reflect mature engineering decisions. The
configuration layer (`settings.py`) is a standout: Pydantic-settings with exhaustive
production validators, property-based parsing for list env vars, and cross-field
model validators represent best practice.

However, several architectural issues require attention, ranging from a critical
stale module (`api/v1/__init__.py`) to a mid-severity service-instantiation pattern
that prevents testability, to lower-severity concerns around logging consistency and
middleware placement.

**Finding counts by severity:**
| Severity | Count |
|----------|-------|
| P0 — Critical / data integrity or security risk | 1 |
| P1 — High / testability or reliability concern | 4 |
| P2 — Medium / maintainability debt | 6 |
| P3 — Low / polish and consistency | 5 |

---

## P0 — Critical

### P0-01: `api/v1/__init__.py` is a stale, misleading contract
**Area:** API versioning / module contract
**File:** `backend/api/v1/__init__.py`

The file exports exactly three routers:
```python
from api.v1.prices import router as prices_router
from api.v1.suppliers import router as suppliers_router
from api.v1.regulations import router as regulations_router
__all__ = ["prices_router", "suppliers_router", "regulations_router"]
```

But `app_factory.py` registers 36 routers by importing each module directly:
```python
from api.v1 import community as community_v1
from api.v1 import neighborhood as neighborhood_v1
# ... 34 more direct imports
```

The `__init__.py` is completely bypassed. No code reads from `__all__`. This means:
- A developer reading `api/v1/__init__.py` believes only 3 routers exist, a **93% blind spot**.
- Any tooling that introspects `__all__` (type checkers, auto-docs generators, dependency
  scanners) will produce incorrect results.
- The three exported names are not consumed anywhere, making this file actively deceptive.

**Recommendation:** Either (a) update `__init__.py` to reflect all 36 routers and actually
use it as the single registration point, or (b) delete the file body and leave only a
docstring stating "routers are registered directly in `app_factory.py`". Option (a) is
preferred for long-term maintainability. Option (b) is the quicker honest fix.

---

## P1 — High

### P1-01: Service classes instantiated ad-hoc inside request handlers
**Area:** Dependency injection / testability
**Files:** `backend/api/v1/community.py`, `backend/api/v1/agent.py`,
`backend/api/v1/neighborhood.py`, `backend/api/v1/billing.py` (partial list)

Multiple handlers instantiate service objects directly:
```python
# community.py — six separate handlers each do this:
service = CommunityService()
post = await service.create_post(...)

# agent.py
service = AgentService()

# billing.py
stripe_service = StripeService()
```

FastAPI's dependency injection system (`Depends`) is used inconsistently.
`get_price_service` in `api/dependencies.py` shows the correct pattern
(factory function with `Depends`), but it is the exception rather than the rule.

Consequences:
- Services cannot be overridden in tests without patching at the class level.
- Any service that acquires shared resources (Redis, HTTP clients, circuit breakers)
  creates a new instance per request, defeating object-level state management.
- Cross-cutting concerns (tracing, caching, connection pooling) cannot be centrally
  injected; each service must wire itself.

**Recommendation:** Register all stateful services as FastAPI dependencies in
`api/dependencies.py` (or a new `api/v1/deps.py`). Example:
```python
# api/dependencies.py
def get_community_service() -> CommunityService:
    return CommunityService()  # or a singleton if stateless

# community.py
async def create_post(
    payload: CreatePostRequest,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    service: CommunityService = Depends(get_community_service),
):
    ...
```
For stateless services (most utility-type services here), a module-level singleton
returned from a `Depends` factory is sufficient and avoids per-request allocation.

---

### P1-02: `_memory_store` type inconsistency in `UserRateLimiter`
**Area:** Rate limiting reliability
**File:** `backend/middleware/rate_limiter.py`

The in-memory fallback store uses two incompatible value types for the same dictionary:

```python
# For rate limiting — stores a list of timestamps:
self._memory_store.setdefault(key, []).append(now)
request_count = len(self._memory_store[key])

# For login attempts — stores a dict:
self._memory_store[key] = {"count": 0, "expires": 0}
attempts = self._memory_store[key]["count"]
```

A single dict `_memory_store: dict = {}` holds both `list[float]` and
`dict[str, Any]` values under different key prefixes (`ratelimit:*` vs `login_attempts:*`).
This is fragile: the eviction loop in `_check_memory` assumes all values are lists
(`v[-1] < window_start`), meaning a `login_attempts:*` dict would raise `TypeError`
during the sweep if it ever fell through. The key-prefix separation currently avoids
this, but it is one naming collision away from a runtime error.

Additionally, the eviction sweep only fires when `len > 10_000`. Under a sustained
Redis outage with heavy traffic, 10,000 mixed-type entries create a significant
memory footprint before any cleanup.

**Recommendation:** Split into two typed stores:
```python
_rate_store: dict[str, list[float]] = {}
_login_store: dict[str, dict[str, Any]] = {}
```
Apply the eviction sweep on `_rate_store` only (its logic is currently correct).
Document the explicit type contract on each.

---

### P1-03: `traced` class duplicates sync and async implementation verbatim
**Area:** Code duplication / maintainability
**File:** `backend/lib/tracing.py`

The `traced` class implements both `__enter__`/`__exit__` and `__aenter__`/`__aexit__`.
The bodies of each pair are word-for-word identical, including the deferred
`from opentelemetry.trace import StatusCode` import:

```python
# __aenter__ body
async def __aenter__(self):
    tracer = get_tracer(self._tracer_name)
    self._span = tracer.start_span(self._operation)
    self._token = _set_span_in_context(self._span)
    for key, value in self._attributes.items():
        self._span.set_attribute(key, value)
    return self._span

# __enter__ body — identical
def __enter__(self):
    tracer = get_tracer(self._tracer_name)
    self._span = tracer.start_span(self._operation)
    self._token = _set_span_in_context(self._span)
    for key, value in self._attributes.items():
        self._span.set_attribute(key, value)
    return self._span
```

The exit implementations are also duplicated. Any change to span management logic
(e.g., adding a baggage propagation step) must be applied in two places.

**Recommendation:** Extract shared setup/teardown into private sync methods:
```python
def _begin(self):
    tracer = get_tracer(self._tracer_name)
    self._span = tracer.start_span(self._operation)
    self._token = _set_span_in_context(self._span)
    for key, value in self._attributes.items():
        self._span.set_attribute(key, value)
    return self._span

def _end(self, exc_val):
    from opentelemetry.trace import StatusCode
    try:
        if exc_val is not None:
            self._span.set_status(StatusCode.ERROR, str(exc_val))
            self._span.record_exception(exc_val)
        else:
            self._span.set_status(StatusCode.OK)
    finally:
        self._span.end()
        _detach_context(self._token)
```

Then `__enter__`, `__exit__`, `__aenter__`, and `__aexit__` each become one-liners.

---

### P1-04: Dual DB session dependency paths create an implicit split contract
**Area:** Dependency injection / coupling
**Files:** `backend/api/v1/user.py`, `backend/api/v1/prices.py`,
`backend/api/v1/auth.py` vs. the majority of other API files

Thirty-two API files import `get_db_session` from `api.dependencies` (the correct
canonical path), but three files import `get_timescale_session` directly from
`config.database`:

```python
# Canonical (29 files)
from api.dependencies import get_current_user, get_db_session, SessionData

# Direct config import — bypasses dependencies layer (3 files)
from config.database import get_timescale_session
```

`api/dependencies.py:get_db_session` wraps `db_manager.get_timescale_session()`
so behaviorally they are equivalent today. However the inconsistency means:
- Any future middleware injected into `get_db_session` (e.g., read-replica routing,
  connection tagging) will silently not apply to the three outlier files.
- `config.database` leaks through the abstraction boundary into the API layer.

**Recommendation:** Standardize on `from api.dependencies import get_db_session` in
all API files. Remove the `get_timescale_session` export from `config/database.py`
or mark it `_private` to signal it is infrastructure-internal only.

---

## P2 — Medium

### P2-01: `app_factory.py` mixes infrastructure concerns with application bootstrap
**Area:** Separation of concerns / single responsibility
**File:** `backend/app_factory.py` (792 lines)

The factory file contains:
1. Logging configuration (structlog setup, processor chain by environment)
2. Two inline ASGI middleware classes (`RequestBodySizeLimitMiddleware`,
   `RequestTimeoutMiddleware`) with their own constants (`MAX_REQUEST_BODY_BYTES`,
   `REQUEST_TIMEOUT_SECONDS`)
3. Application lifecycle management (DB init, Redis wiring, Sentry init, OTel init)
4. Middleware registration order
5. Exception handlers
6. Prometheus metrics protection middleware
7. Root endpoint definition
8. 36 router registrations

The comment in the file acknowledges the inline classes are "tightly coupled to app
construction" and placed to "avoid circular imports". This is a structural coupling
problem: the real fix is to move the constants and classes to `middleware/` and resolve
any import cycle at the module-graph level rather than by colocation.

**Recommendation (phased):**
- Phase 1: Move `RequestBodySizeLimitMiddleware` and `RequestTimeoutMiddleware` to
  `backend/middleware/body_limit.py` and `backend/middleware/timeout.py`.
- Phase 2: Extract the lifespan function into `backend/app_lifecycle.py`.
- Phase 3: Extract the 36 router registrations into `backend/api/router_registry.py`.
- Result: `app_factory.py` shrinks to ~100 lines of pure composition.

---

### P2-02: `SecurityHeadersMiddleware` and `next.config.js` set overlapping but divergent headers
**Area:** Security architecture / duplication
**Files:** `backend/middleware/security_headers.py`, `frontend/next.config.js`

Both layers set `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`,
`Permissions-Policy`, and `Content-Security-Policy`. The values differ:

| Header | Backend (prod) | Frontend (next.config.js) |
|--------|---------------|--------------------------|
| CSP `script-src` | `'self'` | `'self' 'unsafe-inline' https://*.clarity.ms https://cdn.onesignal.com` |
| Permissions-Policy | includes `accelerometer`, `gyroscope`, `magnetometer`, `usb` | omits those four |
| HSTS max-age | 31,536,000 (1 year) | 63,072,000 (2 years) |
| CSP `connect-src` | `'self' https:` (all HTTPS) | explicit whitelist |

Because the frontend (Vercel) and backend (Render/CF Worker) are separate origins,
most API responses go through the backend middleware and most page responses through
Next.js. But the divergence creates confusion: a developer reading one file sees an
incomplete picture. The backend CSP that blocks `'unsafe-inline'` scripts is never
seen by browsers loading the SPA (they load from Vercel), so the backend CSP is
providing false confidence for script injection prevention.

**Recommendation:** Document the intentional separation explicitly. Add a comment
to `security_headers.py` stating: "Backend CSP applies only to API responses served
from the Render origin; SPA pages are governed by `next.config.js`." Also unify the
`Permissions-Policy` attribute list between the two files to close the gap.

---

### P2-03: Inconsistent logging infrastructure — 13 files use stdlib `logging`
**Area:** Observability / consistency
**Files:** `price_service.py`, `recommendation_service.py`, `learning_service.py`,
`vector_store.py`, `hnsw_vector_store.py`, `observation_service.py`,
`price_sync_service.py`, `model_version_service.py`, `ab_test_service.py`,
and 4 others

The project uses `structlog` consistently across middleware, the app factory, and
most services. However 13 backend files use `import logging` (stdlib). These log
records lack the structured context (trace_id, user_id, request metadata) that
`structlog.contextvars` binds per-request, making those log lines orphaned in
Grafana/any log aggregator that relies on the `trace_id` field.

The ML-adjacent services (`vector_store`, `hnsw_vector_store`, `learning_service`,
`observation_service`) are likely legacy from pre-structlog adoption, while
`price_service.py` and `recommendation_service.py` are core services that should
absolutely emit structured traces.

**Recommendation:** Migrate all 13 files to `structlog.get_logger(__name__)`.
The migration is mechanical: replace `import logging` + `logger = logging.getLogger(__name__)`
with `import structlog` + `logger = structlog.get_logger(__name__)`. Log call
syntax is compatible. Prioritize `price_service.py` and `recommendation_service.py`
as P1 impact; remaining ML services can follow in a batch.

---

### P2-04: `useAuth` hook performs side-effect data fetching at auth context level
**Area:** Frontend separation of concerns
**File:** `frontend/lib/hooks/useAuth.tsx`

The `AuthProvider` initAuth effect does three parallel async calls:
1. `authClient.getSession()` — correct; auth state
2. `getUserSupplier()` — user's supplier preference
3. `getUserProfile()` — user profile (region, onboarding status)

Auth initialization should establish identity and nothing more. Supplier and profile
data belong in their own React Query hooks (`useProfile`, `useSupplier`) which already
exist in the codebase. Placing them in the auth effect creates:
- A waterfall on every page load: auth initialization holds the `isLoading=true` gate
  for all three requests to complete, even if the component consuming auth only needs
  identity.
- Tight coupling: `useAuth` now depends on `getUserSupplier`, `getUserProfile`,
  `useSettingsStore`, `loginOneSignal`, and the router. Changes to the profile API
  contract can break auth initialization.
- Test complexity: mocking `useAuth` requires mocking five distinct dependencies.

The onboarding redirect logic (`router.replace('/onboarding')`) is particularly
concerning inside an auth context — routing decisions belong in middleware or
page-level components, not the identity provider.

**Recommendation:** Limit `AuthProvider` to session establishment, user identity,
and sign-in/sign-out actions. Extract the supplier sync, profile sync, and onboarding
redirect into a `usePostAuthSync` hook or a dedicated `<PostAuthBridge>` component
that mounts only when `isAuthenticated` is true. The existing `useProfile` and
`useSupplier` hooks can be used directly in that component.

---

### P2-05: `api/v1/__init__.py` `__all__` stale export is a secondary symptom of a router-registration gap
**Area:** API versioning structure
**File:** `backend/api/v1/__init__.py`

(Distinct from P0-01 which concerns the deceptive contract; this finding concerns the
versioning strategy itself.)

All 36 routers are registered with the same prefix: `f"{settings.api_prefix}/..."` which
expands to `/api/v1/...`. There is no programmatic way to register a `/api/v2/` path
for a single endpoint without touching `app_factory.py`. As the platform evolves,
individual endpoints will need breaking changes while others remain v1-compatible.

Currently the only route toward versioning is to:
1. Fork the entire `api/v1/` directory into `api/v2/`
2. Add more direct imports to an already 792-line `app_factory.py`

This is prohibitively costly and would stall gradual migration.

**Recommendation:** Introduce a `VersionedRouter` abstraction or at minimum a
`router_registry.py` module that maps `(prefix, module, tags)` tuples and can
selectively apply v2 prefixes. This is a design investment with payoff when the first
endpoint requires a breaking change. Even a simple dict-based registry in
`app_factory.py` would make the pattern explicit.

---

### P2-06: `DatabaseManager` uses a "TimescaleDB" naming convention for a Neon PostgreSQL connection
**Area:** Architecture clarity / naming
**File:** `backend/config/database.py`

All database-related names use `timescale_*` (`timescale_engine`, `timescale_pool`,
`get_timescale_session`, `get_timescale_session`). The project uses Neon PostgreSQL,
not TimescaleDB. The naming creates confusion for new contributors who would research
TimescaleDB documentation when debugging connection issues.

Additionally, `DatabaseManager._init_database` conditionally creates an `asyncpg.Pool`
only for non-Neon connections (`if "neon.tech" not in db_url`), meaning `timescale_pool`
is always `None` in production. The `_execute_raw_query` method therefore always falls
through to the SQLAlchemy path, making the asyncpg pool code dead weight in production.

**Recommendation:** Rename `timescale_engine` → `engine`, `timescale_pool` → `pool`,
`get_timescale_session` → `get_db_session`. Remove or clearly document the dead asyncpg
pool path. If raw asyncpg performance is ever needed, it should be a deliberate opt-in,
not a conditional that silently never fires.

---

## P3 — Low

### P3-01: Middleware registration order comment is inverted from FastAPI's actual behavior
**Area:** Middleware ordering documentation
**File:** `backend/app_factory.py` (line ~376)

The comment reads:
```
# Middleware (registration order matters — last registered = outermost
# wrapper = runs first on the inbound request path)
```

This is correct for FastAPI/Starlette's `add_middleware`: the last `add_middleware`
call is the outermost wrapper. However the inline `@app.middleware("http")` decorators
(`add_process_time_header`, `protect_metrics`) are registered **after** the
`add_middleware` calls, which means they are actually inner to all the ASGI middleware.

The `protect_metrics` middleware (guards the `/metrics` route) sits inside the rate
limiter. This means a request to `/metrics` without an API key is still rate-limit
counted before being rejected by `protect_metrics`. Operationally minor, but the
intent (metrics should be fast-rejected before any rate-limit accounting) is not met.

**Recommendation:** Register `protect_metrics` as a pure ASGI class in
`middleware/metrics_auth.py` and add it via `app.add_middleware()` — after
`RateLimitMiddleware` in the registration list, which makes it outer (runs first),
achieving the intended behavior. Update the comment to clarify the order for both
`add_middleware` and decorator-style `@app.middleware`.

---

### P3-02: `settings.py` validators access `os.environ` directly instead of `self`
**Area:** Config management / correctness
**File:** `backend/config/settings.py`

Several `@field_validator` methods call `os.environ.get("ENVIRONMENT", "development")`
directly:
```python
@field_validator("field_encryption_key")
@classmethod
def validate_field_encryption_key(cls, v):
    env = os.environ.get("ENVIRONMENT", "development")  # bypasses Pydantic
    if env == "production":
        ...
```

This means the validator ignores the `environment` field's value as seen by Pydantic
(including any `validation_alias`, case normalization, or test-time override). In a
test that sets `ENVIRONMENT` in `os.environ`, this might work, but the validator will
not honor a Pydantic-level override. More critically, `ENVIRONMENT` is case-insensitive
in this settings model (`case_sensitive=False`), meaning `Environment=production` would
be accepted by the `environment` field but `os.environ.get("ENVIRONMENT")` would miss
a lowercased key.

**Recommendation:** Use `model_validator(mode="after")` for cross-field production
checks (accessing `self.environment` directly), mirroring the pattern already used for
`validate_ai_agent_keys` and `validate_api_key_differs_from_jwt`. This makes all
production checks consistent and testable through Pydantic's own override mechanisms.

---

### P3-03: Frontend `useAuth` contains a hardcoded public-page path list
**Area:** Frontend maintainability
**File:** `frontend/lib/hooks/useAuth.tsx` (line 132)

```typescript
if (path.startsWith('/dashboard') || path.startsWith('/prices') ||
    path.startsWith('/suppliers') || path.startsWith('/optimize') ||
    path.startsWith('/connections') || path.startsWith('/settings') ||
    path.startsWith('/alerts') || path.startsWith('/assistant')) {
  router.replace('/onboarding')
}
```

This list must be kept in sync with:
1. The Next.js `middleware.ts` (which likely has its own auth-protected path matcher)
2. Any new pages added to the `(app)` route group

Missing a route from this list means onboarding-incomplete users can access that route.
Adding a route to this list incorrectly causes premature onboarding redirects.

**Recommendation:** Replace this list with a route-group convention. Since the
`(app)` route group layout already wraps all authenticated pages, middleware-level
redirect logic (in `frontend/middleware.ts`) is the appropriate single enforcement
point. The auth hook should only set state; routing enforcement should be structural.

---

### P3-04: `settings.py` list-parsing properties are duplicated for `cors_origins` and `allowed_redirect_domains`
**Area:** Config management / DRY
**File:** `backend/config/settings.py`

The same JSON-or-CSV parsing logic appears in two identical `@property` methods
(lines 34-46 and 138-150). If a third list-type setting is added (e.g.,
`trusted_proxies`), the logic will be copied a third time.

**Recommendation:** Extract to a private utility function:
```python
def _parse_list_env(raw: str, fallback: list[str]) -> list[str]:
    if not raw:
        return fallback
    raw = raw.strip()
    if raw.startswith("["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in raw.split(",") if item.strip()]
```
Then both properties become one-liners. This is a minor DRY concern but will compound
as configuration grows.

---

### P3-05: Frontend `circuit-breaker.ts` has no persistence across page navigations
**Area:** Frontend resilience architecture
**File:** `frontend/lib/api/circuit-breaker.ts`

The circuit breaker singleton is module-level in the browser bundle:
```typescript
export const circuitBreaker = new CircuitBreaker({ ... })
```

Its state (`_failureCount`, `_state`, `_lastFailureTime`) is in-memory only. A full
page navigation or browser refresh resets it to `CLOSED`, regardless of whether the
CF Worker gateway is actually healthy. This means:
- On a hard refresh during a gateway outage, the first three requests to the
  broken primary are retried before the circuit opens again (wasted latency per page load).
- The 30-second `resetTimeoutMs` is meaningless across navigations.

This is a low-severity issue because the retry mechanism (`fetchWithRetry`) limits
blast radius to two retries per call, but it does mean the fallback guarantee is
weaker for SPA-style navigations (which don't trigger reloads) vs. hard navigations.

**Recommendation:** Persist circuit state to `sessionStorage` with a timestamp.
On initialization, read from `sessionStorage` and restore state if the timestamp is
within the cooldown window. This is a 15-line addition that gives consistent behavior
across both SPA and hard navigations without impacting the happy path.

---

## Architecture Strengths (For the Record)

The following design decisions are specifically called out as exemplary and should
be preserved through future refactors:

1. **App factory pattern** (`app_factory.py`): `create_app()` returning
   `(app, rate_limiter)` makes the app fully testable without module-level side effects.

2. **Pure ASGI middleware**: All five custom middleware classes use the raw ASGI
   protocol (`__call__(scope, receive, send)`) rather than `BaseHTTPMiddleware`.
   This avoids response buffering, is SSE-safe, and has zero overhead for non-HTTP scopes.

3. **Pydantic-settings production validators**: The `Settings` class catches
   mis-configuration at startup rather than at first use. The `model_validator`
   cross-field checks (API key differs from JWT secret, AI agent keys present when
   agent enabled) are notably well-designed.

4. **Centralized env config in frontend** (`lib/config/env.ts`): All `NEXT_PUBLIC_*`
   reads are centralized, typed, and validated. Direct `process.env.*` in components
   is an antipattern; this file correctly enforces the boundary.

5. **Frontend circuit breaker** (`lib/api/circuit-breaker.ts`): The CLOSED/OPEN/HALF_OPEN
   state machine with automatic OPEN→HALF_OPEN timeout transition mirrors the backend
   `lib/circuit_breaker.py` pattern, giving the system defense-in-depth for gateway
   failures at both layers.

6. **Internal API package structure** (`api/v1/internal/__init__.py`): Composing a
   parent router with a shared `Depends(verify_api_key)` dependency ensures all internal
   endpoints are protected by one enforcement point, not scattered `Depends` calls.

7. **Rate limiter in-memory fallback with eviction** (`middleware/rate_limiter.py`):
   The 10,000-key sweep with `setdefault` for race-safe insertion shows careful
   attention to Redis-outage behavior. Most rate limiters silently fail open; this one
   degrades gracefully.

---

## Remediation Priority

| Finding | Effort | Impact | Suggested Sprint |
|---------|--------|--------|-----------------|
| P0-01: Stale `__init__.py` | Low (30 min) | High | Immediate |
| P1-01: Service instantiation in handlers | Medium (2-3 days) | High | Next sprint |
| P1-02: `_memory_store` type inconsistency | Low (1 hour) | Medium | Next sprint |
| P1-03: `traced` class duplication | Low (1 hour) | Low | Next sprint |
| P1-04: Dual DB session import paths | Low (1 hour) | Medium | Next sprint |
| P2-01: `app_factory.py` SRP violation | High (3-5 days) | Medium | Future sprint |
| P2-02: Divergent security header values | Low (2 hours) | Medium | Next sprint |
| P2-03: Stdlib logging in 13 files | Low (4 hours) | Medium | Next sprint |
| P2-04: `useAuth` data-fetching scope | Medium (1-2 days) | Medium | Future sprint |
| P2-05: Versioning strategy gap | High (1 week) | Low (current) / High (future) | Backlog |
| P2-06: TimescaleDB naming | Low (2 hours) | Low | Next sprint |
| P3-01–P3-05 | Each < 1 hour | Low | Cleanup sprint |
