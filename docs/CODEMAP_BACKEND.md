# Backend Codemap

> Last updated: 2026-02-22

## Directory Structure

```
backend/
├── main.py                          # FastAPI app entry point, middleware, health checks
├── gunicorn_config.py               # Production WSGI config (Render free tier optimized)
├── requirements.txt                 # Python dependencies
├── pyproject.toml                   # Project metadata
│
├── config/
│   ├── settings.py                  # Pydantic-settings config (env vars), get_settings() DI
│   ├── database.py                  # DatabaseManager: Supabase, Neon PostgreSQL, Redis
│   └── secrets.py                   # SecretsManager: 1Password (prod) / env vars (dev)
│
├── api/
│   ├── dependencies.py              # FastAPI DI: auth, DB sessions, service factories
│   └── v1/
│       ├── prices.py                # Price endpoints (CRUD, SSE, refresh)
│       ├── suppliers.py             # Supplier listing, comparison, tariffs
│       ├── billing.py               # Stripe checkout, portal, webhook, subscription
│       ├── auth.py                  # Signup, signin, OAuth, magic link, token refresh
│       ├── beta.py                  # Beta signup + welcome email
│       ├── compliance.py            # GDPR consent, data export, data deletion
│       ├── recommendations.py       # Switching & usage recommendations (stub)
│       └── user.py                  # User preferences (stub)
│
├── routers/
│   └── predictions.py               # ML prediction endpoints (forecast, optimal-times, savings)
│
├── models/
│   ├── price.py                     # Price, PriceRegion, PriceForecast, response schemas
│   ├── supplier.py                  # Supplier, Tariff, TariffType, ContractLength
│   ├── user.py                      # User, UserPreferences, UserCreate/Update
│   └── consent.py                   # ConsentRecord, DeletionLog, GDPR request/response
│
├── repositories/
│   ├── base.py                      # BaseRepository[T], CachedRepository, error classes
│   ├── price_repository.py          # PriceRepository: CRUD, bulk_create, statistics
│   ├── supplier_repository.py       # SupplierRepository: by-region, tariffs, green filter
│   └── user_repository.py           # UserRepository: by-email, preferences, consent
│
├── services/
│   ├── price_service.py             # Business logic: comparison, forecast, optimal windows
│   ├── analytics_service.py         # Trends, volatility, peak hours, supplier comparison
│   ├── recommendation_service.py    # Switching + usage recommendations
│   ├── alert_service.py             # Price threshold alerts + email notifications
│   ├── email_service.py             # SendGrid (primary) + SMTP (fallback) + Jinja2
│   ├── stripe_service.py            # Checkout, portal, subscriptions, webhooks
│   └── vector_store.py              # SQLite-backed vector store for price pattern matching
│
├── auth/
│   ├── jwt_handler.py               # JWT create/verify/revoke (Redis-backed blacklist)
│   ├── middleware.py                 # get_current_user, require_permission dependencies
│   ├── password.py                  # Password validation, strength check, PBKDF2 hashing
│   └── supabase_auth.py             # Supabase Auth: signup, signin, OAuth, magic link
│
├── compliance/
│   ├── gdpr.py                      # GDPRComplianceService, DataRetentionService
│   └── repositories.py              # ConsentRecordORM, DeletionLogORM, SQLAlchemy mappers
│
├── integrations/
│   ├── weather_service.py           # OpenWeatherMap integration
│   └── pricing_apis/
│       ├── base.py                  # PricingRegion enum, PriceData, APIError, RateLimitError
│       ├── service.py               # PricingService (unified multi-API interface)
│       ├── nrel.py                  # NREL client (US regions, CT -> ZIP 06510)
│       ├── flatpeak.py              # Flatpeak client (UK/EU regions)
│       ├── iea.py                   # IEA client (global fallback)
│       ├── cache.py                 # PricingCache
│       ├── rate_limiter.py          # API-level RateLimiter
│       └── __init__.py              # create_pricing_service_from_settings()
│
├── middleware/
│   ├── rate_limiter.py              # Redis-backed sliding window rate limiting
│   └── security_headers.py          # CSP, HSTS, X-Frame-Options, etc.
│
├── migrations/
│   ├── init_neon.sql                # Initial schema: users, electricity_prices, suppliers,
│   │                                #   tariffs, consent_records, deletion_logs, beta_signups
│   ├── 002_gdpr_auth_tables.sql     # GDPR tables: auth_sessions, login_attempts, activity_logs
│   └── 003_reconcile_schema.sql     # Schema reconciliation for consent_records/deletion_logs
│
├── templates/emails/
│   ├── welcome_beta.html            # Jinja2 beta welcome email
│   └── price_alert.html             # Jinja2 price alert notification
│
└── tests/
    ├── conftest.py                  # Shared fixtures
    ├── test_api.py                  # API endpoint tests
    ├── test_auth.py                 # Authentication tests
    ├── test_config.py               # Settings validation tests
    ├── test_models.py               # Pydantic model tests
    ├── test_services.py             # Service layer tests
    ├── test_repositories.py         # Repository tests
    ├── test_integrations.py         # Pricing API integration tests
    ├── test_security.py             # Security hardening tests
    ├── test_alert_service.py        # Alert service tests
    ├── test_stripe_service.py       # Stripe service tests
    ├── test_weather_service.py      # Weather service tests
    └── test_gdpr_compliance.py      # GDPR compliance tests
```

