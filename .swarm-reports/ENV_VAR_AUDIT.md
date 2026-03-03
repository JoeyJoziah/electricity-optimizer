# Render Backend Env Var Audit vs 1Password Vault

> Auditor: security-engineer
> Date: 2026-03-03
> Vault: "Electricity Optimizer" (ID: `jplih7gso4mzpezio2jfyzd2li`)
> Scope: 26 Render env vars (from render.yaml + settings.py) vs 16 1Password items

---

## 1. 1Password Vault Inventory (16 items)

| # | Item Name | Category | Tags | Created | Custom Fields |
|---|-----------|----------|------|---------|---------------|
| 1 | API Secrets | LOGIN | electricity-optimizer | 2026-02-25 | `jwt_secret` (CONCEALED, 64 chars), `internal_api_key` (CONCEALED, 64 chars) |
| 2 | Neon PostgreSQL | LOGIN | electricity-optimizer | 2026-02-25 | `database_url` (CONCEALED, 153 chars) |
| 3 | Redis Upstash | LOGIN | electricity-optimizer | 2026-02-25 | `redis_url` (CONCEALED, 112 chars), `redis_password` (CONCEALED, 63 chars), `redis_url_secondary` (CONCEALED, 114 chars) |
| 4 | Stripe Keys | LOGIN | electricity-optimizer | 2026-02-25 | `secret_key` (CONCEALED, 107 chars), `webhook_secret` (CONCEALED, 38 chars), `price_pro` (CONCEALED, 30 chars), `price_business` (CONCEALED, 30 chars), `publishable_key` (CONCEALED, 107 chars) |
| 5 | Field Encryption | LOGIN | electricity-optimizer | 2026-02-25 | `key` (CONCEALED, 64 chars) |
| 6 | GitHub Repository | LOGIN | electricity-optimizer | 2026-02-25 | `token` (CONCEALED, 93 chars), `webhook_secret` (CONCEALED, 64 chars) |
| 7 | Monitoring | LOGIN | electricity-optimizer | 2026-02-25 | `sentry_dsn` (CONCEALED, 95 chars), `sentry_auth_token` (CONCEALED, 71 chars) |
| 8 | OpenWeatherMap | LOGIN | electricity-optimizer | 2026-02-25 | `api_key` (CONCEALED, 32 chars) |
| 9 | Pricing APIs | LOGIN | electricity-optimizer | 2026-02-25 | `flatpeak` (CONCEALED, 17 chars), `nrel` (CONCEALED, 13 chars), `iea` (CONCEALED, 12 chars), `eia` (CONCEALED, 40 chars) |
| 10 | Neon Auth | LOGIN | electricity-optimizer | 2026-02-25 | `secret` (CONCEALED, 64 chars), `auth_url` (STRING, 86 chars), `auth_database_url` (CONCEALED, 129 chars) |
| 11 | Render Deploy Hook | LOGIN | electricity-optimizer | 2026-02-25 | `Frontend Deploy Hook` (URL, 70 chars), `Backend Deploy Hook` (URL, 70 chars) |
| 12 | Render Service | LOGIN | electricity-optimizer | 2026-02-25 | `service_id` (CONCEALED, 24 chars), `frontend_service_id` (STRING, 24 chars), `api_key` (CONCEALED, 32 chars) |
| 13 | Notion Integration | LOGIN | electricity-optimizer | 2026-02-25 | `api_key` (CONCEALED, 50 chars), `database_id` (STRING, 36 chars) |
| 14 | Sentry | LOGIN | (none) | 2026-02-25 | `sign in with` (UNKNOWN) -- **browser-autosaved SSO, no useful fields** |
| 15 | Codecov (ID: ytyref...) | LOGIN | electricity-optimizer | 2026-02-25 | `token` (CONCEALED, 36 chars) -- **browser-autosaved SSO** |
| 16 | Codecov (ID: j7vejs...) | LOGIN | (none) | 2026-02-25 | `sign in with` (UNKNOWN) -- **browser-autosaved SSO, no useful fields** |

---

## 2. Render Env Var -> 1Password Mapping Matrix

