# RateShift Codebase Audit — Remediation Plan
**Date:** 2026-03-19
**Audit Scope:** Full codebase — 20 parallel agents, 514 findings
**Severity Distribution:** 57 P0, 113 P1, 165 P2, 143 P3

---

## Executive Summary

This remediation plan synthesizes 514 findings from a 20-agent parallel codebase audit. After deduplication (38 findings appear across multiple reports), the unique actionable items number **~476**. The plan organizes work into **10 sprints** ordered by risk severity and blast radius.

### Top 3 Most Dangerous Cross-Cutting Patterns

1. **Shared Mutable State in Async Code** — 8 findings across 3 reports (07, 14, 17). Race conditions with shared dicts in `asyncio.gather`, global `stripe.api_key`/`resend.api_key` mutation, fire-and-forget `asyncio.create_task` with no reference retention. Any of these can cause data corruption or silent failures under concurrent load.

2. **Webhook Event Loss Pipeline** — 4 findings in report 14. The idempotency-commit-before-process pattern permanently drops events on transient failures. Combined with missing handlers for `invoice.payment_succeeded`, `charge.refunded`, and `charge.dispute.created`, users can pay without receiving access or retain access after refund.

3. **Database Schema Drift** — 6 findings across reports 08, 12, 14. Ghost columns (`stripe_customer_id`, `subscription_tier`, `carbon_intensity`) referenced in ORM models but never created in migrations. Missing UNIQUE constraint on `stripe_customer_id`. FK constraint contradictions (`DeletionLogORM SET NULL` + `nullable=False`). OAuth tokens stored as plaintext TEXT while other credentials use BYTEA encryption.

### Top 10 Critical Findings (Ranked by Impact)

| Rank | ID | Finding | Report | Impact |
|------|-----|---------|--------|--------|
| 1 | 18-P0-1 | Production Neon DB password in cleartext in local file | Config & Secrets | Full database compromise if file leaked |
| 2 | 14-P0-1 | Webhook idempotency race — events permanently dropped | Payments & Billing | Users pay without receiving access |
| 3 | 12-P0-1 | Ghost columns — stripe_customer_id never created in migration | Database | ORM queries crash or return wrong data |
| 4 | 13-P0-2 | Unsafe pickle deserialization with bypassable hash | ML Pipeline | Remote code execution via crafted model files |
| 5 | 06-P0-1 | OAuth state replay — no timestamp expiry enforcement | API Routes | Account takeover via replayed OAuth callback |
| 6 | 14-P0-2 | No UNIQUE constraint on stripe_customer_id | Payments & Billing | Cross-user subscription corruption |
| 7 | 07-P0-1 | resend.api_key global mutation not concurrency-safe | Backend Services | Email sent from wrong account under load |
| 8 | 08-P0-1 | DeletionLogORM FK SET NULL + nullable=False crashes GDPR deletion | Repositories | GDPR compliance failure |
| 9 | 15-P0-2 | Cron handler sends empty API key when secret unset (fail-open) | CF Worker | Unauthenticated internal API calls |
| 10 | 04-P0-1 | XSS via Clarity dangerouslySetInnerHTML | Frontend Lib | Script injection via analytics |

---

## Sprint 1: Critical Secret Rotation & Credential Hygiene
**Priority:** IMMEDIATE (Day 1)
**Risk:** Database compromise, credential leakage
**Reports:** 18, 11, 06

### Tasks

1. **Rotate Neon database password** [18-P0-1]
   - Rotate via Neon console immediately
   - Update Render env vars, Vercel env vars, 1Password vault
   - Sanitize `.claude/settings.local.json` to remove old password patterns
   - Consider `op://` references instead of raw credentials in local tool configs

2. **Remove sensitive identifiers from committed CLAUDE.md** [18-P0-2]
   - Remove 1Password item IDs (reference by vault name only)
   - Evaluate whether OAuth Client IDs and GCP project IDs need redaction

3. **Add missing test values to JWT insecure_defaults blocklist** [18-P1-1]
   - Add `test_jwt_secret_key_change_in_production`, `test_secret_key_for_ci_minimum_32_chars`, `generate_a_secure_random_string_at_least_32_chars` to `backend/config/settings.py` insecure_defaults list

4. **Add `.env.staging` to .gitignore** [18-P1-3]

5. **Fix detect-rate-changes.yml broken auth** [20-P0-2]
   - The workflow passes `api-key` input that doesn't exist on `retry-curl` — auth is never sent

6. **Fix .dockerignore to exclude .env files** [20-P0-1]

**Estimated effort:** 2-3 hours

