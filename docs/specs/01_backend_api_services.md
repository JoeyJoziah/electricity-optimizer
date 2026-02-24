# Backend API & Services Specification

> SPARC Phase: Specification | Version: 1.0.0 | Updated: 2026-02-22
>
> **Note (2026-02-24):** This spec predates the refactoring roadmap (2026-02-23). Key changes since: `jwt_handler.py` deleted (replaced by Neon Auth sessions), TimescaleDB replaced by Neon PostgreSQL only, health/ready checks updated. See [REFACTORING_ROADMAP.md](REFACTORING_ROADMAP.md).

## 1. System Overview

### 1.1 Architecture

```
Clients (Next.js, GitHub Actions, Stripe)
  -> [Middleware] RateLimit -> SecurityHeaders -> GZip -> CORS -> RequestID
  -> [API Layer] Routers + Pydantic models
  -> [Service Layer] PriceService, StripeService, AlertService, VectorStore
  -> [Repository Layer] SQLAlchemy ORM (async)
  -> [Data Stores] Neon PostgreSQL | Redis | SQLite (vectors)
```

### 1.2 Tech Stack

FastAPI + Uvicorn, Python 3.12 (3.11 in CI), SQLAlchemy 2.x async + asyncpg, Pydantic v2,
PyJWT (HS256), Neon PostgreSQL, Redis (aioredis), Stripe SDK, NumPy/Pandas
CNN-LSTM ensemble, Prometheus + Sentry + structlog, SendGrid/SMTP email.

### 1.3 Route Registration (main.py)

All API routers mounted under `settings.api_prefix` (`/api/v1`):
`prices`, `billing`, `ml` (predictions), `suppliers`, `auth`, `beta`,
`compliance`, `user`, `recommendations`. Health/metrics at root level.

---

## 2. API Endpoints

Auth: `none`=public, `jwt`=Bearer, `api-key`=X-API-Key header.

### 2.1 Health & Infrastructure (root)

| Method | Path | Auth | Returns |
|--------|------|------|---------|
| GET | `/` | none | API metadata; hides `/docs` link in prod |
| GET | `/health` | none | `{ status, version, environment, uptime_seconds, database_status }` |
| GET | `/health/ready` | none | Checks Redis + TimescaleDB + Neon PostgreSQL; 503 if any fail |
| GET | `/health/live` | none | `{ status: "alive" }` |
| GET | `/metrics` | none | Prometheus ASGI sub-app |

### 2.2 Prices (`/api/v1/prices`)

| Method | Path | Auth | Params | Fallback |
|--------|------|------|--------|----------|
| GET | `/current` | none | `region` (req), `supplier?`, `limit?` 1-100 | mock/503 |
| GET | `/history` | none | `region`, `days?` 1-365 | mock/503 |
| GET | `/forecast` | none | `region`, `hours?` 1-168, `supplier?` | mock/503 |
| GET | `/compare` | none | `region` | mock/503 |
| GET | `/statistics` | none | `region`, `days?` 1-365 | mock/503 |
| GET | `/optimal-windows` | none | `region`, `duration_hours?` 1-12, `within_hours?` 1-48 | mock/503 |
| GET | `/trends` | none | `region`, `days?` 1-90 | mock/503 |
| GET | `/peak-hours` | none | `region`, `days?` 1-30 | mock/503 |
| POST | `/refresh` | api-key | -- | errors array |
| GET | `/stream` | none | `region`, `interval?` 10-300s | SSE |

**Production fallback pattern (every GET endpoint):**
```
TRY: result = fetch_from_db(params); RETURN {result, source: "live"}
CATCH: IF production: RAISE 503; ELSE: RETURN {mock_data, source: "fallback"}
```

**POST `/refresh` pseudocode:**
```
verify_api_key(X-API-Key)
regions = [US_CT, US_NY, US_CA, UK, GERMANY, FRANCE]
ASYNC WITH pricing_service:
    comparison = compare_prices(regions)
    FOR (region, price_data): convert to kWh, map region, batch Price records
    synced = repo.bulk_create(batch)
RETURN { status, synced_records, regions_covered, errors }
```