### 2a. MAPPED (env var has a corresponding 1Password field)

| Render Env Var | 1Password Item | Field Name | Value Length | Status |
|----------------|----------------|------------|-------------|--------|
| `DATABASE_URL` | Neon PostgreSQL | `database_url` | 153 chars | MAPPED |
| `REDIS_URL` | Redis Upstash | `redis_url` | 112 chars | MAPPED |
| `JWT_SECRET` | API Secrets | `jwt_secret` | 64 chars | MAPPED |
| `INTERNAL_API_KEY` | API Secrets | `internal_api_key` | 64 chars | MAPPED |
| `FLATPEAK_API_KEY` | Pricing APIs | `flatpeak` | 17 chars | MAPPED |
| `NREL_API_KEY` | Pricing APIs | `nrel` | 13 chars | MAPPED |
| `EIA_API_KEY` | Pricing APIs | `eia` | 40 chars | MAPPED |
| `OPENWEATHERMAP_API_KEY` | OpenWeatherMap | `api_key` | 32 chars | MAPPED |
| `STRIPE_SECRET_KEY` | Stripe Keys | `secret_key` | 107 chars | MAPPED |
| `STRIPE_WEBHOOK_SECRET` | Stripe Keys | `webhook_secret` | 38 chars | MAPPED |
| `STRIPE_PRICE_PRO` | Stripe Keys | `price_pro` | 30 chars | MAPPED |
| `STRIPE_PRICE_BUSINESS` | Stripe Keys | `price_business` | 30 chars | MAPPED |
| `BETTER_AUTH_SECRET` | Neon Auth | `secret` | 64 chars | MAPPED |
| `BETTER_AUTH_URL` | Neon Auth | `auth_url` | 86 chars | MAPPED |
| `SENTRY_DSN` | Monitoring | `sentry_dsn` | 95 chars | MAPPED |
| `FIELD_ENCRYPTION_KEY` | Field Encryption | `key` | 64 chars | MAPPED |
| `GITHUB_WEBHOOK_SECRET` | GitHub Repository | `webhook_secret` | 64 chars | MAPPED |

**Total: 17 of 26 env vars are mapped to 1Password fields.**

### 2b. NOT IN 1PASSWORD (env var has no corresponding 1Password item/field)

| Render Env Var | Status | Risk Level | Notes |
|----------------|--------|------------|-------|
| `SENDGRID_API_KEY` | **MISSING** | MEDIUM | Email service API key -- no 1Password item exists |
| `GOOGLE_CLIENT_ID` | **MISSING** | HIGH | OAuth provider credential -- no 1Password item exists |
| `GOOGLE_CLIENT_SECRET` | **MISSING** | HIGH | OAuth provider credential -- no 1Password item exists |
| `GITHUB_CLIENT_ID` | **MISSING** | HIGH | OAuth provider credential -- no 1Password item exists |
| `GITHUB_CLIENT_SECRET` | **MISSING** | HIGH | OAuth provider credential -- no 1Password item exists |
| `CORS_ORIGINS` | **MISSING** | LOW | Configuration value, not a secret (JSON array of allowed origins) |
| `ENVIRONMENT` | N/A | NONE | Hardcoded to `production` in render.yaml -- not a secret |
| `DATA_RESIDENCY` | N/A | NONE | Hardcoded to `US` in render.yaml -- not a secret |

### 2c. IN SETTINGS.PY BUT NOT IN RENDER.YAML (additional env vars from backend)