---

## Sprint 2: Webhook & Payment Data Integrity
**Priority:** CRITICAL (Days 1-2)
**Risk:** Revenue loss, subscription corruption
**Reports:** 14, 12

### Tasks

1. **Fix webhook idempotency race condition** [14-P0-1]
   - Wrap idempotency insert + business logic in single transaction
   - OR: delete idempotency record when processing fails (allow Stripe retry)
   - File: `backend/api/v1/billing.py:386-452`

2. **Add UNIQUE constraint on stripe_customer_id** [14-P0-2]
   - Migration: `ALTER TABLE users ADD CONSTRAINT uq_users_stripe_customer_id UNIQUE (stripe_customer_id);`
   - NULLs excluded from PostgreSQL unique checks (free-tier users unaffected)

3. **Add missing webhook handlers** [14-P1-1, 14-P1-2]
   - `invoice.payment_succeeded` — re-activate tier + clear dunning state
   - `charge.refunded` — downgrade or flag for review
   - `charge.dispute.created` — flag account immediately
   - File: `backend/services/stripe_service.py:394-506`

4. **Fix dunning escalation reversibility** [14-P1-4]
   - Link tier downgrade to Stripe subscription status (not local counter)
   - `invoice.payment_succeeded` handler restores tier

5. **Fix global stripe.api_key mutation** [14-P1-3]
   - Set key once at startup OR use per-request `stripe_client` (SDK v7+ pattern)
   - File: `backend/services/stripe_service.py:38`

6. **Externalize hardcoded MRR prices** [14-P1-5]
   - Replace `4.99`/`14.99` literals with config constants or Stripe Price API fetch
   - File: `backend/services/kpi_report_service.py:120`

**Estimated effort:** 1-2 days

---

## Sprint 3: Database Schema Integrity
**Priority:** CRITICAL (Days 2-3)
**Risk:** ORM crashes, data corruption, GDPR failure
**Reports:** 12, 08, 09

### Tasks

1. **Audit and create ghost columns** [12-P0-1, 12-P0-2]
   - Verify whether `stripe_customer_id`, `subscription_tier`, `carbon_intensity` exist in production
   - If ORM references them but they don't exist: create migration to add them
   - If they exist but aren't in migrations: add retroactive migration documentation

2. **Fix DeletionLogORM FK constraint** [08-P0-1, 09-P0-02]
   - `user_id` has `ondelete="SET NULL"` but `nullable=False` — crashes GDPR deletion
   - Either make `user_id` nullable OR change to `ondelete="CASCADE"`
   - Consider GDPR implications of each approach

3. **Fix ConsentRecordORM FK mismatch** [12-P0-3]
   - ORM defines CASCADE but live schema has SET NULL
   - Migration to align live schema with ORM definition

4. **Encrypt OAuth tokens at rest** [12-P0-4]
   - OAuth access/refresh tokens stored as plaintext TEXT
   - Migrate to BYTEA with AES-256-GCM encryption (same pattern as portal credentials)

5. **Fix GDPR deletion log transaction isolation** [09-P0-3]
   - Deletion log must persist in same transaction as deletion OR use a compensating mechanism
   - Current separate transaction can lose audit trail on crash

6. **Add missing updated_at triggers** [12-P1]
   - 15+ tables lack `updated_at` auto-update triggers

**Estimated effort:** 2-3 days

---

## Sprint 4: Auth & OAuth Hardening
**Priority:** HIGH (Days 3-4)
**Risk:** Account takeover, session hijacking
**Reports:** 06, 11

### Tasks

1. **Enforce OAuth state token expiry** [06-P0-1, 11-P0-1]
   - Add timestamp to OAuth state parameter
   - Reject states older than 10 minutes in callback handler
   - File: `backend/api/v1/auth.py`

2. **Add timestamp to email OAuth state** [11-P0-2]
   - Email OAuth flow has no timestamp validation at all
   - Same 10-minute expiry pattern

3. **Add login brute-force protection** [11-P1-1]
   - Rate limit login attempts per IP + username
   - Better Auth may have built-in support — check docs

4. **Reduce session cache TTL after ban** [11-P1-2]
   - 60s stale access window after user ban via session cache
   - Implement immediate cache invalidation on ban/suspension

5. **Strengthen password reset policy** [11-P1-3]
   - Currently validates length only — add complexity requirements

6. **Fix email OAuth callback ownership check** [11-P2]
   - Verify callback state belongs to requesting user

**Estimated effort:** 1-2 days

---

