# Audit Report: Config & Secrets Management
**Date:** 2026-03-19
**Scope:** Environment variables, secret handling, config files, .gitignore
**Files Reviewed:**
- `.env`, `.env.test`, `.env.example`
- `backend/.env.example`, `frontend/.env.example`, `frontend/.env.local`
- `.gitignore`, `frontend/.gitignore`
- `backend/config/settings.py`, `backend/config/secrets.py`
- `render.yaml`, `workers/api-gateway/wrangler.toml`
- `docker-compose.yml`, `docker-compose.prod.yml`
- `.gitleaks.toml`, `.mcp.json`
- `.claude/settings.local.json` (gitignored, local-only)
- `.github/workflows/secret-scan.yml`, `deploy-production.yml`, `deploy-worker.yml`, `daily-data-pipeline.yml`, `db-backup.yml`, `ci.yml`, `e2e-tests.yml`, `_backend-tests.yml`, `utility-type-tests.yml`
- `backend/auth/password.py`, `backend/utils/encryption.py`, `backend/middleware/security_headers.py`
- `backend/gunicorn_config.py`, `backend/observability.py`
- `backend/services/portal_scraper_service.py`, `backend/api/v1/health.py`
- `frontend/next.config.js`, `CLAUDE.md`

***

## P0 -- Critical (Fix Immediately)

### P0-1: Production Neon Database Password in Local File (Local-Only Risk)

**File:** `.claude/settings.local.json`, lines 128, 238-239, 244, 254, 257-259

**Description:** The production Neon database password `npg_cKef3qdjJL0k` appears in cleartext at least 8 times in `.claude/settings.local.json`, embedded in approved Bash command patterns (PGPASSWORD assignments and DATABASE_URL connection strings with full credentials).

**Mitigating factor:** This file IS in `.gitignore` (line 129), so it is not tracked by git and will not be committed. However, the password is stored in cleartext on the local filesystem, and any local filesystem compromise, backup, or accidental copy exposes the production database.

**Remediation:**
1. Rotate the Neon database password immediately via the Neon console.
2. Update all downstream consumers (Render env vars, Vercel env vars, 1Password vault) with the new password.
3. Sanitize `.claude/settings.local.json` to remove the old password patterns.
4. Consider using `op://` references instead of raw credentials in local tool configurations.

---

### P0-2: OAuth Client IDs and Internal Identifiers in Committed CLAUDE.md

**File:** `CLAUDE.md`, line 135

**Description:** The project's `CLAUDE.md` file (committed to the repository) contains:
- GitHub OAuth Client ID: `Ov23liuYEgAM1Ay8tSWg`
- GitHub OAuth App ID: `3466397`
- 1Password item ID: `xfucwotbnak4smvc6y4gad34eq`
- Google OAuth Client ID: `268675977965-o21ia1l01f9bv37ivq34bbvno9qvb3pf.apps.googleusercontent.com`
- GCP project ID: `project-aa7b3d1e-97ac-4437-b55`

While OAuth client IDs are considered semi-public, committing them alongside 1Password vault item IDs and GCP project IDs provides attackers with infrastructure reconnaissance data.

**Remediation:**
1. Remove 1Password item IDs from CLAUDE.md. Reference secrets by vault name only.
2. Move OAuth Client IDs to documentation that is not committed to the public repository, or accept the risk given they are functionally public.

***

## P1 -- High (Fix This Sprint)

### P1-1: JWT `insecure_defaults` Blocklist Missing Known Test Values

**File:** `backend/config/settings.py`, lines 274-291

**Description:** The `validate_jwt_secret()` validator checks JWT_SECRET against an `insecure_defaults` list in production. However, the list does NOT include values known to be used in test/CI configurations:
- `test_jwt_secret_key_change_in_production`
- `test_secret_key_for_ci_minimum_32_chars`
- `generate_a_secure_random_string_at_least_32_chars`

If any of these CI/test values were accidentally deployed to production, the validator would NOT catch them.

**Remediation:** Add these three strings to the `insecure_defaults` list.

---

### P1-2: Infrastructure Identifiers Scattered Across Committed Documentation

**Files:** `CLAUDE.md`, `docs/DEPLOYMENT.md`, `docs/INFRASTRUCTURE.md`, `docs/REDEPLOYMENT_RUNBOOK.md`, `docs/launch/MONITORING_RUNBOOK.md`, `.github/workflows/deploy-production.yml`

**Description:** Internal infrastructure identifiers committed in multiple files:
- Cloudflare Account ID: `b41be0d03c76c0b2cc91efccdb7a10df` (15+ occurrences)
- Cloudflare Zone ID: `ac03dd28616da6d1c4b894c298c1da58` (5+ occurrences)
- CF KV Namespace ID: `6946d19ce8264f6fae4481d6ad8afcd1` (5+ occurrences)
- Render Service ID: `srv-d649uhur433s73d557cg` (20+ occurrences)
- Neon Project ID: `cold-rice-23455092` (6+ occurrences)
- Slack Workspace/Channel IDs, Composio connection ID
- Personal email: `Mcginvs@gmail.com`

**Remediation:** Move identifiers to GitHub secrets for workflows. Use placeholder patterns in documentation.

---

### P1-3: Missing `.env.staging` in `.gitignore`

**File:** `.gitignore`

**Description:** `.gitignore` covers `.env`, `.env.local`, `.env.test`, `.env.production`, but NOT `.env.staging`. Risk of accidental commit.

**Remediation:** Add `.env.staging` and `.env.staging.local` to `.gitignore`.

