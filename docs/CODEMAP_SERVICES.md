# RateShift Backend Services Codemap

**Last Updated**: 2026-03-25
**Total Services**: 51
**Total Test Files**: 105+
**Repositories**: 1 (monorepo)

---

## Quick Navigation

This document maps all 51 backend services across 9 functional domains. Use this to:
- Find which service handles a feature
- Understand service dependencies
- Locate related tests
- Navigate to source code

**Table of Contents**:
1. [Service Domains Overview](#service-domains-overview)
2. [Pricing Services (5)](#pricing-services)
3. [Billing Services (2)](#billing-services)
4. [ML/AI Services (8)](#mlai-services)
5. [Utility Services (5)](#utility-services)
6. [Connection Services (6)](#connection-services)
7. [Community Services (4)](#community-services)
8. [Notification Services (6)](#notification-services)
9. [Analytics Services (4)](#analytics-services)
10. [Utility Support Services (11)](#utility-support-services)
11. [Service Dependency Diagram](#service-dependency-diagram)

---

## Service Domains Overview

| Domain | Count | Purpose |
|--------|-------|---------|
| **Pricing** | 5 | Fetch, sync, forecast, and analyze electricity prices |
| **Billing** | 2 | Stripe subscription management and dunning cycles |
| **ML/AI** | 8 | Machine learning, vector search, forecasting, AI agent |
| **Utilities** | 5 | Gas, oil, propane, water rates and discovery |
| **Connections** | 6 | UtilityAPI sync, email/portal scraping, bill parsing |
| **Community** | 4 | Posts, voting, solar/CCA services, neighborhood insights |
| **Notifications** | 6 | Email, push, in-app, alerts, dispatching, rendering |
| **Analytics** | 4 | Usage tracking, KPI reports, optimization, A/B tests |
| **Support** | 11 | Geocoding, weather, features, referrals, savings, etc. |

---

## Pricing Services

### price_service.py
- **Class**: `PriceService`
- **Purpose**: Core business logic for price queries, comparisons, and ML predictions
- **Key Methods**:
  - `get_current_price(region: str) -> Decimal` — fetch latest price for region
  - `get_forecast(region: str, days: int) -> list[PriceForecast]` — predict future prices
  - `compare_suppliers(region: str) -> list[dict]` — rank suppliers by price
  - `get_price_history(region: str, lookback_days: int)` — historical prices
- **Dependencies**: `PriceRepository`, ML `EnsemblePredictor`, async cache (Redis/in-memory)
- **Tests**: `test_api_predictions.py`, `test_vector_store.py`

### price_sync_service.py
- **Class**: `PriceSyncService`
- **Purpose**: Orchestrates external API calls, transforms data, persists via repository
- **Key Methods**:
  - `sync_prices(regions: list[str]) -> dict` — main entry point (called by /prices/refresh)
  - `_fetch_from_api(region: str)` — calls configured pricing provider
  - `_persist_prices(prices: list[Price])` — bulk insert to DB
- **Dependencies**: `PricingService`, `PriceRepository`, external APIs (EIA, NREL, utility-specific)
- **Tests**: `test_price_sync_service.py`, `test_api_predictions.py`

### rate_scraper_service.py
- **Class**: `RateScraperService`
- **Purpose**: Parallel web scraping via Diffbot Extract API with semaphore gating (5 calls/min)
- **Key Methods**:
  - `scrape_supplier_rates(suppliers: list[str]) -> list[dict]` — batch scrape 37+ suppliers
  - `_scrape_one(supplier_name: str, url: str)` — individual supplier with 30s timeout
  - `_extract_rate_from_diffbot_data(data: dict) -> Decimal` — parse Diffbot response
- **Dependencies**: `httpx` (async HTTP), Diffbot API, `structlog` tracing
- **Tests**: `test_supplier_cache.py`, `test_integrations.py`

### rate_change_detector.py
- **Class**: `RateChangeDetector`, `AlertPreferenceService`
- **Purpose**: Detect price movements, classify as alerts, route to user preferences
- **Key Methods**:
  - `detect_changes(region: str) -> list[PriceChange]` — compare current vs recent
  - `classify_alert_severity(change: PriceChange) -> AlertType` — LOW/MEDIUM/HIGH
  - `apply_user_preferences(alerts: list, user_id: str) -> list` — filter by user config
- **Dependencies**: `AlertService`, `PriceRepository`, `NotificationDispatcher`
- **Tests**: `test_rate_change_detector.py`

### rate_export_service.py
- **Class**: `RateExportService`
- **Purpose**: Formats price data for bulk export (CSV, JSON, API integrations)
- **Key Methods**:
  - `export_to_csv(region: str, lookback_days: int) -> bytes` — CSV export
  - `export_to_json(region: str) -> dict` — JSON response
  - `validate_export_quota(user_id: str) -> bool` — rate limit check (tier-gated)
- **Dependencies**: `PriceRepository`, CSV writer, JSON serializer
- **Tests**: `test_rate_export_service.py`, `test_public_rates.py`

---

## Billing Services

### stripe_service.py
- **Class**: `StripeService`
- **Purpose**: Subscription lifecycle, checkout sessions, webhook handling, customer portal
- **Key Methods**:
  - `create_checkout_session(user_id: str, plan: str) -> str` — checkout URL (Free/$4.99 Pro/$14.99 Business)
  - `apply_webhook_action(event: StripeEvent)` — handle payment_intent.succeeded, invoice.payment_failed, etc.
  - `get_customer_portal_url(user_id: str) -> str` — self-service billing portal
  - `get_active_subscription(user_id: str) -> dict` — current tier + end_date
- **Dependencies**: Stripe SDK (`stripe`), `UserRepository`, `DunningService`, async operations
- **Tests**: `test_stripe_service.py`, `test_internal_billing.py`, `test_webhooks.py`

### dunning_service.py
- **Class**: `DunningService`
- **Purpose**: Overdue payment escalation (7-day grace period, soft → final email)
- **Key Methods**:
  - `dunning_cycle()` -> list[dict]` — process all overdue invoices (daily 7am UTC)
  - `record_dunning_attempt(invoice_id: str, step: str)` — track retry attempts
  - `resolve_via_webhook(event: StripeEvent)` — real-time payment success/failure
- **Dependencies**: `StripeService`, `EmailService`, `PaymentRetryHistory` table (migration 024), `UserRepository`
- **Tests**: `test_dunning_service.py`, `test_internal_billing.py`

---

## ML/AI Services

### forecast_service.py
- **Class**: `ForecastService`
- **Purpose**: Multi-utility forecasting — electricity (ML ensemble) + gas/oil/propane (linear trend) + water (scheduled changes)
- **Key Methods**:
  - `forecast(utility_type: str, region: str, horizon_days: int) -> list[Forecast]` — unified API
  - `_forecast_electricity(region: str, days: int)` — delegates to `PriceService.get_forecast()` (EnsemblePredictor)
  - `_forecast_trend(utility_type: str, region: str, days: int)` — linear extrapolation (gas/oil/propane)
  - `_forecast_water(region: str, days: int)` — scheduled municipal changes (no ML)
- **Dependencies**: `PriceService`, `EnsemblePredictor`, SQL trend queries, `structlog`
- **Tests**: `test_forecast_service.py`, `test_forecast_observation_repository.py`

### learning_service.py
- **Class**: `LearningService`
- **Purpose**: Nightly learning cycle — computes accuracy, detects bias, adjusts ensemble weights, prunes stale patterns
- **Key Methods**:
  - `run_learning_cycle() -> dict` — main entry point (POST /internal/learn, daily 4am UTC via daily-data-pipeline)
  - `_compute_rolling_accuracy()` — accuracy over last 30 days per model
  - `_adjust_ensemble_weights(accuracies: dict)` — rebalance model weights
  - `_prune_vector_store()` — remove stale patterns from HNSW
- **Dependencies**: `HNSWVectorStore`, `ObservationService`, `ModelVersionService`, Redis + PostgreSQL weight persistence
- **Tests**: `test_learning_service.py`, `test_observation_service.py`

### hnsw_vector_store.py
- **Class**: `HNSWVectorStore`
- **Purpose**: O(log n) approximate nearest-neighbor search via HNSW index (accelerates VectorStore)
- **Key Methods**:
  - `search(query_vector: np.ndarray, k: int) -> list[dict]` — find k nearest patterns
  - `insert(pattern: dict, vector: np.ndarray)` — add pattern to index + SQLite
  - `record_outcome(pattern_id: str, outcome: float)` — mark forecast accuracy
  - `rebuild_index()` — reconstruct HNSW from SQLite on startup
- **Dependencies**: `hnswlib` (HNSW index), `VectorStore` (SQLite), NumPy, structlog
- **Tests**: `test_hnsw_vector_store.py`

### vector_store.py
- **Class**: `VectorStore`
- **Purpose**: SQLite-backed pattern storage (24-dim vectors from hourly price curves)
- **Key Methods**:
  - `insert(pattern: dict, vector: np.ndarray)` — persist pattern + vector
  - `search(query: np.ndarray) -> list[dict]` — brute-force distance search (fallback for HNSW)
  - `record_outcome(pattern_id: str, outcome: float)` — update forecast accuracy
  - `vector_from_curve(prices: list[float]) -> np.ndarray` — convert 24 hourly prices to vector
- **Dependencies**: SQLite3, NumPy, structlog
- **Tests**: `test_vector_store.py`, `test_hnsw_vector_store.py`

### observation_service.py
- **Class**: `ObservationService`
- **Purpose**: Records forecast observations — actual prices vs predictions for accuracy tracking
- **Key Methods**:
  - `record_observation(forecast_id: str, actual_price: Decimal)` — log outcome
  - `get_recent_observations(model_name: str, days: int)` -> list[dict]` — fetch accuracy data
  - `compute_model_accuracy(model_name: str, window_days: int) -> float` — % within ±5%
- **Dependencies**: `ForecastObservationRepository`, `forecast_observations` table (migration 020)
- **Tests**: `test_observation_service.py`

### model_version_service.py
- **Class**: `ModelVersionService`
- **Purpose**: Versioning and HMAC signing of ML models to detect tampering
- **Key Methods**:
  - `sign_model(model_path: str)` — HMAC-SHA256 with `ML_MODEL_SIGNING_KEY`
  - `verify_model(model_path: str, signature: str) -> bool` — guard `sign_model()` with `os.path.exists(path)`
  - `track_version(model_name: str, metrics: dict)` — record accuracy/loss per version
- **Dependencies**: HMAC crypto, `ModelVersionRepository`, `ML_MODEL_SIGNING_KEY` env var
- **Tests**: `test_model_version_service.py`, `test_model_config.py`

### agent_service.py
- **Class**: `AgentService`, `AgentMessage` (dataclass)
- **Purpose**: RateShift AI Assistant — Gemini 3 Flash (primary, 10 RPM free) + Groq Llama 3.3 (fallback) + Composio tools
- **Key Methods**:
  - `query(prompt: str, user_id: str) -> AsyncGenerator[str]` — stream response (SSE)
  - `submit_task(prompt: str, user_id: str) -> str` — async job with polling endpoint
  - `get_usage(user_id: str) -> dict` — queries/day by tier (Free=3, Pro=20, Business=unlimited)
  - `_call_primary_provider()` → Gemini (primary), `_call_fallback_provider()` → Groq (on 429)
- **Dependencies**: `google.genai`, `groq.AsyncGroq`, Composio SDK, `AgentRepository`, rate limiting via `require_tier()`
- **Tests**: `test_agent_service.py`

### data_quality_service.py
- **Class**: `DataQualityService`
- **Purpose**: Validates price data (outlier detection, missing values, anomalies)
- **Key Methods**:
  - `validate_prices(prices: list[Price]) -> list[ValidationResult]` — quality checks
  - `detect_outliers(prices: list[float]) -> list[int]` — Z-score + IQR detection
  - `flag_anomalies(region: str)` — detect sudden spikes/drops
- **Dependencies**: NumPy, SciPy, `structlog`
- **Tests**: `test_data_quality_service.py`

---

## Utility Services

### gas_rate_service.py
- **Class**: `GasRateService`
- **Purpose**: Natural gas pricing — fetch from state regulators + EIA, handle therm conversion
- **Key Methods**:
  - `get_rate(state: str) -> Decimal` — price per therm for state
  - `get_forecast(state: str, days: int) -> list[dict]` — trend extrapolation
  - `convert_therms_to_mmbtu(therms: float) -> float` — energy unit conversion
- **Dependencies**: `PriceRepository`, EIA API, state regulator APIs, `Region` enum
- **Tests**: `test_gas_rate_service.py`, `test_multi_utility.py`

### heating_oil_service.py
- **Class**: `HeatingOilService`
- **Purpose**: Heating oil pricing — regional data from EIA, trend forecasting
- **Key Methods**:
  - `get_rate(region: str) -> Decimal` — price per gallon
  - `get_forecast(region: str, days: int)` — linear trend
  - `get_availability(region: str) -> bool` — check if heating oil is relevant
- **Dependencies**: `PriceRepository`, EIA API
- **Tests**: `test_heating_oil_service.py`

### propane_service.py
- **Class**: `PropaneService`
- **Purpose**: Propane pricing — rural market data, availability checks
- **Key Methods**:
  - `get_rate(state: str) -> Decimal` — price per gallon
  - `get_forecast(state: str, days: int)` — trend forecast
  - `is_available(address: str) -> bool` — check propane availability at address
- **Dependencies**: `PriceRepository`, EIA API, geocoding
- **Tests**: `test_propane_service.py`, `test_multi_utility.py`

### water_rate_service.py
- **Class**: `WaterRateService`
- **Purpose**: Water pricing — municipal schedules (changes via council vote, not market)
- **Key Methods**:
  - `get_rate(city: str) -> Decimal` — price per 1000 gallons
  - `get_schedule(city: str)` → `dict` — rate change dates/amounts
  - `is_tiered(city: str) -> bool` — tiered rates (higher usage = higher $/gal)
- **Dependencies**: `PriceRepository`, municipal APIs (aggregated data)
- **Tests**: `test_water_rate_service.py`, `test_multi_utility.py`

### utility_discovery_service.py
- **Class**: `UtilityDiscoveryService`
- **Purpose**: Identify which utilities serve an address (electricity, gas, water, alternative)
- **Key Methods**:
  - `discover_utilities(address: str, state: str) -> list[str]` — returns ["electricity", "natural_gas", ...]
  - `get_utility_details(utility_type: str, state: str) -> dict` — provider name, regulation, deregulation status
  - `is_deregulated(utility_type: str, state: str) -> bool` — can user choose supplier?
- **Dependencies**: `GeocodingService`, municipal databases, `structlog`
- **Tests**: `test_utility_feature_flags.py`, `test_multi_utility.py`

---

## Connection Services

### connection_sync_service.py
- **Class**: `ConnectionSyncService`
- **Purpose**: Orchestrates UtilityAPI data pulls for authorized connections
- **Key Methods**:
  - `sync_all_due() -> list[str]` — find connections needing sync (sync_frequency_hours overdue)
  - `sync_connection(connection_id: str) -> dict` — call UtilityAPI, persist usage + rate data
  - `handle_sync_error(error: Exception, connection_id: str)` — log error, update connection status
- **Dependencies**: `UtilityAPIClient`, `UserConnectionRepository`, structlog, atomic transaction rollback
- **Tests**: `test_internal_sync.py`, `test_utilityapi.py`

### connection_analytics_service.py
- **Class**: `ConnectionAnalyticsService`
- **Purpose**: Tracks connection performance (uptime, data quality, provider success rate)
- **Key Methods**:
  - `record_sync_success(connection_id: str, rows_imported: int)` — log successful pull
  - `get_connection_health(connection_id: str) -> dict` — uptime %, data completeness
  - `identify_stale_connections()` → `list[str]` — haven't synced in 30 days
- **Dependencies**: `UserConnectionRepository`, `ConnectionAnalyticsRepository`
- **Tests**: `test_connection_analytics.py`, `test_portal_connections.py`

### portal_scraper_service.py
- **Class**: `PortalScraperService`
- **Purpose**: Web scraping for 5 major utilities (Duke, PG&E, Con Edison, ComEd, FPL) with encrypted credentials
- **Key Methods**:
  - `scrape_connection(connection_id: str) -> dict` — trigger portal login + bill extract
  - `_scrape_duke_energy(username: str, password: str)` → `dict` — Duke portal automation
  - `_extract_bill_data(portal_response: dict)` → `BillData` — parse HTML/PDF
  - `store_encrypted_credentials(creds: dict)` → `str` — AES-256-GCM encryption
- **Dependencies**: `httpx` + browser automation (Playwright/Selenium), `CryptoService`, structlog
- **Tests**: `test_portal_scraper_service.py`, `test_portal_connections.py`

### email_scanner_service.py
- **Class**: `EmailScanResult` (dataclass), scanner methods
- **Purpose**: Batch scan email accounts (Gmail/Outlook) for utility bills, extract rates
- **Key Methods**:
  - `scan_emails(user_id: str) -> EmailScanResult` — check all email_import connections
  - `download_gmail_attachments(gmail_auth: dict, query: str)` → `list[bytes]` — Gmail API
  - `download_outlook_attachments(outlook_auth: dict, query: str)` → `list[bytes]` — Outlook API
  - `extract_rates_from_email(email_body: str, utility_type: str) -> list[float]` — regex patterns
  - `extract_rates_from_attachments(pdfs: list[bytes]) -> list[float]` — PDF text extraction
- **Dependencies**: `GmailClient`, `OutlookClient`, PDF text extraction, `BillParser`
- **Tests**: `test_email_scanner_service.py`, `test_email_scan_extraction.py`, `test_email_attachment_parsing.py`

### email_oauth_service.py
- **Class**: `EmailOAuthService`
- **Purpose**: OAuth token management for Gmail/Outlook (request, refresh, revoke)
- **Key Methods**:
  - `request_authorization(provider: str, callback_url: str) -> str` — auth URL
  - `exchange_code_for_token(code: str) -> dict` — convert auth code to token
  - `refresh_token(user_id: str, provider: str)` — keep token fresh
  - `revoke_token(user_id: str, provider: str)` — disconnect account
- **Dependencies**: OAuth 2.0 libraries (authlib, google-auth), `UserRepository`, token encryption
- **Tests**: `test_integrations.py`, `test_utilityapi.py`

### bill_parser.py
- **Class**: `BillParserService`
- **Purpose**: Parses PDF/HTML bills to extract rates, usage, due dates, account numbers
- **Key Methods**:
  - `parse_bill(bill_content: bytes, utility_type: str) -> BillData` — universal parser
  - `_parse_electricity_bill(pdf_text: str) -> BillData` — extract kWh, rate/kWh, charges
  - `_extract_account_number(text: str) -> str` — regex + fuzzy match
  - `_extract_due_date(text: str) -> date` — date parsing with fallbacks
- **Dependencies**: `pdfplumber` (PDF text), regex patterns, `structlog`
- **Tests**: `test_bill_parser.py`, `test_bill_upload.py`, `test_email_attachment_parsing.py`

---

## Community Services

### community_service.py
- **Class**: `CommunityService`
- **Purpose**: CRUD for community posts, voting, reporting, AI moderation (fail-closed until reviewed)
- **Key Methods**:
  - `create_post(db: AsyncSession, user_id: str, body: str) -> str` — insert + queue for moderation
  - `moderate_posts(db: AsyncSession)` → `dict` — Groq (primary) + Gemini (fallback) classification
  - `vote_post(db: AsyncSession, post_id: str, user_id: str, vote_type: str)` — upvote/downvote
  - `report_post(db: AsyncSession, post_id: str, reporter_id: str)` → auto-hide after 5 reports
  - `get_posts(db: AsyncSession, is_pending: bool = False) -> list[dict]` — list visible posts
- **Dependencies**: `nh3` (XSS sanitize), Groq + Gemini APIs, `structlog`, `community_posts` + `community_votes` + `community_reports` tables (migration 049)
- **Tests**: `test_community_service.py`

### community_solar_service.py
- **Class**: `CommunitySolarService`
- **Purpose**: Community solar program finder and enrollment
- **Key Methods**:
  - `discover_programs(address: str, state: str)` → `list[dict]` — list local programs + savings
  - `get_program_details(program_id: str) -> dict` — savings %, eligibility, enrollment link
  - `enroll_user(user_id: str, program_id: str)` — record enrollment, update user profile
- **Dependencies**: `GeocodingService`, community solar provider APIs (geospatial lookup)
- **Tests**: `test_community_solar_service.py`

### cca_service.py
- **Class**: `CCAService`
- **Purpose**: Community Choice Aggregation (CCA) provider finder and rates
- **Key Methods**:
  - `get_cca_provider(address: str) -> dict` — which CCA serves this address
  - `get_rates(cca_name: str) -> list[dict]` — tiered rates + renewable %
  - `compare_to_incumbent(cca_name: str)` → `dict` — CCA savings vs utility rate
- **Dependencies**: `GeocodingService`, CCA provider databases
- **Tests**: `test_cca_service.py`, `test_multi_utility.py`

### neighborhood_service.py
- **Class**: `NeighborhoodService`
- **Purpose**: Aggregate neighborhood usage + rates, show user how they compare
- **Key Methods**:
  - `get_neighborhood_stats(zip_code: str, utility_type: str) -> dict` — median usage, avg rate, %tile ranking
  - `get_user_percentile(user_id: str, utility_type: str) -> dict` — where user ranks (0-100)
  - `get_savings_potential(user_id: str) -> dict` — could save this much % vs median
- **Dependencies**: `SavingsAggregator`, `UserRepository`, `PriceRepository`, `SavingsAggregator`
- **Tests**: `test_neighborhood_service.py`, `test_savings_neighborhood_api.py`

---

## Notification Services

### email_service.py
- **Class**: `EmailService`
- **Purpose**: Email delivery — Resend (primary) + SMTP (fallback), Jinja2 HTML templates
- **Key Methods**:
  - `send(to: str, subject: str, html_body: str)` → async delivery
  - `render_template(template_name: str, **kwargs) -> str` — Jinja2 render
  - `_send_via_resend(to, subject, html)` — try Resend first
  - `_send_via_smtp(to, subject, html)` — fallback if Resend fails
- **Dependencies**: Resend SDK, nodemailer SMTP, Jinja2 template engine, structlog
- **Tests**: `test_email_service.py`, `test_notifications.py`

### notification_service.py
- **Class**: `NotificationService`
- **Purpose**: In-app notifications — create, list unread, mark read
- **Key Methods**:
  - `create(user_id: str, title: str, body: str, type: str)` — insert to `notifications` table
  - `get_unread(user_id: str) -> list[dict]` — fetch is_read=false rows
  - `count_unread(user_id: str) -> int` — quick count for badge
  - `mark_as_read(notification_id: str)` — set is_read=true
- **Dependencies**: `AsyncSession` (SQL via `text()`), structlog
- **Tests**: `test_notifications.py`, `test_notification_repository.py`

### notification_dispatcher.py
- **Class**: `NotificationDispatcher`, `NotificationChannel` (StrEnum: IN_APP, PUSH, EMAIL)
- **Purpose**: Strategy-pattern dispatcher routing to all 3 channels with dedup + retry tracking
- **Key Methods**:
  - `send(user_id, title, body, channels, email_to, dedup_key, cooldown_seconds)` → async dispatch
  - `_route_in_app(user_id, notification_id)` — persist to DB
  - `_route_push(user_id, title)` — OneSignal
  - `_route_email(user_id, email_to, title, html)` — EmailService
  - `_record_delivery(notification_id, channel, status, error_message)` — audit trail (migration 032)
- **Dependencies**: `NotificationService`, `PushNotificationService`, `EmailService`, `NotificationRepository`
- **Tests**: `test_notification_dispatcher.py`, `test_notification_delivery.py`

### push_notification_service.py
- **Class**: `PushNotificationService`
- **Purpose**: OneSignal integration for mobile/web push notifications
- **Key Methods**:
  - `send_to_user(user_id: str, title: str, body: str)` — route via OneSignal
  - `send_to_segment(segment_id: str, title: str)` — broadcast to user segment
  - `bind_user(user_id: str)` — called post-auth (login(userId))
  - `unbind_user(user_id: str)` — on logout
- **Dependencies**: OneSignal SDK, `UserRepository`
- **Tests**: `test_push_notification_service.py`

### alert_service.py
- **Class**: `AlertService`, `AlertThreshold` (dataclass), `PriceAlert` (dataclass)
- **Purpose**: Price alert configuration (CRUD), triggering, and routing via `NotificationDispatcher`
- **Key Methods**:
  - `create_alert(user_id: str, region: str, threshold: Decimal, alert_type: str)` → alert_id
  - `get_user_alerts(user_id: str) -> list[AlertThreshold]` — active alerts
  - `update_alert(alert_id: str, threshold: Decimal)` — modify threshold
  - `delete_alert(alert_id: str)` — remove alert
  - `check_and_trigger(region: str)` — price dropped? notify via dispatcher
  - `record_triggered_alert(alert_id: str, actual_price: Decimal)` → `alert_history`
- **Dependencies**: `AlertRenderer`, `NotificationDispatcher`, `PriceRepository`, alert cooldowns (1h immediate, 24h daily, 7d weekly)
- **Tests**: `test_alert_service.py`, `test_internal_alerts.py`, `test_api_alerts.py`

### alert_renderer.py
- **Class**: `AlertRenderer`
- **Purpose**: Formats alert titles/body from threshold + price data
- **Key Methods**:
  - `render_title(alert_type: str, region: str, threshold: Decimal) -> str` — "Low price in Connecticut!"
  - `render_body(actual_price: Decimal, threshold: Decimal, savings: Decimal) -> str` — detailed message
  - `render_optimal_window(region: str) -> dict` — cheapest 4-hour window + usage recommendation
- **Dependencies**: `structlog`, template strings
- **Tests**: `test_alert_renderer.py`, `test_notifications.py`

---

## Analytics Services

### analytics_service.py
- **Class**: `AnalyticsService`
- **Purpose**: Tracks user actions (page views, clicks, feature usage) for product metrics
- **Key Methods**:
  - `record_event(user_id: str, event_name: str, properties: dict)` — log event to `events` table
  - `get_user_journey(user_id: str, last_n_days: int)` → `list[dict]` — chronological event log
  - `get_cohort_metrics(cohort_key: str) -> dict` — aggregated stats by cohort
- **Dependencies**: `AnalyticsRepository`, `AsyncSession`, structlog
- **Tests**: `test_analytics_service.py`, `test_unified_analytics.py`

### optimization_report_service.py
- **Class**: `OptimizationReportService`
- **Purpose**: Multi-utility spend optimization — identifies top opportunities (Business tier)
- **Key Methods**:
  - `generate_report(state: str, user_id: str = None) -> dict` — aggregated savings across utilities
  - `_calculate_multi_utility_spend(state: str) -> dict` — electricity + gas + oil + propane + water
  - `_rank_opportunities(spend: dict) -> list[dict]` — sorted by dollar savings potential
  - Uses CTE queries (3 → 1 DB call, migration 061 pattern)
- **Dependencies**: `AsyncSession`, SQL CTEs, `structlog`
- **Tests**: `test_optimization_report_service.py`, `test_api_predictions.py`

### kpi_report_service.py
- **Class**: `KPIReportService`
- **Purpose**: Daily business metrics aggregation (DAU, signups, churn, revenue)
- **Key Methods**:
  - `generate_kpi_report() -> dict` — daily metrics (POST /internal/kpi-report, 6am UTC via GHA)
  - `_count_active_users(date: date) -> int` — unique users with activity
  - `_sum_revenue(date: date) -> Decimal` — total Stripe revenue
  - `_calculate_churn(lookback_days: int) -> float` — % subscribers who cancelled
- **Dependencies**: `UserRepository`, `AnalyticsRepository`, `StripeService`, structlog
- **Tests**: `test_kpi_report_service.py`, `test_internal_operations.py`

### ab_test_service.py
- **Class**: `ABTestService`
- **Purpose**: A/B test framework for UI variants, pricing, onboarding flows
- **Key Methods**:
  - `assign_variant(user_id: str, test_name: str) -> str` — deterministic split (variant A or B)
  - `record_conversion(user_id: str, test_name: str, event: str)` — mark goal completion
  - `get_results(test_name: str) -> dict` — conversion rate + statistical significance
- **Dependencies**: `ABTestRepository`, MD5 hash for deterministic assignment, structlog
- **Tests**: `test_ab_test_service.py`

---

## Utility Support Services

### geocoding_service.py
- **Class**: `GeocodingService`
- **Purpose**: Address → lat/lon, reverse geocoding, utility service area lookup
- **Key Methods**:
  - `geocode(address: str) -> dict` — address → {lat, lon, formatted_address, zip}
  - `reverse_geocode(lat: float, lon: float) -> str` — coords → address
  - `get_service_area(lat: float, lon: float) -> dict` — which utilities serve this location
  - Uses OWM primary + Nominatim fallback
- **Dependencies**: OpenWeatherMap API, Nominatim API (with User-Agent), structlog
- **Tests**: `test_geocoding_service.py`

### weather_service.py
- **Class**: `WeatherService`
- **Purpose**: Current + forecast weather (temperature, humidity, wind) for usage prediction
- **Key Methods**:
  - `get_current_weather(lat: float, lon: float) -> dict` — temp, humidity, conditions
  - `get_forecast(lat: float, lon: float, days: int) -> list[dict]` — 7-day forecast
  - `get_heating_cooling_degree_days(region: str) -> dict` — for HVAC estimation
- **Dependencies**: OpenWeatherMap API, `GeocodingService`, structlog
- **Tests**: `test_weather_service.py`, `test_internal_operations.py`

### market_intelligence_service.py
- **Class**: `MarketIntelligenceService`
- **Purpose**: External market research — Tavily + Diffbot news aggregation
- **Key Methods**:
  - `research_supplier_changes(state: str) -> list[dict]` — new suppliers, mergers, policy changes
  - `research_rate_trends(utility_type: str)` → `list[dict]` — news articles, rate news
  - `identify_policy_changes(state: str)` → `list[dict]` — regulatory changes (PSC orders, bills)
- **Dependencies**: Tavily AI Search API, Diffbot API, structlog
- **Tests**: `test_integrations.py`, `test_internal_operations.py`

### feature_flag_service.py
- **Class**: `FeatureFlagService`
- **Purpose**: Runtime feature toggles (beta features, gradual rollouts, A/B testing)
- **Key Methods**:
  - `is_enabled(user_id: str, flag_name: str) -> bool` — check flag state
  - `get_flags_for_user(user_id: str) -> dict` — all flags + values
  - `set_flag(flag_name: str, enabled: bool, rollout_percent: int = 100)` — admin control
- **Dependencies**: `FeatureFlagRepository`, Redis cache (optional), structlog
- **Tests**: `test_feature_flags.py`, `test_utility_feature_flags.py`

### referral_service.py
- **Class**: `ReferralService`, `ReferralError` (exception)
- **Purpose**: Referral rewards program — generate codes, track signups, award credits
- **Key Methods**:
  - `generate_code(user_id: str) -> str` — unique referral code
  - `apply_referral(referrer_id: str, new_user_id: str)` → credit both users
  - `get_referral_stats(user_id: str) -> dict` — referrals made, credits earned
  - `claim_reward(user_id: str)` — redeem credits for discount
- **Dependencies**: `ReferralRepository`, `UserRepository`, structlog
- **Tests**: `test_referral_service.py`

### affiliate_service.py
- **Class**: `AffiliateService`
- **Purpose**: Partner affiliate program — track clicks, conversions, payouts
- **Key Methods**:
  - `create_affiliate(user_id: str, commission_rate: float) -> dict` — onboard partner
  - `track_click(affiliate_id: str, link_id: str, referrer_url: str)` — log click
  - `calculate_commission(affiliate_id: str, period: str) -> Decimal` — earned commission
  - `request_payout(affiliate_id: str, amount: Decimal, bank_account: dict)` — withdrawal
- **Dependencies**: `AffiliateRepository`, `UserRepository`, structlog
- **Tests**: `test_affiliate_service.py`

### savings_service.py
- **Class**: `SavingsService`
- **Purpose**: Calculates potential savings from switching suppliers / changing usage patterns
- **Key Methods**:
  - `calculate_savings(current_rate: Decimal, alternative_rate: Decimal, usage: float) -> Decimal` — dollar savings
  - `calculate_payback_period(savings: Decimal, switch_cost: Decimal) -> float` — months to break even
  - `get_switching_options(region: str, current_supplier: str)` → `list[SwitchingRecommendation]`
- **Dependencies**: `RecommendationService`, `PriceService`, structlog
- **Tests**: `test_savings.py`, `test_savings_aggregator.py`

### savings_aggregator.py
- **Class**: `SavingsAggregator`
- **Purpose**: Multi-utility savings aggregation (electricity + gas + oil + water), neighborhood comparisons
- **Key Methods**:
  - `aggregate_household_savings(user_id: str, region: str) -> dict` — total potential savings across utilities
  - `get_neighbor_comparison(zip_code: str) -> dict` — median savings in neighborhood
  - `identify_quick_wins(user_id: str)` → `list[dict]` — easiest actions (switch, usage change)
- **Dependencies**: `SavingsService`, `NeighborhoodService`, `PriceRepository`, structlog
- **Tests**: `test_savings_aggregator.py`

### recommendation_service.py
- **Class**: `RecommendationService`, `SwitchingRecommendation` (dataclass), `UsageRecommendation` (dataclass)
- **Purpose**: Generates switching + usage optimization recommendations
- **Key Methods**:
  - `generate_switching_recommendations(user_id: str) -> list[SwitchingRecommendation]` — best supplier to switch to
  - `generate_usage_recommendations(user_id: str) -> list[UsageRecommendation]` — shift usage to cheap hours
  - `rank_by_confidence(recommendations: list) -> list` — filter low-confidence suggestions
- **Dependencies**: `PriceService`, `UserRepository`, `SavingsService`, structlog
- **Tests**: `test_api_recommendations.py`

### maintenance_service.py
- **Class**: `MaintenanceService`
- **Purpose**: Database maintenance tasks — vacuuming, index rebuilding, row cleanup
- **Key Methods**:
  - `vacuum_database()` → async — reclaim space from deleted rows
  - `reindex_tables()` → async — rebuild indices for performance
  - `cleanup_stale_data(days: int)` → async — delete old events/logs beyond retention
- **Dependencies**: `AsyncSession`, raw SQL VACUUM/REINDEX/DELETE, structlog
- **Tests**: `test_integrations.py`

### data_persistence_helper.py
- **Class**: Data persistence helper functions
- **Purpose**: Utility functions for batch inserts, migrations, data transformations
- **Key Methods**:
  - `bulk_create(db, model_class, rows: list, chunk_size: int = 500)` → async batch insert
  - `create_or_update_many(db, model, rows, key)` — upsert pattern
- **Dependencies**: SQLAlchemy ORM, structlog
- **Tests**: `test_services.py`

---

## Service Dependency Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  API & Routing Layer                         │
│  (api/v1/*.py routes → endpoint handlers)                    │
└───────────────┬─────────────────────────────────────────────┘
                │
        ┌───────┴──────────────────────────┬──────────────────┬───────┐
        │                                  │                  │       │
   ┌────▼─────────┐          ┌─────────────▼─────┐  ┌────────▼──┐   │
   │ Pricing      │          │ Notification      │  │ Community │   │
   │ Services (5) │          │ Services (6)      │  │ Services  │   │
   │              │          │                   │  │           │   │
   │- price_svc   │          │- alert_svc ◄──┐  │  │- comm_svc │   │
   │- forecast_svc│          │- notif_svc    │  │  │- solar_svc│   │
   │- rate_change │          │- dispatcher ◄─┘  │  │- cca_svc  │   │
   │- rate_scrape │          │- push_notif   │  │  │- neighbor │   │
   │- rate_export │          │- email_svc    │  │  │           │   │
   └────┬────────┘          └────────────────┘  └──┴───────────┘   │
        │                           ▲                                │
        │                           │                                │
   ┌────▼─────────┐     ┌──────────┴──────┐     ┌────────────────┐ │
   │ ML/AI        │     │ Billing         │     │ Connections    │ │
   │ Services (8) │     │ Services (2)    │     │ Services (6)   │ │
   │              │     │                 │     │                │ │
   │- forecast    │     │- stripe_svc ────┼────►│- sync_svc      │ │
   │- learning    │     │- dunning_svc    │     │- email_oauth   │ │
   │- hnsw_vec    │     └─────────────────┘     │- email_scan    │ │
   │- vector_store│                             │- portal_scrape │ │
   │- observation │     ┌───────────────┐       │- bill_parser   │ │
   │- model_ver   │     │ Analytics (4) │       │- analytics     │ │
   │- agent       │     │               │       └────┬───────────┘ │
   │- data_qual   │     │- analytics    │            │              │
   └────┬─────────┘     │- kpi_report   │            │              │
        │               │- optimization │            │              │
        │               │- ab_test      │            │              │
        │               └───────────────┘            │              │
        │                                            │              │
   ┌────▼─────────┐  ┌───────────────┐    ┌────────▼─────────┐   │
   │ Utilities    │  │ Support (11)  │    │ Repos & External │   │
   │ Services (5) │  │               │    │                  │   │
   │              │  │- geocoding    │    │- SQL (Neon)      │   │
   │- gas_svc     │  │- weather      │    │- Redis (cache)   │   │
   │- oil_svc     │  │- market_intel │    │- Stripe API      │   │
   │- propane_svc │  │- feature_flag │    │- UtilityAPI      │   │
   │- water_svc   │  │- referral     │    │- OneSignal       │   │
   │- discovery   │  │- affiliate    │    │- Gmail/Outlook   │   │
   └──────────────┘  │- savings      │    │- Diffbot         │   │
                     │- aggregator   │    │- Tavily          │   │
                     │- recommend    │    │- Gemini 3 Flash  │   │
                     │- maintenance  │    │- Groq Llama      │   │
                     │- persistence  │    │- Composio Tools  │   │
                     └───────────────┘    └──────────────────┘   │
                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing Strategy

**Test File Count**: 105+ test files
**Total Test Cases**: ~7,362 across all layers

### Test Organization
- **Unit tests** — service methods, business logic (e.g., `test_price_sync_service.py`)
- **Integration tests** — service + repository + DB interactions (e.g., `test_internal_alerts.py`)
- **E2E tests** — full API request/response flows (e.g., `test_api_alerts.py`)
- **Security tests** — adversarial inputs, IDOR, injection (e.g., `test_security_adversarial.py`)

### Running Service Tests
```bash
# Run all service tests
.venv/bin/python -m pytest backend/tests/test_*_service.py -v

# Run specific service tests
.venv/bin/python -m pytest backend/tests/test_alert_service.py -v

# Run with coverage
.venv/bin/python -m pytest backend/tests/ --cov=backend/services --cov-report=html
```

---

## Key Patterns & Conventions

### Service Constructor Pattern
```python
class ExampleService:
    def __init__(self, db: AsyncSession, cache: Optional[Redis] = None):
        self._db = db
        self._cache = cache
```

### Error Handling Pattern
```python
try:
    result = await self._db.execute(...)
    await self._db.commit()
except Exception as e:
    await self._db.rollback()
    logger.error("operation_failed", error=str(e))
    raise
```

### Async Patterns
- Use `asyncio.gather()` for parallel ops, BUT **NOT** with shared `AsyncSession` (causes corruption — use sequential loops)
- Semaphore gating for rate-limited APIs (e.g., `asyncio.Semaphore(5)` in `RateScraperService`)
- 30s timeout guards prevent single slow provider from blocking batch jobs

### Logging
- Use `structlog` for all logging
- Include context: `logger.info("event_name", user_id=uid, region=region, status=status)`
- Structured output enables Sentry + Grafana aggregation

### Repository Pattern
- Services call repositories for data access (e.g., `PriceService` → `PriceRepository`)
- Repositories use raw SQL (`sqlalchemy.text()`) or SQLAlchemy ORM
- Transaction management stays in repositories or service callers

### Tracing
- Use `@traced` decorator from `lib.tracing` on key service methods
- Exports to Grafana Tempo for production observability
- Helps identify bottlenecks in multi-step workflows

---

## Migration References

Services depend on database tables created by migrations:

| Migration | Tables | Services |
|-----------|--------|----------|
| 008 | user_connections | connection_sync_service |
| 014 | price_alerts, alert_history | alert_service |
| 020 | forecast_observations | observation_service |
| 024 | payment_retry_history | dunning_service |
| 029 | notifications + delivery tracking | notification_dispatcher |
| 032 | notifications (expanded schema) | notification_dispatcher |
| 049 | community_posts, community_votes, community_reports | community_service |
| 061 | (pattern: CTE query optimization) | optimization_report_service |

---

## Quick Reference: Find a Service

**Want to...**
- Fetch electricity prices? → `price_service.py`
- Send email alerts? → `email_service.py` + `notification_dispatcher.py`
- Sync UtilityAPI data? → `connection_sync_service.py`
- Predict future prices? → `forecast_service.py`
- Handle Stripe webhooks? → `stripe_service.py`
- Parse PDF bills? → `bill_parser.py`
- Run nightly ML update? → `learning_service.py`
- Moderate community posts? → `community_service.py`
- Generate optimization report? → `optimization_report_service.py`
- Check feature flags? → `feature_flag_service.py`

---

## Last Updated

2026-03-25 — 51 services documented, 105+ test files, dependency diagram included.