## Sprint 5: Async Concurrency Safety
**Priority:** HIGH (Days 4-5)
**Risk:** Data corruption, silent failures, resource leaks
**Reports:** 07, 17

### Tasks

1. **Fix shared mutable dict races** [17-P0-1, 17-P0-2, 07-P1]
   - `gas_rate_service`: shared `results` dict mutated in `asyncio.gather` — use sequential loop or per-task dicts
   - `weather_service`: same pattern — fix identically
   - File: `backend/services/gas_rate_service.py`, `weather_service.py`

2. **Fix resend.api_key global mutation** [07-P0-1]
   - `resend.api_key` set per-call, not concurrency-safe
   - Set once at startup or use per-request client

3. **Fix fire-and-forget asyncio.create_task** [07-P0-3, 17-P0-4]
   - Tasks with no reference can be garbage collected before completion
   - Store task references in a set, use `add_done_callback` to remove

4. **Fix notification asyncio.gather swallowing exceptions** [17-P0-3]
   - `return_exceptions=True` silently drops notification failures
   - Log exceptions, don't silently continue

5. **Clear structlog contextvars between requests** [09-P0-1]
   - trace_id/request_id leaking between requests
   - Add middleware to clear context at request start

**Estimated effort:** 1-2 days

---

## Sprint 6: API Input Validation & Edge Security
**Priority:** HIGH (Days 5-6)
**Risk:** Injection, cache poisoning, SSRF
**Reports:** 06, 15

### Tasks

1. **Add UUID type annotations on path parameters** [06-P0-2, 06-P0-3]
   - Change `connection_id: str` to `connection_id: uuid.UUID` across connections package (6 instances)
   - Same for `post_id`, `job_id`, `cca_id`, `program_id`
   - Gets free 422 validation from FastAPI

2. **Fix rate limit bypass key timing attack** [15-P0-1]
   - Replace `===` with `timingSafeEqual` in `rate-limiter.ts:26`
   - Extract shared utility from `internal-auth.ts`

3. **Fix cron handler fail-open auth** [15-P0-2]
   - When `INTERNAL_API_KEY` is undefined, abort rather than send empty string
   - File: `workers/api-gateway/src/handlers/scheduled.ts:54`