**SSE format:** `data: {"region","supplier","price_per_kwh","currency","is_peak","timestamp"}\n\n`

### 2.3 Billing (`/api/v1/billing`)

| Method | Path | Auth | Body/Headers |
|--------|------|------|-------------|
| POST | `/checkout` | jwt | `{ tier: "pro"\|"business", success_url, cancel_url }` |
| POST | `/portal` | jwt | `{ return_url }` |
| GET | `/subscription` | jwt | -- |
| POST | `/webhook` | signature | Raw body + `stripe-signature` header |

**Redirect URL validation:** allowed domains = `electricity-optimizer.vercel.app`,
`electricity-optimizer-frontend.onrender.com`, `localhost` (subdomains accepted).

**Responses:** `CheckoutSessionResponse{session_id, checkout_url}`,
`SubscriptionStatusResponse{tier, status, has_active_subscription, current_period_end?, cancel_at_period_end?}`,
`WebhookEventResponse{received, event_id}`.

### 2.4 ML Predictions (`/api/v1/ml`)

| Method | Path | Body |
|--------|------|------|
| POST | `/predict/price` | `{ region, hours_ahead 1-168, include_confidence }` |
| POST | `/predict/optimal-times` | `{ region, duration_hours, earliest_start?, latest_end?, num_slots 1-10 }` |
| POST | `/predict/savings` | `{ region, appliances: [{ name, power_kw, duration_hours, earliest_start, latest_end, continuous }] }` |
| GET | `/predict/model-info` | -- |

**Forecast pseudocode:**
```
model = load_cached_or_from_disk(ensemble -> single -> None)
IF model: features = last 168 DB prices -> model.predict(horizon) -> predictions
ELSE: sinusoidal simulation (base=0.20, amplitude=0.05, noise=N(0,0.01))
Cache result in Redis (TTL 1h)
```

**Optimal times:** sliding window over 24h forecast, sort by avg_price, return top N ranked slots with savings_percent.

---

## 3. Services Layer

### 3.1 StripeService (`services/stripe_service.py`)

Tiers: Free ($0), Pro ($4.99/mo), Business ($14.99/mo).

```
create_checkout_session(user_id, email, tier, urls, customer_id?):
    price_id = settings.stripe_price_{tier}
    stripe.checkout.Session.create(mode="subscription", metadata={user_id,tier})

verify_webhook_signature(payload, sig):
    stripe.Webhook.construct_event(payload, sig, webhook_secret)

handle_webhook_event(event):
    MATCH event.type:
        "checkout.session.completed" -> activate_subscription
        "customer.subscription.updated" -> update_subscription (tier or "free")
        "customer.subscription.deleted" -> deactivate (tier="free")
        "invoice.payment_failed" -> payment_failed notification

cancel_subscription(sub_id, immediately?):
    IF immediately: stripe.Subscription.cancel()
    ELSE: stripe.Subscription.modify(cancel_at_period_end=True)
```

### 3.2 AlertService (`services/alert_service.py`)

```
check_thresholds(prices, thresholds):
    FOR threshold, price WHERE region matches:
        IF price <= threshold.price_below: emit "price_drop"
        IF price >= threshold.price_above: emit "price_spike"

check_optimal_windows(forecast, thresholds, window_hours=2):
    sliding window finds cheapest consecutive block
    estimated_savings = (overall_avg - best_avg) * window_hours
    emit "optimal_window" for users with notify_optimal_windows=True

send_alerts(triggered): render HTML email (template or fallback), send via EmailService
```

### 3.3 VectorStore (`services/vector_store.py`)

SQLite-backed, numpy cosine similarity, LRU cache (500 entries, thread-safe).

```
insert(domain, vector[24], metadata, confidence) -> id (SHA256[:16])
    auto-resize vector (pad/truncate to dimension)

search(query, domain?, k=5, min_similarity=0.7):
    brute-force cosine similarity over all stored vectors
    increment usage_count for returned results

record_outcome(id, success): update confidence = success_count / usage_count
prune(min_confidence=0.3): DELETE low-quality vectors

Helpers: price_curve_to_vector(prices) -> resample + L2-normalize
         appliance_config_to_vector(appliances) -> encode power/duration/time
```