## Application Lifecycle

**Entry Point:** `main.py` creates a FastAPI app with `lifespan` context manager.

```
Startup:
  1. db_manager.initialize()  -- Supabase, Neon PostgreSQL, Redis (graceful degradation)
  2. Sentry SDK init (lazy import, if SENTRY_DSN configured)
  3. Mount middleware: CORS, GZip, SecurityHeaders, RateLimiting, request-id/timing
  4. Mount routers (see API Routes below)

Shutdown:
  1. db_manager.close()  -- close all connection pools
```

**Production:** `gunicorn_config.py` -- 1 Uvicorn worker, 512MB RAM budget.

**Swagger/ReDoc:** Disabled in production (`docs_url=None if is_production`).


## API Routes

All routes use prefix `{settings.api_prefix}` (default `/api/v1`).

### Prices (`/api/v1/prices`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/current` | None | Current prices by region (fallback: mock + source=fallback) |
| GET | `/history` | None | Historical prices for a date range |
| GET | `/forecast` | None | ML-based price forecast (1-168 hours) |
| GET | `/compare` | None | Compare supplier prices in a region |
| GET | `/statistics` | None | Min/max/avg price stats |
| GET | `/optimal-windows` | None | Find cheapest usage windows |
| GET | `/trends` | None | Price trend analysis (direction, change %) |
| GET | `/peak-hours` | None | Peak vs off-peak hour analysis |
| POST | `/refresh` | X-API-Key | Trigger price sync from external APIs |
| GET | `/stream` | None | SSE real-time price updates |

**Production behavior:** All GET endpoints return HTTP 503 on DB errors instead of
mock data. The `source` field in responses indicates `"live"` or `"fallback"`.

### ML Predictions (`/api/v1/ml`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/predict/price` | None | Price forecast (CNN-LSTM ensemble or simulation) |
| POST | `/predict/optimal-times` | None | Optimal appliance scheduling slots |
| POST | `/predict/savings` | None | Savings estimate for multi-appliance optimization |
| GET | `/predict/model-info` | None | Model version, accuracy, last-updated |

**Model loading:** `_load_model()` tries `EnsemblePredictor` then `PricePredictor`
from `ml/`, caches in `_model_cache` dict. Falls back to `_simulate_forecast()`.
Multi-region currency: UK/EU -> GBP/EUR, default -> USD.

### Suppliers (`/api/v1/suppliers`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | None | List suppliers (paginated, filterable) |
| GET | `/{supplier_id}` | None | Supplier details |
| GET | `/{supplier_id}/tariffs` | None | Supplier tariff list |
| GET | `/region/{region}` | None | Suppliers by region |
| GET | `/compare/{region}` | None | Compare suppliers in region |

**Note:** Currently uses mock data (Eversource, UI, NextEra for CT region).

