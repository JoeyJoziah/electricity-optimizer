# Audit Report: Config & Secrets Management

**Date:** 2026-03-23
**Scope:** Configuration files, secret handling, env vars, encryption, log sanitization
**Auditor:** Security Auditor (Claude Opus 4.6)

**Files Reviewed:** 42 files across backend/config, backend/auth, backend/utils, backend/middleware, backend/api, backend/services, workers/, frontend/, root config files, and all GHA workflows. Full codebase grep for sensitive patterns.

---

## P0 -- Critical (Fix Immediately)

### 18-P0-1: Exception Details Leaked to Clients in `routers/predictions.py`

**File:** `backend/routers/predictions.py`, lines 483, 572, 668

Three endpoints pass raw exception text to the HTTP response body via `detail=f"Failed to generate forecast: {str(e)}"`. SQLAlchemy exceptions routinely include the `DATABASE_URL` in connection error messages.

**Risk:** Information disclosure via error messages.
**Remediation:** Return generic "Internal server error" message in production. Log `str(e)` server-side only.

### 18-P0-2: Dev/Test Mode Leaks Raw Exception Details to HTTP Clients

**File:** `backend/app_factory.py`, line 557

The general exception handler returns `str(exc)` to the client in development environments. If the backend is accidentally deployed with `ENVIRONMENT=development`, all exceptions become visible.

**Risk:** Information disclosure. Database URLs, file paths, and internal state can leak.
**Remediation:** Never return `str(exc)` to clients in any environment.

### 18-P0-3: Portal Scan Endpoint Leaks Crypto Exception Details in Response

**File:** `backend/api/v1/internal/portal_scan.py`, line 183

When credential decryption fails, the raw exception is included in the API response: `"error": f"Credential decrypt failed: {exc}"`. Cryptographic exceptions can include key length information and algorithm details.

**Risk:** Cryptographic implementation details leaked in error responses.
**Remediation:** Return generic error message. Log details server-side only.

---

## P1 -- High (Fix This Sprint)

### 18-P1-1: OAuth HMAC Signing Reuses `INTERNAL_API_KEY` Instead of Dedicated Secret

**File:** `backend/services/email_oauth_service.py`, lines 61-64

OAuth state HMAC is signed with `settings.internal_api_key` rather than a dedicated `OAUTH_STATE_SECRET`. The CLAUDE.md documents the expected secret name but the code uses `INTERNAL_API_KEY`.

**Risk:** Key separation violation. Compromise of either channel compromises both.
**Remediation:** Add dedicated `OAUTH_STATE_SECRET` env var.

### 18-P1-2: `ML_MODEL_SIGNING_KEY` Not in `settings.py` -- Bypasses Validation

**File:** `ml/inference/predictor.py`, line 133

`ML_MODEL_SIGNING_KEY` read directly from `os.environ.get()`, bypassing centralized validation. No production validator ensures it is set.

**Risk:** Models could be loaded without integrity verification in production.
**Remediation:** Add to `settings.py` with production validator.

### 18-P1-3: `OTEL_EXPORTER_OTLP_HEADERS` Bypasses All Validation

**File:** Not in `settings.py`; consumed directly by OTel SDK. Render config: `render.yaml`, line 80.

Contains Grafana Cloud `Authorization=Basic` credential. Not covered by log sanitizer patterns. Not in `SECRET_MAPPINGS`.

**Risk:** Credential leak via log aggregation.
**Remediation:** Add log sanitizer pattern, add to `settings.py`, add to `SECRET_MAPPINGS`.

### 18-P1-4: Log Sanitizer Does Not Cover Resend, Groq, Gemini, or Diffbot Key Prefixes

**File:** `backend/app_factory.py`, lines 63-68

Only redacts `postgresql://`, `redis://`, `sk_live_`, `rk_live_`. Does NOT cover `re_`, `gsk_`, `AIza`, `sk_test_`, Bearer tokens, or Authorization headers.

**Risk:** API key exposure in logs.
**Remediation:** Expand `_SENSITIVE_PATTERNS` to cover all key prefixes.

### 18-P1-5: Stripe Key Prefix Logged at Module Load Time

**File:** `backend/services/stripe_service.py`, line 37

Logs first 7 characters of Stripe secret key. Confirms key type in production logs.

**Remediation:** Log only key type classification ("live" or "test").

### 18-P1-6: AES-256-GCM Encryption Uses No Associated Data (AAD)

**File:** `backend/utils/encryption.py`, lines 44, 65

AAD is `None` for all encrypt/decrypt calls. Without AAD, ciphertext can be swapped between columns/rows without detection.

**Risk:** Ciphertext portability attack within the database.
**Remediation:** Pass field name and record ID as AAD. Breaking change requiring re-encryption migration.

### 18-P1-7: No Encryption Key Rotation Mechanism

**File:** `backend/utils/encryption.py`

No key versioning, dual-key decryption, re-encryption scripts, or key age tracking. If key needs rotation, existing encrypted fields become permanently unreadable.

