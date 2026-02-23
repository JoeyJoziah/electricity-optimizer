# Backend Codemap

> Last updated: 2026-02-23 (multi-utility expansion)

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
│   ├── database.py                  # DatabaseManager: Neon PostgreSQL, Redis
│   └── secrets.py                   # SecretsManager: 1Password (prod) / env vars (dev)
│
├── api/
│   ├── dependencies.py              # FastAPI DI: auth, DB sessions, service factories
│   └── v1/
│       ├── prices.py                # Price endpoints (CRUD, SSE, refresh)
│       ├── suppliers.py             # Supplier listing, comparison, tariffs (DB-backed via SupplierRegistryRepository)
│       ├── regulations.py           # State regulation data (deregulation status, PUC info)
│       ├── billing.py               # Stripe checkout, portal, webhook, subscription
│       ├── auth.py                  # Signup, signin, OAuth, magic link, token refresh
│       ├── beta.py                  # Beta signup + welcome email
│       ├── compliance.py            # GDPR consent, data export, data deletion
│       ├── recommendations.py       # Switching & usage recommendations (stub)
│       ├── user.py                  # User preferences (stub)
│       └── internal.py              # API-key-protected: observe-forecasts, learn, observation-stats
│
├── routers/
│   └── predictions.py               # ML prediction endpoints (forecast, optimal-times, savings)
│
├── models/
│   ├── price.py                     # Price, PriceForecast, response schemas (utility_type field)
│   ├── supplier.py                  # Supplier, Tariff, TariffType, ContractLength (utility_types field)
│   ├── user.py                      # User, UserPreferences, UserCreate/Update
│   ├── utility.py                   # UtilityType enum, PriceUnit enum (multi-utility), labels/defaults
│   ├── region.py                    # Region enum (single source of truth, all 50 US states + intl)
│   └── consent.py                   # ConsentRecord, DeletionLog, GDPR request/response
│
├── repositories/
│   ├── base.py                      # BaseRepository[T], CachedRepository, error classes
│   ├── price_repository.py          # PriceRepository: CRUD, bulk_create, statistics (utility_type filter)
│   ├── supplier_repository.py       # SupplierRegistryRepository + StateRegulationRepository (DB-backed)
│   └── user_repository.py           # UserRepository: by-email, preferences, consent
│
├── services/
│   ├── price_service.py             # Business logic: comparison, forecast, optimal windows
│   ├── analytics_service.py         # Trends, volatility, peak hours, supplier comparison
│   ├── recommendation_service.py    # Switching + usage recommendations
│   ├── alert_service.py             # Price threshold alerts + email notifications
│   ├── email_service.py             # SendGrid (primary) + SMTP (fallback) + Jinja2
│   ├── stripe_service.py            # Checkout, portal, subscriptions, webhooks
│   ├── vector_store.py              # SQLite-backed vector store for price pattern matching
│   ├── hnsw_vector_store.py         # HNSW-indexed wrapper (O(log n) ANN, fallback to brute-force)
│   ├── observation_service.py       # Record forecasts, backfill actuals, track recommendation outcomes
│   └── learning_service.py          # Nightly learning: accuracy, bias detection, weight tuning
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
│       ├── base.py                  # PricingRegion (alias->Region), PriceData, APIError, RateLimitError
│       ├── service.py               # PricingService (unified multi-API interface)
│       ├── nrel.py                  # NREL client (US regions, all 50 state ZIPs)
│       ├── flatpeak.py              # Flatpeak client (UK/EU regions)
│       ├── iea.py                   # IEA client (global fallback)
│       ├── eia.py                   # EIA client (US: electricity, gas, heating oil, propane)
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
│   ├── 003_reconcile_schema.sql     # Schema reconciliation for consent_records/deletion_logs
│   ├── 004_performance_indexes.sql  # Compound + partial indexes for perf optimization
│   ├── 005_observation_tables.sql   # forecast_observations + recommendation_outcomes (adaptive learning)
│   └── 006_multi_utility_expansion.sql # utility_type enum, supplier_registry, state_regulations tables
│
├── templates/emails/
│   ├── welcome_beta.html            # Jinja2 beta welcome email
│   └── price_alert.html             # Jinja2 price alert notification
│
└── tests/
    ├── conftest.py                  # Shared fixtures
    ├── test_api.py                  # API endpoint tests
    ├── test_api_beta.py             # Beta API endpoint tests
    ├── test_api_billing.py          # Billing/Stripe endpoint tests (33 tests)
    ├── test_api_compliance.py       # Compliance API endpoint tests
    ├── test_api_predictions.py      # ML prediction endpoint tests
    ├── test_api_recommendations.py  # Recommendation endpoint tests
    ├── test_api_user.py             # User preference endpoint tests
    ├── test_auth.py                 # Authentication tests
    ├── test_config.py               # Settings validation tests
    ├── test_email_service.py        # Email service tests (SendGrid + SMTP)
    ├── test_models.py               # Pydantic model tests
    ├── test_services.py             # Service layer tests
    ├── test_repositories.py         # Repository tests
    ├── test_integrations.py         # Pricing API integration tests
    ├── test_security.py             # Security hardening tests
    ├── test_security_adversarial.py # Adversarial security tests (46 tests)
    ├── test_alert_service.py        # Alert service tests
    ├── test_stripe_service.py       # Stripe service tests
    ├── test_vector_store.py         # Vector store tests (VectorStore + HNSWVectorStore)
    ├── test_weather_service.py      # Weather service tests
    ├── test_gdpr_compliance.py      # GDPR compliance tests
    ├── test_multi_utility.py        # Multi-utility expansion tests (39 tests)
    └── test_performance.py          # Performance tests (16 tests)