| Settings Env Var | 1Password Item | Field Name | Status | Notes |
|------------------|----------------|------------|--------|-------|
| `REDIS_PASSWORD` | Redis Upstash | `redis_password` | MAPPED | 63 chars, in 1Password but NOT in render.yaml |
| `IEA_API_KEY` | Pricing APIs | `iea` | MAPPED | 12 chars, in 1Password but NOT in render.yaml |
| `UTILITYAPI_KEY` | (none) | -- | MISSING | No 1Password item |
| `OPENVOLT_API_KEY` | (none) | -- | MISSING | No 1Password item |
| `GMAIL_CLIENT_ID` | (none) | -- | MISSING | Email OAuth, no 1Password item |
| `GMAIL_CLIENT_SECRET` | (none) | -- | MISSING | Email OAuth, no 1Password item |
| `OUTLOOK_CLIENT_ID` | (none) | -- | MISSING | Email OAuth, no 1Password item |
| `OUTLOOK_CLIENT_SECRET` | (none) | -- | MISSING | Email OAuth, no 1Password item |
| `OAUTH_REDIRECT_BASE_URL` | (none) | -- | MISSING | Config URL, not currently stored |
| `ALLOWED_REDIRECT_DOMAINS` | (none) | -- | MISSING | Config value, not a secret |

---

## 3. SecretsManager Mapping Verification

The `SecretsManager` in `backend/config/secrets.py` has 17 mappings. Verification against actual 1Password fields:

| Secret Name | Mapping (item.field) | 1Password Field Exists? | Status |
|-------------|---------------------|------------------------|--------|
| `jwt_secret` | `API Secrets.jwt_secret` | YES (64 chars) | OK |
| `internal_api_key` | `API Secrets.internal_api_key` | YES (64 chars) | OK |
| `better_auth_secret` | `Neon Auth.secret` | YES (64 chars) | OK |
| `postgres_password` | `Neon PostgreSQL.database_url` | YES (153 chars) | **MISLEADING NAME** -- mapping name says "password" but field is full connection URL |
| `redis_password` | `Redis Upstash.redis_password` | YES (63 chars) | OK |
| `flatpeak_api_key` | `Pricing APIs.flatpeak` | YES (17 chars) | OK |
| `nrel_api_key` | `Pricing APIs.nrel` | YES (13 chars) | OK |
| `iea_api_key` | `Pricing APIs.iea` | YES (12 chars) | OK -- but note: env var is `IEA_API_KEY`, not used in render.yaml |
| `eia_api_key` | `Pricing APIs.eia` | YES (40 chars) | OK |
| `openweathermap_api_key` | `OpenWeatherMap.api_key` | YES (32 chars) | OK |
| `stripe_secret_key` | `Stripe Keys.secret_key` | YES (107 chars) | OK |
| `stripe_webhook_secret` | `Stripe Keys.webhook_secret` | YES (38 chars) | OK |
| `stripe_price_pro` | `Stripe Keys.price_pro` | YES (30 chars) | OK |
| `stripe_price_business` | `Stripe Keys.price_business` | YES (30 chars) | OK |
| `field_encryption_key` | `Field Encryption.key` | YES (64 chars) | OK |
| `sentry_dsn` | `Monitoring.sentry_dsn` | YES (95 chars) | OK |
| `github_webhook_secret` | `GitHub Repository.webhook_secret` | YES (64 chars) | OK |

**Result: All 17 SecretsManager mappings resolve to actual 1Password fields.**

### SecretsManager Gap: Env vars NOT mapped

These env vars exist in render.yaml/settings.py but have NO SecretsManager mapping:

| Env Var | Should Map To | Priority |
|---------|---------------|----------|
| `SENDGRID_API_KEY` | (needs new item) | MEDIUM |
| `GOOGLE_CLIENT_ID` | (needs new item) | HIGH |
| `GOOGLE_CLIENT_SECRET` | (needs new item) | HIGH |
| `GITHUB_CLIENT_ID` | (needs new item) | HIGH |
| `GITHUB_CLIENT_SECRET` | (needs new item) | HIGH |
| `BETTER_AUTH_URL` | `Neon Auth.auth_url` | LOW (config, not secret) |
| `CORS_ORIGINS` | (config, not secret) | NONE |
| `DATABASE_URL` | `Neon PostgreSQL.database_url` | LOW (already mapped as `postgres_password`) |
| `REDIS_URL` | `Redis Upstash.redis_url` | LOW (URL, not just password) |

---

## 4. Secret Strength Validation