4. **Fix SQL LIKE wildcard injection** [06-P1-1]
   - Beta verify-code uses unescaped LIKE — escape `%`, `_`, `\` in user input

5. **Validate cache key query parameters** [15-P1-2]
   - Validate `region` against Region enum before including in cache key
   - Cap parameter value length (64 chars max)

6. **Add missing security headers to CF Worker** [15-P1-4, 15-P1-5]
   - Add `Permissions-Policy`, `Content-Security-Policy`, `X-XSS-Protection`
   - Add `preload` to HSTS directive

7. **Add Host header override in proxy** [15-P1-1]
   - Explicitly set `Host` to origin hostname
   - File: `workers/api-gateway/src/handlers/proxy.ts:17-27`

8. **Make price-sync endpoint internal-only** [15-P2-6]
   - Add `requireApiKey: true` to `/api/v1/prices/refresh` route config

**Estimated effort:** 2 days

---

## Sprint 7: ML Pipeline Safety
**Priority:** HIGH (Days 6-7)
**Risk:** Remote code execution, model corruption, training failures
**Reports:** 13

### Tasks

1. **Fix torch.save/torch.load incompatibility** [13-P0-1]
   - Trainer saves full model; predictor loads with `weights_only=True`
   - Align serialization: either both use `state_dict()` or both use full model

2. **Replace unsafe pickle deserialization** [13-P0-2]
   - Hash verification is bypassable — attacker can recalculate hash
   - Use `safetensors` format instead of pickle
   - OR: use cryptographic signing (HMAC) with a secret key, not just content hash

3. **Fix deprecated Optuna API** [13-P0-3]
   - Will crash on Optuna v4+ — update API calls to current interface

4. **Fix broken import build_model_from_params** [13-P0-4]
   - Non-existent function referenced — identify correct import path

5. **Fix data leakage in CNNLSTMTrainer** [13-P1-1]
   - Scaler fit on full dataset before train/test split
   - Fit scaler only on training data

6. **Fix shuffle=True on time series DataLoader** [13-P1-2]
   - Time series data must maintain temporal ordering
   - Set `shuffle=False`

7. **Fix LightGBM type mismatch on reload** [13-P1-3]
   - Saved model expects different feature types than inference provides

**Estimated effort:** 2-3 days

---

## Sprint 8: Frontend Security & UX
**Priority:** MEDIUM (Days 7-8)
**Risk:** XSS, invisible UI states, auth bypass
**Reports:** 01, 03, 04, 05

### Tasks

1. **Fix XSS via Clarity dangerouslySetInnerHTML** [04-P0-1]
   - Remove or sanitize Clarity script injection
   - Use proper Clarity SDK integration

2. **Fix handleResponse crash on 204 No Content** [04-P0-3]
   - `response.json()` throws on empty body — check `content-length` first

3. **Define bg-muted/text-muted-foreground in Tailwind** [05-P0-1, 01-P0]
   - Used in 15+ locations but never defined — invisible skeleton states
   - Add to `tailwind.config.ts` theme extend section

4. **Fix auth pages nested in app layout** [03-P0-1]
   - Auth pages render with Sidebar — should use standalone layout

5. **Add layout-level auth guard** [03-P0-2]
   - No middleware/layout gate for authenticated routes

6. **Fix 401 handler bypass of redirect-loop protection** [04-P0-2]
   - Agent SSE 401 handler bypasses redirect-loop protection

7. **Replace raw blue-* with primary-* tokens on landing page** [05-P1-1]
   - 19+ instances of off-brand raw Tailwind colors

**Estimated effort:** 2 days

---

## Sprint 9: Dependency Cleanup & Build Hygiene
**Priority:** MEDIUM (Days 8-9)
**Risk:** Supply chain, reproducibility, version conflicts
**Reports:** 10, 20

### Tasks

1. **Regenerate or delete requirements.lock** [10-P0-1]
   - Massively stale (sentry v1 vs v2, stripe v7 vs v14, numpy 1.x vs 2.x)
   - If no build uses it: delete. If builds consume it: regenerate from requirements.txt

2. **Declare cryptography as direct dependency** [10-P0-2]
   - Add `cryptography>=44.0,<47.0` to backend/requirements.txt
   - Currently transitive via PyJWT[crypto] — fragile

3. **Consolidate ML requirements files** [10-P0-3]
   - Three files with conflicting constraints (Keras 2 vs 3)
   - Keep `ml/requirements-ml.txt` as canonical, archive/delete others

4. **Fix pytest-asyncio phantom version** [10-P1-1]
   - `pytest-asyncio==1.3.0` doesn't exist — change to `>=0.24.0,<1.0`

5. **Move @testing-library/dom to devDependencies** [10-P1-2]

6. **Add server-only guard to email send.ts** [10-P1-5]
   - `import "server-only"` to prevent client-side bundling of SMTP credentials

7. **Add Dependabot coverage for workers/api-gateway** [10-P1-6]

8. **Fix ML Dockerfile Python version divergence** [10-P2-7, 20-P1]
   - ML uses 3.11, backend uses 3.12 — document rationale or align

**Estimated effort:** 1-2 days

---

## Sprint 10: Test Quality & Observability
**Priority:** MEDIUM (Days 9-10)
**Risk:** False confidence, missed regressions
**Reports:** 16, 19

### Tasks

1. **Fix tests that silently pass when server unavailable** [16-P0-1]
   - Performance tests should fail explicitly when no server

2. **Fix broad status-code assertions** [16-P0-2]
   - Replace `assert status in [200, 404, 422, 500]` with exact expected status

3. **Fix SQL injection tests accepting 500** [16-P0-3]
   - A 500 response to SQL injection means the payload reached the database
   - Assert 400 or 422 specifically

4. **Implement structured log sanitizer** [18-P2-5]
   - Redact patterns matching `postgresql://.*@`, `redis://.*@`, and API key prefixes
   - Add as structlog processor

5. **Fix unbounded forecast query** [19-P1-1]
   - No LIMIT clause — add sensible limit + pagination

6. **Fix sync Redis+DB in EnsemblePredictor constructor** [19-P1-3]
   - Blocking I/O in constructor — use lazy initialization or async factory

7. **Add GDPR-compliant IP anonymization to CF Worker logs** [15-P2-8]
   - Hash or truncate IP addresses before logging

**Estimated effort:** 2 days

---

## Deferred Items (P2/P3 Backlog)

### Performance Optimization (19 findings)
- Serial alert dispatch loop → parallel dispatch [19-P1-4]
- Full vector table loaded via fetchall() → streaming/pagination [19-P1-2]
- Frontend re-render cascades from SidebarProvider [02-P0-2]
- Cache stampede single-retry pattern [08-P1-4]

### Frontend Polish (45+ findings)
- Dark mode support (config exists, no implementation) [05-P1-2]
- Shared select component primitive [05-P1-3]
- Off-brand cyan focus rings on water components [05-P1-4]
- Client components exporting server-only dynamic config [03-P0-3]

