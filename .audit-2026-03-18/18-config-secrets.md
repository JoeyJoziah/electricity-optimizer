# Audit Report: Configuration & Secrets Management

**Date:** 2026-03-18
**Auditor:** Security Auditor (Opus 4.6)
**Scope:** Configuration files, secrets handling, environment variables, secret leakage
**Comparison Baseline:** Previous audit `/Users/devinmcgrath/projects/electricity-optimizer/.audit-2026-03-17/28-config-secrets.md`

---

## Executive Summary

**Files audited:** 18 configuration files, 34 GHA workflow files, all backend/frontend/worker source files (via pattern search across the entire repository).

The project maintains a **strong secrets management posture** with several well-implemented defenses: `.gitignore` correctly excludes all `.env*` files (line 44-50), `render.yaml` uses `sync: false` for all 42 secret env vars, `settings.py` has comprehensive production-grade validators for 8 critical secrets, the CF Worker uses `crypto.subtle.timingSafeEqual` for constant-time API key comparison, validation error handlers strip the `input` field to prevent credential echo, and the general exception handler sanitizes error details in production/staging.

**No hardcoded live secrets were found in any git-tracked source file.** All GHA workflows correctly use `${{ secrets.* }}` references.

However, the **P0 finding from the 2026-03-17 audit remains unremediated**: `backend/.env` still contains 4 live production-grade credentials on disk. Additionally, several medium-severity configuration hygiene issues persist from the prior audit, and this audit identifies 3 new findings not covered previously.

**Findings Summary:**

| Severity | Count | New vs Prior |
|----------|-------|--------------|
| P0 - Critical | 1 | Carried forward (unremediated) |
| P1 - High | 5 | 3 carried forward, 2 new |
| P2 - Medium | 8 | 4 carried forward, 4 new |
| P3 - Low | 5 | 3 carried forward, 2 new |
| **Total** | **19** | |

---

## P0 -- Critical

### P0-1: `backend/.env` contains live production-grade credentials on disk [UNREMEDIATED]

**File:** `backend/.env`, lines 10, 13, 18, 33
**Prior Finding:** P0-1 from 2026-03-17 audit -- identical finding.
**Status:** NOT FIXED. All 4 secrets confirmed still present on disk.

The file exists on disk (untracked by git per `.gitignore` line 44 matching `.env`) and contains four high-value secrets in plaintext:

1. **Line 10** -- `REDIS_URL` with embedded Upstash password (the connection string `rediss://default:AcP1AAIncDI...@holy-gull-50165.upstash.io:6379` embeds the full Redis password)
2. **Line 13** -- `JWT_SECRET` = 64-character hex key (used for internal API key validation/signing)
3. **Line 18** -- `INTERNAL_API_KEY` = 64-character hex key (authenticates service-to-service calls, GHA cron workflows, and CF Worker cron triggers)
4. **Line 33** -- `FIELD_ENCRYPTION_KEY` = 64-character hex key (AES-256-GCM key for encrypting utility account numbers in the database)

**Risk Assessment:**
- If this file is accidentally committed (e.g., via `git add .` or `git add backend/`), all four secrets enter permanent git history.
- The `.gitignore` pattern `.env` on line 44 catches `backend/.env` as a relative path -- but only because the pattern is not anchored with `/`. A future `.gitignore` refactor that anchors patterns (e.g., `/.env`) would silently unprotect `backend/.env`.
- Compromise of `FIELD_ENCRYPTION_KEY` allows decryption of all stored utility portal credentials in the database.
- Compromise of `INTERNAL_API_KEY` allows unauthorized invocation of all `/internal/*` endpoints (check-alerts, scrape-rates, dunning-cycle, GDPR deletion, etc.).
- The file also has `DEBUG=true` (line 3) alongside production credentials -- if accidentally sourced against a production environment, this enables detailed tracebacks in HTTP responses.

**Immediate Actions Required:**
1. **Rotate all four secrets** on Render and Upstash immediately. For `FIELD_ENCRYPTION_KEY`, this requires a migration to re-encrypt existing rows.
2. **Delete `backend/.env`** from disk. Developers should copy `backend/.env.example` and populate from 1Password.
3. **Run** `git log --all --oneline -- backend/.env` and `git fsck --lost-found` to verify the file was never committed or stashed.
4. **Add an explicit gitignore entry:** `backend/.env` (anchored) to protect against future `.gitignore` refactors.

---

## P1 -- High

### P1-1: `SecretsManager` (1Password integration) defined but unused at runtime [UNREMEDIATED]

**File:** `backend/config/secrets.py` (defined, 287 lines)
**Prior Finding:** P1-1 from 2026-03-17 audit.
**Status:** NOT FIXED. Confirmed via grep: `SecretsManager`, `get_secret`, and `require_secret` are imported only in `backend/tests/test_security.py` (lines 302, 315, 324, 334, 354). Zero production code imports exist.

The `SecretsManager` contains 34 `SECRET_MAPPINGS` (lines 47-104), a 1-hour TTL cache, and proper 1Password CLI integration. However, all secrets reach the running process exclusively via `settings.py` environment variable loading. The entire 1Password integration provides zero runtime security benefit.

**Actions:**
1. Either wire `SecretsManager` into the `Settings` pydantic model (e.g., as a `model_validator` fallback for production), OR explicitly document it as a developer reference tool only.

### P1-2: `JWT_SECRET` auto-generates ephemeral key when env var is absent [UNREMEDIATED]

**File:** `backend/config/settings.py`, lines 59-62

```python
jwt_secret: str = Field(
    default_factory=lambda: __import__("secrets").token_hex(32),
    validation_alias="JWT_SECRET",
)
```

**Prior Finding:** P1-3 from 2026-03-17 audit.