---

### P1-4: No Secret Rotation Policy Enforcement

**File:** `backend/config/secrets.py`, line 41

**Description:** SecretsManager has a 1-hour cache TTL but no automated rotation enforcement. No secret age tracking. `FIELD_ENCRYPTION_KEY` cannot be rotated without re-encrypting existing ciphertexts -- no migration tooling exists.

**Remediation:** Add GHA workflow for secret age monitoring. Build encryption key rotation migration script.

***

## P2 -- Medium (Fix Soon)

### P2-1: Gitleaks Allowlist Excludes All Markdown and Test Files

**File:** `.gitleaks.toml`, lines 54-77

**Description:** Gitleaks allowlist globally excludes all `*.md` files, all test files, all `.env.example` files, and `.audit-*` directories. Overly broad -- real secrets in markdown or test files would be silently ignored.

**Remediation:** Use rule-level allowlists instead of blanket path exclusions. At minimum, remove `*.md` from the global allowlist.

---

### P2-2: Hardcoded Render Service ID in Deploy Workflow

**File:** `.github/workflows/deploy-production.yml`, line 194

**Description:** Render service ID `srv-d649uhur433s73d557cg` hardcoded in workflow.

**Remediation:** Replace with `${{ secrets.RENDER_SERVICE_ID }}`.

---

### P2-3: CI Workflows Use Trivial Database Passwords

**Files:** `ci.yml`, `e2e-tests.yml`, `_backend-tests.yml`, `utility-type-tests.yml`

**Description:** CI workflows use `postgres` and `testpassword` for ephemeral test databases. Acceptable for CI service containers -- risk is negligible.

**Remediation:** No action required.

---

### P2-4: `docker-compose.yml` Enables DEBUG=true

**File:** `docker-compose.yml`, line 31

**Description:** Development compose sets `DEBUG=true`. Production compose correctly sets `DEBUG=false`.

**Remediation:** Add validator to `settings.py` that raises error if `DEBUG=true` when `ENVIRONMENT=production`.

---

### P2-5: Error Messages in API Logs May Contain Connection Strings

**Files:** `backend/api/v1/health.py`, `prices.py`, `billing.py`, `internal/data_pipeline.py`

**Description:** Multiple endpoints log `str(e)` in error handlers. Database connection errors often include full connection strings with embedded credentials. These appear in Render logs, Grafana traces, and Sentry.

**Remediation:** Add log sanitizer processor to structlog configuration that redacts patterns matching `postgresql://.*@`, `redis://.*@`, and known API key prefixes.

---

### P2-6: Neon Project ID in GHA Workflow Environment Block

**File:** `.github/workflows/db-backup.yml`, lines 16-17

**Description:** Neon project ID `cold-rice-23455092` hardcoded in workflow.

**Remediation:** Move to `${{ secrets.NEON_PROJECT_ID }}`.

***

## P3 -- Low / Housekeeping

### P3-1: `frontend/.gitignore` Is Minimal

**File:** `frontend/.gitignore` (only contains `.vercel`)

**Description:** Root `.gitignore` covers `.env.local` globally, but frontend's own `.gitignore` would lose that coverage if extracted as standalone repo.

**Remediation:** Add `.env.local` and `.env*.local` to `frontend/.gitignore`.

---

### P3-2: `.env.example` Contains Placeholder Values That Look Like Real Prefixes

**File:** `.env.example`

**Description:** Example values use realistic-looking prefixes (`fp_your_api_key_here`, `secret_your_notion_key`, `ghp_your_github_token`).

**Remediation:** Use clearly fake placeholders like `REPLACE_ME_flatpeak_key`.

---

### P3-3: Portal Scraper Docstring Uses `password="secret"` Example

**File:** `backend/services/portal_scraper_service.py`, line 205

**Remediation:** Use `password="<user_portal_password>"` in docstring example.

---

### P3-4: KV Namespace ID in `wrangler.toml`

**File:** `workers/api-gateway/wrangler.toml`, line 12

**Description:** KV namespace IDs are required by wrangler for binding resolution. This is the expected pattern per Cloudflare documentation. Accept the risk.

---

### P3-5: Personal Email Exposed in Documentation

**File:** `docs/DEPLOYMENT.md`, line 513

**Remediation:** Remove personal email from committed documentation.

***

## Summary

**Total Findings:** 15

| Severity | Count |
|----------|-------|
| P0 - Critical | 2 |
| P1 - High | 4 |
| P2 - Medium | 6 |
| P3 - Low | 5 |

**Positive Findings:**
1. No hardcoded production API keys, tokens, or passwords in any tracked source code files
2. Exceptionally thorough production validators in `settings.py`
3. Proper 1Password integration via SecretsManager
4. All `render.yaml` secrets use `sync: false`
5. AES-256-GCM encryption with per-ciphertext random nonces
6. Gitleaks secret scanning on every PR, push, and weekly
7. GHA workflows consistently use `${{ secrets.* }}` references
8. `db-backup.yml` properly masks passwords with `::add-mask::`
9. Docker compose files never contain literal credentials
10. Comprehensive `.gitignore` coverage

**Top 3 Recommendations:**
1. **Rotate the Neon database password** immediately -- exposed in cleartext in local `.claude/settings.local.json`
2. **Add missing test values to JWT `insecure_defaults` blocklist** to prevent CI/test secrets from being accepted in production
3. **Implement structured log sanitizer** to prevent database connection strings from appearing in Render logs, Grafana, and Sentry
