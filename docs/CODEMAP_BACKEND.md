# Backend Codemap

> Last updated: 2026-03-13 (Wave 5 complete: community features, tabbed dashboard, security hardening. Test count: 2,339. Migrations: 49. Tables: 50 = 41 public + 9 neon_auth. Services: 52. API routes: 38 files.)

## Directory Structure

```
backend/
├── main.py                          # FastAPI app entry point, 27 lines (lifespan only); app created via app_factory.py
├── app_factory.py                   # create_app() factory: middleware, routers, health endpoints
├── gunicorn_config.py               # Production WSGI config (Render free tier optimized)
├── requirements.txt                 # Python dependencies
├── requirements.lock                # Pinned lockfile for reproducible builds
├── pyproject.toml                   # Project metadata
│
├── config/
│   ├── settings.py                  # Pydantic-settings config (env vars), get_settings() DI
│   ├── database.py                  # DatabaseManager: Neon PostgreSQL, Redis
│   └── secrets.py                   # SecretsManager: 27 SECRET_MAPPINGS, 1Password (prod) / env vars (dev)
│
├── api/
│   ├── dependencies.py              # FastAPI DI: auth, DB sessions, service factories; require_tier() factory (_TIER_ORDER: free=0, pro=1, business=2) for revenue gating on 7 endpoints
│   └── v1/
│       ├── prices.py                # Price CRUD endpoints (current, history, forecast, compare, refresh)
│       ├── prices_analytics.py      # Price analytics (statistics, optimal-windows, trends, peak-hours)
│       ├── prices_sse.py            # SSE streaming (real DB prices via PriceService, connection tracking)
│       ├── suppliers.py             # Supplier listing, comparison, tariffs (DB-backed via SupplierRegistryRepository)
│       ├── regulations.py           # State regulation data (deregulation status, PUC info)
│       ├── billing.py               # Stripe checkout, portal, webhook, subscription
│       ├── auth.py                  # GET /me + POST /password/check-strength (Neon Auth)
│       ├── beta.py                  # Beta signup + welcome email
│       ├── compliance.py            # GDPR consent, data export, data deletion
│       ├── recommendations.py       # Switching, usage, & daily recommendations (wired to RecommendationService)
│       ├── user.py                  # User preferences (stub)
│       ├── user_supplier.py         # Supplier selection + account linking (AES-256-GCM encrypted fields)
│       ├── connections/
│       │   ├── __init__.py          # Router registration
│       │   ├── router.py            # CRUD, analytics endpoints; routes registered in app_factory
│       │   ├── common.py            # ConnectionValidator, _validate_connection_type, require_paid_tier
│       │   ├── crud.py              # GET/POST/DELETE connection endpoints
│       │   ├── rates.py             # GET rates endpoint, bulk_create_rates helper
│       │   ├── analytics.py         # Analytics endpoints: comparison, history, savings, health
│       │   ├── email_oauth.py       # Email OAuth endpoints (consent URL, scan, callback)
│       │   ├── bill_upload.py       # Bill upload endpoints (upload, reparse, list uploads)
│       │   ├── direct_sync.py       # Direct login sync endpoint
│       │   ├── portal_scrape.py     # Portal connection endpoints (create with encrypted creds, trigger scrape)
│       ├── alerts.py                # Price alert CRUD endpoints (create, list, delete, trigger check)
│       ├── health.py                # 3 health endpoints: /health, /health/ready, /health/live
│       ├── notifications.py         # User notification endpoints (list, mark read, preferences)
│       ├── savings.py               # Savings tracking endpoints (summary, history, goals)
│       ├── users.py                 # User profile management (get, update, delete account)
│       ├── agent.py                 # RateShift AI assistant endpoints (SSE streaming, async jobs, usage tracking)
│       ├── feedback.py              # User feedback submission and collection
│       ├── gas_rates.py             # Natural gas rate endpoints (Wave 2)
│       ├── community_solar.py       # Community solar program endpoints (Wave 2)
│       ├── utility_discovery.py     # Utility discovery card endpoints (GET /discover, GET /completion)
│       ├── cca.py                   # CCA detection endpoints (Wave 3)
│       ├── heating_oil.py           # Heating oil dealer + pricing endpoints (Wave 3)
│       ├── rate_changes.py          # Rate change alerting endpoints (Wave 3)
│       ├── public_rates.py          # Public SEO rate pages (ISR, 153 pages)
│       ├── affiliate.py             # Affiliate link tracking endpoints (Wave 3)
│       ├── propane.py               # Propane pricing + fill-up timing endpoints (Wave 4)
│       ├── water.py                 # Water rate benchmarking endpoints (Wave 4, monitoring-only)
│       ├── forecast.py              # Multi-utility forecasting endpoints (Wave 4)
│       ├── reports.py               # Optimization report endpoints (Wave 4)
│       ├── export.py                # Rate data export endpoints (CSV/JSON)
│       ├── community.py             # Community posts, voting, reporting endpoints (Wave 5)
│       ├── savings.py               # Savings tracking endpoints (summary, history, goals)
│       ├── neighborhood.py          # Neighborhood comparison endpoints (Wave 5)
│       ├── referrals.py             # Referral program endpoints
│       ├── internal/
│       │   ├── __init__.py          # Internal router aggregation
│       │   ├── data_pipeline.py     # observe-forecasts, learn, observation-stats, scrape-rates (with Diffbot rate extraction + persistence)
│       │   ├── operations.py        # maintenance/cleanup, check-alerts, sync-connections, dunning-cycle, kpi-report, geocode-address, health-data
│       │   ├── email_scan.py         # POST /scan-emails — batch scan all active email connections
│       │   └── portal_scan.py       # POST /scrape-portals — batch scrape all active portal connections
│
├── routers/
│   └── predictions.py               # ML prediction endpoints (forecast, optimal-times, savings)
│
├── models/
│   ├── price.py                     # Price, PriceForecast, response schemas; PriceUnit imported from utility.py
│   ├── supplier.py                  # Supplier, Tariff, TariffType, ContractLength (utility_types field)
│   ├── user.py                      # User, UserPreferences, UserCreate/Update
│   ├── utility.py                   # UtilityType enum, PriceUnit enum (canonical, incl. GBP_KWH/EUR_KWH/USD_KWH), labels/defaults
│   ├── region.py                    # Region enum (single source of truth, all 50 US states + intl)
│   ├── observation.py               # ForecastObservation, RecommendationOutcome, AccuracyMetrics, HourlyBias
│   ├── regulation.py                # StateRegulation, StateRegulationResponse, StateRegulationListResponse
│   ├── user_supplier.py             # SetSupplierRequest, LinkAccountRequest, UserSupplierResponse, LinkedAccountResponse
│   ├── connections.py               # CreateConnectionRequest (5 types incl. portal_scrape), BillUploadResponse, ConnectionResponse, ConnectionAnalytics, CreatePortalConnectionRequest, PortalConnectionResponse
│   ├── consent.py                   # ConsentRecord, DeletionLog, GDPR request/response
│   ├── model_version.py             # ModelVersion, ABTest, ABOutcome schemas for versioning and A/B testing
│   ├── model_config.py              # ModelConfiguration for ML pipeline parameterization
│   └── notification.py              # Notification schema with delivery tracking (channel, status, delivered_at, error_message)
│
├── repositories/
│   ├── base.py                      # BaseRepository[T], error classes
│   ├── price_repository.py          # PriceRepository: CRUD, bulk_create, statistics (utility_type filter)
│   ├── supplier_repository.py       # SupplierRegistryRepository + StateRegulationRepository; SQL-injection-safe WHERE clauses
│   ├── forecast_observation_repository.py  # ForecastObservationRepository: observation queries (with version breakdown)
│   ├── user_repository.py           # UserRepository: by-email, by-stripe-customer-id, preferences, consent
│   ├── notification_repository.py    # NotificationRepository: CRUD + delivery_status tracking, update_delivery()
│   └── model_config_repository.py    # ModelConfigRepository: versioned ML config persistence
│
├── services/
│   ├── price_service.py             # Business logic: comparison, forecast, optimal windows
│   ├── analytics_service.py         # Trends, volatility, peak hours, supplier comparison
│   ├── recommendation_service.py    # Switching + usage recommendations
│   ├── alert_service.py             # Price threshold alerts + email notifications + deduplication + active config loading
│   ├── email_service.py             # Resend (primary) + SMTP (fallback) + Jinja2
│   ├── stripe_service.py            # Checkout, portal, subscriptions, webhooks (payment_failed resolves user via stripe_customer_id)
│   ├── vector_store.py              # SQLite-backed vector store for price pattern matching
│   ├── hnsw_vector_store.py         # HNSW-indexed wrapper (O(log n) ANN, fallback); get_vector_store_singleton()
│   ├── observation_service.py       # Record forecasts, backfill actuals, track recommendation outcomes
│   ├── learning_service.py          # Nightly learning: accuracy, bias detection, weight tuning
│   ├── price_sync_service.py        # Orchestrate external API price fetch + persist via PriceRepository
│   ├── connection_service.py        # Core connection CRUD, status management
│   ├── connection_sync_service.py   # UtilityAPI direct sync service (Phase 4)
│   ├── connection_analytics_service.py # Rate comparison, history, savings estimates, stale detection, rate change alerts
│   ├── email_oauth_service.py       # OAuth2 flows for Gmail + Outlook, HMAC-SHA256 state validation, token encryption
│   ├── email_scanner_service.py     # Gmail REST API + Microsoft Graph API inbox scanning, rate extraction via regex, attachment download (Gmail attachments.get / Graph attachments endpoint)
│   ├── bill_parser.py               # Bill document parsing (PDF/image OCR), rate extraction
│   ├── portal_scraper_service.py    # Headless portal scraping via httpx (5 utilities: Duke Energy, PG&E, Con Edison, ComEd, FPL), rate extraction from HTML
│   ├── maintenance_service.py       # Data retention cleanup (activity logs 365d, uploads 730d, prices 365d, observations 90d, parameterized SQL + PL/pgSQL)
│   ├── notification_service.py      # Notification creation, delivery, preference management
│   ├── savings_service.py           # Savings calculation and tracking
│   ├── feature_flag_service.py      # Feature flag evaluation and management
│   ├── dunning_service.py           # Stripe dunning: record failure, 24h cooldown, soft/final email, escalate to free after 3 failures
│   ├── kpi_report_service.py        # KPI metrics aggregation: active users, MRR, subscription breakdown, data freshness
│   ├── notification_dispatcher.py    # Multi-channel notification dispatch (in-app, push, email) with delivery tracking and dedup cooldowns
│   ├── ab_test_service.py           # A/B testing framework with SHA-256 consistent hashing, assignment persistence, metric aggregation
│   ├── model_version_service.py     # Model versioning and promotion, A/B test lifecycle management
│   ├── agent_service.py             # RateShift AI agent: Gemini 3 Flash primary + Groq fallback + Composio tools (SSE streaming, async jobs, rate limiting)
│   ├── alert_renderer.py            # Alert message templating and formatting
│   ├── data_persistence_helper.py    # Shared batch INSERT logic for internal data pipeline endpoints
│   ├── gas_rate_service.py          # Natural gas rate service (Wave 2: comparison, history, forecasts)
│   ├── community_solar_service.py   # Community solar program discovery and enrollment (Wave 2)
│   ├── utility_discovery_service.py # Post-signup utility discovery (pure logic, dashboard cards)
│   ├── data_quality_service.py      # Data freshness, anomaly detection, source failure alerting
│   ├── cca_service.py               # Community Choice Aggregation detection (Wave 3)
│   ├── heating_oil_service.py       # Heating oil dealer comparison + pricing (Wave 3)
│   ├── affiliate_service.py         # Affiliate link tracking + revenue attribution (Wave 3)
│   ├── rate_change_detector.py      # Rate change detection + alerting across utility types (Wave 3)
│   ├── propane_service.py           # Propane pricing + fill-up timing (Wave 4)
│   ├── water_rate_service.py        # Water rate benchmarking + tier calculation (Wave 4, monitoring-only)
│   ├── forecast_service.py          # Multi-utility price forecasting (Wave 4)
│   ├── optimization_report_service.py # Cross-utility optimization reports (Wave 4)
│   ├── rate_export_service.py       # Rate data CSV/JSON export (Wave 4)
│   ├── community_service.py         # Community posts, voting, reporting (Wave 5)
│   ├── savings_aggregator.py        # Community savings aggregation (Wave 5)
│   ├── neighborhood_service.py      # Neighborhood comparison + benchmarking (Wave 5)
│   └── referral_service.py          # User referral program tracking
│
├── auth/
│   ├── neon_auth.py                 # Neon Auth session validation; Redis cache (120s TTL, SHA-256 key)
│   └── password.py                  # Password validation, strength check
│
├── compliance/
│   ├── gdpr.py                      # GDPRComplianceService, DataRetentionService
│   └── repositories.py              # ConsentRecordORM, DeletionLogORM, SQLAlchemy mappers
│
├── integrations/
│   ├── weather_service.py           # OpenWeatherMap integration, WeatherCircuitBreaker (failure threshold 5, timeout 60s, recovery 2 successes)
│   └── pricing_apis/
│       ├── base.py                  # PricingRegion (alias->Region), PriceData, APIError, RateLimitError; PriceUnit imported from models/utility.py
│       ├── service.py               # PricingService (unified multi-API interface)
│       ├── nrel.py                  # NREL client (US regions, all 50 state ZIPs)
│       ├── flatpeak.py              # Flatpeak client (UK/EU regions)
│       ├── iea.py                   # IEA client (global fallback)
│       ├── eia.py                   # EIA client (US: electricity, gas, heating oil, propane)
│       ├── cache.py                 # PricingCache
│       ├── rate_limiter.py          # API-level RateLimiter
│       └── __init__.py              # create_pricing_service_from_settings()
│
├── lib/
│   ├── tracing.py                   # OpenTelemetry traced() context manager (async/sync), 16 span types, Grafana Cloud Tempo
│   └── circuit_breaker.py           # Generic circuit breaker (CLOSED/OPEN/HALF_OPEN states), integrated into PricingService + UtilityAPIClient
│
├── utils/
│   └── encryption.py                # AES-256-GCM field-level encryption (account numbers, meter numbers)
│
├── middleware/
│   ├── rate_limiter.py              # Pure ASGI rate limiting (sliding window, Redis or in-memory) + reset() for test isolation
│   ├── security_headers.py          # Pure ASGI security headers (CSP, HSTS, X-Frame-Options, etc.)
│   └── tracing.py                   # Request tracing middleware (correlation IDs, timing)
│
├── migrations/
│   ├── init_neon.sql                # Initial schema: users, electricity_prices, suppliers,
│   │                                #   tariffs, consent_records, deletion_logs, beta_signups
│   ├── 002_gdpr_auth_tables.sql     # GDPR tables: auth_sessions, login_attempts, activity_logs
│   ├── 003_reconcile_schema.sql     # Schema reconciliation for consent_records/deletion_logs
│   ├── 004_performance_indexes.sql  # Compound + partial indexes for perf optimization
│   ├── 005_observation_tables.sql   # forecast_observations + recommendation_outcomes (adaptive learning)
│   ├── 006_multi_utility_expansion.sql # utility_type enum, supplier_registry, state_regulations tables
│   ├── 007_user_supplier_accounts.sql # User supplier account tables
│   ├── 008_connection_feature.sql   # Base connection tables: user_connections, bill_uploads, connection_extracted_rates
│   ├── 009_email_oauth_tokens.sql   # OAuth token columns on user_connections
│   ├── 010_utilityapi_sync_columns.sql # UtilityAPI sync columns (last_sync_at, sync_frequency_hours, etc.)
│   ├── 011_utilityapi_sync_columns.sql # (renumbered from 010)
│   ├── 012_user_savings.sql         # Savings tracking tables
│   ├── 013_user_profile_columns.sql # Additional user profile fields
│   ├── 014_alert_tables.sql         # Alert configuration and history tables
│   ├── 015_notifications.sql        # Notification tables
│   ├── 016_feature_flags.sql        # Feature flag tables
│   ├── 017_additional_indexes.sql   # Performance indexes
│   ├── 018_add_region_to_user.sql   # Add region column to users table
│   ├── 019_savings_columns.sql      # Savings tracking columns
│   ├── 020_connection_sync_log.sql  # Connection sync log table
│   ├── 021_connection_fixes.sql     # Connection feature bug fixes
│   ├── 022_bill_upload_fixes.sql    # Bill upload improvements
│   ├── 023_db_audit_indexes.sql     # Database audit indexes, bulk_create refactor
│   ├── 024_payment_retry_history.sql # Dunning retry tracking: UUID PK, retry_count, escalation_action, email tracking
│   ├── 025_data_cache_tables.sql     # 3 cache tables for internal fetch endpoints (weather, market intelligence, rate data)
│   ├── 026_notifications_metadata.sql # Enhanced notification metadata columns
│   ├── 027_model_config.sql          # ModelConfiguration table for ML parameterization
│   ├── 028_feedback_table.sql        # User feedback collection table
│   ├── 029_notification_delivery_tracking.sql # Delivery channel, status, delivered_at, retry_count columns
│   ├── 030_model_versioning_ab_tests.sql # model_versions, ab_tests, ab_outcomes tables
│   ├── 031_agent_tables.sql          # agent_conversations, agent_usage_daily, agent_messages tables
│   ├── 032_notification_error_message.sql # error_message column for notification delivery diagnostics
│   ├── 033_model_predictions_ab_assignments.sql # model_predictions, model_ab_assignments tables for A/B test tracking
│   ├── 034_portal_credentials.sql     # Portal credential columns on user_connections
│   ├── 035_wave0_prereqs.sql          # Wave 0 prerequisites (schema alignment)
│   ├── 036_wave1_foundation.sql       # Wave 1 foundation tables
│   ├── 037_gas_prices.sql             # Natural gas prices table
│   ├── 038_gas_supplier_seed.sql      # Seed 12 gas suppliers into supplier_registry
│   ├── 039_onboarding_v2.sql          # Onboarding V2 schema changes
│   ├── 040_gas_supplier_seed.sql      # Gas supplier seed data (Wave 2)
│   ├── 041_community_solar_programs.sql # community_solar_programs table (15 programs, 13 states)
│   ├── 042_cca_programs.sql           # cca_programs table (14 CCA programs seeded)
│   ├── 043_heating_oil.sql            # heating_oil_prices + heating_oil_dealers tables (15 dealers seeded)
│   ├── 044_alerting_tables.sql        # Rate change alerting tables
│   ├── 045_affiliate_tracking.sql     # affiliate_clicks table
│   ├── 046_propane_prices.sql         # propane_prices table
│   ├── 047_water_rates.sql            # water_rates table (JSONB rate_tiers)
│   ├── 048_dashboard_tabs.sql         # Tabbed multi-utility dashboard preferences
│   └── 049_community_tables.sql       # community_posts, community_votes, community_reports tables
│
├── templates/emails/
│   ├── welcome_beta.html            # Jinja2 beta welcome email
│   ├── price_alert.html             # Jinja2 price alert notification
│   ├── dunning_soft.html            # Jinja2 soft dunning email (amber gradient, empathetic tone)
│   └── dunning_final.html           # Jinja2 final dunning email (red gradient, grace period warning)
│
└── tests/
    ├── conftest.py                  # Shared fixtures (mock_sqlalchemy_select, reset_rate_limiter)
    ├── test_api.py                  # API endpoint tests
    ├── test_api_beta.py             # Beta API endpoint tests
    ├── test_api_billing.py          # Billing/Stripe endpoint tests (33 tests)
    ├── test_api_compliance.py       # Compliance API endpoint tests
    ├── test_api_predictions.py      # ML prediction endpoint tests
    ├── test_api_recommendations.py  # Recommendation endpoint tests
    ├── test_api_user.py             # User preference endpoint tests
    ├── test_auth.py                 # Authentication tests
    ├── test_config.py               # Settings validation tests
    ├── test_email_service.py        # Email service tests (Resend + SMTP)
    ├── test_models.py               # Pydantic model tests
    ├── test_services.py             # Service layer tests
    ├── test_repositories.py         # Repository tests
    ├── test_integrations.py         # Pricing API integration tests
    ├── test_security.py             # Security hardening tests
    ├── test_security_adversarial.py # Adversarial security tests (42 tests)
    ├── test_alert_service.py        # Alert service tests
    ├── test_stripe_service.py       # Stripe service tests
    ├── test_vector_store.py         # Vector store tests (VectorStore)
    ├── test_hnsw_vector_store.py    # HNSW vector store tests (HNSWVectorStore)
    ├── test_weather_service.py      # Weather service tests (12 circuit breaker tests: 7 breaker, 5 integration)
    ├── test_gdpr_compliance.py      # GDPR compliance tests
    ├── test_multi_utility.py        # Multi-utility expansion tests (39 tests)
    ├── test_observation_service.py  # ObservationService tests (31 tests)
    ├── test_learning_service.py     # LearningService tests (32 tests)
    ├── test_performance.py          # Performance tests (18 tests: query counts, caching, async operations)
    ├── test_api_internal.py         # Internal API endpoint tests (observe-forecasts, learn, check-alerts, sync-connections, dunning-cycle, kpi-report)
    ├── test_api_regulations.py      # State regulation API tests
    ├── test_analytics_service.py    # AnalyticsService tests
    ├── test_encryption.py           # AES-256-GCM encryption tests
    ├── test_forecast_observation_repository.py  # ForecastObservationRepository tests
    ├── test_price_sync_service.py   # PriceSyncService tests
    ├── test_sse_streaming.py        # SSE streaming endpoint tests
    ├── test_user_supplier.py        # Supplier selection + account linking tests
    ├── test_connections.py          # Connection endpoint tests (40 tests)
    ├── test_bill_upload.py          # Bill upload + parse tests
    ├── test_email_oauth.py          # OAuth state gen/verify, consent URLs, token encryption, email scanning, endpoint tests (70 tests)
    ├── test_connection_analytics.py # Connection analytics service tests (39+ tests)
    ├── test_connection_service.py   # ConnectionService CRUD + status management tests (51 tests)
    ├── test_supplier_cache.py       # Supplier registry Redis caching tests (25 tests)
    ├── test_middleware_asgi.py      # ASGI middleware compliance tests (9 tests: SSE, rate limits, body size, timeout)
    ├── test_api_alerts.py           # Alert endpoint tests
    ├── test_api_health.py           # Health endpoint tests (/health, /health/ready, /health/live)
    ├── test_api_prices_analytics.py # Analytics endpoint tests
    ├── test_feature_flags.py        # Feature flag service tests
    ├── test_maintenance_service.py  # Maintenance service tests (28 tests: cleanup_activity_logs, cleanup_expired_uploads, cleanup_old_prices, cleanup_old_observations, endpoint integration)
    ├── test_migrations.py           # Migration validation tests
    ├── test_notifications.py        # Notification service tests
    ├── test_resilience.py           # Resilience/circuit breaker tests
    ├── test_savings_service.py      # SavingsService calculation & tracking tests (52 tests)
    ├── test_forecast_observation_repository.py # ForecastObservationRepository with new coverage/accuracy class methods
    ├── test_dunning_service.py      # DunningService tests (13 tests: record, cooldown, email template selection, escalation, full flow)
    ├── test_kpi_report_service.py   # KPIReportService tests (7 tests: happy path, empty tables, subscription breakdown, MRR calculation, weather freshness)
    ├── test_notification_dispatcher.py # NotificationDispatcher tests (multi-channel, dedup cooldowns, delivery tracking)
    ├── test_email_scan_extraction.py # Email body rate extraction tests
    ├── test_email_attachment_parsing.py # Gmail/Outlook attachment download + parsing tests (28 tests)
    ├── test_internal_scan_emails.py  # Internal scan-emails endpoint tests (20 tests)
    ├── test_portal_connections.py    # Portal connection CRUD + encrypted credential tests (14 tests)
    ├── test_portal_scraper_service.py # PortalScraperService tests (30 tests)
    ├── test_internal_scrape_portals.py # Internal scrape-portals endpoint tests (9 tests)
    ├── test_scraper_persistence.py   # Diffbot scraper rate persistence tests (25 tests)
    ├── test_unified_analytics.py     # Unified analytics across all connection sources (24 tests)
    ├── test_ab_test_service.py       # ABTestService tests (consistent hashing, assignment persistence, metric aggregation)
    ├── test_model_version_service.py # ModelVersionService tests (versioning, promotion, A/B test lifecycle)
    ├── test_agent_service.py         # AgentService tests (Gemini/Groq fallback, tool execution, streaming, rate limits)
    ├── test_api_agent.py            # Agent API endpoint tests (query streaming, async jobs, usage tracking)
    ├── test_api_feedback.py         # Feedback API endpoint tests
    ├── test_load.py                 # Load/stress test helpers
    ├── test_gas_rate_service.py     # Gas rate service tests (Wave 2)
    ├── test_community_solar_service.py # Community solar service tests (Wave 2)
    ├── test_utility_discovery.py    # Utility discovery service + API tests (Wave 2)
    ├── test_data_quality_service.py # Data quality service tests (Wave 2)
    ├── test_cca_service.py          # CCA detection service tests (Wave 3)
    ├── test_heating_oil_service.py  # Heating oil service tests (Wave 3)
    ├── test_rate_change_detector.py # Rate change detection tests (Wave 3)
    ├── test_affiliate_service.py    # Affiliate tracking service tests (Wave 3)
    ├── test_public_rates.py         # Public SEO rate page tests (Wave 3)
    ├── test_propane_service.py      # Propane service tests (Wave 4)
    ├── test_water_rate_service.py   # Water rate service tests (Wave 4)
    ├── test_forecast_service.py     # Multi-utility forecast tests (Wave 4)
    ├── test_community_service.py    # Community posts/voting/reporting tests (Wave 5)
    ├── test_savings_aggregator.py   # Community savings aggregation tests (Wave 5)
    ├── test_neighborhood_service.py # Neighborhood comparison tests (Wave 5)
    └── test_tracing.py              # OpenTelemetry tracing tests (37 tests)
```

