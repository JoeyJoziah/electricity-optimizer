# Environment Variable Audit Report

**Date**: 2026-03-03
**Swarm**: 3 agents (render-auditor, vercel-auditor, security-reviewer) + lead
**Scope**: Render backend, Vercel frontend, 1Password vault, SecretsManager code

## Executive Summary

- **27 env vars** mapped to 1Password (up from 17)
- **5 new 1Password items** created (OAuth Providers, Email OAuth, Email Service, CORS and Redirects, Vercel Frontend)
- **2 code fixes** applied (BETTER_AUTH_SECRET validator, INTERNAL_API_KEY != JWT_SECRET enforcer)
- **0 leaked secrets** in git history
- **Security posture**: STRONG (27 PASS, 0 FAIL, 0 unresolved WARN)

## 1Password Vault: "Electricity Optimizer"

### Items (21 total, including 3 kept-but-stale)

| Item | Category | Fields | Tags | Status |
|------|----------|--------|------|--------|
| API Secrets | LOGIN | jwt_secret (64ch), internal_api_key (64ch) | tagged | Active |
| Neon PostgreSQL | LOGIN | database_url (153ch) | tagged | Active |
| Neon Auth | LOGIN | secret (64ch), auth_url (86ch), auth_database_url (129ch) | tagged | Active |
| Redis Upstash | LOGIN | redis_url (112ch), redis_password (63ch), redis_url_secondary (114ch) | tagged | Active |
| Pricing APIs | LOGIN | flatpeak (17ch), nrel (13ch), iea (12ch), eia (40ch) | tagged | Active |
| Stripe Keys | LOGIN | secret_key (107ch), webhook_secret (38ch), price_pro (30ch), price_business (30ch), publishable_key (107ch) | tagged | Active |
| Field Encryption | LOGIN | key (64ch) | tagged | Active |
| GitHub Repository | LOGIN | token (93ch), webhook_secret (64ch) | tagged | Active |
| OpenWeatherMap | LOGIN | api_key (32ch) | tagged | Active |
| Monitoring | LOGIN | sentry_dsn (95ch), sentry_auth_token (71ch) | tagged | Active |
| Notion Integration | LOGIN | api_key (50ch), database_id (36ch) | tagged | Active |
| Render Service | LOGIN | service_id (24ch), frontend_service_id (24ch, STALE), api_key (32ch) | tagged | Active |
| Render Deploy Hook | LOGIN | (url field) | tagged | Active |
| **Vercel Frontend** | SECURE_NOTE | deployment_url, next_public_api_url, next_public_app_url, next_public_site_url, better_auth_url | tagged | **NEW** |
| **OAuth Providers** | SECURE_NOTE | google_client_id, google_client_secret, github_client_id, github_client_secret | tagged | **NEW** |
| **Email OAuth** | SECURE_NOTE | gmail_client_id, gmail_client_secret, outlook_client_id, outlook_client_secret | tagged | **NEW** |
| **Email Service** | SECURE_NOTE | sendgrid_api_key | tagged | **NEW** |
| **CORS and Redirects** | SECURE_NOTE | cors_origins, allowed_redirect_domains, oauth_redirect_base_url | tagged | **NEW** |
| Sentry | LOGIN | (empty — browser SSO autosave) | untagged | Stale (kept) |
| Codecov (1) | LOGIN | (has token) | tagged | Active |
| Codecov (2) | LOGIN | (empty — browser autosave) | untagged | Stale (kept) |
| OAuth Providers (dup) | API_CREDENTIAL | (empty — agent duplicate) | — | Stale (kept) |

### Secret Strength Validation

| Secret | Length | Format | Status |
|--------|--------|--------|--------|
| JWT_SECRET | 64 chars | Hex | PASS |
| INTERNAL_API_KEY | 64 chars | Hex | PASS |
| BETTER_AUTH_SECRET | 64 chars | Hex | PASS |
| FIELD_ENCRYPTION_KEY | 64 chars | Hex (32 bytes) | PASS |
| GITHUB_WEBHOOK_SECRET | 64 chars | Hex | PASS |
| STRIPE_SECRET_KEY | 107 chars | sk_live_ prefix | PASS |

## Render Backend (26 env vars)

