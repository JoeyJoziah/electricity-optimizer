#!/usr/bin/env python3
"""DSP Bootstrap — register all entities for the electricity-optimizer project."""

import subprocess
import sys
import json
from pathlib import Path

ROOT = "/Users/devinmcgrath/projects/electricity-optimizer"
CLI = f"python3 {ROOT}/dsp-cli.py"
uid_map: dict[str, str] = {}  # source_path -> uid


def run(cmd: str) -> str:
    """Run a dsp-cli command and return stdout."""
    result = subprocess.run(
        f"{CLI} --root {ROOT} {cmd}",
        shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ERROR: {cmd[:80]}... => {result.stderr.strip()}", file=sys.stderr)
        return ""
    return result.stdout.strip()


def obj(source: str, purpose: str, kind: str = "object") -> str:
    """Create an object entity and store its UID."""
    uid = run(f'create-object "{source}" "{purpose}" --kind {kind}')
    if uid:
        uid_map[source] = uid
        print(f"  + {uid} {source}")
    return uid


def imp(importer_src: str, imported_src: str, why: str):
    """Add an import relationship between two entities."""
    i_uid = uid_map.get(importer_src, "")
    d_uid = uid_map.get(imported_src, "")
    if i_uid and d_uid:
        run(f'add-import {i_uid} {d_uid} "{why}"')


def shared(exporter_src: str, *shared_srcs: str):
    """Register shared/exported entities."""
    e_uid = uid_map.get(exporter_src, "")
    s_uids = " ".join(uid_map.get(s, "") for s in shared_srcs if uid_map.get(s))
    if e_uid and s_uids:
        run(f"create-shared {e_uid} {s_uids}")


# ============================================================
# PHASE 1: External Dependencies
# ============================================================
print("\n=== Phase 1: External Dependencies ===")

externals = [
    # Backend
    ("fastapi", "Python async web framework for building APIs"),
    ("sqlalchemy", "Python SQL toolkit and ORM for database access"),
    ("asyncpg", "Async PostgreSQL driver for Python"),
    ("pydantic", "Data validation using Python type annotations"),
    ("stripe", "Stripe payment processing SDK"),
    ("resend", "Resend email service SDK"),
    ("httpx", "Async HTTP client for Python"),
    ("structlog", "Structured logging for Python"),
    # Frontend
    ("next", "Next.js React framework for server-rendered apps"),
    ("react", "React UI library for building component-based interfaces"),
    ("@tanstack/react-query", "TanStack React Query for server state management"),
    ("zustand", "Lightweight state management for React"),
    ("better-auth", "Authentication library with session-based auth"),
    ("nodemailer", "Node.js SMTP email client"),
    ("tailwindcss", "Utility-first CSS framework"),
    ("clsx", "Utility for constructing className strings"),
    ("tailwind-merge", "Merge Tailwind CSS classes without conflicts"),
    # ML
    ("torch", "PyTorch deep learning framework for CNN-LSTM models"),
    ("xgboost", "XGBoost gradient boosting library"),
    ("lightgbm", "LightGBM gradient boosting library"),
    ("pulp", "PuLP linear programming toolkit for MILP optimization"),
    ("numpy", "Numerical computing library for array operations"),
    ("pandas", "Data manipulation and analysis library"),
    ("scikit-learn", "Machine learning utilities and preprocessing"),
    ("hnswlib", "HNSW approximate nearest neighbor search"),
]

for src, desc in externals:
    obj(src, desc, kind="external")


# ============================================================
# PHASE 2: Backend — Config Layer
# ============================================================
print("\n=== Phase 2: Backend Config ===")

backend_config = [
    ("backend/config/__init__.py", "Config package init, re-exports settings"),
    ("backend/config/settings.py", "50+ config knobs via Pydantic BaseSettings"),
    ("backend/config/database.py", "AsyncSession factory, get_db_session, engine creation with asyncpg"),
    ("backend/config/secrets.py", "Secret management with 1Password CLI fallback"),
]
for src, desc in backend_config:
    obj(src, desc)

imp("backend/config/database.py", "sqlalchemy", "ORM engine and async session creation")
imp("backend/config/database.py", "asyncpg", "Async PostgreSQL driver for connection pool")
imp("backend/config/database.py", "backend/config/settings.py", "Database URL and pool configuration")
imp("backend/config/settings.py", "pydantic", "BaseSettings for typed configuration")
imp("backend/config/__init__.py", "backend/config/settings.py", "Re-exports Settings class")


# ============================================================
# PHASE 3: Backend — Models
# ============================================================
print("\n=== Phase 3: Backend Models ===")

models = [
    ("backend/models/__init__.py", "Model package, re-exports all SQLAlchemy models"),
    ("backend/models/base.py", "SQLAlchemy declarative Base class"),
    ("backend/models/user.py", "User model with UUID PK, subscription_tier, stripe_customer_id"),
    ("backend/models/price.py", "Price model for electricity price records"),
    ("backend/models/region.py", "Region enum — 50 US states + DC + international codes"),
    ("backend/models/utility.py", "Utility company model"),
    ("backend/models/supplier.py", "Supplier and SupplierRegistry models"),
    ("backend/models/connections.py", "UserConnection and ConnectionExtractedRate models"),
    ("backend/models/observation.py", "ForecastObservation model for ML predictions"),
    ("backend/models/user_supplier.py", "UserSupplier association table"),
    ("backend/models/consent.py", "UserConsent model for GDPR compliance"),
    ("backend/models/regulation.py", "Regulation model for utility regulations"),
]
for src, desc in models:
    obj(src, desc)

for m in models[2:]:  # all models except __init__ and base
    imp(m[0], "backend/models/base.py", "Inherits declarative Base class")
    imp(m[0], "sqlalchemy", "Column types, relationships, and ORM decorators")

imp("backend/models/__init__.py", "backend/models/user.py", "Re-exports User model")
imp("backend/models/__init__.py", "backend/models/price.py", "Re-exports Price model")
imp("backend/models/__init__.py", "backend/models/region.py", "Re-exports Region enum")
imp("backend/models/__init__.py", "backend/models/supplier.py", "Re-exports Supplier models")
imp("backend/models/__init__.py", "backend/models/connections.py", "Re-exports connection models")
imp("backend/models/user.py", "backend/models/region.py", "User region field uses Region enum")
imp("backend/models/price.py", "backend/models/region.py", "Price region uses Region enum")
imp("backend/models/connections.py", "backend/models/user.py", "FK to User for connection ownership")


# ============================================================
# PHASE 4: Backend — Auth
# ============================================================
print("\n=== Phase 4: Backend Auth ===")

auth = [
    ("backend/auth/__init__.py", "Auth package init"),
    ("backend/auth/neon_auth.py", "SessionData type, get_current_user and get_optional_user dependencies"),
    ("backend/auth/password.py", "Password hashing and verification utilities"),
]
for src, desc in auth:
    obj(src, desc)

imp("backend/auth/neon_auth.py", "backend/config/database.py", "Database session for user lookup")
imp("backend/auth/neon_auth.py", "backend/models/user.py", "User model for session resolution")
imp("backend/auth/neon_auth.py", "fastapi", "Depends and HTTPException for auth flow")


# ============================================================
# PHASE 5: Backend — Repositories
# ============================================================
print("\n=== Phase 5: Backend Repositories ===")

repos = [
    ("backend/repositories/base.py", "BaseRepository with generic CRUD operations"),
    ("backend/repositories/user_repository.py", "UserRepository with get_by_stripe_customer_id"),
    ("backend/repositories/price_repository.py", "PriceRepository for price data access"),
    ("backend/repositories/supplier_repository.py", "SupplierRepository for supplier queries"),
    ("backend/repositories/forecast_observation_repository.py", "ForecastObservationRepository for ML predictions"),
]
for src, desc in repos:
    obj(src, desc)

imp("backend/repositories/base.py", "sqlalchemy", "SQLAlchemy session and query building")
for r in repos[1:]:
    imp(r[0], "backend/repositories/base.py", "Inherits generic CRUD from BaseRepository")

imp("backend/repositories/user_repository.py", "backend/models/user.py", "Queries User model")
imp("backend/repositories/price_repository.py", "backend/models/price.py", "Queries Price model")
imp("backend/repositories/supplier_repository.py", "backend/models/supplier.py", "Queries Supplier models")
imp("backend/repositories/forecast_observation_repository.py", "backend/models/observation.py", "Queries ForecastObservation")


# ============================================================
# PHASE 6: Backend — Middleware & Utils
# ============================================================
print("\n=== Phase 6: Backend Middleware & Utils ===")

middleware = [
    ("backend/middleware/rate_limiter.py", "Rate limiting middleware with Redis or in-memory fallback"),
    ("backend/middleware/security_headers.py", "Security headers middleware (CSP, HSTS, etc.)"),
    ("backend/middleware/tracing.py", "Request tracing middleware for observability"),
]
for src, desc in middleware:
    obj(src, desc)
    imp(src, "fastapi", "ASGI middleware integration")

obj("backend/utils/encryption.py", "AES-256-GCM field encryption for sensitive data")

obj("backend/compliance/gdpr.py", "GDPR compliance logic for data handling")
obj("backend/compliance/repositories.py", "Compliance data access layer")
imp("backend/compliance/repositories.py", "sqlalchemy", "Database queries for compliance data")
imp("backend/compliance/gdpr.py", "backend/compliance/repositories.py", "Data access for GDPR operations")


# ============================================================
# PHASE 7: Backend — Integrations
# ============================================================
print("\n=== Phase 7: Backend Integrations ===")

integrations = [
    ("backend/integrations/pricing_apis/base.py", "BasePricingAPI abstract class for pricing providers"),
    ("backend/integrations/pricing_apis/flatpeak.py", "FlatPeak pricing API integration"),
    ("backend/integrations/pricing_apis/nrel.py", "NREL electricity rate API integration"),
    ("backend/integrations/pricing_apis/iea.py", "IEA energy data API integration"),
    ("backend/integrations/pricing_apis/eia.py", "EIA energy information API integration"),
    ("backend/integrations/pricing_apis/cache.py", "API response caching layer"),
    ("backend/integrations/pricing_apis/rate_limiter.py", "Per-provider rate limiting"),
    ("backend/integrations/pricing_apis/service.py", "Unified pricing service aggregating all providers"),
    ("backend/integrations/utilityapi.py", "UtilityAPI integration for utility data sync"),
    ("backend/integrations/weather_service.py", "Weather API integration with asyncio.gather parallelization"),
]
for src, desc in integrations:
    obj(src, desc)

for api in ["flatpeak", "nrel", "iea", "eia"]:
    imp(f"backend/integrations/pricing_apis/{api}.py", "backend/integrations/pricing_apis/base.py",
        f"Inherits BasePricingAPI for {api} provider")
    imp(f"backend/integrations/pricing_apis/{api}.py", "httpx", "HTTP client for API calls")

imp("backend/integrations/pricing_apis/service.py", "backend/integrations/pricing_apis/flatpeak.py", "FlatPeak provider")
imp("backend/integrations/pricing_apis/service.py", "backend/integrations/pricing_apis/nrel.py", "NREL provider")
imp("backend/integrations/pricing_apis/service.py", "backend/integrations/pricing_apis/iea.py", "IEA provider")
imp("backend/integrations/pricing_apis/service.py", "backend/integrations/pricing_apis/eia.py", "EIA provider")
imp("backend/integrations/pricing_apis/service.py", "backend/integrations/pricing_apis/cache.py", "Response caching")
imp("backend/integrations/pricing_apis/service.py", "backend/integrations/pricing_apis/rate_limiter.py", "Rate limit enforcement")
imp("backend/integrations/utilityapi.py", "httpx", "HTTP client for UtilityAPI calls")
imp("backend/integrations/weather_service.py", "httpx", "HTTP client for weather API calls")
imp("backend/integrations/weather_service.py", "backend/config/settings.py", "API keys and configuration")


# ============================================================
# PHASE 8: Backend — Services
# ============================================================
print("\n=== Phase 8: Backend Services ===")

services = [
    ("backend/services/price_service.py", "Price fetching, caching, and CRUD operations"),
    ("backend/services/price_sync_service.py", "Price synchronization across sources"),
    ("backend/services/savings_service.py", "Savings calculations and analysis"),
    ("backend/services/recommendation_service.py", "Recommendation engine for optimization suggestions"),
    ("backend/services/observation_service.py", "Forecast observation recording and analysis"),
    ("backend/services/learning_service.py", "Adaptive learning from forecast accuracy"),
    ("backend/services/hnsw_vector_store.py", "HNSW vector search for similar patterns"),
    ("backend/services/alert_service.py", "Alert checking with dedup cooldown windows"),
    ("backend/services/notification_service.py", "Notification dispatch orchestration"),
    ("backend/services/push_notification_service.py", "OneSignal push notification delivery"),
    ("backend/services/email_service.py", "Email sending via Resend SDK"),
    ("backend/services/stripe_service.py", "Stripe payment operations and subscription management"),
    ("backend/services/dunning_service.py", "Payment retry and dunning escalation with 24h cooldown"),
    ("backend/services/connection_sync_service.py", "Utility API connection synchronization"),
    ("backend/services/email_oauth_service.py", "Email OAuth flow for bill scanning"),
    ("backend/services/email_scanner_service.py", "Email bill scanning and extraction"),
    ("backend/services/bill_parser.py", "Bill OCR and parsing logic"),
    ("backend/services/rate_scraper_service.py", "Web scraping for electricity rates"),
    ("backend/services/market_intelligence_service.py", "Market research via Tavily and Diffbot"),
    ("backend/services/weather_service.py", "Weather data fetching with Semaphore(10) parallelism"),
    ("backend/services/geocoding_service.py", "Geocoding service for location resolution"),
    ("backend/services/analytics_service.py", "General analytics and metrics"),
    ("backend/services/connection_analytics_service.py", "Connection-specific analytics"),
    ("backend/services/maintenance_service.py", "Database maintenance operations"),
    ("backend/services/feature_flag_service.py", "Feature flag management"),
    ("backend/services/kpi_report_service.py", "KPI aggregation for business metrics"),
]
for src, desc in services:
    obj(src, desc)

# Key service imports
imp("backend/services/price_service.py", "backend/repositories/price_repository.py", "Price data access")
imp("backend/services/price_service.py", "backend/integrations/pricing_apis/service.py", "Fetch prices from APIs")
imp("backend/services/price_service.py", "backend/models/region.py", "Region enum for price queries")
imp("backend/services/savings_service.py", "backend/services/price_service.py", "Price data for savings calc")
imp("backend/services/recommendation_service.py", "backend/services/price_service.py", "Price data for recommendations")
imp("backend/services/recommendation_service.py", "backend/services/savings_service.py", "Savings data for recommendations")
imp("backend/services/observation_service.py", "backend/repositories/forecast_observation_repository.py", "Store forecast observations")
imp("backend/services/learning_service.py", "backend/services/observation_service.py", "Observation data for learning")
imp("backend/services/learning_service.py", "backend/services/hnsw_vector_store.py", "Vector search for similar patterns")
imp("backend/services/hnsw_vector_store.py", "hnswlib", "HNSW approximate nearest neighbor index")
imp("backend/services/alert_service.py", "backend/services/notification_service.py", "Send alert notifications")
imp("backend/services/alert_service.py", "backend/services/price_service.py", "Price data for threshold checks")
imp("backend/services/notification_service.py", "backend/services/push_notification_service.py", "Push delivery channel")
imp("backend/services/notification_service.py", "backend/services/email_service.py", "Email delivery channel")
imp("backend/services/email_service.py", "resend", "Resend SDK for email delivery")
imp("backend/services/stripe_service.py", "stripe", "Stripe SDK for payment operations")
imp("backend/services/stripe_service.py", "backend/repositories/user_repository.py", "User lookup for billing")
imp("backend/services/dunning_service.py", "backend/services/stripe_service.py", "Stripe for retry attempts")
imp("backend/services/dunning_service.py", "backend/services/email_service.py", "Dunning email notifications")
imp("backend/services/dunning_service.py", "backend/repositories/user_repository.py", "User data for dunning")
imp("backend/services/connection_sync_service.py", "backend/integrations/utilityapi.py", "UtilityAPI for data sync")
imp("backend/services/email_scanner_service.py", "backend/services/bill_parser.py", "Parse scanned bills")
imp("backend/services/rate_scraper_service.py", "httpx", "HTTP client for web scraping")
imp("backend/services/market_intelligence_service.py", "httpx", "HTTP client for Tavily/Diffbot APIs")
imp("backend/services/weather_service.py", "backend/integrations/weather_service.py", "Weather API client")
imp("backend/services/kpi_report_service.py", "backend/repositories/user_repository.py", "User metrics for KPI")
imp("backend/services/kpi_report_service.py", "backend/services/price_service.py", "Price metrics for KPI")


# ============================================================
# PHASE 9: Backend — API Dependencies
# ============================================================
print("\n=== Phase 9: Backend API Dependencies ===")

obj("backend/api/__init__.py", "API package init")
obj("backend/api/dependencies.py", "FastAPI dependencies: get_db_session, verify_api_key, require_tier, require_scope")

imp("backend/api/dependencies.py", "fastapi", "Depends and HTTPException for dependency injection")
imp("backend/api/dependencies.py", "backend/config/database.py", "Database session factory")
imp("backend/api/dependencies.py", "backend/auth/neon_auth.py", "Session-based user authentication")
imp("backend/api/dependencies.py", "backend/models/user.py", "User model for tier checking")


# ============================================================
# PHASE 10: Backend — API Routes
# ============================================================
print("\n=== Phase 10: Backend API Routes ===")

routes = [
    ("backend/api/v1/prices.py", "Price CRUD, refresh, and search endpoints"),
    ("backend/api/v1/prices_analytics.py", "Price analytics and trend endpoints"),
    ("backend/api/v1/prices_sse.py", "SSE streaming endpoint (business tier gated)"),
    ("backend/api/v1/suppliers.py", "Supplier registry and search endpoints"),
    ("backend/api/v1/auth.py", "Authentication endpoints"),
    ("backend/api/v1/user.py", "User profile CRUD endpoints"),
    ("backend/api/v1/users.py", "Admin user management endpoints"),
    ("backend/api/v1/alerts.py", "Alert configuration CRUD endpoints"),
    ("backend/api/v1/billing.py", "Stripe billing and subscription endpoints"),
    ("backend/api/v1/savings.py", "Savings analysis endpoints (pro tier gated)"),
    ("backend/api/v1/recommendations.py", "Recommendation endpoints (pro tier gated)"),
    ("backend/api/v1/notifications.py", "Push notification endpoints"),
    ("backend/api/v1/webhooks.py", "Stripe webhook handler with dunning integration"),
    ("backend/api/v1/health.py", "Health check endpoint"),
    ("backend/api/v1/beta.py", "Beta feature endpoints"),
    ("backend/api/v1/regulations.py", "Utility regulation endpoints"),
    ("backend/api/v1/compliance.py", "GDPR compliance endpoints"),
    ("backend/api/v1/internal.py", "Internal cron endpoints: alerts, weather, market, sync, scrape, dunning, kpi, health"),
    ("backend/api/v1/user_supplier.py", "User-supplier relationship endpoints"),
    # Connections sub-package
    ("backend/api/v1/connections/router.py", "Connections sub-router aggregating all connection endpoints"),
    ("backend/api/v1/connections/crud.py", "Connection CRUD operations"),
    ("backend/api/v1/connections/direct_sync.py", "Direct utility sync via UtilityAPI"),
    ("backend/api/v1/connections/email_oauth.py", "Email OAuth flow for bill scanning"),
    ("backend/api/v1/connections/bill_upload.py", "Bill upload and OCR processing"),
    ("backend/api/v1/connections/rates.py", "Extracted rate viewing endpoints"),
    ("backend/api/v1/connections/analytics.py", "Connection analytics endpoints"),
    ("backend/api/v1/connections/common.py", "Shared utilities for connection routes"),
]
for src, desc in routes:
    obj(src, desc)

# All routes import FastAPI and dependencies
for r in routes:
    imp(r[0], "fastapi", "APIRouter and route decorators")
    imp(r[0], "backend/api/dependencies.py", "Auth and DB session dependencies")

# Route-specific service imports
imp("backend/api/v1/prices.py", "backend/services/price_service.py", "Price business logic")
imp("backend/api/v1/prices_analytics.py", "backend/services/analytics_service.py", "Analytics computations")
imp("backend/api/v1/savings.py", "backend/services/savings_service.py", "Savings calculations")
imp("backend/api/v1/recommendations.py", "backend/services/recommendation_service.py", "Recommendation logic")
imp("backend/api/v1/alerts.py", "backend/services/alert_service.py", "Alert management")
imp("backend/api/v1/billing.py", "backend/services/stripe_service.py", "Stripe operations")
imp("backend/api/v1/webhooks.py", "backend/services/stripe_service.py", "Webhook processing")
imp("backend/api/v1/webhooks.py", "backend/services/dunning_service.py", "Dunning on payment_failed")
imp("backend/api/v1/notifications.py", "backend/services/push_notification_service.py", "Push notification delivery")
imp("backend/api/v1/internal.py", "backend/services/alert_service.py", "Cron alert checking")
imp("backend/api/v1/internal.py", "backend/services/weather_service.py", "Cron weather fetching")
imp("backend/api/v1/internal.py", "backend/services/market_intelligence_service.py", "Cron market research")
imp("backend/api/v1/internal.py", "backend/services/connection_sync_service.py", "Cron connection sync")
imp("backend/api/v1/internal.py", "backend/services/rate_scraper_service.py", "Cron rate scraping")
imp("backend/api/v1/internal.py", "backend/services/dunning_service.py", "Cron dunning cycle")
imp("backend/api/v1/internal.py", "backend/services/kpi_report_service.py", "Cron KPI report")
imp("backend/api/v1/connections/router.py", "backend/api/v1/connections/crud.py", "Connection CRUD routes")
imp("backend/api/v1/connections/router.py", "backend/api/v1/connections/direct_sync.py", "Sync routes")
imp("backend/api/v1/connections/router.py", "backend/api/v1/connections/bill_upload.py", "Upload routes")
imp("backend/api/v1/connections/direct_sync.py", "backend/services/connection_sync_service.py", "UtilityAPI sync")
imp("backend/api/v1/connections/bill_upload.py", "backend/services/bill_parser.py", "Bill parsing after upload")
imp("backend/api/v1/connections/analytics.py", "backend/services/connection_analytics_service.py", "Analytics logic")


# ============================================================
# PHASE 11: Backend — App Factory & Main
# ============================================================
print("\n=== Phase 11: Backend Core ===")

obj("backend/app_factory.py", "create_app() factory: registers routes, middleware, CORS, lifespan events")
obj("backend/main.py", "FastAPI application entry point, imports and runs create_app()")

imp("backend/main.py", "backend/app_factory.py", "Creates the FastAPI application instance")
imp("backend/app_factory.py", "fastapi", "FastAPI app class and CORS middleware")
imp("backend/app_factory.py", "backend/config/settings.py", "Application configuration")
imp("backend/app_factory.py", "backend/config/database.py", "Database engine lifecycle")
imp("backend/app_factory.py", "backend/middleware/rate_limiter.py", "Rate limiting middleware registration")
imp("backend/app_factory.py", "backend/middleware/security_headers.py", "Security headers middleware")
imp("backend/app_factory.py", "backend/middleware/tracing.py", "Request tracing middleware")
imp("backend/app_factory.py", "backend/api/v1/prices.py", "Price route registration")
imp("backend/app_factory.py", "backend/api/v1/auth.py", "Auth route registration")
imp("backend/app_factory.py", "backend/api/v1/health.py", "Health check route registration")


# ============================================================
# PHASE 12: Frontend — Config & Utils
# ============================================================
print("\n=== Phase 12: Frontend Config & Utils ===")

fe_config = [
    ("frontend/lib/config/env.ts", "Environment configuration and API URL resolution"),
    ("frontend/next.config.js", "Next.js config: API rewrites, CSP, HSTS headers"),
    ("frontend/tailwind.config.ts", "Tailwind CSS configuration with custom design tokens"),
]
for src, desc in fe_config:
    obj(src, desc)

fe_utils = [
    ("frontend/lib/utils/format.ts", "Formatting utilities for currency, dates, numbers"),
    ("frontend/lib/utils/cn.ts", "className utility combining clsx and tailwind-merge"),
    ("frontend/lib/utils/url.ts", "URL validation with isSafeRedirect for security"),
    ("frontend/lib/utils/calculations.ts", "Client-side calculation utilities"),
    ("frontend/lib/utils/devGate.ts", "Dev environment gate for development-only features"),
]
for src, desc in fe_utils:
    obj(src, desc)

imp("frontend/lib/utils/cn.ts", "clsx", "className string construction")
imp("frontend/lib/utils/cn.ts", "tailwind-merge", "Merge conflicting Tailwind classes")

obj("frontend/types/index.ts", "All TypeScript types with snake_case to camelCase mapping")


# ============================================================
# PHASE 13: Frontend — Auth & Email
# ============================================================
print("\n=== Phase 13: Frontend Auth & Email ===")

fe_auth = [
    ("frontend/lib/auth/client.ts", "Better Auth client instance configuration"),
    ("frontend/lib/auth/server.ts", "Server-side auth helpers for route protection"),
    ("frontend/lib/hooks/useAuth.tsx", "AuthProvider context with signIn, signUp, OAuth, magic link, OneSignal binding"),
]
for src, desc in fe_auth:
    obj(src, desc)

imp("frontend/lib/auth/client.ts", "better-auth", "Auth client creation and configuration")
imp("frontend/lib/auth/server.ts", "better-auth", "Server-side session validation")
imp("frontend/lib/hooks/useAuth.tsx", "frontend/lib/auth/client.ts", "Auth client for user operations")
imp("frontend/lib/hooks/useAuth.tsx", "react", "React context and hooks for auth state")

obj("frontend/middleware.ts", "Next.js middleware for route protection via session cookies")
imp("frontend/middleware.ts", "frontend/lib/auth/server.ts", "Server auth for session checking")
imp("frontend/middleware.ts", "next", "NextResponse for redirects")

obj("frontend/lib/email/send.ts", "Dual-provider email: Resend primary + nodemailer SMTP fallback")
imp("frontend/lib/email/send.ts", "resend", "Primary email delivery via Resend SDK")
imp("frontend/lib/email/send.ts", "nodemailer", "SMTP fallback when Resend unavailable")

obj("frontend/lib/notifications/onesignal.ts", "OneSignal push: loginOneSignal/logoutOneSignal user binding")


# ============================================================
# PHASE 14: Frontend — API Clients
# ============================================================
print("\n=== Phase 14: Frontend API Clients ===")

api_clients = [
    ("frontend/lib/api/client.ts", "Base HTTP client with retry logic and error handling"),
    ("frontend/lib/api/prices.ts", "Price API calls: fetch, search, analytics"),
    ("frontend/lib/api/alerts.ts", "Alert API calls: CRUD, history"),
    ("frontend/lib/api/suppliers.ts", "Supplier API calls: search, registry"),
    ("frontend/lib/api/profile.ts", "Profile API calls: get, update"),
    ("frontend/lib/api/optimization.ts", "Optimization API calls: analyze, schedule"),
]
for src, desc in api_clients:
    obj(src, desc)

imp("frontend/lib/api/client.ts", "frontend/lib/config/env.ts", "API base URL configuration")
for c in api_clients[1:]:
    imp(c[0], "frontend/lib/api/client.ts", "Base HTTP client for API requests")


# ============================================================
# PHASE 15: Frontend — Hooks
# ============================================================
print("\n=== Phase 15: Frontend Hooks ===")

hooks = [
    ("frontend/lib/hooks/usePrices.ts", "TanStack Query hooks for price data"),
    ("frontend/lib/hooks/useConnections.ts", "TanStack Query hooks for connections with 403 gate"),
    ("frontend/lib/hooks/useAlerts.ts", "TanStack Query hooks for alert CRUD"),
    ("frontend/lib/hooks/useSuppliers.ts", "TanStack Query hooks for supplier data"),
    ("frontend/lib/hooks/useOptimization.ts", "TanStack Query hooks for optimization"),
    ("frontend/lib/hooks/useSavings.ts", "TanStack Query hooks for savings analysis"),
    ("frontend/lib/hooks/useRealtime.ts", "SSE hooks for real-time price streaming"),
    ("frontend/lib/hooks/useProfile.ts", "TanStack Query hooks for user profile"),
    ("frontend/lib/hooks/useDiagrams.ts", "Hooks for Excalidraw diagram editor"),
    ("frontend/lib/hooks/useGeocoding.ts", "Hooks for geocoding location data"),
]
for src, desc in hooks:
    obj(src, desc)

hook_api_map = {
    "usePrices.ts": "prices.ts",
    "useAlerts.ts": "alerts.ts",
    "useSuppliers.ts": "suppliers.ts",
    "useOptimization.ts": "optimization.ts",
    "useProfile.ts": "profile.ts",
}
for hook_name, api_name in hook_api_map.items():
    imp(f"frontend/lib/hooks/{hook_name}", f"frontend/lib/api/{api_name}", "API client for data fetching")

for h in hooks[:8]:  # TanStack hooks
    imp(h[0], "@tanstack/react-query", "useQuery/useMutation for server state")


# ============================================================
# PHASE 16: Frontend — State Management
# ============================================================
print("\n=== Phase 16: Frontend State ===")

obj("frontend/lib/store/settings.ts", "Zustand store for user preferences and settings")
imp("frontend/lib/store/settings.ts", "zustand", "State management with persistence")

obj("frontend/lib/contexts/sidebar-context.tsx", "React context for sidebar open/close state")
obj("frontend/lib/contexts/toast-context.tsx", "React context for toast notification dispatch")
imp("frontend/lib/contexts/sidebar-context.tsx", "react", "createContext and useContext")
imp("frontend/lib/contexts/toast-context.tsx", "react", "createContext and useContext")


# ============================================================
# PHASE 17: Frontend — UI Components
# ============================================================
print("\n=== Phase 17: Frontend UI Components ===")

ui_components = [
    ("frontend/components/ui/input.tsx", "Enhanced Input with labelSuffix, labelRight, success states"),
    ("frontend/components/ui/button.tsx", "Button component with variants and loading state"),
    ("frontend/components/ui/card.tsx", "Card component with header and content sections"),
    ("frontend/components/ui/modal.tsx", "Modal dialog component"),
    ("frontend/components/ui/skeleton.tsx", "Loading skeleton placeholder component"),
    ("frontend/components/ui/badge.tsx", "Badge component for status indicators"),
    ("frontend/components/ui/toast.tsx", "Toast notification component"),
]
for src, desc in ui_components:
    obj(src, desc)
    imp(src, "react", "React component primitives")
    imp(src, "frontend/lib/utils/cn.ts", "className utility for conditional styling")


# ============================================================
# PHASE 18: Frontend — Feature Components
# ============================================================
print("\n=== Phase 18: Frontend Feature Components ===")

# Layout
layout_components = [
    ("frontend/components/layout/Sidebar.tsx", "Navigation sidebar with Bell icon and 7 nav items"),
    ("frontend/components/layout/Header.tsx", "Page header with title and actions"),
    ("frontend/components/layout/NotificationBell.tsx", "Notification bell icon with unread count"),
    ("frontend/components/layout/StatusBadge.tsx", "Connection status indicator badge"),
]
for src, desc in layout_components:
    obj(src, desc)
imp("frontend/components/layout/Sidebar.tsx", "frontend/lib/contexts/sidebar-context.tsx", "Sidebar open/close state")
imp("frontend/components/layout/Sidebar.tsx", "frontend/lib/hooks/useAuth.tsx", "User auth state for nav")

# Auth forms
auth_components = [
    ("frontend/components/auth/LoginForm.tsx", "Login form with email/password and OAuth options"),
    ("frontend/components/auth/SignupForm.tsx", "Signup form with email verification"),
    ("frontend/components/auth/ForgotPassword.tsx", "Forgot password form"),
    ("frontend/components/auth/ResetPassword.tsx", "Reset password form"),
    ("frontend/components/auth/VerifyEmail.tsx", "Email verification status component"),
]
for src, desc in auth_components:
    obj(src, desc)
    imp(src, "frontend/lib/hooks/useAuth.tsx", "Auth operations for form submission")
    imp(src, "frontend/components/ui/input.tsx", "Shared Input component for forms")

# Dashboard
dashboard_components = [
    ("frontend/components/dashboard/DashboardContent.tsx", "Main dashboard layout orchestrating widgets"),
    ("frontend/components/dashboard/DashboardStatsRow.tsx", "Stats summary row with key metrics"),
    ("frontend/components/dashboard/DashboardCharts.tsx", "Price and usage chart widgets"),
    ("frontend/components/dashboard/DashboardForecast.tsx", "Price forecast widget"),
    ("frontend/components/dashboard/DashboardSchedule.tsx", "Optimization schedule widget"),
    ("frontend/components/dashboard/SetupChecklist.tsx", "Onboarding checklist for new users"),
]
for src, desc in dashboard_components:
    obj(src, desc)

imp("frontend/components/dashboard/DashboardContent.tsx", "frontend/components/dashboard/DashboardStatsRow.tsx", "Stats row widget")
imp("frontend/components/dashboard/DashboardContent.tsx", "frontend/components/dashboard/DashboardCharts.tsx", "Chart widgets")
imp("frontend/components/dashboard/DashboardContent.tsx", "frontend/components/dashboard/DashboardForecast.tsx", "Forecast widget")
imp("frontend/components/dashboard/DashboardContent.tsx", "frontend/components/dashboard/DashboardSchedule.tsx", "Schedule widget")
imp("frontend/components/dashboard/DashboardContent.tsx", "frontend/lib/hooks/usePrices.ts", "Price data for dashboard")

# Alerts
alert_components = [
    ("frontend/components/alerts/AlertForm.tsx", "Alert creation form with region, thresholds, optimal windows"),
    ("frontend/components/alerts/AlertsContent.tsx", "Alerts page content with My Alerts and History tabs"),
]
for src, desc in alert_components:
    obj(src, desc)

imp("frontend/components/alerts/AlertsContent.tsx", "frontend/components/alerts/AlertForm.tsx", "Alert creation form")
imp("frontend/components/alerts/AlertsContent.tsx", "frontend/lib/hooks/useAlerts.ts", "Alert data hooks")

# Connections
connection_components = [
    ("frontend/components/connections/ConnectionsOverview.tsx", "Connections list with useQuery migration"),
    ("frontend/components/connections/ConnectionCard.tsx", "Single connection display card"),
    ("frontend/components/connections/DirectLoginForm.tsx", "Direct utility login form"),
    ("frontend/components/connections/EmailConnectionFlow.tsx", "Email connection wizard"),
    ("frontend/components/connections/ConnectionUploadFlow.tsx", "Bill upload wizard flow"),
    ("frontend/components/connections/ConnectionRates.tsx", "Extracted rate display"),
    ("frontend/components/connections/ConnectionAnalytics.tsx", "Connection analytics dashboard (refactored 770->95+6)"),
    ("frontend/components/connections/ConnectionMethodPicker.tsx", "Connection method selection"),
    ("frontend/components/connections/BillUploadForm.tsx", "Bill upload form (refactored 658->352+6)"),
]
for src, desc in connection_components:
    obj(src, desc)

imp("frontend/components/connections/ConnectionsOverview.tsx", "frontend/lib/hooks/useConnections.ts", "Connection data hooks")
imp("frontend/components/connections/ConnectionsOverview.tsx", "frontend/components/connections/ConnectionCard.tsx", "Card for each connection")

# Onboarding
onboarding_components = [
    ("frontend/components/onboarding/OnboardingWizard.tsx", "Multi-step onboarding wizard"),
    ("frontend/components/onboarding/RegionSelector.tsx", "Region selection step"),
    ("frontend/components/onboarding/UtilityTypeSelector.tsx", "Utility type selection step"),
    ("frontend/components/onboarding/SupplierPicker.tsx", "Supplier selection step"),
    ("frontend/components/onboarding/AccountLinkStep.tsx", "Account linking step"),
]
for src, desc in onboarding_components:
    obj(src, desc)

imp("frontend/components/onboarding/OnboardingWizard.tsx", "frontend/components/onboarding/RegionSelector.tsx", "Region step")
imp("frontend/components/onboarding/OnboardingWizard.tsx", "frontend/components/onboarding/UtilityTypeSelector.tsx", "Utility step")
imp("frontend/components/onboarding/OnboardingWizard.tsx", "frontend/components/onboarding/SupplierPicker.tsx", "Supplier step")
imp("frontend/components/onboarding/OnboardingWizard.tsx", "frontend/components/onboarding/AccountLinkStep.tsx", "Link step")


# ============================================================
# PHASE 19: Frontend — Pages
# ============================================================
print("\n=== Phase 19: Frontend Pages ===")

pages = [
    ("frontend/app/layout.tsx", "Root layout for marketing pages, no sidebar"),
    ("frontend/app/(app)/layout.tsx", "App layout with Sidebar for authenticated pages"),
    ("frontend/app/(dev)/layout.tsx", "Dev-only gate layout for development tools"),
    ("frontend/app/page.tsx", "Landing/marketing page"),
    ("frontend/app/(app)/dashboard/page.tsx", "Dashboard page"),
    ("frontend/app/(app)/alerts/page.tsx", "Alerts management page with CRUD and history"),
    ("frontend/app/(app)/prices/page.tsx", "Price tracking page"),
    ("frontend/app/(app)/suppliers/page.tsx", "Supplier browser page"),
    ("frontend/app/(app)/connections/page.tsx", "Utility connections page"),
    ("frontend/app/(app)/optimize/page.tsx", "Optimization tools page"),
    ("frontend/app/(app)/settings/page.tsx", "User settings page"),
    ("frontend/app/(app)/onboarding/page.tsx", "Onboarding wizard page"),
    ("frontend/app/(app)/auth/login/page.tsx", "Login page"),
    ("frontend/app/(app)/auth/signup/page.tsx", "Signup page"),
    ("frontend/app/(app)/auth/verify-email/page.tsx", "Email verification page"),
    ("frontend/app/(app)/auth/forgot-password/page.tsx", "Forgot password page"),
    ("frontend/app/(app)/auth/reset-password/page.tsx", "Reset password page"),
    ("frontend/app/(app)/auth/callback/page.tsx", "OAuth callback handler page"),
    ("frontend/app/pricing/page.tsx", "Pricing page showing Free/Pro/Business tiers"),
    ("frontend/app/privacy/page.tsx", "Privacy policy page"),
    ("frontend/app/terms/page.tsx", "Terms of service page"),
    ("frontend/app/beta-signup/page.tsx", "Beta signup page"),
]
for src, desc in pages:
    obj(src, desc)

# Page -> component imports
imp("frontend/app/(app)/layout.tsx", "frontend/components/layout/Sidebar.tsx", "Sidebar navigation")
imp("frontend/app/(app)/layout.tsx", "frontend/components/layout/Header.tsx", "Page header")
imp("frontend/app/(app)/dashboard/page.tsx", "frontend/components/dashboard/DashboardContent.tsx", "Dashboard content")
imp("frontend/app/(app)/alerts/page.tsx", "frontend/components/alerts/AlertsContent.tsx", "Alerts content")
imp("frontend/app/(app)/connections/page.tsx", "frontend/components/connections/ConnectionsOverview.tsx", "Connections list")
imp("frontend/app/(app)/onboarding/page.tsx", "frontend/components/onboarding/OnboardingWizard.tsx", "Onboarding wizard")
imp("frontend/app/(app)/auth/login/page.tsx", "frontend/components/auth/LoginForm.tsx", "Login form")
imp("frontend/app/(app)/auth/signup/page.tsx", "frontend/components/auth/SignupForm.tsx", "Signup form")
imp("frontend/app/(app)/auth/forgot-password/page.tsx", "frontend/components/auth/ForgotPassword.tsx", "Forgot password form")
imp("frontend/app/(app)/auth/reset-password/page.tsx", "frontend/components/auth/ResetPassword.tsx", "Reset password form")
imp("frontend/app/(app)/auth/verify-email/page.tsx", "frontend/components/auth/VerifyEmail.tsx", "Verification component")


# ============================================================
# PHASE 20: ML Layer
# ============================================================
print("\n=== Phase 20: ML Layer ===")

ml_modules = [
    ("ml/models/__init__.py", "ML models package exports"),
    ("ml/models/price_forecaster.py", "CNN-LSTM price forecasting model"),
    ("ml/models/ensemble.py", "XGBoost/LightGBM ensemble model"),
    ("ml/inference/__init__.py", "ML inference package exports"),
    ("ml/inference/predictor.py", "Single model predictor for inference"),
    ("ml/inference/ensemble_predictor.py", "Ensemble predictor combining CNN-LSTM and gradient boosting"),
    ("ml/optimization/__init__.py", "ML optimization package exports"),
    ("ml/optimization/appliance_models.py", "Appliance energy consumption models"),
    ("ml/optimization/load_shifter.py", "MILP load shifting optimizer using PuLP/CBC"),
    ("ml/optimization/scheduler.py", "Scheduling engine for optimal appliance timing"),
    ("ml/optimization/constraints.py", "Optimization constraints definition"),
    ("ml/optimization/objective.py", "Objective functions for optimization"),
    ("ml/optimization/visualization.py", "Optimization result visualization"),
    ("ml/optimization/switching_decision.py", "Supplier switching decision logic"),
    ("ml/data/__init__.py", "ML data package exports"),
    ("ml/data/feature_engineering.py", "Feature extraction and transformation pipeline"),
    ("ml/evaluation/__init__.py", "ML evaluation package exports"),
    ("ml/evaluation/metrics.py", "Evaluation metrics: MAE, RMSE, MAPE"),
    ("ml/evaluation/backtesting.py", "Backtesting framework for model validation"),
    ("ml/training/__init__.py", "ML training package exports"),
    ("ml/training/train_forecaster.py", "CNN-LSTM training pipeline orchestration"),
    ("ml/training/cnn_lstm_trainer.py", "CNN-LSTM training logic and data loading"),
    ("ml/training/hyperparameter_tuning.py", "Hyperparameter optimization via search"),
]
for src, desc in ml_modules:
    obj(src, desc)

# ML imports
imp("ml/models/price_forecaster.py", "torch", "PyTorch for CNN-LSTM neural network layers")
imp("ml/models/price_forecaster.py", "numpy", "Array operations for model input/output")
imp("ml/models/ensemble.py", "xgboost", "XGBoost gradient boosting model")
imp("ml/models/ensemble.py", "lightgbm", "LightGBM gradient boosting model")
imp("ml/models/ensemble.py", "scikit-learn", "Train/test split and preprocessing")
imp("ml/inference/predictor.py", "ml/models/price_forecaster.py", "CNN-LSTM model for predictions")
imp("ml/inference/predictor.py", "torch", "Model loading and tensor operations")
imp("ml/inference/ensemble_predictor.py", "ml/inference/predictor.py", "Base predictor for CNN-LSTM")
imp("ml/inference/ensemble_predictor.py", "ml/models/ensemble.py", "Ensemble model for predictions")
imp("ml/optimization/load_shifter.py", "pulp", "MILP optimization solver")
imp("ml/optimization/load_shifter.py", "ml/optimization/appliance_models.py", "Appliance energy profiles")
imp("ml/optimization/load_shifter.py", "ml/optimization/constraints.py", "Constraint definitions")
imp("ml/optimization/load_shifter.py", "ml/optimization/objective.py", "Objective function")
imp("ml/optimization/scheduler.py", "ml/optimization/load_shifter.py", "Load shifting results")
imp("ml/optimization/switching_decision.py", "ml/inference/ensemble_predictor.py", "Price predictions for decisions")
imp("ml/data/feature_engineering.py", "pandas", "DataFrame manipulation for features")
imp("ml/data/feature_engineering.py", "numpy", "Numerical feature computations")
imp("ml/evaluation/metrics.py", "numpy", "Array math for metric calculations")
imp("ml/evaluation/backtesting.py", "ml/evaluation/metrics.py", "Metrics for evaluation")
imp("ml/evaluation/backtesting.py", "ml/inference/ensemble_predictor.py", "Predictor for backtesting")
imp("ml/training/train_forecaster.py", "ml/models/price_forecaster.py", "Model to train")
imp("ml/training/train_forecaster.py", "ml/data/feature_engineering.py", "Training data preparation")
imp("ml/training/train_forecaster.py", "ml/training/cnn_lstm_trainer.py", "Training logic")
imp("ml/training/cnn_lstm_trainer.py", "torch", "PyTorch training loop")
imp("ml/training/hyperparameter_tuning.py", "ml/training/train_forecaster.py", "Training pipeline to tune")
imp("ml/training/hyperparameter_tuning.py", "ml/evaluation/metrics.py", "Metrics for tuning evaluation")

# ML __init__ re-exports
imp("ml/models/__init__.py", "ml/models/price_forecaster.py", "Re-exports PriceForecaster")
imp("ml/models/__init__.py", "ml/models/ensemble.py", "Re-exports EnsembleModel")


# ============================================================
# PHASE 21: Migrations, Workflows, Scripts, Docs, Configs
# ============================================================
print("\n=== Phase 21: Infrastructure ===")

# Migrations
obj("backend/migrations", "SQL migration directory — 25 migrations, init_neon through 025_data_cache_tables")
for i in range(1, 26):
    num = f"{i:03d}"
    names = {
        1: "init_neon", 2: "add_prices", 3: "add_suppliers", 4: "add_utilities",
        5: "add_regions", 6: "seed_suppliers", 7: "add_user_fields", 8: "add_connections",
        9: "add_observations", 10: "add_user_suppliers", 11: "add_consents",
        12: "add_regulations", 13: "add_alerts", 14: "add_notifications",
        15: "add_billing", 16: "add_extracted_rates", 17: "add_analytics",
        18: "add_user_region", 19: "seed_supplier_registry", 20: "add_oauth_tokens",
        21: "fix_connections", 22: "fix_extracted_rates", 23: "add_consent_cascade",
        24: "payment_retry_history", 25: "data_cache_tables",
    }
    name = names.get(i, f"migration_{num}")
    obj(f"backend/migrations/{num}_{name}.sql", f"Migration {num}: {name.replace('_', ' ')}")

# GHA Workflows
workflows = [
    (".github/workflows/ci.yml", "Main CI pipeline — lint, type check, build"),
    (".github/workflows/backend-tests.yml", "Backend pytest suite with PostgreSQL service"),
    (".github/workflows/e2e-tests.yml", "E2E Playwright tests with full stack"),
    (".github/workflows/code-analysis.yml", "Static analysis and security scanning"),
    (".github/workflows/secret-scan.yml", "Gitleaks secret scanning on PRs and push"),
    (".github/workflows/_docker-build-push.yml", "Reusable Docker build and push workflow"),
    (".github/workflows/price-sync.yml", "Price sync cron workflow"),
    (".github/workflows/fetch-weather.yml", "Weather fetch cron every 6 hours"),
    (".github/workflows/market-research.yml", "Market research cron daily 2am UTC"),
    (".github/workflows/sync-connections.yml", "Connection sync cron every 2 hours"),
    (".github/workflows/scrape-rates.yml", "Rate scraping cron daily 3am UTC"),
    (".github/workflows/check-alerts.yml", "Alert checking cron every 15 minutes"),
    (".github/workflows/dunning-cycle.yml", "Dunning cycle cron daily 7am UTC"),
    (".github/workflows/kpi-report.yml", "KPI report cron daily 6am UTC"),
    (".github/workflows/model-retrain.yml", "ML model retraining workflow"),
    (".github/workflows/data-retention.yml", "Data retention cleanup workflow"),
    (".github/workflows/data-health-check.yml", "Data health monitoring cron"),
    (".github/workflows/observe-forecasts.yml", "Forecast observation recording workflow"),
    (".github/workflows/deploy-staging.yml", "Staging deployment pipeline"),
    (".github/workflows/deploy-production.yml", "Production deployment with migration gate"),
    (".github/workflows/keepalive.yml", "Render keepalive ping"),
    (".github/workflows/self-healing-monitor.yml", "Self-healing monitor: auto-issues after 3+ failures"),
    (".github/workflows/nightly-learning.yml", "Nightly ML learning workflow"),
]
for src, desc in workflows:
    obj(src, desc)

# Composite Actions
actions = [
    (".github/actions/setup-python-env/action.yml", "Composite action: Python environment setup with caching"),
    (".github/actions/setup-node-env/action.yml", "Composite action: Node.js environment setup with caching"),
    (".github/actions/wait-for-service/action.yml", "Composite action: Wait for service health check"),
    (".github/actions/retry-curl/action.yml", "Composite action: Retry HTTP calls with exponential backoff"),
    (".github/actions/notify-slack/action.yml", "Composite action: Color-coded Slack failure alerts"),
    (".github/actions/validate-migrations/action.yml", "Composite action: Migration convention validation"),
]
for src, desc in actions:
    obj(src, desc)

# Cron workflows use retry-curl and notify-slack
cron_workflows = [
    ".github/workflows/check-alerts.yml",
    ".github/workflows/fetch-weather.yml",
    ".github/workflows/market-research.yml",
    ".github/workflows/sync-connections.yml",
    ".github/workflows/scrape-rates.yml",
    ".github/workflows/dunning-cycle.yml",
    ".github/workflows/kpi-report.yml",
    ".github/workflows/data-health-check.yml",
    ".github/workflows/price-sync.yml",
    ".github/workflows/observe-forecasts.yml",
    ".github/workflows/data-retention.yml",
    ".github/workflows/keepalive.yml",
]
for wf in cron_workflows:
    imp(wf, ".github/actions/retry-curl/action.yml", "Exponential backoff for API calls")
    imp(wf, ".github/actions/notify-slack/action.yml", "Slack failure alerts")

# Scripts
scripts = [
    ("scripts/deploy.sh", "Deployment script for staging/production"),
    ("scripts/production-deploy.sh", "Production deployment with safety checks"),
    ("scripts/install-hooks.sh", "Git hooks installation script"),
    ("scripts/health-check.sh", "Application health check script"),
    ("scripts/backup.sh", "Database backup script"),
    ("scripts/restore.sh", "Database restore script"),
    ("scripts/docker-entrypoint.sh", "Docker container entrypoint script"),
    ("scripts/loki-feature.sh", "Loki Mode feature workflow script"),
    ("scripts/loki-verify.sh", "Loki Mode verification script"),
    ("scripts/loki-decompose.py", "Loki task decomposition utility"),
    ("scripts/stream-chain-run.sh", "Stream chain execution script"),
    ("scripts/verification-loop-full.sh", "Full verification loop script"),
    ("scripts/notion_hub_setup.py", "Notion hub page and database setup"),
    ("scripts/project-intelligence-sync.sh", "Project intelligence sync script"),
    ("scripts/run_migrations_007_019.py", "Migration runner for migrations 7-19"),
    ("scripts/run_migrations_018_019.py", "Migration runner for migrations 18-19"),
]
for src, desc in scripts:
    obj(src, desc)

# Root configs
configs = [
    ("pyproject.toml", "Python project config: pytest, coverage thresholds, dependencies"),
    ("Dockerfile", "Docker build configuration for backend container"),
    ("docker-compose.yml", "Docker Compose for local development stack"),
    ("render.yaml", "Render deployment configuration for backend and frontend"),
    (".github/dependabot.yml", "Dependabot config: pip, npm, github-actions weekly Monday"),
]
for src, desc in configs:
    obj(src, desc)

# Docs
docs = [
    ("docs/DEPLOYMENT.md", "Deployment procedures and rollback documentation"),
    ("docs/TESTING.md", "Testing strategy and framework documentation"),
    ("docs/INFRASTRUCTURE.md", "Infrastructure architecture documentation"),
    ("docs/MONITORING.md", "Monitoring and observability documentation"),
    ("docs/STRIPE_ARCHITECTURE.md", "Stripe payment architecture documentation"),
    ("docs/DNS_EMAIL_SETUP.md", "DNS and email provider setup guide"),
    ("docs/CODEMAP_BACKEND.md", "Backend code map documentation"),
    ("docs/CODEMAP_FRONTEND.md", "Frontend code map documentation"),
    ("docs/OAUTH_SETUP_GUIDE.md", "OAuth provider setup guide"),
    ("docs/LOKI_INTEGRATION.md", "Loki Mode integration documentation"),
    ("docs/AUTOMATION_PLAN.md", "Automation plan: 9 workflows, 7 approved"),
]
for src, desc in docs:
    obj(src, desc)


# ============================================================
# PHASE 22: Cross-layer imports
# ============================================================
print("\n=== Phase 22: Cross-layer imports ===")

# Backend services used by ML
imp("backend/services/hnsw_vector_store.py", "hnswlib", "HNSW approximate nearest neighbor index")
imp("backend/services/learning_service.py", "numpy", "Numerical operations for adaptive learning")

# Deploy workflows use composite actions
imp(".github/workflows/deploy-production.yml", ".github/actions/setup-python-env/action.yml", "Python env for migration gate")
imp(".github/workflows/deploy-production.yml", ".github/actions/validate-migrations/action.yml", "Migration validation before deploy")
imp(".github/workflows/deploy-production.yml", ".github/actions/notify-slack/action.yml", "Rollback alert on failure")
imp(".github/workflows/backend-tests.yml", ".github/actions/setup-python-env/action.yml", "Python env for test suite")
imp(".github/workflows/e2e-tests.yml", ".github/actions/setup-node-env/action.yml", "Node env for Playwright")
imp(".github/workflows/e2e-tests.yml", ".github/actions/wait-for-service/action.yml", "Wait for backend health")
imp(".github/workflows/ci.yml", ".github/actions/setup-python-env/action.yml", "Python env for lint/type check")
imp(".github/workflows/ci.yml", ".github/actions/setup-node-env/action.yml", "Node env for frontend build")


# ============================================================
# PHASE 23: Shared exports
# ============================================================
print("\n=== Phase 23: Shared exports ===")

# Backend model package exports all models
model_exports = [f"backend/models/{m}" for m in ["user.py", "price.py", "region.py", "supplier.py", "connections.py"]]
shared("backend/models/__init__.py", *model_exports)

# Config exports
shared("backend/config/__init__.py", "backend/config/settings.py", "backend/config/database.py")

# ML package exports
shared("ml/models/__init__.py", "ml/models/price_forecaster.py", "ml/models/ensemble.py")
shared("ml/inference/__init__.py", "ml/inference/predictor.py", "ml/inference/ensemble_predictor.py")

# Frontend types exports
# (types/index.ts is broadly consumed but has no child entities to share)


# ============================================================
# DONE — Print stats
# ============================================================
print("\n=== Bootstrap Complete ===")
stats = run("get-stats")
print(stats)

# Save UID map for reference
uid_file = Path(ROOT) / ".dsp" / "uid_map.json"
with open(uid_file, "w") as f:
    json.dump(uid_map, f, indent=2)
print(f"\nUID map saved to {uid_file} ({len(uid_map)} entries)")