```

## Application Lifecycle

**Entry Point:** `main.py` creates a FastAPI app with `lifespan` context manager.

```
Startup:
  1. db_manager.initialize()  -- Neon PostgreSQL, Redis (graceful degradation)
  2. Sentry SDK init (lazy import, if SENTRY_DSN configured)
  3. Mount middleware: CORS, GZip, SecurityHeaders, RateLimiting, BodySizeLimit,
     RequestTimeout, request-id/timing
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
| GET | `/` | None | List suppliers (paginated, filterable by region/utility_type/green) |
| GET | `/{supplier_id}` | None | Supplier details (UUID validated) |
| GET | `/{supplier_id}/tariffs` | None | Supplier tariff list (UUID validated) |
| GET | `/region/{region}` | None | Suppliers by region (region code validated) |
| GET | `/compare/{region}` | None | Compare suppliers in region |

**Data source:** `supplier_registry` table via `SupplierRegistryRepository`. Supports filtering
by `utility_type` (electricity, natural_gas, heating_oil, propane, community_solar), `green_only`,
and region. Input validation (`_validate_uuid`, `_validate_region_code`) rejects invalid IDs/regions
before DB access.

### State Regulations (`/api/v1/regulations`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | None | List state regulations (filterable by electricity/gas/oil/community_solar) |
| GET | `/{state_code}` | None | Get regulation details for a specific state |

**Data source:** `state_regulations` table via `StateRegulationRepository`. Returns deregulation
status, PUC contact info, licensing requirements, and comparison tool URLs.

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

### Internal (`/api/v1/internal`)