**Risk:** Operational risk -- inability to rotate encryption key without data loss.
**Remediation:** Add key versioning, dual-key support, and rotation tooling.

---

## P2 -- Medium (Fix Soon)

### 18-P2-1: `.env` and `.env.test` Contain Predictable Test Credentials

Weak test creds on local disk (`POSTGRES_PASSWORD=testpassword123`, `JWT_SECRET=test_jwt_secret_key_change_in_production`). Properly `.gitignore`d but predictable. `JWT_SECRET` value is on the insecure defaults blocklist.

### 18-P2-2: CI/CD Workflows Use Predictable JWT Secrets

`JWT_SECRET: test_secret_key_for_ci_minimum_32_chars` hardcoded in `_backend-tests.yml`, `e2e-tests.yml`, `utility-type-tests.yml`. Identical across all workflows.

### 18-P2-3: `docker-compose.prod.yml` References Local PostgreSQL Container

Production Docker Compose file defines local `DATABASE_URL` without `?sslmode=require`. Vestige of pre-Neon setup.

### 18-P2-4: `.mcp.json` Not in `.gitignore`

Contains machine-specific absolute paths. Should not be in version control.

### 18-P2-5: `.composio.lock` Not in `.gitignore`

Contains personal email addresses and GitHub username. PII that should not be in version control.

### 18-P2-6: Internal Endpoints Return Raw Exception Text

Multiple internal endpoints include raw `str(exc)` in JSON responses: `backend/api/v1/internal/email_scan.py:286`, `portal_scan.py:201`, `data_pipeline.py:630`. Visible in GHA workflow logs.

### 18-P2-7: `GRAFANA_PASSWORD=admin` in Root `.env.example`

Weak default password suggestion in example file.

### 18-P2-8: Session Cache Encryption Silently Falls Back to Plaintext

**File:** `backend/auth/neon_auth.py`, lines 76-79. No warning log emitted when `FIELD_ENCRYPTION_KEY` is not set.

---

## P3 -- Low / Housekeeping

### 18-P3-1: Portal Scraper Docstring Uses `password="secret"` Example
**File:** `backend/services/portal_scraper_service.py`, line 205

### 18-P3-2: Pricing API Client Docstrings Use Placeholder API Keys
**Files:** `backend/integrations/pricing_apis/nrel.py:113`, `iea.py:100`, `eia.py:92`, `flatpeak.py:75`

### 18-P3-3: `SecretsManager` Singleton Never Re-Evaluates 1Password Availability
**File:** `backend/config/secrets.py`, lines 112-115 and 229-232

### 18-P3-4: `wrangler.toml` KV Namespace ID Exposed (standard CF practice, no action needed)

### 18-P3-5: Rate Limiter Namespace IDs Are Sequential (no risk)

### 18-P3-6: `backfill_users.py` Script Returns Raw Exception in Detail
**File:** `backend/scripts/backfill_users.py`, line 201

---

## Files With No Issues Found

- `backend/config/settings.py` -- Excellent production validators for all secrets
- `backend/api/dependencies.py` -- Constant-time API key comparison, fail-closed
- `workers/api-gateway/src/middleware/internal-auth.ts` -- `crypto.subtle.timingSafeEqual`
- `workers/api-gateway/src/middleware/security.ts` -- Comprehensive security headers
- `backend/middleware/security_headers.py` -- Proper HSTS configuration
- `backend/auth/neon_auth.py` -- Session tokens hashed, Redis cache encrypted
- `backend/auth/password.py` -- Strong password policy
- `backend/api/v1/webhooks.py` -- Proper HMAC-SHA256 verification
- `render.yaml` -- All sensitive env vars use `sync: false`
- `docker-compose.yml` -- All secrets reference `${VAR}` from environment
- `.gitignore` -- Comprehensive exclusion of sensitive files
- `.dockerignore` -- Excludes `.env*`, `.loki/`, `.claude/`
- `frontend/.env.local` -- Only non-secret config
- `frontend/lib/api/client.ts` -- No secrets in frontend code
- `backend/app_factory.py` -- Swagger/ReDoc disabled in production
- `backend/observability.py` -- No secrets in OTel configuration

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0 | 3 | Exception details leaked to clients (predictions router, general handler, portal scan) |
| P1 | 7 | OAuth HMAC key reuse, ML signing key outside settings, OTel headers bypass, log sanitizer gaps, Stripe key prefix logged, missing AAD, no key rotation |
| P2 | 8 | Local .env weak creds, CI predictable JWT, stale docker-compose.prod, files not gitignored, internal endpoints leak errors |
| P3 | 6 | Docstring placeholders, singleton behavior, KV namespace IDs |

**Overall Assessment:** Mature secrets management with strong production validators, constant-time comparisons, encrypted session caching, and proper .gitignore coverage. **No hardcoded production secrets found anywhere in the codebase.** Primary gaps: error message sanitization, key separation, log sanitizer coverage, encryption key lifecycle.

**Estimated remediation effort:** P0: 1-2 hours. P1: 1-2 sprints. P2/P3: housekeeping batches.