### Infrastructure Hardening (35+ findings)
- Missing CI permissions on 3 workflows [20-P1-1]
- Procfile/Dockerfile bypass gunicorn config [20-P1-2]
- Prod compose includes local Postgres conflicting with Neon [20-P1-7]
- Data-health-check.yml fragile secret handling [20-P0-3]

### Additional Auth/Security (15+ findings)
- In-memory rate limiter unbounded under load [09-P1-3]
- CORS missing expose_headers [09-P1-1]
- anonymize_ip() doesn't handle IPv6 [09-P1-4]
- Encryption without AAD [09-P1-6]
- Bot detection trivially bypassable [15-P2-1]

### Dependency Housekeeping (18+ findings)
- Remove unused bcrypt, PyJWT from production deps [10-P1-3]
- Align wrangler versions (v3 vs v4) [10-P1-4]
- Remove unused heavy ML packages (PyTorch/transformers/wandb/shap/lime) [10-P2-4]
- Standardize documentation system (Sphinx vs MkDocs) [10-P3-6]
- ESLint 9 upgrade [10-P2-8]
- Plan Node 22 migration [10-P3-10]

---

## Duplicate Finding Cross-Reference

These findings appear in multiple reports (counted once in sprint priorities):

| Finding | Reports |
|---------|---------|
| OAuth state no expiry | 06-P0-1, 11-P0-1 |
| DeletionLogORM FK contradiction | 08-P0-1, 09-P0-2 |
| Shared mutable dict race (gas_rate) | 07-P1, 17-P0-1 |
| Shared mutable dict race (weather) | 07-P1, 17-P0-2 |
| asyncio.create_task fire-and-forget | 07-P0-3, 17-P0-4 |
| Global stripe.api_key mutation | 14-P1-3, 07-P0-1 (same pattern) |
| Agent TOCTOU rate limit | 07-P0-4, 17-P1-2 |
| SSRF allowlist not enforced | 07-P1, 17-P1-3 |
| Fail-open moderation | 07-P1, 17-P1-1 |
| KV namespace ID committed | 15-P3-6, 18-P3-4 |
| Infrastructure IDs scattered | 18-P1-2, 20-P2 (multiple) |
| bg-muted undefined | 05-P0-1, 01-P0 |

---

## Summary Metrics

| Sprint | Priority | Findings Covered | Est. Effort |
|--------|----------|-----------------|-------------|
| 1 - Secret Rotation | IMMEDIATE | 6 | 2-3 hours |
| 2 - Webhook & Payments | CRITICAL | 6 | 1-2 days |
| 3 - DB Schema Integrity | CRITICAL | 6 | 2-3 days |
| 4 - Auth & OAuth | HIGH | 6 | 1-2 days |
| 5 - Async Concurrency | HIGH | 5 | 1-2 days |
| 6 - API & Edge Security | HIGH | 8 | 2 days |
| 7 - ML Pipeline | HIGH | 7 | 2-3 days |
| 8 - Frontend Security | MEDIUM | 7 | 2 days |
| 9 - Dependencies | MEDIUM | 8 | 1-2 days |
| 10 - Test & Observability | MEDIUM | 7 | 2 days |
| **Deferred Backlog** | LOW | ~450 | — |
| **Total Covered in Sprints** | — | **~66 critical** | **~15-20 days** |

---

## Recommended First 5 Tasks

1. **Rotate Neon database password** — exposed in cleartext, immediate risk
2. **Fix webhook idempotency race** — users can pay without receiving access
3. **Add UNIQUE constraint on stripe_customer_id** — prevents cross-user corruption
4. **Replace unsafe pickle deserialization** — remote code execution vector
5. **Enforce OAuth state token expiry** — prevents account takeover via replay

---

## Architecture Strengths Identified

Across all 20 reports, auditors noted these positive patterns:
- No hardcoded production API keys in tracked source code
- Webhook signature verification correctly uses Stripe SDK
- Docker images pinned by sha256 digest across all Dockerfiles
- Comprehensive production validators in settings.py
- AES-256-GCM encryption with per-ciphertext random nonces
- Gitleaks secret scanning on every PR + weekly
- Free-tier alert limit uses SELECT...FOR UPDATE (race-safe)
- Frontend checkout constructs redirect URLs server-side
- Internal auth uses fail-closed pattern with constant-time comparison
- CI pipeline includes both pip-audit and npm audit gates
- Subscription status changes preserve tier for non-terminal states
- Constant-time comparison (hmac.compare_digest) for API keys