When `JWT_SECRET` is not set, a fresh random value is generated on each server restart. This silently invalidates all authentication tokens and sessions.

**Actions:**
1. Replace `default_factory` with an empty string default; move the ephemeral generation logic into the validator where it can log a clear warning.

### P1-3: `insecure_defaults` blocklist incomplete [UNREMEDIATED]

**File:** `backend/config/settings.py`, lines 243-248

The following values used in `.env.test`, `.env.example`, and CI workflows are NOT in the blocklist:
- `test_jwt_secret_key_change_in_production` (`.env.test` line 20, CI workflows)
- `test_secret_key_for_ci_minimum_32_chars` (`_backend-tests.yml` line 74, `e2e-tests.yml` line 113)
- `generate_a_secure_random_string_at_least_32_chars` (`.env.example` line 58)

**Actions:**
1. Add all three values to the `insecure_defaults` list.
2. Consider adding a heuristic: reject values containing common placeholder words in production.

### P1-4: Internal endpoint error handlers expose raw exception details [NEW]

**Files:** `backend/api/v1/internal/ml.py` (lines 75, 109, 136), `backend/api/v1/compliance.py` (lines 106, 135, 166, 222, 394), `backend/api/v1/webhooks.py` (line 90), `backend/api/v1/billing.py` (lines 170, 375), `backend/api/v1/referrals.py` (line 49)

Multiple API endpoints use `detail=str(e)` or `detail=f"... {str(e)}"` in `HTTPException` responses. These explicit `HTTPException` raises bypass the global handler and directly return raw exception messages to the client.

**Actions:**
1. Replace all `detail=str(e)` in production-facing endpoints with sanitized messages.

### P1-5: `OTEL_EXPORTER_OTLP_HEADERS` not validated or mapped in settings [UNREMEDIATED]

**Files:** `backend/.env.example` line 126, `render.yaml` line 80-81, `backend/config/settings.py`

`OTEL_EXPORTER_OTLP_HEADERS` holds a Base64-encoded `instanceId:token` credential for Grafana Cloud Tempo authentication. It is consumed directly by the OTel SDK from the environment, bypassing `settings.py` entirely.

**Actions:**
1. Add an `otel_otlp_headers` field to `Settings` with a `model_validator` that raises when `otel_enabled=True` but headers are empty in production.

---

## P2 -- Medium

### P2-1: `.gitleaks.toml` has minimal custom rules [UNREMEDIATED]
No custom rules for Upstash connection strings, Neon connection strings, Base64-encoded OTLP headers, or Composio API keys.

### P2-2: Root `.env.example` and `backend/.env.example` diverge on critical vars [UNREMEDIATED]
`DATA_RESIDENCY` defaults to `EU` in root but `US` in backend and `settings.py`.

### P2-3: `FIELD_ENCRYPTION_KEY` validator only enforces in production, not staging [UNREMEDIATED]
In staging, a missing or malformed key lets the service start without encryption.

### P2-4: `SecretsManager._get_from_1password()` logs raw stderr [UNREMEDIATED]
Raw `op read` stderr can include vault paths, leaking 1Password vault structure in logs.

### P2-5: `render.yaml` missing env vars that are set manually on Render [PARTIALLY FIXED]
`ALLOWED_REDIRECT_DOMAINS` still missing from `render.yaml`.

### P2-6: Cloudflare Account ID and Render Service ID hardcoded in committed files [NEW]
CF Account ID in `CLAUDE.md`, Render Service ID in `deploy-production.yml` line 194.

### P2-7: `backend/.env.example` references wrong 1Password vault name [PARTIALLY FIXED]
Vault name `"dd"` on line 17 does not match documented vault `"RateShift"`.

### P2-8: `lru_cache` on `SecretsManager.get_instance()` prevents test isolation [UNREMEDIATED]

---

## P3 -- Low

### P3-1: Root `.env.example` contains stale infrastructure variables [UNREMEDIATED]
### P3-2: `.env.example` includes `LOKI_*` developer tooling variables [UNREMEDIATED]
### P3-3: `GRAFANA_PASSWORD=admin` in on-disk `.env` and `.env.test` [UNREMEDIATED]
### P3-4: CI workflows use non-rotating test credentials in plaintext [NEW]
### P3-5: `DATA_RESIDENCY` default inconsistency between `.env.example` files [UNREMEDIATED]

---

## Positive Findings

1. **Validation Error Sanitization** — strips `input` and `ctx` fields in 422 responses
2. **Production Error Sanitization** — returns `"Internal server error"` in production/staging
3. **Swagger/ReDoc Disabled in Production**
4. **Timing-Safe API Key Comparison** in CF Worker
5. **Fail-Closed Internal Auth** — returns 503 when `INTERNAL_API_KEY` not configured
6. **CF Worker Secrets via `wrangler secret put`**
7. **Comprehensive Production Validators** — 8 validators for critical secrets
8. **INTERNAL_API_KEY != JWT_SECRET Validator**
9. **GHA Workflows Use Secrets References Exclusively**
10. **Render `sync: false` on All Secrets**
11. **Non-Root Docker User** in both Dockerfiles
12. **No Docker Build ARG Secrets**
13. **MCP Config Clean** — no API keys or tokens
14. **AES-256-GCM Encryption** with per-ciphertext random nonce
15. **`BETTER_AUTH_SECRET` Presence Validator Fixed**

## Statistics

| Severity | Count | New | Carried Forward | Remediated Since Last Audit |
|----------|-------|-----|-----------------|----------------------------|
| P0 | 1 | 0 | 1 | 0 |
| P1 | 5 | 2 | 3 | 0 |
| P2 | 8 | 4 | 4 | 2 partially fixed |
| P3 | 5 | 2 | 3 | 0 |
| **Total** | **19** | **8** | **11** | **2** |