### Authentication (`/api/v1/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/signup` | None | Create account (12+ char password required) |
| POST | `/signin` | None | Email/password sign-in (sets refresh_token cookie) |
| POST | `/signin/oauth` | None | Initiate OAuth flow (google, github, apple...) |
| POST | `/signin/magic-link` | None | Send passwordless magic link |
| POST | `/signout` | JWT | Sign out + revoke tokens |
| POST | `/refresh` | None | Refresh access token (body or cookie) |
| GET | `/me` | JWT | Current user info |
| POST | `/password/check-strength` | None | Password strength assessment |

**Redirect URL validation:** OAuth and magic-link endpoints validate `redirect_url`
against an allowlist of domains (localhost, electricity-optimizer.app/vercel.app).

### Billing (`/api/v1/billing`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/checkout` | JWT | Create Stripe Checkout session (pro/business) |
| POST | `/portal` | JWT | Create Stripe Customer Portal session |
| GET | `/subscription` | JWT | Get current subscription status |
| POST | `/webhook` | Stripe sig | Handle Stripe webhook events |

**Tiers:** Free ($0), Pro ($4.99/mo), Business ($14.99/mo).
**Checkout URL validation:** `success_url`/`cancel_url` validated against allowed domains.

### Compliance (`/api/v1/compliance`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/consent` | JWT | Record consent decision (GDPR Art. 6, 7) |
| GET | `/gdpr/consents` | JWT | Get consent history |
| GET | `/gdpr/consents/status` | JWT | Current consent status per purpose |
| GET | `/gdpr/export` | JWT | Export all user data (GDPR Art. 15, 20) |
| DELETE | `/gdpr/delete-my-data` | JWT | Delete all user data (GDPR Art. 17) |
| POST | `/gdpr/withdraw-all-consents` | JWT | Withdraw all consents (GDPR Art. 21) |

### Beta (`/api/v1/beta`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/signup` | None | Beta registration + welcome email |
| GET | `/signups/count` | JWT | Beta signup count vs target |
| GET | `/signups/stats` | JWT | Signup stats (by supplier/source/bill) |
| POST | `/verify-code` | None | Verify beta access code |