## Application Lifecycle

**Entry Point:** `main.py` (27 lines) calls `create_app()` from `app_factory.py` and runs Uvicorn with lifespan context manager.

**App Factory:** `app_factory.py` -- `create_app()` factory function handles:

```
create_app():
  1. db_manager = DatabaseManager.get_instance()
  2. db_manager.initialize()  -- Neon PostgreSQL, Redis (graceful degradation)
  3. Sentry SDK init (lazy import, if SENTRY_DSN configured)
  4. Mount middleware stack (see Middleware below)
  5. Mount 30+ routers (prices, suppliers, regulations, auth, gas, solar, etc.) with OpenAPI tags
  6. Include health check endpoints (/health, /health/ready, /health/live) from health.py
  7. Include root routes (/, /metrics)
  8. Define lifespan context manager for startup/shutdown
  9. Return FastAPI app
```

**Production:** `gunicorn_config.py` -- 1 Uvicorn worker, 512MB RAM budget.

**Swagger/ReDoc:** Disabled in production (`docs_url=None if is_production`).


## API Routes

All routes use prefix `{settings.api_prefix}` (default `/api/v1`).

**OpenAPI Tags:** All 19 router files now include explicit `tags` parameter for OpenAPI documentation.
Routers organized by domain: prices, suppliers, regulations, auth, billing, compliance, users, connections, alerts, notifications, savings, recommendations, predictions, health, internal.
Routes registered in `app_factory.py` with consistent tag naming.