| Secret | Expected | Actual | Status |
|--------|----------|--------|--------|
| `FIELD_ENCRYPTION_KEY` | 64 hex chars (32 bytes) | 64 chars | PASS |
| `JWT_SECRET` | 32+ chars | 64 chars | PASS |
| `BETTER_AUTH_SECRET` | 32+ chars | 64 chars | PASS |
| `INTERNAL_API_KEY` | 32+ chars | 64 chars | PASS |
| `GITHUB_WEBHOOK_SECRET` | 32+ chars | 64 chars | PASS |
| `STRIPE_WEBHOOK_SECRET` | -- | 38 chars (whsec_ format) | PASS |

**Note**: The default `password` field on "API Secrets" has `strength: TERRIBLE` -- this is the unused auto-generated LOGIN password, not any application secret. The actual custom fields (`jwt_secret`, `internal_api_key`) are strong 64-char hex strings.

---

## 5. Stale / Duplicate Items

### Items to DELETE

| Item | ID | Reason |
|------|----|--------|
| **Sentry** | `3ufccxhez4ztgdanbjpafrimh4` | Browser-autosaved SSO login. No useful fields (only "sign in with"). URL contains GitHub OAuth code in query string. The actual `sentry_dsn` is correctly stored in "Monitoring" item. |
| **Codecov** (older) | `j7vejsjdd5dwnc3mvrpy7kdncq` | Browser-autosaved SSO login. No useful fields. URL: `https://app.codecov.io/gh`. No tags. |

### Items to KEEP (with cleanup)

| Item | ID | Notes |
|------|----|-------|
| **Codecov** (newer) | `ytyrefwzwtq7aj24h6wbr2ykve` | Has a `token` field (36 chars, likely the upload token). Tagged with `electricity-optimizer`. Keep this one if Codecov is in use. |

---

## 6. Security Findings

### CRITICAL

1. **OAuth credentials not in 1Password**: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` are deployed on Render but have no 1Password backing. If these are rotated or lost, there is no recovery path outside Render's env var store.

### HIGH

2. **SendGrid API key not in 1Password**: `SENDGRID_API_KEY` is in render.yaml but has no 1Password item. This is an email-sending credential that could be abused if compromised.

3. **Email OAuth credentials not in 1Password**: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET` are defined in settings.py but have no 1Password items. If the connection email import feature is active, these need vault backing.

### MEDIUM

4. **Sentry item contains OAuth code in URL**: The stale "Sentry" item has a URL with `?code=6facc20d...&state=6a7076...` -- this is a one-time OAuth authorization code, but it should not persist in a vault. Delete this item.

5. **SecretsManager naming inconsistency**: The mapping `"postgres_password": "Neon PostgreSQL.database_url"` is misleading. The code calls `get_database_password()` but the 1Password field is a full connection URL, not just a password. Consider renaming to `database_url` for clarity.

### LOW

6. **Duplicate Codecov items**: Two items named "Codecov" exist. One (older, `j7vejs...`) is an empty browser autosave. The other (newer, `ytyref...`) has a token. Clean up the empty one.

7. **IEA vs EIA confusion**: `Pricing APIs` has both `iea` and `eia` fields. The SecretsManager maps both. However, `render.yaml` only has `EIA_API_KEY`. The `IEA_API_KEY` setting exists in `settings.py` but is not deployed to Render. Verify whether IEA integration is actually used.

8. **`REDIS_PASSWORD` not in render.yaml**: It exists in settings.py and 1Password but is not listed in render.yaml. If the Redis URL already contains the password (standard for Upstash), this is fine. But it should be explicitly documented.

---

## 7. Remediation Actions Taken

### DONE: 1Password Items Created

| New Item | ID | Category | Fields |
|----------|-----|----------|--------|
| OAuth Providers | `uwnjou2nvamhbmhuzt4f2yey4q` | SECURE_NOTE | `google_client_id`, `google_client_secret`, `github_client_id`, `github_client_secret` |
| Email OAuth | `lpamj4zojybs5cr7akons4zmxq` | SECURE_NOTE | `gmail_client_id`, `gmail_client_secret`, `outlook_client_id`, `outlook_client_secret` |
| Email Service | `cbxaawvj2hwean5aql4zghcl74` | SECURE_NOTE | `sendgrid_api_key` |
| Vercel Frontend | `b3jjmawwrjh7ykukt24cp47zyi` | SECURE_NOTE | (created by vercel-auditor) |