---

## 4. Authentication Flow

### 4.1 JWT Handler (`auth/jwt_handler.py`)

Global singleton: `jwt_handler` -- HS256, 15-min access, 7-day refresh.

```
create_access_token(user_id, email, scopes):
    {sub, email, scopes, type:"access", iat, exp:+15min, jti:uuid4, iss}

create_refresh_token(user_id):
    {sub, type:"refresh", iat, exp:+7d, jti:uuid4, iss}

verify_token(token, expected_type):
    decode -> assert type matches -> assert not revoked -> return payload
    Errors: TokenExpiredError, InvalidTokenError, TokenRevokedError

revoke_token(jti, ttl?):
    Redis: SETEX "jwt:revoked:{jti}" ttl "1" (auto-expires)
    Fallback: in-memory Set (no TTL, process-lifetime)

is_token_revoked(jti): Redis EXISTS || in-memory lookup
```

### 4.2 Dependency Injection (`api/dependencies.py`)

```
get_current_user(Bearer token): decode JWT -> TokenData{user_id, email, scopes} | 401
get_current_user_optional(token): same but returns None on failure
verify_api_key(X-API-Key): hmac.compare_digest against INTERNAL_API_KEY | 401/503
require_scope(name): get_current_user -> check scope in scopes | 403
```

---

## 5. Configuration (`config/settings.py`)

### 5.1 Key Environment Variables