### Prices (`/api/v1/prices`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/current` | None | Current prices by region (fallback: mock + source=fallback) |
| GET | `/history` | None | Historical prices for a date range (supports pagination: limit, offset) |
| GET | `/forecast` | None | ML-based price forecast (1-168 hours) |
| GET | `/compare` | None | Compare supplier prices in a region |
| GET | `/statistics` | None | Min/max/avg price stats |
| GET | `/optimal-windows` | None | Find cheapest usage windows |
| GET | `/trends` | None | Price trend analysis (direction, change %) |
| GET | `/peak-hours` | None | Peak vs off-peak hour analysis |
| POST | `/refresh` | X-API-Key | Trigger price sync from external APIs |
| GET | `/stream` | Session | SSE real-time price updates (max 3 connections/user, heartbeat every 15s) |

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
| GET | `/registry` | None | Supplier registry with API availability (for DirectLoginForm dropdown) — returns suppliers where `api_available=true` |
| GET | `/` | None | List suppliers (paginated, filterable by region/utility_type/green) |
| GET | `/{supplier_id}` | None | Supplier details (UUID validated) |
| GET | `/{supplier_id}/tariffs` | None | Supplier tariff list (UUID validated) |
| GET | `/region/{region}` | None | Suppliers by region (region code validated) |
| GET | `/compare/{region}` | None | Compare suppliers in region |