### Other

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/recommendations/switching` | JWT | Switching recommendation (stub) |
| GET | `/recommendations/usage` | JWT | Usage timing recommendation (stub) |
| GET | `/user/preferences` | JWT | Get user preferences (stub) |
| POST | `/user/preferences` | JWT | Update user preferences (stub) |

### Health / Meta (no prefix)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API info (name, version, env) |
| GET | `/health` | Health check (uptime, DB status) |
| GET | `/health/ready` | Readiness (Redis, TimescaleDB, Supabase) |
| GET | `/health/live` | Liveness probe |
| GET | `/metrics` | Prometheus metrics (ASGI mount) |


## Key Modules

### config/settings.py

`Settings(BaseSettings)` with `get_settings() -> Settings` for DI.

| Category | Notable Fields |
|----------|---------------|
| App | `environment` (dev/staging/prod/test), `api_prefix`, `backend_port` |
| Database | `supabase_url`, `supabase_service_key`, `database_url`, `timescaledb_url` |
| Redis | `redis_url`, `redis_password` |
| Auth | `jwt_secret` (validated: 32+ chars in prod), `jwt_algorithm` (HS256) |
| API keys | `internal_api_key`, `flatpeak_api_key`, `nrel_api_key`, `iea_api_key`, `openweathermap_api_key` |
| Email | `sendgrid_api_key`, `smtp_host/port/username/password`, `email_from_address/name` |
| Stripe | `stripe_secret_key`, `stripe_webhook_secret`, `stripe_price_pro`, `stripe_price_business` |
| ML | `model_path`, `model_forecast_hours` (24), `model_accuracy_threshold_mape` (10.0) |
| GDPR | `data_retention_days` (730), `consent_required`, `data_residency` |
| Features | `enable_auto_switching`, `enable_load_optimization`, `enable_real_time_updates` |
| Celery | `celery_broker_url`, `celery_result_backend` (auto-set from `redis_url`; **inactive**) |

**Properties:** `is_production`, `is_development`, `effective_database_url`.

### config/database.py

`DatabaseManager` manages three backends:

| Backend | Client | Pool Config |
|---------|--------|-------------|
| Supabase | `supabase.Client` | Single client via `create_client()` |
| Neon PostgreSQL | SQLAlchemy `AsyncEngine` + optional `asyncpg.Pool` | pool_size=2, max_overflow=3, pool_recycle=300 |
| Redis | `redis.asyncio.Redis` | max_connections=10, socket_keepalive=True |

**Neon handling:** SSL auto-required for `neon.tech` URLs; `sslmode`/`channel_binding`
params stripped from URL (asyncpg uses connect_args). Raw-query asyncpg pool skipped
for Neon; uses SQLAlchemy-only path.

### auth/jwt_handler.py

`JWTHandler` with Redis-backed JTI blacklist.

- **Access tokens:** 15 min expiry, includes `sub`, `email`, `scopes`, `type`, `jti`, `iss`
- **Refresh tokens:** 7 day expiry
- **Revocation:** `revoke_token(jti, ttl_seconds)` writes `jwt:revoked:<jti>` to Redis
  with TTL matching token remaining lifetime; auto-expires
- **Fallback:** In-memory `Set[str]` when Redis unavailable (no cross-process revocation)
- **clear_revoked_tokens():** Uses SCAN to delete `jwt:revoked:*` keys (test use)

### services/vector_store.py

`VectorStore` -- AgentDB-inspired SQLite-backed vector database.

| Feature | Detail |
|---------|--------|
| Storage | SQLite at `.agentdb/electricity.db` |
| Dimensions | 24 (default, configurable) |
| Search | Cosine similarity with min_similarity threshold |
| Cache | In-memory LRU (`OrderedDict`, 500 entries) |
| Domains | `price_pattern`, `optimization`, `recommendation` |
| Learning | `record_outcome(vector_id, success)` updates confidence via success_rate |
| Pruning | `prune(min_confidence, min_usage)` removes low-quality vectors |

**Helper functions:**
- `price_curve_to_vector(prices, target_dim=24)` -- resample + L2-normalize
- `appliance_config_to_vector(appliances, target_dim=24)` -- encode power/duration/start

### services/stripe_service.py

`StripeService` handles subscription lifecycle.

| Operation | Method | Stripe API |
|-----------|--------|-----------|
| Checkout | `create_checkout_session()` | `stripe.checkout.Session.create` |
| Portal | `create_customer_portal_session()` | `stripe.billing_portal.Session.create` |
| Status | `get_subscription_status()` | `stripe.Subscription.list` |
| Cancel | `cancel_subscription()` | `stripe.Subscription.cancel` / `.modify` |
| Webhook | `handle_webhook_event()` | Processes checkout.session.completed, subscription.updated/deleted, invoice.payment_failed |


## Models

### PriceRegion enum (models/price.py)

14 regions: `uk`, `germany`, `france`, `spain`, `italy`, `netherlands`, `belgium`,
`us_ct`, `us_ca`, `us_tx`, `us_ny`, `us_fl`, `australia`, `japan`

### PricingRegion enum (integrations/pricing_apis/base.py)

Used for external API routing:

| PricingRegion | API Client | Fallback |
|---------------|-----------|----------|
| US_CT, US_CA, US_NY | NREL | IEA |
| UK, GERMANY, FRANCE | Flatpeak | IEA |
| Other | IEA | -- |

### Price model

Core fields: `id`, `region`, `supplier`, `price_per_kwh` (Decimal), `timestamp`,
`currency` (3-letter uppercase), `unit` (kWh/MWh), `is_peak`, `carbon_intensity`,
`energy_source`, `source_api`.

Response models: `PriceResponse`, `PriceListResponse`, `PriceHistoryResponse`,
`PriceForecastResponse`, `PriceComparisonResponse` -- all include `source: Optional[str]`.

### User model

Fields: `id`, `email`, `name`, `region`, `subscription_tier` (free/pro/business),
`stripe_customer_id`, `preferences` (JSON dict), `current_supplier`, `current_tariff`,
GDPR fields (`consent_given`, `consent_date`, `data_processing_agreed`).

### Consent models

`ConsentPurpose` enum: `data_processing`, `marketing`, `analytics`, `price_alerts`,
`optimization`, `third_party_sharing`.

`ConsentRecord`: immutable audit record with `ip_address`, `user_agent`, `consent_version`.

`DeletionLog`: immutable deletion audit with `deletion_type` (full/anonymization),
`data_categories_deleted`, `legal_basis`.


## Repositories

All extend `BaseRepository[T]` (abstract generic with CRUD + list + count).

| Repository | Model | Key Methods |
|------------|-------|-------------|
| `PriceRepository` | `Price` | `get_current_prices`, `get_latest_by_supplier`, `get_historical_prices`, `bulk_create`, `get_price_statistics` |
| `SupplierRepository` | `Supplier` | `list_by_region`, `get_tariffs`, `create_tariff`, `get_green_suppliers` |
| `UserRepository` | `User` | `get_by_email`, `update_preferences`, `update_last_login`, `record_consent` |
| `ConsentRepository` | `ConsentRecord` | `get_by_user_and_purpose`, `get_latest_by_user_and_purpose`, `delete_by_user_id` |
| `DeletionLogRepository` | `DeletionLog` | `create`, `get_by_user_id` (immutable -- no update/delete) |

`PriceRepository` has built-in Redis caching (60s TTL for current prices).


## Services

| Service | Dependencies | Purpose |
|---------|-------------|---------|
| `PriceService` | PriceRepository, Redis | Price queries, comparison, forecast, optimal windows |
| `AnalyticsService` | PriceRepository | Trends, volatility, peak hours, supplier comparison |
| `RecommendationService` | PriceService, UserRepository | Switching + usage recommendations |
| `AlertService` | EmailService | Threshold checking + alert emails |
| `EmailService` | Settings | SendGrid primary, SMTP fallback, Jinja2 templates |
| `StripeService` | Settings | Checkout, portal, subscriptions, webhooks |
| `VectorStore` | SQLite, numpy | Price pattern matching, optimization caching |
| `GDPRComplianceService` | ConsentRepo, UserRepo | Consent, export, deletion, retention |


## Middleware Stack

Applied in reverse order (last added = first executed):

1. **Request ID + Timing** -- UUID per request, X-Process-Time header
2. **RateLimitMiddleware** -- Per-user/IP sliding window (Redis or in-memory fallback)
3. **SecurityHeadersMiddleware** -- CSP, HSTS, X-Frame-Options, Permissions-Policy
4. **GZipMiddleware** -- Compress responses > 1000 bytes
5. **CORSMiddleware** -- Origin regex restricted to `electricity-optimizer*.(vercel|onrender)`

Excluded from rate limiting: `/health`, `/health/live`, `/health/ready`, `/metrics`.


## Authentication & Authorization

Two auth mechanisms:

1. **JWT Bearer Token** (user auth):
   - `get_current_user` dependency validates token via `jwt_handler.verify_token()`
   - Checks revocation via Redis-backed JTI blacklist
   - `get_current_user_optional` returns `None` if missing/invalid

2. **X-API-Key Header** (service-to-service):
   - `verify_api_key` dependency uses `hmac.compare_digest` (constant-time)
   - Validates against `settings.internal_api_key`
   - Used by `/prices/refresh` endpoint (GitHub Actions)

**Authorization:** `require_permission(scope)`, `require_permissions([...])`,
`require_any_permission([...])` factory functions for scope-based access control.


## Database (Neon PostgreSQL)

10 tables (init_neon.sql + 002_gdpr_auth_tables.sql):

| Table | PK Type | Notes |
|-------|---------|-------|
| `users` | UUID | email UNIQUE, region indexed |
| `electricity_prices` | UUID | region + timestamp indexed |
| `suppliers` | UUID | name UNIQUE |
| `tariffs` | UUID | FK to suppliers |
| `consent_records` | UUID | FK to users (ON DELETE CASCADE) |
| `deletion_logs` | UUID | Immutable (trigger blocks UPDATE/DELETE) |
| `beta_signups` | UUID | email UNIQUE |
| `auth_sessions` | UUID | FK to users |
| `login_attempts` | UUID | FK to users |
| `activity_logs` | UUID | FK to users |


## Migrations

| File | Purpose |
|------|---------|
| `init_neon.sql` | Initial schema (7 tables, indexes, seed data) |
| `002_gdpr_auth_tables.sql` | GDPR consent/deletion tables, auth sessions, activity logs |
| `003_reconcile_schema.sql` | Reconcile column divergence between init and 002 (renames `metadata` -> `metadata_json`, `timestamp` -> `deleted_at`, `deleted_categories` -> `data_categories_deleted` with TEXT[] -> JSONB conversion, adds missing FK/indexes/columns) |

**003 details:** Safe to re-run (IF NOT EXISTS / IF EXISTS guards). Temporarily
disables `tr_prevent_deletion_log_update` trigger for schema backfill operations.


## External Dependencies

### Runtime

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.109.0 | Web framework |
| uvicorn | 0.27.0 | ASGI server |
| pydantic | 2.5.3 | Data validation |
| pydantic-settings | 2.1.0 | Env-based config |
| asyncpg | 0.29.0 | PostgreSQL async driver |
| sqlalchemy[asyncio] | 2.0.25 | ORM |
| supabase | >=2.3,<3.0 | Supabase client |
| redis[hiredis] | 5.0.1 | Redis client |
| stripe | >=7.0,<8.0 | Payment processing |
| python-jose | 3.3.0 | JWT tokens |
| sendgrid | >=6.0,<7.0 | Email (primary) |
| aiosmtplib | >=3.0,<4.0 | Email (fallback) |
| jinja2 | >=3.0 | Email templates |
| structlog | 24.1.0 | Structured logging |
| sentry-sdk | 1.39.2 | Error tracking |
| prometheus-client | 0.19.0 | Metrics |
| numpy | 1.26.3 | Numerical (ML, vector store) |
| pandas | 2.1.4 | DataFrames (ML features) |
| scikit-learn | 1.4.0 | ML models |
| celery[redis] | 5.3.6 | **Inactive** -- no tasks module defined |

### Dev/Test

| Package | Purpose |
|---------|---------|
| pytest + pytest-asyncio + pytest-cov | Testing |
| faker | Test data generation |
| black, isort, flake8, mypy | Code quality |


## Data Flow

### Price Refresh (GitHub Actions, every 6 hours)

```
GitHub Actions -> POST /api/v1/prices/refresh (X-API-Key header)
  -> create_pricing_service_from_settings()
  -> PricingService.compare_prices([US_CT, US_NY, US_CA, UK, DE, FR])
       -> NREL (US regions) / Flatpeak (EU) -> IEA (fallback)
  -> Map PricingRegion -> PriceRegion (db_region)
  -> PriceRepository.bulk_create(prices)
  -> AlertService.check_thresholds() (planned)