All endpoints require `X-API-Key` header (same key as `/prices/refresh`).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/observe-forecasts` | Backfill actual prices into unobserved forecast rows |
| POST | `/learn` | Run adaptive learning cycle (accuracy, bias, weight tuning, pruning) |
| GET | `/observation-stats` | Forecast accuracy metrics and hourly bias |

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
| GET | `/health/ready` | Readiness (Database, Redis) |
| GET | `/health/live` | Liveness probe |
| GET | `/metrics` | Prometheus metrics (API key required) |


## Key Modules

### config/settings.py

`Settings(BaseSettings)` with `get_settings() -> Settings` for DI.

| Category | Notable Fields |
|----------|---------------|
| App | `environment` (dev/staging/prod/test), `api_prefix`, `backend_port` |
| Database | `database_url` |
| Redis | `redis_url`, `redis_password` |
| Auth | `jwt_secret` (validated: 32+ chars in prod), `jwt_algorithm` (HS256) |
| API keys | `internal_api_key`, `flatpeak_api_key`, `nrel_api_key`, `iea_api_key`, `eia_api_key`, `openweathermap_api_key` |
| Email | `sendgrid_api_key`, `smtp_host/port/username/password`, `email_from_address/name` |
| Stripe | `stripe_secret_key`, `stripe_webhook_secret`, `stripe_price_pro`, `stripe_price_business` |
| ML | `model_path`, `model_forecast_hours` (24), `model_accuracy_threshold_mape` (10.0) |
| GDPR | `data_retention_days` (730), `consent_required`, `data_residency` |
| Features | `enable_auto_switching`, `enable_load_optimization`, `enable_real_time_updates` |
**Properties:** `is_production`, `is_development`, `effective_database_url`.

### config/database.py

`DatabaseManager` manages two backends:

| Backend | Client | Pool Config |
|---------|--------|-------------|
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

### services/vector_store.py + hnsw_vector_store.py

`VectorStore` -- AgentDB-inspired SQLite-backed vector database.
`HNSWVectorStore` -- HNSW-accelerated wrapper (O(log n) ANN search).

| Feature | VectorStore | HNSWVectorStore |
|---------|-------------|-----------------|
| Storage | SQLite at `.agentdb/electricity.db` | SQLite (durable) + HNSW (in-memory) |
| Dimensions | 24 (default) | 24 (default) |
| Search | Brute-force cosine similarity | HNSW ANN (fallback to brute-force) |
| Cache | In-memory LRU (500 entries) | HNSW index + SQLite metadata |
| Config | -- | `max_elements=10000`, `ef_search=50`, `M=16` |
| Learning | `record_outcome(vector_id, success)` | Delegates to VectorStore |
| Pruning | `prune(min_confidence, min_usage)` | Prunes + rebuilds HNSW index |

**HNSW fallback:** If `hnswlib` is not installed, `HNSWVectorStore` falls back to
brute-force `VectorStore.search()` transparently. HNSW index rebuilt from SQLite on startup.

**Domains:** `price_pattern`, `optimization`, `recommendation`, `bias_correction`.

**Helper functions:**
- `price_curve_to_vector(prices, target_dim=24)` -- resample + L2-normalize
- `appliance_config_to_vector(appliances, target_dim=24)` -- encode power/duration/start

### services/observation_service.py

`ObservationService` -- closes the feedback gap between predictions and actuals.

| Method | Purpose |
|--------|---------|
| `record_forecast()` | Batch INSERT forecast predictions into `forecast_observations` |
| `observe_actuals_batch()` | Match unobserved forecasts to `electricity_prices` by region+hour |
| `record_recommendation()` | Record recommendation served to user |
| `record_recommendation_response()` | Update outcome with user acceptance/savings |
| `get_forecast_accuracy()` | MAPE, RMSE, coverage for a region/timeframe |
| `get_hourly_bias()` | Per-hour AVG(predicted - actual) for bias correction |
| `get_model_accuracy_by_version()` | Accuracy breakdown by model version for weight tuning |

### services/learning_service.py

`LearningService` -- nightly adaptive learning cycle (inspired by AgentDB's NightlyLearner).

| Step | Method | Action |
|------|--------|--------|
| 1 | `compute_rolling_accuracy()` | MAPE/RMSE per model from `forecast_observations` |
| 2 | `detect_bias()` | Systematic over/under by hour-of-day |
| 3 | `update_ensemble_weights()` | Inverse-MAPE weighting -> Redis `model:ensemble_weights` |
| 4 | `store_bias_correction()` | Hourly correction vector -> vector store domain `bias_correction` |
| 5 | `prune_stale_patterns()` | Remove low-confidence vectors |

**Weight bounds:** 0.1 min, 0.8 max per model. Re-normalized after clamping.

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

### Region enum (models/region.py) -- Single Source of Truth

All 50 US states + DC + 16 international regions. Replaces the former duplicate
`PriceRegion` (price.py) and `PricingRegion` (base.py) enums.

US format: `us_XX` (e.g., `us_ct`, `us_tx`). International: ISO codes (`uk`, `de`, `fr`).
Backward-compatible aliases: `PriceRegion = Region`, `PricingRegion = Region`.

Helper properties: `is_us`, `state_code`, `from_state_code()`, `us_regions()`.

Constants: `DEREGULATED_ELECTRICITY_STATES` (18), `DEREGULATED_GAS_STATES` (16),
`HEATING_OIL_STATES` (9), `COMMUNITY_SOLAR_STATES` (28).

### UtilityType enum (models/utility.py)

5 utility types: `ELECTRICITY`, `NATURAL_GAS`, `HEATING_OIL`, `PROPANE`, `COMMUNITY_SOLAR`.

`PriceUnit` enum: `KWH`, `MWH`, `CENTS_KWH`, `THERM`, `MCF`, `MMBTU`, `CCF`, `GALLON`, `CREDIT_KWH`.

Lookup dicts: `UTILITY_DEFAULT_UNITS`, `UTILITY_LABELS`, `UNIT_LABELS`.

### Price model

Core fields: `id`, `region`, `supplier`, `price_per_kwh` (Decimal), `timestamp`,
`currency` (3-letter uppercase), `unit` (kWh/MWh), `is_peak`, `carbon_intensity`,
`energy_source`, `source_api`, `utility_type` (UtilityType, default: ELECTRICITY).

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
| `PriceRepository` | `Price` | `get_current_prices` (filters by utility_type), `get_latest_by_supplier`, `get_historical_prices`, `bulk_create`, `get_price_statistics` |
| `SupplierRegistryRepository` | `SupplierRegistry` | `list_suppliers` (paginated, filters: region/utility_type/green/active), `get_by_id`, `create`, `update` |
| `StateRegulationRepository` | `StateRegulation` | `list_deregulated` (filters: electricity/gas/oil/community_solar), `get_by_state` |
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
| `HNSWVectorStore` | VectorStore, hnswlib | HNSW-accelerated vector search (wraps VectorStore) |
| `ObservationService` | AsyncSession | Record forecasts, backfill actuals, track outcomes |
| `LearningService` | ObservationService, HNSWVectorStore, Redis | Nightly learning: accuracy, bias, weight tuning |
| `GDPRComplianceService` | ConsentRepo, UserRepo | Consent, export, deletion, retention |


## Middleware Stack

Applied in reverse order (last added = first executed):

1. **Request ID + Timing** -- UUID per request, X-Process-Time header (dev only)
2. **Metrics Auth** -- API key required for `/metrics` endpoint
3. **RequestTimeoutMiddleware** -- 30s timeout per request (SSE excluded)
4. **RequestBodySizeLimitMiddleware** -- 1 MB limit (Content-Length + chunked encoding)
5. **RateLimitMiddleware** -- Per-user/IP sliding window (Redis or in-memory fallback)
6. **SecurityHeadersMiddleware** -- CSP, HSTS, X-Frame-Options, Permissions-Policy
7. **GZipMiddleware** -- Compress responses > 1000 bytes
8. **CORSMiddleware** -- Origin regex restricted to `electricity-optimizer*.(vercel|onrender)`

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

14 tables (init_neon.sql + 002 + 005 + 006):

| Table | PK Type | Notes |
|-------|---------|-------|
| `users` | UUID | email UNIQUE, region indexed |
| `electricity_prices` | UUID | region + timestamp indexed, utility_type column (default: electricity) |
| `suppliers` | UUID | name UNIQUE, utility_types array column |
| `tariffs` | UUID | FK to suppliers, utility_type column |
| `supplier_registry` | UUID | DB-backed supplier data (replaces mock data). Columns: utility_types[], regions[], rating, green_energy_provider, metadata JSONB |
| `state_regulations` | VARCHAR(2) PK | Deregulation flags, PUC info, licensing requirements |
| `consent_records` | UUID | FK to users (ON DELETE CASCADE) |
| `deletion_logs` | UUID | Immutable (trigger blocks UPDATE/DELETE) |
| `beta_signups` | UUID | email UNIQUE |
| `auth_sessions` | UUID | FK to users |
| `login_attempts` | UUID | FK to users |
| `activity_logs` | UUID | FK to users |
| `forecast_observations` | UUID | predicted vs actual prices, partial index on unobserved |
| `recommendation_outcomes` | UUID | user acceptance + actual savings tracking |

**Custom types:** `utility_type` enum (electricity, natural_gas, heating_oil, propane, community_solar).


## Migrations

| File | Purpose |
|------|---------|
| `init_neon.sql` | Initial schema (7 tables, indexes, seed data) |
| `002_gdpr_auth_tables.sql` | GDPR consent/deletion tables, auth sessions, activity logs |
| `003_reconcile_schema.sql` | Reconcile column divergence between init and 002 |
| `004_performance_indexes.sql` | Compound index on `electricity_prices(region, supplier, timestamp DESC)`, partial index on `users(stripe_customer_id)` |
| `005_observation_tables.sql` | `forecast_observations` + `recommendation_outcomes` tables with indexes for adaptive learning |
| `006_multi_utility_expansion.sql` | `utility_type` enum, `utility_type` columns on prices/suppliers/tariffs, `supplier_registry` table, `state_regulations` table, CT seed data |

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
| redis[hiredis] | 5.0.1 | Redis client |
| stripe | >=7.0,<8.0 | Payment processing |
| PyJWT | >=2.8,<3.0 | JWT tokens |
| sendgrid | >=6.0,<7.0 | Email (primary) |
| aiosmtplib | >=3.0,<4.0 | Email (fallback) |
| jinja2 | >=3.0 | Email templates |
| structlog | 24.1.0 | Structured logging |
| sentry-sdk | 1.39.2 | Error tracking |
| prometheus-client | 0.19.0 | Metrics |
| numpy | 1.26.3 | Numerical (ML, vector store) |
| pandas | 2.1.4 | DataFrames (ML features) |
| scikit-learn | 1.4.0 | ML models |
| hnswlib | >=0.8.0 | HNSW vector index (optional, graceful fallback) |

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
       -> NREL (US regions) / Flatpeak (EU) / EIA (gas/oil/propane) -> IEA (fallback)
  -> Region enum (single source of truth)
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

### Adaptive Learning Loop (GitHub Actions, nightly)

```
Forecast Generation (POST /api/v1/ml/predict/price):
  -> generate_price_forecast()
  -> ObservationService.record_forecast()  (fire-and-forget)
  -> forecast_observations table