| Env Var | 1Password Item.Field | Status |
|---------|---------------------|--------|
| DATABASE_URL | Neon PostgreSQL.database_url | MAPPED |
| REDIS_URL | Redis Upstash.redis_url | MAPPED |
| JWT_SECRET | API Secrets.jwt_secret | MAPPED |
| INTERNAL_API_KEY | API Secrets.internal_api_key | MAPPED |
| BETTER_AUTH_SECRET | Neon Auth.secret | MAPPED |
| BETTER_AUTH_URL | Neon Auth.auth_url | MAPPED |
| FLATPEAK_API_KEY | Pricing APIs.flatpeak | MAPPED |
| NREL_API_KEY | Pricing APIs.nrel | MAPPED |
| EIA_API_KEY | Pricing APIs.eia | MAPPED |
| OPENWEATHERMAP_API_KEY | OpenWeatherMap.api_key | MAPPED |
| STRIPE_SECRET_KEY | Stripe Keys.secret_key | MAPPED |
| STRIPE_WEBHOOK_SECRET | Stripe Keys.webhook_secret | MAPPED |
| STRIPE_PRICE_PRO | Stripe Keys.price_pro | MAPPED |
| STRIPE_PRICE_BUSINESS | Stripe Keys.price_business | MAPPED |
| FIELD_ENCRYPTION_KEY | Field Encryption.key | MAPPED |
| GITHUB_WEBHOOK_SECRET | GitHub Repository.webhook_secret | MAPPED |
| SENTRY_DSN | Monitoring.sentry_dsn | MAPPED |
| CORS_ORIGINS | CORS and Redirects.cors_origins | MAPPED (new) |
| GOOGLE_CLIENT_ID | OAuth Providers.google_client_id | MAPPED (new, placeholder) |
| GOOGLE_CLIENT_SECRET | OAuth Providers.google_client_secret | MAPPED (new, placeholder) |
| GITHUB_CLIENT_ID | OAuth Providers.github_client_id | MAPPED (new, placeholder) |
| GITHUB_CLIENT_SECRET | OAuth Providers.github_client_secret | MAPPED (new, placeholder) |
| SENDGRID_API_KEY | Email Service.sendgrid_api_key | MAPPED (new, placeholder) |
| ENVIRONMENT | (hardcoded: production) | N/A |
| DATA_RESIDENCY | (hardcoded: US) | N/A |
| ALLOWED_REDIRECT_DOMAINS | CORS and Redirects.allowed_redirect_domains | MAPPED (new) |

## Vercel Frontend (8 env vars)

| Env Var | Type | 1Password Reference | Status |
|---------|------|-------------------|--------|
| NEXT_PUBLIC_API_URL | Client-visible | Vercel Frontend.next_public_api_url | MAPPED (new) |
| NEXT_PUBLIC_APP_URL | Client-visible | Vercel Frontend.next_public_app_url | MAPPED (new) |
| NEXT_PUBLIC_SITE_URL | Client-visible | Vercel Frontend.next_public_site_url | MAPPED (new) |
| BETTER_AUTH_SECRET | Server SECRET | Neon Auth.secret | MAPPED |
| BETTER_AUTH_URL | Server | Vercel Frontend.better_auth_url | MAPPED (new) |
| DATABASE_URL | Server SECRET | Neon Auth.auth_database_url | MAPPED |
| GOOGLE_CLIENT_ID | Server | OAuth Providers.google_client_id | MAPPED (new) |
| GITHUB_CLIENT_ID | Server | OAuth Providers.github_client_id | MAPPED (new) |

### CRITICAL: Verify BETTER_AUTH_SECRET is set on Vercel
Better Auth falls back to a DEFAULT_SECRET if env var is missing — session cookies could be forged. Ensure `BETTER_AUTH_SECRET` is set in Vercel to the value from `op://Electricity Optimizer/Neon Auth/secret`.

## SecretsManager Mappings (27 total)

Updated in `backend/config/secrets.py`:
- **Original 17**: jwt_secret, internal_api_key, better_auth_secret, database_url, redis_url, redis_password, flatpeak_api_key, nrel_api_key, iea_api_key, eia_api_key, openweathermap_api_key, stripe_secret_key, stripe_webhook_secret, stripe_price_pro, stripe_price_business, field_encryption_key, sentry_dsn, github_webhook_secret
- **Added 10**: sendgrid_api_key, google_client_id, google_client_secret, github_client_id, github_client_secret, gmail_client_id, gmail_client_secret, outlook_client_id, outlook_client_secret (+ database_url renamed from postgres_password)

## Code Changes

1. **backend/config/settings.py**: Added `better_auth_secret` field, `validate_better_auth_secret` field_validator, `validate_api_key_differs_from_jwt` model_validator
2. **backend/config/secrets.py**: 10 new SECRET_MAPPINGS added by render-auditor agent

## Action Items (for user)

- [ ] **CRITICAL**: Verify `BETTER_AUTH_SECRET` is set in Vercel dashboard (not just Render)
- [ ] Set real values for OAuth Providers in 1Password when enabling social login
- [ ] Set real SendGrid API key in 1Password when enabling email
- [ ] Set real Gmail/Outlook OAuth credentials when enabling email bill import
- [ ] Update `Render Service.frontend_service_id` (stale — points to old Render frontend)
- [ ] Consider setting up 1Password Service Account for automated secret injection in CI/CD