```

### User Request Flow

```
Client -> FastAPI (middleware: rate_limit -> security_headers -> CORS)
  -> Router (JWT validation via get_current_user)
  -> Service layer (business logic)
  -> Repository (SQLAlchemy async + Redis cache)
  -> Neon PostgreSQL
```

### SSE Price Stream

```
Client -> GET /api/v1/prices/stream?region=us_ct&interval=30
  -> StreamingResponse(event_stream())
  -> _price_event_generator() polls every {interval} seconds
  -> Emits JSON price events via text/event-stream
  -> Checks request.is_disconnected() to stop
```


## Security

| Area | Implementation |
|------|----------------|
| JWT secrets | Validated in production (32+ chars, not default) |
| CORS | Origin regex scoped to `electricity-optimizer*` |
| Rate limiting | Per-minute (100) + per-hour (1000), Redis sliding window |
| Login lockout | 5 failed attempts -> 15 min lockout |
| Password | 12+ chars, uppercase+lowercase+digit+special required |
| API key | Constant-time comparison (`hmac.compare_digest`) |
| Webhooks | Stripe signature verification |
| Redirect URLs | Allowlist validation on OAuth/checkout/portal URLs |
| Validation errors | Input values stripped from 422 responses |
| Production errors | Generic 500 messages (no stack traces) |
| Headers | CSP, HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy |
| Token revocation | Redis JTI blacklist with auto-expiring TTL |


## Test Commands

```bash
# Run all backend tests (use venv)
.venv/bin/python -m pytest backend/tests/ -v

# Run specific test file
.venv/bin/python -m pytest backend/tests/test_security.py -v

# Run with coverage
.venv/bin/python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

**Test status:** 338 passing (as of 2026-02-12), 13 test files.