Observation Backfill (observe-forecasts.yml, every 6h + 30min):
  -> POST /api/v1/internal/observe-forecasts (X-API-Key)
  -> ObservationService.observe_actuals_batch()
  -> JOIN forecast_observations <-> electricity_prices
  -> SET actual_price, observed_at

Nightly Learning (nightly-learning.yml, 4AM UTC):
  -> POST /api/v1/internal/learn (X-API-Key)
  -> LearningService.run_full_cycle()
     1. compute_rolling_accuracy() -> MAPE/RMSE from observed forecasts
     2. detect_bias() -> hourly over/under-prediction
     3. update_ensemble_weights() -> inverse-MAPE -> Redis model:ensemble_weights
     4. store_bias_correction() -> bias vector -> vector store domain=bias_correction
     5. prune_stale_patterns() -> remove low-confidence vectors
  -> EnsemblePredictor reads weights from Redis on next inference
```

### Recommendation Confidence Adjustment

```
RecommendationService._compute_switching() / _compute_usage():
  -> price_curve_to_vector(prices)
  -> HNSWVectorStore.search(vector, domain="recommendation", k=3)
  -> If similar pattern found with high confidence: boost recommendation confidence
  -> If similar pattern found with low confidence: reduce recommendation confidence
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

**Test status:** 555 passing (as of 2026-02-23), 23 test files. 23 known test-ordering failures (pass individually).