**Data source:** `supplier_registry` table via `SupplierRegistryRepository`. Supports filtering
by `utility_type` (electricity, natural_gas, heating_oil, propane, community_solar), `green_only`,
and region. Input validation (`_validate_uuid`, `_validate_region_code`) rejects invalid IDs/regions
before DB access. The `/registry` endpoint (2026-03-04) provides a minimal list of suppliers with
direct login APIs available, used by DirectLoginForm for user selection.

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
| GET | `/me` | Session | Current user info (Neon Auth session validation) |
| POST | `/password/check-strength` | None | Password strength assessment |

**Auth provider:** Neon Auth (Better Auth) — managed by the frontend via `/api/auth/[...all]`
API route. Sign-up, sign-in, sign-out, OAuth (Google/GitHub), magic link, and password reset
are all handled by the Better Auth SDK on the frontend. The backend only validates sessions
by querying the `neon_auth.session` + `neon_auth.user` tables directly.

### Billing (`/api/v1/billing`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/checkout` | Session | Create Stripe Checkout session (pro/business) |
| POST | `/portal` | Session | Create Stripe Customer Portal session |
| GET | `/subscription` | Session | Get current subscription status |
| POST | `/webhook` | Stripe sig | Handle Stripe webhook events |

**Tiers:** Free ($0), Pro ($4.99/mo), Business ($14.99/mo).
**Checkout URL validation:** `success_url`/`cancel_url` validated against allowed domains.

### Compliance (`/api/v1/compliance`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/consent` | Session | Record consent decision (GDPR Art. 6, 7) |
| GET | `/gdpr/consents` | Session | Get consent history |
| GET | `/gdpr/consents/status` | Session | Current consent status per purpose |
| GET | `/gdpr/export` | Session | Export all user data (GDPR Art. 15, 20) |
| DELETE | `/gdpr/delete-my-data` | Session | Delete all user data (GDPR Art. 17) |
| POST | `/gdpr/withdraw-all-consents` | Session | Withdraw all consents (GDPR Art. 21) |

### Beta (`/api/v1/beta`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/signup` | None | Beta registration + welcome email |
| GET | `/signups/count` | Session | Beta signup count vs target |
| GET | `/signups/stats` | Session | Signup stats (by supplier/source/bill) |
| POST | `/verify-code` | None | Verify beta access code |

### Internal (`/api/v1/internal`)

All endpoints require `X-API-Key` header (same key as `/prices/refresh`).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/observe-forecasts` | Backfill actual prices into unobserved forecast rows |
| POST | `/learn` | Run adaptive learning cycle (accuracy, bias, weight tuning, pruning) |
| GET | `/observation-stats` | Forecast accuracy metrics and hourly bias |
| POST | `/maintenance/cleanup` | Run data retention cleanup: activity logs, uploads, prices, observations (returns counts deleted) |
| POST | `/scan-emails` | Batch scan all active email connections (asyncio.gather + Semaphore) |
| POST | `/scrape-portals` | Batch scrape all active portal connections (asyncio.gather + Semaphore(2)) |
| POST | `/scrape-rates` | Scrape supplier rates via Diffbot + extract rate_per_kwh via regex |

### User Supplier (`/api/v1/user/supplier`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Session | Get user's current supplier + linked accounts |
| POST | `/set` | Session | Set current supplier (by supplier_id) |
| POST | `/link-account` | Session | Link utility account (AES-256-GCM encrypted fields) |
| DELETE | `/link-account/{account_id}` | Session | Unlink a utility account |

**Security:** Account numbers and meter numbers encrypted at rest via AES-256-GCM
(`utils/encryption.py`). Ciphertext format: nonce (12B) || ciphertext || tag (16B).
Key from `FIELD_ENCRYPTION_KEY` env var (32-byte hex).

### Connections (`/api/v1/connections`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/` | Paid tier | Create new connection (email_oauth, bill_upload, direct_login, utilityapi) |
| GET | `/` | Paid tier | List user's connections |
| GET | `/{connection_id}` | Paid tier | Get connection details |
| DELETE | `/{connection_id}` | Paid tier | Delete connection |
| PATCH | `/{connection_id}/label` | Paid tier | Update connection label |
| GET | `/email/callback` | None | OAuth callback (Gmail/Outlook), HMAC state verification |
| POST | `/email/{connection_id}/scan` | Paid tier | Trigger email inbox scan |
| POST | `/{connection_id}/upload` | Paid tier | Upload bill document (PDF/image) |
| GET | `/{connection_id}/uploads` | Paid tier | List uploads for connection |
| GET | `/{connection_id}/uploads/{upload_id}` | Paid tier | Get single upload status (for polling) |
| POST | `/{connection_id}/uploads/{upload_id}/reparse` | Paid tier | Re-parse an uploaded bill |
| POST | `/{connection_id}/sync` | Paid tier | Trigger UtilityAPI sync |
| GET | `/{connection_id}/sync-status` | Paid tier | Get sync status |
| GET | `/{connection_id}/rates` | Paid tier | Get extracted rates for connection |
| GET | `/analytics/comparison` | Paid tier | Rate comparison (user vs market) |
| GET | `/analytics/history` | Paid tier | Rate history for charts |
| GET | `/analytics/savings` | Paid tier | Estimated savings calculation |
| GET | `/analytics/health` | Paid tier | Connection health (stale connections + rate changes) |
| POST | `/portal` | Paid tier | Create portal connection (encrypted credentials, supported utility) |
| POST | `/portal/{connection_id}/scrape` | Paid tier | Trigger manual portal scrape |

**Connection types:** `email_oauth`, `bill_upload`, `direct_login`, `utilityapi`, `portal_scrape`

**Auth:** All endpoints require paid subscription tier (Pro or Business) via `require_paid_tier` dependency.

**Route ordering:** Analytics routes registered before `/{connection_id}` to prevent path parameter capture. Organized into 9 submodules: `router.py` (registration), `crud.py`, `analytics.py`, `rates.py`, `email_oauth.py`, `bill_upload.py`, `direct_sync.py`, `portal_scrape.py`, `common.py` (validators). Registration order: analytics → email_oauth → bill_upload → portal_scrape → direct_sync → rates → crud.

**Security:** OAuth tokens AES-256-GCM encrypted at rest. OAuth state HMAC-SHA256 signed with nonce
for CSRF protection (state timeout configured). Bill uploads: File type validation (PDF, PNG, JPG, JPEG, TIFF only), 10 MB max size. Password rate limit enforced (5 attempts / 15 min lockout).

### Alerts (`/api/v1/alerts`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/` | Session | Create price alert (threshold + region) |
| GET | `/` | Session | List user's alerts |
| DELETE | `/{alert_id}` | Session | Delete alert |
| POST | `/{alert_id}/check` | Session | Trigger threshold check |

**Trigger:** AlertService checks hourly via GitHub Actions, sends email via EmailService.

### Notifications (`/api/v1/notifications`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Session | List user notifications (paginated) |
| PATCH | `/{notification_id}/read` | Session | Mark notification as read |
| DELETE | `/{notification_id}` | Session | Delete notification |
| GET | `/preferences` | Session | Get notification preferences |
| PATCH | `/preferences` | Session | Update notification preferences |

**Types:** price_alert, recommendation, savings_milestone, connection_health.

### Savings (`/api/v1/savings`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/summary` | Session | Total savings + time period breakdown |
| GET | `/history` | Session | Monthly savings history (chart data) |
| GET | `/goals` | Session | User savings goals + progress |
| POST | `/goals` | Session | Create/update savings goal |

**Calculation:** Actual spend (connections) vs estimated spend (supplier rates).

### Users (`/api/v1/users`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/profile` | Session | Get user profile (email, name, region, preferences) |
| PATCH | `/profile` | Session | Update profile fields |
| DELETE | `/account` | Session | Schedule account deletion (GDPR Art. 17) |
| GET | `/settings` | Session | Get user settings (privacy, notifications, language) |
| PATCH | `/settings` | Session | Update user settings |

**Profile fields:** email, name, region, phone, address, notification preferences, language.