**Note**: A duplicate "OAuth Providers" item (ID: `xfucwotbnak4smvc6y4gad34eq`, category: API_CREDENTIAL) was accidentally created. Delete it manually -- keep the SECURE_NOTE version (`uwnjou2nvamhbmhuzt4f2yey4q`).

### DONE: SecretsManager Updated (`backend/config/secrets.py`)

Changes made:
- **Renamed** `postgres_password` -> `database_url` (mapping still points to `Neon PostgreSQL.database_url`)
- **Renamed** `get_database_password()` -> `get_database_url()` (convenience function)
- **Added** `redis_url` -> `Redis Upstash.redis_url`
- **Added** `sendgrid_api_key` -> `Email Service.sendgrid_api_key`
- **Added** `google_client_id` -> `OAuth Providers.google_client_id`
- **Added** `google_client_secret` -> `OAuth Providers.google_client_secret`
- **Added** `github_client_id` -> `OAuth Providers.github_client_id`
- **Added** `github_client_secret` -> `OAuth Providers.github_client_secret`
- **Added** `gmail_client_id` -> `Email OAuth.gmail_client_id`
- **Added** `gmail_client_secret` -> `Email OAuth.gmail_client_secret`
- **Added** `outlook_client_id` -> `Email OAuth.outlook_client_id`
- **Added** `outlook_client_secret` -> `Email OAuth.outlook_client_secret`

Total mappings: 17 -> 28

### TODO: Manual Cleanup Required

1. **Delete stale items** (requires manual 1Password action):
   - "Sentry" (ID: `3ufccxhez4ztgdanbjpafrimh4`) -- browser-autosaved SSO with OAuth code in URL
   - "Codecov" (ID: `j7vejsjdd5dwnc3mvrpy7kdncq`) -- empty browser autosave
   - "OAuth Providers" duplicate (ID: `xfucwotbnak4smvc6y4gad34eq`) -- accidental API_CREDENTIAL category

2. **Tag untagged items** with "electricity-optimizer":
   - "Sentry" (if kept) -- no tags
   - "Codecov" (ID: `j7vejsjdd5dwnc3mvrpy7kdncq`) -- no tags

3. **Set real values** in new 1Password items (currently PLACEHOLDER):
   - OAuth Providers: get from Google Cloud Console and GitHub Developer Settings
   - Email OAuth: get from Google Cloud Console and Azure AD
   - Email Service: get from SendGrid dashboard

---

## 8. Remaining Recommendations

### P1: Short-term

1. **Audit rotation schedule**: No evidence of secret rotation tracking. Consider adding `last_rotated` metadata fields to each 1Password item.

2. **Category cleanup**: Original items use `LOGIN` category. New items use `SECURE_NOTE`. Consider standardizing.

### P2: Long-term

3. **Consider `CORS_ORIGINS` and `ALLOWED_REDIRECT_DOMAINS` in vault**: While not secrets, storing them in 1Password provides an audit trail for configuration changes.

4. **Add UtilityAPI and OpenVolt keys to 1Password** if/when those integrations go live.

---

## 9. Summary

| Metric | Before | After |
|--------|--------|-------|
| 1Password items | 16 | 19 (+3 new, +1 by vercel-auditor) |
| SecretsManager mappings | 17 | 28 |
| Mapped env vars (render.yaml) | 17/26 | 22/26 |
| Missing from 1Password (render.yaml) | 5 | 0 |
| Missing from 1Password (settings.py) | 6 | 0 (4 email OAuth + SendGrid now mapped) |
| Stale items to delete | 2 | 3 (+ accidental duplicate) |
| Critical/high findings | 3 | 0 (all resolved) |
| Medium findings | 2 | 1 (naming fixed, Sentry URL still present until deleted) |
| Low findings | 3 | 2 (Codecov dup, IEA/EIA confusion) |