## Scripts & Automation

### scripts/

| File | Purpose |
|------|---------|
| `notion_setup_schema.py` | Idempotent Notion database schema provisioning (13 properties). Supports `--dry-run` |
| `notion_sync.py` | Syncs TODO.md tasks to Notion (`--once` or continuous). Uses `database_id` query endpoint |
| `github_notion_sync.py` | Syncs GitHub issues/PRs to Notion roadmap (`--mode full` or `--mode event`) |
| `install-hooks.sh` | Installs git hooks from `.claude/hooks/board-sync/` templates |

### .claude/hooks/board-sync/

Local board-sync infrastructure. See [Infrastructure](./INFRASTRUCTURE.md#board-sync-local-automation) for full details.

| File | Purpose |
|------|---------|
| `sync-boards.sh` | Central orchestrator (lock, debounce, queue, GitHub + Notion sync) |
| `post-edit-sync.sh` | Claude PostToolUse hook — queues sync on Edit/Write/MultiEdit |
| `post-task-sync.sh` | Claude PostToolUse hook — drains queue on TaskUpdate |
| `session-end-sync.sh` | Claude Stop hook — foreground forced sync |
| `git-post-commit.sh` | Git hook template (background sync on commit) |
| `git-post-merge.sh` | Git hook template (background sync on merge) |
| `git-post-checkout.sh` | Git hook template (background sync on branch switch) |