### Agent (`/api/v1/agent`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/query` | Session | Stream agent response (SSE, Gemini 3 Flash primary + Groq fallback) |
| POST | `/task` | Session | Submit async job for tool-heavy tasks |
| GET | `/task/{job_id}` | Session | Poll async job result |
| GET | `/usage` | Session | Remaining queries today (rate limited: Free=3/day, Pro=20/day, Business=unlimited) |

**Integration:** Powered by RateShift AI agent with Composio tool integration (16 connected apps: Gmail, GitHub, Firecrawl, Sentry, Vercel, Resend, Stripe, Render, Google Sheets/Drive, UptimeRobot, OneSignal, Better Stack, Slack, Notion, Neon). Rate limits enforced per tier. SSE streaming for real-time responses.

### Feedback (`/api/v1/feedback`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/` | Session | Submit user feedback (type, message, context) |
| GET | `/` | Session | List user's feedback submissions |

**Types:** bug_report, feature_request, general_feedback, savings_tracking, rate_quality.

### Recommendations (`/api/v1/recommendations`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/switching` | Session | Switching recommendation (real RecommendationService) |
| GET | `/usage` | Session | Usage timing recommendation (real RecommendationService) |
| GET | `/daily` | Session | Daily combined recommendations (switching + usage) |

### Gas Rates (`/api/v1/rates/gas`) — Wave 2

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | None | Current gas rates by region |
| GET | `/history` | None | Historical gas rate data |
| GET | `/compare` | None | Gas supplier comparison |

### Community Solar (`/api/v1/community-solar`) — Wave 2

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/programs` | None | List programs by state |
| GET | `/programs/{id}` | None | Program details + enrollment info |
| POST | `/enroll` | Session | Request enrollment |

### CCA Detection (`/api/v1/cca`) — Wave 3

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/programs` | None | List CCA programs by region |
| GET | `/detect` | Session | Detect if user is in a CCA zone |

### Heating Oil (`/api/v1/rates/heating-oil`) — Wave 3

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | None | Current heating oil prices by region |
| GET | `/dealers` | None | Heating oil dealers by region |
| GET | `/compare` | None | Dealer comparison |

### Rate Changes (`/api/v1/rate-changes`) — Wave 3

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Session | Recent rate changes across utility types |
| GET | `/alerts` | Session | User's rate change alert configs |
| POST | `/alerts` | Session | Create rate change alert |

### Public Rates (`/api/v1/rates`) — Wave 3 SEO

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/{state}/{utility_type}` | None | Public rate data for ISR pages (153 pages: 51 states x 3+ utility types) |

### Affiliate (`/api/v1/affiliate`) — Wave 3

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/click` | None | Record affiliate link click |
| GET | `/stats` | X-API-Key | Affiliate click stats |

### Propane (`/api/v1/rates/propane`) — Wave 4

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | None | Current propane prices by region |
| GET | `/history` | None | Historical propane prices |
| GET | `/fill-timing` | Session | Optimal fill-up timing recommendation |
| GET | `/compare` | None | Regional propane price comparison |

### Water (`/api/v1/rates/water`) — Wave 4

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | None | Current water rates by region (monitoring-only, no switching) |
| GET | `/benchmark` | Session | User usage vs regional benchmark |
| GET | `/tips` | None | Conservation tips |

### Forecast (`/api/v1/forecast`) — Wave 4

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Pro | Multi-utility price forecast |

### Reports (`/api/v1/reports`) — Wave 4

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/optimization` | Session | Cross-utility optimization report |

### Export (`/api/v1/export`) — Wave 4

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/rates` | Session | Export rate data (CSV/JSON) |

### Community (`/api/v1/community`) — Wave 5

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/posts` | Session | List community posts (paginated) |
| POST | `/posts` | Session | Create post (AI moderated: Groq classify_content primary, Gemini fallback, nh3 XSS sanitization) |
| POST | `/posts/{id}/vote` | Session | Vote on post (up/down) |
| POST | `/posts/{id}/report` | Session | Report post (5 unique reporters auto-hides) |

### Neighborhood (`/api/v1/neighborhood`) — Wave 5

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/comparison` | Session | Compare user rates to neighborhood average |
| GET | `/stats` | None | Neighborhood aggregated stats |

### Referrals (`/api/v1/referrals`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Session | User's referral stats |
| POST | `/invite` | Session | Send referral invite |