| Category | Variables |
|----------|----------|
| App | `ENVIRONMENT`, `BACKEND_PORT`, `CORS_ORIGINS` |
| Database | `DATABASE_URL` / `TIMESCALEDB_URL` |
| Cache | `REDIS_URL`, `REDIS_PASSWORD` |
| Auth | `JWT_SECRET` (min 32 chars prod), `JWT_ALGORITHM`, `INTERNAL_API_KEY` |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO/BUSINESS` |
| APIs | `FLATPEAK_API_KEY`, `NREL_API_KEY`, `OPENWEATHERMAP_API_KEY`, etc. |
| Email | `SENDGRID_API_KEY`, `SMTP_HOST/PORT/USERNAME/PASSWORD` |
| ML | `MODEL_PATH`, `MODEL_FORECAST_HOURS` (24), `MODEL_RETRAIN_INTERVAL_DAYS` (7) |
| GDPR | `DATA_RETENTION_DAYS` (730), `CONSENT_REQUIRED`, `DATA_RESIDENCY` |
| Monitor | `SENTRY_DSN`, `PROMETHEUS_PORT` |

### 5.2 Feature Flags

`ENABLE_AUTO_SWITCHING` (false), `ENABLE_LOAD_OPTIMIZATION` (true), `ENABLE_REAL_TIME_UPDATES` (true).

### 5.3 Validators

- `jwt_secret`: blocks known defaults (`"changeme"`, etc.) and requires 32+ chars in production.
- `environment`: must be `development|staging|production|test`.
- `cors_origins`: parses comma-separated string or JSON list.

### 5.4 Rate Limits

100/min, 1000/hour per user/IP. Login lockout: 5 failures -> 15-min lock.

---

## 6. Error Handling

### 6.1 Production vs Development

| Scenario | Production | Development |
|----------|-----------|-------------|
| DB unavailable at startup | Crash (raises) | Warns, continues |
| Price query fails | 503 | Mock data (`source:"fallback"`) |
| Unhandled exception | 500 generic message | 500 with actual error |
| Validation error | 422 sanitized (no `input` field) | Same |
| Swagger/ReDoc | Disabled | `/docs`, `/redoc` |
| HSTS | 1-year max-age | Omitted |
| Request logging | Slow/error only (>1s or >=400) | All requests |

### 6.2 Graceful Degradation

```
Database: available -> live data | unavailable -> prod:503, dev:mock
Redis: available -> cache/rate-limit/JWT revocation | unavailable -> in-memory fallback
ML Model: ensemble -> single model -> sinusoidal simulation
Stripe: configured -> full billing | unconfigured -> 503 on billing endpoints
```

### 6.3 Middleware Errors

429 with `Retry-After` (rate limit), 401 (missing/invalid API key), 503 (API key not configured).
Excluded from rate limiting: `/health`, `/health/live`, `/health/ready`, `/metrics`.

---

## 7. TDD Anchors

### 7.1 Prices

```
TEST current_prices_live: mock service -> GET /current?region=us_ct -> 200, source="live"
TEST current_prices_503_prod: env=production, service raises -> 503
TEST current_prices_fallback_dev: env=development, service raises -> 200, source="fallback"
TEST refresh_rejects_missing_key: POST /refresh (no header) -> 401
TEST refresh_rejects_wrong_key: POST /refresh (bad key) -> 401
TEST stream_sse_content_type: GET /stream -> content-type "text/event-stream"
TEST supplier_filter_single: GET /current?supplier=X -> response.price set, response.prices null
```

### 7.2 Billing

```
TEST checkout_requires_auth: no Bearer -> 401
TEST checkout_rejects_bad_tier: tier="enterprise" -> 422
TEST checkout_rejects_bad_domain: success_url="https://evil.com" -> 422
TEST checkout_503_unconfigured: no STRIPE_SECRET_KEY -> 503
TEST webhook_rejects_no_sig: no stripe-signature -> 400
TEST webhook_processes_checkout: mock event -> 200, received=true
TEST subscription_free_default: no customer_id -> tier="free", has_active=false
```

### 7.3 ML Predictions

```
TEST forecast_length: POST /predict/price {hours_ahead:24} -> 24 predictions
TEST forecast_cache: second identical call served from Redis
TEST optimal_times_ranked: response slots ranked 1..N, ascending price
TEST savings_positive: optimized_cost <= unoptimized_cost
```

### 7.4 JWT Authentication

```
TEST access_token_claims: create -> decode -> sub, type="access", jti present
TEST expired_token: negative expiry -> TokenExpiredError
TEST wrong_type_rejected: refresh token verified as "access" -> InvalidTokenError
TEST revoke_then_verify: revoke(jti) -> verify raises TokenRevokedError
TEST revoke_memory_fallback: no Redis -> revoke uses in-memory set, still works
```

### 7.5 AlertService

```
TEST price_drop_triggered: price <= threshold.price_below -> alert_type="price_drop"
TEST region_mismatch_skipped: different regions -> no alerts
TEST optimal_window_found: sliding window finds cheapest block, estimated_savings > 0
TEST send_alerts_count: mock email success/failure -> returns correct count
```

### 7.6 VectorStore

```
TEST insert_search_roundtrip: insert vec -> search same vec -> similarity > 0.99
TEST min_similarity_filter: orthogonal vectors -> 0 results at threshold 0.9
TEST record_outcome_confidence: success -> confidence = success_count/usage_count
TEST prune_removes_low_quality: confidence=0.1 pruned, confidence=0.9 kept
TEST price_curve_unit_vector: output shape (24,), L2 norm ~= 1.0
```

### 7.7 Middleware

```
TEST rate_limit_allows_within: 5 requests under limit of 5 -> all allowed
TEST rate_limit_blocks_over: 3rd request with limit=2 -> blocked
TEST login_lockout: 5 failures -> is_locked_out=true
TEST security_headers_present: GET /health -> X-Frame-Options, X-Content-Type-Options, CSP
TEST api_no_cache: GET /api/v1/... -> Cache-Control: no-store
TEST hsts_prod_only: dev -> no HSTS header; prod -> HSTS present
```

---

## Appendix: Pool Sizing (free tier)

| Pool | Size | Overflow | Recycle |
|------|------|----------|---------|
| SQLAlchemy | 2 | 3 | 300s |
| asyncpg (non-Neon) | 1-5 | -- | 30s cmd timeout |
| Redis | 10 max | -- | 5s connect timeout |