### Other

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/user/preferences` | Session | Get user preferences (stub) |
| POST | `/user/preferences` | Session | Update user preferences (stub) |

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
| Auth | `jwt_secret` (used only for internal API key validation), `jwt_algorithm` (HS256). User auth via Neon Auth sessions. `field_encryption_key` (32-byte hex, validates via @field_validator). `better_auth_secret` (32+ chars in production, validated via @field_validator) |
| API keys | `internal_api_key`, `flatpeak_api_key`, `nrel_api_key`, `iea_api_key`, `eia_api_key`, `openweathermap_api_key` |
| Email | `resend_api_key`, `smtp_host/port/username/password`, `email_from_address/name` |
| Stripe | `stripe_secret_key`, `stripe_webhook_secret`, `stripe_price_pro`, `stripe_price_business` |
| ML | `model_path`, `model_forecast_hours` (24), `model_accuracy_threshold_mape` (10.0) |
| GDPR | `data_retention_days` (730), `consent_required`, `data_residency` |
| Features | `enable_auto_switching`, `enable_load_optimization`, `enable_real_time_updates` |
| Security | `allowed_redirect_domains` (configurable, allows `electricity-optimizer*.vercel.app` and `electricity-optimizer*.onrender.com`). TimescaleDB removed (PostgreSQL only) |
**Validators:** `validate_api_key_differs_from_jwt` (@model_validator) ensures `internal_api_key` and `jwt_secret` are not identical in production.

**Properties:** `is_production`, `is_development`, `effective_database_url`.

### config/secrets.py

`SecretsManager` with 27 `SECRET_MAPPINGS` (up from 17) mapping 1Password item/field pairs to env vars. In production, secrets are fetched from 1Password vault "Electricity Optimizer" (`OP_VAULT`); in dev, falls back to env vars.

**New mappings (added in env var audit):** `resend_api_key`, `google_client_id`, `google_client_secret`, `github_client_id`, `github_client_secret`, `gmail_client_id`, `gmail_client_secret`, `outlook_client_id`, `outlook_client_secret`, `redis_url`.

**Renamed:** `postgres_password` → `database_url` (full connection string instead of password-only).

### config/database.py

`DatabaseManager` manages two backends:

| Backend | Client | Pool Config |
|---------|--------|-------------|
| Neon PostgreSQL | SQLAlchemy `AsyncEngine` + optional `asyncpg.Pool` | pool_size=3, max_overflow=5, pool_recycle=200, pool_timeout=20 |
| Redis | `redis.asyncio.Redis` | max_connections=10, socket_keepalive=True |

**Neon handling:** SSL auto-required for `neon.tech` URLs; `sslmode`/`channel_binding`
params stripped from URL (asyncpg uses connect_args). Raw-query asyncpg pool skipped
for Neon; uses SQLAlchemy-only path.

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

**Singleton factory:** `get_vector_store_singleton()` returns a module-level `HNSWVectorStore`
instance, avoiding repeated HNSW index rebuilds across requests. Used by `api/dependencies.py`
for both `get_recommendation_service` and `get_learning_service`.

**Domains:** `price_pattern`, `optimization`, `recommendation`, `bias_correction`.

**Helper functions:**
- `price_curve_to_vector(prices, target_dim=24)` -- resample + L2-normalize
- `appliance_config_to_vector(appliances, target_dim=24)` -- encode power/duration/start

### services/observation_service.py

`ObservationService` -- closes the feedback gap between predictions and actuals.

| Method | Purpose |
|--------|---------|
| `record_forecast()` | Batch INSERT forecast predictions into `forecast_observations` (region normalized to lowercase via `region.lower()`) — supports bulk observables |
| `observe_actuals_batch()` | Match unobserved forecasts to `electricity_prices` by region+hour (uses parameterized SQL, no LOWER()) |
| `record_recommendation()` | Record recommendation served to user |
| `record_recommendation_response()` | Update outcome with user acceptance/savings |
| `get_forecast_accuracy()` | MAPE, RMSE, coverage for a region/timeframe |
| `get_hourly_bias()` | Per-hour AVG(predicted - actual) for bias correction |
| `get_model_accuracy_by_version()` | Accuracy breakdown by model version for weight tuning |

**Bulk inserts:** Both `forecast_observations` and `connection_extracted_rates` use batch insert patterns via `bulk_create()` in repositories for efficient bulk data persistence.

### services/learning_service.py

`LearningService` -- nightly adaptive learning cycle (inspired by AgentDB's NightlyLearner).

| Step | Method | Action |
|------|--------|--------|
| 1 | `compute_rolling_accuracy()` | MAPE/RMSE per model from `forecast_observations` (SQL GROUP BY aggregation with coverage metric) |
| 2 | `detect_bias()` | Systematic over/under by hour-of-day |
| 3 | `update_ensemble_weights()` | Inverse-MAPE weighting -> Redis `model:ensemble_weights` |
| 4 | `store_bias_correction()` | Hourly correction vector -> vector store domain `bias_correction` |
| 5 | `prune_stale_patterns()` | Remove low-confidence vectors |

**Weight bounds:** 0.1 min, 0.8 max per model. Re-normalized after clamping.
**Aggregation:** Uses parameterized SQL with `GROUP BY` and coverage filtering instead of Python-level grouping.

### services/stripe_service.py

`StripeService` handles subscription lifecycle.

| Operation | Method | Stripe API |
|-----------|--------|-----------|
| Checkout | `create_checkout_session()` | `stripe.checkout.Session.create` |
| Portal | `create_customer_portal_session()` | `stripe.billing_portal.Session.create` |
| Status | `get_subscription_status()` | `stripe.Subscription.list` |
| Cancel | `cancel_subscription()` | `stripe.Subscription.cancel` / `.modify` |
| Webhook | `handle_webhook_event()` | Processes checkout.session.completed, subscription.updated/deleted, invoice.payment_failed |

**payment_failed fix**: Resolves user_id from `stripe_customer_id` via `UserRepository.get_by_stripe_customer_id()` when invoice webhook lacks user metadata.

### services/notification_dispatcher.py

`NotificationDispatcher` -- multi-channel notification routing with delivery tracking and deduplication.

| Channel | Purpose | Persistence |
|---------|---------|-------------|
| IN_APP | Database notification row | Full (notifications table) |
| PUSH | OneSignal push notification | Tracked in notification row |
| EMAIL | Transactional email via Resend/SMTP | Tracked in notification row |

**Delivery Tracking (Migrations 029 + 032):**
- `delivery_channel`: which channel was used
- `delivery_status`: pending → sent / failed
- `delivered_at`: timestamp when status became "sent"
- `retry_count`: incremented on each attempt
- `error_message`: diagnostics on failure

**Deduplication:** Optional cooldown window (immediate=1h, hourly=1h, daily=24h, weekly=7d) via `dedup_key` + `cooldown_seconds`.

**Methods:**
- `send()`: Async dispatch across channels with tracking
- `batch_send()`: Dispatch to multiple users
- `get_delivery_status()`: Query tracking by notification_id

### services/ab_test_service.py

`ABTestService` -- consistent-hash-based A/B test assignment without hot-path DB writes.

| Method | Purpose |
|--------|---------|
| `assign_user(user_id, version_a, version_b, split_ratio)` | Deterministic SHA-256 assignment (persisted lazily) |
| `get_assignment(user_id)` | Query persisted assignment or compute via hash |
| `record_prediction(user_id, model_version, region, predicted, actual)` | Store prediction event |
| `update_actual(prediction_id, actual_value)` | Backfill actual + compute error % |
| `get_split_metrics()` | MAPE/MAE/count aggregated by version |
| `auto_promote(version_a, version_b, threshold, min_predictions)` | Automatic winner selection if challenger beats champion |

**Tables:** `model_predictions` (per-user, per-version events), `model_ab_assignments` (persistent user→version mapping).

### services/model_version_service.py

`ModelVersionService` -- ML model versioning and lifecycle management.

| Method | Purpose |
|--------|---------|
| `create_version(model_name, config, metrics)` | Persist new (inactive) model version |
| `get_active_version(model_name)` | Get currently active version |
| `promote_version(version_id)` | Atomically set version active, deactivate others |
| `list_versions(model_name, limit)` | Recent versions newest-first |
| `compare_versions(version_a_id, version_b_id)` | Side-by-side metric comparison |
| `create_ab_test(version_a_id, version_b_id, split_ratio)` | Start A/B test run |
| `evaluate_ab_test(test_id)` | Compute winner via accuracy metrics |

**Tables:** `model_versions`, `ab_tests`, `ab_outcomes`, `model_predictions`, `model_ab_assignments`.

### services/agent_service.py

`AgentService` -- RateShift AI assistant with LLM failover and tool integration.

| Component | Purpose |
|-----------|---------|
| **Primary LLM** | Gemini 2.5 Flash (free tier: 10 RPM, 250 RPD) |
| **Fallback LLM** | Groq Llama 3.3 70B (on Gemini 429) |
| **Tools** | Composio (16 connected apps, 1K actions/month free) |
| **Streaming** | SSE via `POST /agent/query` |
| **Async Jobs** | Queue + polling via `POST /agent/task` + `GET /agent/task/{job_id}` |

**Rate Limits (per tier):**
- Free: 3 queries/day
- Pro: 20 queries/day
- Business: unlimited

**Methods:**
- `query_stream()`: Stream LLM response with tool execution
- `submit_job()`: Async task submission for long-running queries
- `get_job_result()`: Poll job status
- `get_usage()`: Query rate limit tracking

**Persistence:** `agent_conversations`, `agent_usage_daily`, `agent_messages` tables (migration 031).

### services/alert_renderer.py

`AlertRenderer` -- template-based alert message formatting.

| Method | Purpose |
|--------|---------|
| `render_price_alert()` | Format price threshold breach notification |
| `render_recommendation()` | Format savings recommendation |
| `render_connection_health()` | Format connection status alert |

### services/data_persistence_helper.py

`persist_batch()` -- shared batch INSERT logic for internal fetch endpoints.

**Used by:**
- `fetch-weather` → weather_cache table
- `market-research` → market_intel_cache table
- `scrape-rates` → rate_data_cache table

**Parameters:**
- `db`: AsyncSession
- `table`: destination table name
- `sql`: parameterized INSERT statement
- `rows`: list[dict] of data
- `log_context`: for safe logging (no PII)

**Returns:** count of persisted rows.


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

`PriceUnit` enum (canonical, single source of truth): `KWH`, `MWH`, `CENTS_KWH`, `GBP_KWH`, `EUR_KWH`, `USD_KWH`,
`THERM`, `MCF`, `MMBTU`, `CCF`, `GALLON`, `CREDIT_KWH`.
All modules import `PriceUnit` from `models/utility.py`; the former local definitions in
`models/price.py` and `integrations/pricing_apis/base.py` have been removed.

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

### ModelVersion model

Fields: `id` (UUID), `model_name`, `version_string`, `config` (JSONB), `metrics` (MAPE, MAE, RMSE, coverage), `is_active`, `created_at`, `promoted_at`.

**Purpose:** Versioning and A/B testing infrastructure for ML models. Supports side-by-side metric comparison and automated winner selection.

### ModelConfig model

Fields: `id` (UUID), `model_name`, `config_name`, `parameters` (JSONB), `version`, `created_at`.

**Purpose:** Store and retrieve ML pipeline configurations (ensemble weights, hyperparameters, feature flags).

### Notification model (enhanced)

Fields: `id` (UUID), `user_id` (FK), `type`, `title`, `body`, `read` (boolean), `created_at`,
**Delivery tracking (Migration 029 + 032):**
- `delivery_channel` (in_app/push/email)
- `delivery_status` (pending/sent/failed)
- `delivered_at` (timestamp on success)
- `retry_count` (incremented per attempt)
- `error_message` (diagnostics on failure)

### ABAssignment model

Fields: `id` (UUID), `user_id` (FK), `model_version` (string), `assigned_at` (timestamp).

**Purpose:** Persistent storage of A/B test assignments to ensure users receive consistent model versions.

### Prediction model

Fields: `id` (UUID), `user_id` (FK), `model_version`, `region`, `predicted_value`, `actual_value` (nullable, backfilled), `error_pct` (computed), `created_at`.

**Purpose:** Event tracking for A/B test accuracy evaluation and model performance metrics.


## Repositories

All extend `BaseRepository[T]` (abstract generic with CRUD + list + count).

| Repository | Model | Key Methods |
|------------|-------|-------------|
| `PriceRepository` | `Price` | `get_current_prices` (filters by utility_type), `get_latest_by_supplier`, `get_historical_prices_paginated` (pagination support), `bulk_create`, `get_price_statistics` |
| `SupplierRegistryRepository` | `SupplierRegistry` | `list_suppliers` (paginated, filters: region/utility_type/green/active), `get_by_id`; Redis TTL cache (5min) for supplier data; WHERE clauses built from fixed literals only (no f-string interpolation — CWE-89 fix) |
| `StateRegulationRepository` | `StateRegulation` | `list_deregulated` (filters: electricity/gas/oil/community_solar), `get_by_state`; WHERE clauses built from fixed literals only (CWE-89 fix) |
| `UserRepository` | `User` | `get_by_email`, `update_preferences`, `update_last_login`, `record_consent` |
| `ConsentRepository` | `ConsentRecord` | `get_by_user_and_purpose`, `get_latest_by_user_and_purpose`, `delete_by_user_id` |
| `DeletionLogRepository` | `DeletionLog` | `create`, `get_by_user_id` (immutable -- no update/delete) |

`PriceRepository` has built-in Redis caching (60s TTL for current prices).


## Services

| Service | Dependencies | Purpose |
|---------|-------------|---------|
| `PriceService` | PriceRepository, Redis, ML EnsemblePredictor | Price queries, comparison, forecast (ML-first with simulation fallback), optimal windows |
| `AnalyticsService` | PriceRepository, Redis | Trends, volatility, peak hours, supplier comparison (cache=redis wired in dependencies.py) |
| `RecommendationService` | PriceService, UserRepository, HNSWVectorStore | Switching + usage recommendations (with pattern-based confidence adjustment) |
| `AlertService` | EmailService | Threshold checking + alert emails |
| `EmailService` | Settings | Resend primary, SMTP fallback, Jinja2 templates |
| `StripeService` | Settings | Checkout, portal, subscriptions, webhooks |
| `VectorStore` | SQLite, numpy | Price pattern matching, optimization caching |
| `HNSWVectorStore` | VectorStore, hnswlib | HNSW-accelerated vector search (wraps VectorStore) |
| `ObservationService` | AsyncSession | Record forecasts, backfill actuals, track outcomes |
| `LearningService` | ObservationService, HNSWVectorStore, Redis | Nightly learning: accuracy, bias, weight tuning |
| `PriceSyncService` | PricingService, PriceRepository | Orchestrate external API fetch + bulk persist (used by /prices/refresh) |
| `ConnectionService` | AsyncSession | Core connection CRUD and status management |
| `ConnectionSyncService` | AsyncSession, encryption | UtilityAPI sync: fetch meters, bills, extract rates |
| `ConnectionAnalyticsService` | AsyncSession | Rate comparison vs market, history, savings, stale detection, rate change alerts |
| `EmailOAuthService` | Settings, encryption | OAuth2 for Gmail/Outlook: consent URLs, token exchange, refresh, HMAC state |
| `EmailScannerService` | AsyncSession | Gmail/Outlook inbox scanning: keyword search, MIME traversal, regex rate extraction |
| `BillParser` | -- | Document parsing: PDF text extraction, OCR for images, rate/supplier/amount detection |
| `GDPRComplianceService` | ConsentRepo, UserRepo | Consent, export, deletion, retention |
| `MaintenanceService` | AsyncSession | Data retention cleanup: activity logs (365d), bill uploads (730d), prices (365d), observations (90d); calls PL/pgSQL functions |
| `NotificationService` | AsyncSession, EmailService | Create/deliver notifications, manage preferences |
| `SavingsService` | AsyncSession, ConnectionService | Calculate/track savings, manage goals |
| `FeatureFlagService` | Redis | Evaluate feature flags, manage user toggles |


## Middleware Stack

All custom middleware uses the **pure ASGI protocol** (`__call__(scope, receive, send)`) instead of Starlette's `BaseHTTPMiddleware`. This avoids response buffering that would deadlock SSE streams. Headers are injected via `send_wrapper` intercepting `http.response.start` messages.

Applied in reverse order (last added = first executed):

1. **TracingMiddleware** -- Request tracing with correlation IDs, timing, structured logging
2. **Request ID + Timing** -- UUID per request, X-Process-Time header (dev only)
3. **Metrics Auth** -- API key required for `/metrics` endpoint
4. **RequestTimeoutMiddleware** -- 30s timeout per request (SSE `/prices/stream` and `/api/v1/internal/*` excluded); pure ASGI with `asyncio.wait_for`
5. **RequestBodySizeLimitMiddleware** -- 1 MB limit (10 MB for `/connections/upload`); pure ASGI with Content-Length fast path + chunked `counting_receive` wrapper
6. **RateLimitMiddleware** -- Per-user/IP sliding window (Redis or in-memory fallback); pure ASGI, extracts identifier from raw `scope["headers"]`
7. **SecurityHeadersMiddleware** -- CSP, HSTS, X-Frame-Options, Permissions-Policy, cache-control for `/api/*`; pure ASGI
8. **GZipMiddleware** -- Compress responses > 1000 bytes
9. **CORSMiddleware** -- Origin regex restricted to `electricity-optimizer*.(vercel|onrender)`

Excluded from rate limiting: `/health`, `/health/live`, `/health/ready`, `/metrics`.


## Authentication & Authorization

Two auth mechanisms:

1. **Neon Auth Session** (user auth):
   - `get_current_user` dependency in `auth/neon_auth.py` validates sessions
   - Checks `better-auth.session_token` cookie or `Authorization: Bearer <token>` header
   - Checks Redis cache first (120s TTL, key=`session:<sha256(token)[:32]>`) before DB query
   - Queries `neon_auth.session` + `neon_auth.user` tables directly via raw SQL on cache miss
   - Returns `SessionData(user_id, email, name)` on success (canonical name; `TokenData` deprecated)
   - Returns HTTP 401 if token invalid/expired, HTTP 503 if DB unavailable
   - `get_current_user_optional` returns `None` if missing/invalid
   - `ensure_user_profile()` syncs new Neon Auth users to our `users` table on first API call

2. **X-API-Key Header** (service-to-service):
   - `verify_api_key` dependency uses `hmac.compare_digest` (constant-time)
   - Validates against `settings.internal_api_key`
   - Used by `/prices/refresh` and `/internal/*` endpoints (GitHub Actions)

**Authorization:** `require_permission(scope)`, `require_permissions([...])`,
`require_any_permission([...])` factory functions for scope-based access control.

**Legacy cleanup:** `jwt_handler.py` and `middleware.py` have been deleted.
`TokenData` is aliased to `SessionData` in `api/dependencies.py` for backward compat.


## Database (Neon PostgreSQL)

20 public tables + 9 neon_auth tables = 29 total (init_neon.sql + 002-009, 011-023):

| Table | PK Type | Notes |
|-------|---------|-------|
| `users` | UUID | email UNIQUE, region indexed |
| `electricity_prices` | UUID | region + timestamp indexed, utility_type column (default: electricity) |
| `suppliers` | UUID | name UNIQUE, utility_types array column |
| `tariffs` | UUID | FK to suppliers, utility_type column |
| `supplier_registry` | UUID | DB-backed supplier data (replaces mock data). Columns: utility_types[], regions[], rating, green_energy_provider, metadata JSONB |
| `state_regulations` | VARCHAR(2) PK | Deregulation flags, PUC info, licensing requirements |
| `consent_records` | UUID | FK to users (ON DELETE SET NULL), user_id nullable for GDPR compliance |
| `deletion_logs` | UUID | Immutable (trigger blocks UPDATE/DELETE) |
| `beta_signups` | UUID | email UNIQUE |
| `auth_sessions` | UUID | FK to users |
| `login_attempts` | UUID | FK to users |
| `activity_logs` | UUID | FK to users |
| `forecast_observations` | UUID | predicted vs actual prices, partial index on unobserved |
| `recommendation_outcomes` | UUID | user acceptance + actual savings tracking |
| `user_connections` | UUID | FK to users, connection_type enum, status, supplier_name, OAuth tokens (encrypted), sync columns |
| `bill_uploads` | UUID | FK to user_connections, file metadata, parse_status, detected rates/supplier/amounts |
| `connection_extracted_rates` | UUID | FK to user_connections, rate_per_kwh, effective_date, source, raw_label |
| `user_alerts` | UUID | FK to users, price threshold, region, status, trigger_count |
| `alert_history` | UUID | FK to user_alerts, triggered_at, actual_price, sent status |
| `user_savings` | UUID | FK to users, period (month), savings_amount, projected savings |
| `savings_goals` | UUID | FK to users, target_amount, target_date, category, progress |
| `user_notifications` | UUID | FK to users, type, title, body, read, created_at |
| `notification_preferences` | UUID | FK to users, price_alerts, recommendations, savings, connections |
| `feature_flags` | UUID | flag_name, enabled, rollout_percentage |
| `user_feature_toggles` | UUID | FK to users, FK to feature_flags, user_enabled |
| `model_versions` | UUID | model_name, version_string, config (JSONB), metrics (JSONB), is_active, promoted_at |
| `ab_tests` | UUID | version_a_id, version_b_id, split_ratio, status, created_at |
| `ab_outcomes` | UUID | FK to ab_tests, user_id, outcome_type, value |
| `model_configs` | UUID | model_name, config_name, parameters (JSONB), version |
| `feedback` | UUID | FK to users, feedback_type, message, context (JSONB), created_at |
| `agent_conversations` | UUID | FK to users, title, model_used, created_at |
| `agent_messages` | UUID | FK to agent_conversations, role, content, tokens_used, duration_ms |
| `agent_usage_daily` | UUID | FK to users, date, query_count, token_count |
| `weather_cache` | UUID | region, temperature, humidity, wind_speed, timestamp, cached_at |
| `market_intel_cache` | UUID | query, results (JSONB), source, cached_at |
| `rate_data_cache` | UUID | supplier_id, region, rates (JSONB), effective_date, cached_at |
| `model_predictions` | UUID | user_id, model_version, region, predicted_value, actual_value (nullable), error_pct (nullable), created_at |
| `model_ab_assignments` | UUID | user_id (UNIQUE per test context), model_version, assigned_at |

**Custom types:** `utility_type` enum (electricity, natural_gas, heating_oil, propane, community_solar). `connection_type` enum (email_oauth, bill_upload, direct_login, utilityapi, portal_scrape). `notification_type` enum (price_alert, recommendation, savings_milestone, connection_health). `delivery_channel` enum (in_app, push, email). `delivery_status` enum (pending, sent, failed). `feedback_type` enum (bug_report, feature_request, general_feedback, savings_tracking, rate_quality).


## Migrations

| File | Purpose |
|------|---------|
| `init_neon.sql` | Initial schema (7 tables, indexes, seed data) |
| `002_gdpr_auth_tables.sql` | GDPR consent/deletion tables, auth sessions, activity logs |
| `003_reconcile_schema.sql` | Reconcile column divergence between init and 002 |
| `004_performance_indexes.sql` | Compound index on `electricity_prices(region, supplier, timestamp DESC)`, partial index on `users(stripe_customer_id)` |
| `005_observation_tables.sql` | `forecast_observations` + `recommendation_outcomes` tables with indexes for adaptive learning |
| `006_multi_utility_expansion.sql` | `utility_type` enum, `utility_type` columns on prices/suppliers/tariffs, `supplier_registry` table, `state_regulations` table, CT seed data |
| `007_user_supplier_accounts.sql` | User supplier account tables |
| `008_connection_feature.sql` | Base connection tables: `user_connections`, `bill_uploads`, `connection_extracted_rates` |
| `009_email_oauth_tokens.sql` | OAuth token columns on `user_connections` |
| `011_utilityapi_sync_columns.sql` | UtilityAPI sync columns (`last_sync_at`, `sync_frequency_hours`, etc.) |
| `012_user_savings.sql` | Savings tracking tables for user analytics |
| `013_user_profile_columns.sql` | Additional profile fields: phone, address, notification preferences |
| `014_alert_tables.sql` | Alert configuration, history, and delivery logs |
| `015_notifications.sql` | User notification storage and preference tracking |
| `016_feature_flags.sql` | Feature flag storage and user feature toggles |
| `017_additional_indexes.sql` | Performance indexes for alerts, notifications, savings queries |
| `018_connection_supplier_name.sql` | Supplier name column on user_connections (denormalization for rates display) |
| `019_nationwide_suppliers_seed.sql` | 34+ nationwide suppliers seeded across deregulated states (TX, OH, PA, IL, NY, NJ, MA, MD, MI, CA, FL, GA, VA) |
| `020_composite_indexes.sql` | 3 composite indexes: prices(region+supplier+created DESC), prices(region+utility_type+created DESC), users(region) |
| `021_supplier_api_available.sql` | Set `api_available=true` for 37 suppliers with direct login APIs |
| `022_user_supplier_composite_index.sql` | Composite index on `user_supplier_accounts` for faster lookups |
| `023_db_audit_indexes.sql` | **DEPLOYED** — 2 partial indexes (sync_due + alert_configs), meter_number columns, consent FK CASCADE->SET NULL, 2 PL/pgSQL data retention functions |

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
| resend | >=2.0,<3.0 | Email (primary) |
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
  -> Router (Neon Auth session validation via get_current_user)
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

Data Retention (data-retention.yml, Sunday 3AM UTC):
  -> POST /api/v1/internal/maintenance/cleanup (X-API-Key)
  -> MaintenanceService cleanup chain:
     - cleanup_activity_logs(365) -> activity logs table
     - cleanup_expired_uploads(730) -> bill uploads table
     - cleanup_old_prices(365) -> electricity_prices table
     - cleanup_old_observations(90) -> forecast_observations table
  -> All calls use PL/pgSQL cleanup_* functions for efficiency
```

### Recommendation Confidence Adjustment

```
RecommendationService._compute_switching() / _compute_usage():
  -> price_curve_to_vector(prices)
  -> HNSWVectorStore.search(vector, domain="recommendation", k=3)
  -> If similar pattern found with high confidence: boost recommendation confidence
  -> If similar pattern found with low confidence: reduce recommendation confidence
```

### Connection Import (5 methods)

```
1. Email OAuth (Gmail/Outlook):
   POST /connections {type: email_oauth} -> create connection
   -> redirect to Google/Outlook consent URL (HMAC-SHA256 state)
   -> GET /connections/email/callback -> verify state, exchange code, encrypt tokens
   -> POST /connections/email/{id}/scan -> search inbox for utility emails
   -> extract rates from body via regex + download/parse attachments via BillParser
   -> store in connection_extracted_rates

2. Bill Upload:
   POST /connections {type: bill_upload} -> create connection
   -> POST /connections/{id}/upload (multipart) -> store file, queue parse
   -> BillParser: PDF text extraction / OCR -> detect supplier, rates, amounts
   -> GET /connections/{id}/uploads/{uid} -> poll parse status

3. Direct Login:
   POST /connections {type: direct_login} -> create connection + encrypted credentials
   -> POST /connections/{id}/sync -> trigger UtilityAPI-style data fetch
   -> GET /connections/{id}/sync-status -> poll sync status

4. UtilityAPI:
   POST /connections {type: utilityapi} -> create connection
   -> POST /connections/{id}/sync -> UtilityAPI meters/bills endpoint
   -> extract rates from bill data -> store in connection_extracted_rates

5. Portal Scrape:
   POST /connections/portal -> create connection + encrypt portal credentials (AES-256-GCM)
   -> POST /connections/portal/{id}/scrape -> httpx-based portal login + data extraction
   -> PortalScraperService: login, navigate account page, extract rates from HTML
   -> store in connection_extracted_rates
   Supported utilities: Duke Energy, PG&E, Con Edison, ComEd, FPL
```

### SSE Price Stream

```
Client -> GET /api/v1/prices/stream?region=us_ct&interval=30
  -> get_current_user (Session auth required -- HTTP 401 if missing)
  -> Connection limit check: _SSE_MAX_CONNECTIONS_PER_USER = 3 (HTTP 429 if exceeded)
  -> _sse_connections[user_id] incremented; decremented on disconnect (finally block)
  -> StreamingResponse(event_stream())
  -> _price_event_generator(region, price_service, interval, request):
     -> PriceService.get_current_prices(region, limit=3) for real DB data
     -> Falls back to _generate_mock_prices() if DB returns empty or errors
     -> Each event includes "source": "live" or "source": "fallback"
  -> Sends heartbeat comment (": heartbeat") every 15 seconds to keep proxies alive
  -> Checks request.is_disconnected() between sleep chunks to stop promptly
```

**Frontend client:** `@microsoft/fetch-event-source` (replaces native `EventSource`)
with `credentials: 'include'` for cookie-based session auth.


## Security

| Area | Implementation |
|------|----------------|
| Session auth | Neon Auth sessions validated via `neon_auth.session` table (httpOnly cookies, SHA-256 cache key) |
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
| Token revocation | Neon Auth manages session expiry; legacy JWT system removed |
| OAuth tokens | AES-256-GCM encrypted at rest (base64-encoded for TEXT columns) |
| OAuth state | HMAC-SHA256 signed with nonce for CSRF protection |
| Connection endpoints | Paid tier required (subscription gating via `require_paid_tier` dependency) |
| Bill uploads | File type validation (PDF, PNG, JPG, JPEG, TIFF only), 10 MB max size |


## Test Commands

```bash
# Run all backend tests (use venv)
.venv/bin/python -m pytest backend/tests/ -v

# Run specific test file
.venv/bin/python -m pytest backend/tests/test_security.py -v

# Run with coverage
.venv/bin/python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

**Test status:** 2,043 passed, 2 skipped, 0 failures (as of 2026-03-11). 68+ test files. Includes: utility integration track (+150 tests: email extraction, attachment parsing, portal connections, portal scraping, scraper persistence, unified analytics, internal scan/scrape endpoints), notification delivery tracking, A/B testing framework, CSP security headers, tier gating, health-data endpoint.


## Scripts & Automation

### scripts/

| File | Purpose |
|------|---------|
| `deploy.sh` | One-command deployment (validates `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `INTERNAL_API_KEY`) |
| `health-check.sh` | Service health verification: Backend API, Frontend, Redis (configurable via `REDIS_HOST`/`REDIS_PORT`) |
| `db_maintenance.py` | Scheduled database maintenance cron job. Runs `cleanup_old_prices(365)` and `cleanup_old_observations(90)` via asyncpg. Designed for Render cron jobs |
| `notion_hub_setup.py` | Creates Notion Hub page + 3 databases (Project Tracker, Automation Workflows, Architecture Decisions). Rerunnable — detects existing hub page. Outputs `.notion_hub_ids.json` |
| `install-hooks.sh` | Installs git hooks from `.claude/hooks/board-sync/` templates |
| `loki-feature.sh` | Automated feature pipeline: PRD → branch → RARV → verify → draft PR |
| `loki-decompose.py` | Parse PRD markdown into JSON task list for RARV orchestrator |
| `loki-verify.sh` | Verification gate: full/quick/backend-only test + lint, emits events |

### .claude/hooks/board-sync/

Local board-sync infrastructure. See [Infrastructure](./INFRASTRUCTURE.md#board-sync-local-automation) for full details.

| File | Purpose |
|------|---------|
| `sync-boards.sh` | Central orchestrator (lock, debounce, queue, GitHub Projects sync). Notion sync removed 2026-03-06 — handled by Rube recipe only |
| `activate-orchestration.sh` | Claude PreToolUse hook — Claude Flow MCP detect + Loki init + hooks pretrain |
| `session-end-orchestration.sh` | Claude Stop hook — state persist + SONA metrics export + marker cleanup |
| `post-edit-sync.sh` | Claude PostToolUse hook — queues sync on Edit/Write/MultiEdit |
| `post-task-sync.sh` | Claude PostToolUse hook — drains queue on TaskUpdate |
| `session-end-sync.sh` | Claude Stop hook — foreground forced sync |
| `git-post-commit.sh` | Git hook template (background sync on commit) |
| `git-post-merge.sh` | Git hook template (background sync on merge) |
| `git-post-checkout.sh` | Git hook template (background sync on branch switch) |
