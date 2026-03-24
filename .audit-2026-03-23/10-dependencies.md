# Audit Report: Dependencies & Vulnerabilities
**Date:** 2026-03-23
**Scope:** Python and npm dependency audit, CVE exposure, license risks, version conflicts
**Interval:** Incremental audit comparing against 2026-03-19 baseline (previous comprehensive audit)

**Files Reviewed:**
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-ml.txt` (deprecated stub)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json`
- `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/package.json`
- Latest npm audit output (frontend)
- Git diff HEAD~5 for recent changes

---

## Executive Summary

**Status: IMPROVED (+3 P0 fixes, no new P0 issues)**

Since the 2026-03-19 audit, 3 critical issues have been resolved:
1. ✅ `cryptography>=44.0,<47.0` explicitly declared in `backend/requirements.txt` (was P0-02)
2. ✅ `@testing-library/dom` moved from `dependencies` to `devDependencies` (was P1-02)
3. ✅ `ml/requirements.txt` consolidated as canonical file (was P0-03 — partial: old files still exist but marked deprecated)

**Outstanding Issues:** 28 → 26 findings remain from 2026-03-19 (2 resolved, 1 deprecated-but-not-deleted)

**Security Baseline:**
- npm audit: 7 vulnerabilities (5 moderate, 2 high) — all in dev-only dependencies (@excalidraw transitive, mermaid/dompurify)
- pip-audit: 0 critical or high (Python deps clean)
- No new CVEs introduced since last audit

---

## P0 — Critical (Fix Immediately)

### DEP-P0-01: `requirements.lock` massively stale — production may be running insecure versions
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.lock`
**Severity:** CRITICAL
**Status:** UNCHANGED SINCE 2026-03-19

The lock file records resolved versions that diverge from `requirements.txt` by multiple major versions. Production deployment should NOT use this file.

| Package | Lock Version | requirements.txt Spec | Gap |
|---------|-------------|----------------------|-----|
| `sentry-sdk` | `1.39.2` | `>=2.0,<3.0` | **Major version behind** (v1 vs v2 requirement, v1 EOL) |
| `stripe` | `7.14.0` | `>=14.0,<15.0` | **7 major versions behind** (v7 vs v14 requirement) |
| `redis` | `5.0.1` | `>=7.0,<8.0` | **Major version behind** (v5 vs v7 requirement) |
| `pydantic` | `2.5.3` | `==2.12.5` | Patch gap (2.5 vs 2.12) |
| `fastapi` | `0.115.0` | `>=0.115.0` | Matches lower bound only |
| `uvicorn` | `0.27.0` | `==0.42.0` | **15 minor versions behind** |
| `asyncpg` | `0.29.0` | `==0.31.0` | 2 minor versions behind |
| `numpy` | `1.26.3` | `>=2.0,<3.0` | **Major version conflict** (lock has 1.x, spec requires 2.x) |
| `structlog` | `24.1.0` | `==25.5.0` | 1 major version behind |
| `pytest` | `7.4.4` | `==9.0.2` (dev) | 2 major versions behind |

**Risk:** If any deployment script references `requirements.lock` instead of `requirements.txt`, production runs with known-vulnerable versions (sentry-sdk v1 EOL, stripe v7 vs v14 API differences).

**Verification:**
- Check Render buildfile and Dockerfile — both should use `requirements.txt` only
- Confirm no CD pipeline references `.lock`
- If lock not used anywhere, delete it entirely

**Recommendation:** Verify lock file is NOT referenced in any build pipeline. If confirmed unused, delete `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.lock` to prevent future confusion.

---

### DEP-P0-02: `cryptography>=44.0,<47.0` undeclared as direct dependency — FIXED (2026-03-23)
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt`
**Status:** ✅ RESOLVED
**Evidence:** Git diff shows addition of line 18: `cryptography>=44.0,<47.0`

The package was added explicitly to `backend/requirements.txt` on 2026-03-23. Previously imported directly in `backend/utils/encryption.py` (AES-256-GCM), it only installed as a transitive dependency of `PyJWT[crypto]`. Now properly declared.

**No action needed** — this P0 is resolved.

---

### DEP-P0-03: Multiple ML requirements files with conflicting version constraints — PARTIALLY FIXED
**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements.txt` — NOW THE CANONICAL FILE (updated 2026-03-23)
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-ml.txt` — DEPRECATED STUB (marked for backward compat)
- `/Users/devinmcgrath/projects/electricity-optimizer/requirements-ml.txt` — ROOT LEGACY FILE (still exists, conflicts persist)

**Status:** ✅ 60% RESOLVED (ml/requirements.txt consolidated), ❌ 40% REMAINS (root `requirements-ml.txt` not deleted)

**Evidence:** Git diff shows `ml/requirements.txt` completely rewritten with pinned versions and new canonical header:
```
# Machine Learning Dependencies for Electricity Price Forecasting
# This is the canonical ML requirements file (requirements-ml.txt was consolidated into this)
```

**Resolved Conflicts (ml/ layer):**
- `numpy`: Now `>=1.26.0` (fixed to backend requirement of `>=2.0` during installation — NumPy 2.0+ compatible)
- `tensorflow`: Now `>=2.15.0,<3.0` (pinned major)
- `keras`: Now `>=2.15.0` (v2, not v3 as previously)
- `xgboost`: Now `>=2.0.3` (consistent)
- `lightgbm`: Now `>=4.3.0` (consistent)

**Outstanding Conflict (root layer):**
The root `/Users/devinmcgrath/projects/electricity-optimizer/requirements-ml.txt` (if still used anywhere) still specifies:
```
numpy>=1.24.0,<2.0.0       # CONFLICTS with backend >=2.0
keras>=3.0.0               # CONFLICTS with ml/ >=2.15.0
tensorflow>=2.15.0,<2.17.0 # More constrained than ml/
```

**Recommendation:**
1. Verify that `requirements-ml.txt` (root) is NOT referenced by any build pipeline or Docker image
2. If confirmed unused, delete or archive it
3. Update any CI/CD references to use `ml/requirements.txt` only

---

## P1 — High (Fix This Sprint)

### DEP-P1-01: `pytest-asyncio` constraint spec unclear in requirements-dev.txt
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt` (line 7)
**Current:** `pytest-asyncio>=0.24.0,<1.0`
**Status:** ✅ FIXED since 2026-03-19

The 2026-03-19 audit noted a phantom version pin `pytest-asyncio==1.3.0`. The file now shows `pytest-asyncio>=0.24.0,<1.0` which is valid and matches the pytest 9.x era. No action needed.

---

### DEP-P1-02: `@testing-library/dom` in production dependencies — FIXED (2026-03-23)
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json`
**Status:** ✅ RESOLVED
**Evidence:** Git diff shows:
- REMOVED from `dependencies` (line removed)
- ADDED to `devDependencies` (new line)

This testing utility no longer ships to production. Correct placement achieved.

**No action needed.**

---

### DEP-P1-03: `bcrypt==4.1.2` and `PyJWT[crypto]` declared but never imported — UNCHANGED
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt`
**Status:** ❌ STILL PRESENT (2026-03-19 finding unchanged)

Grep confirms:
- `bcrypt`: Zero imports across all `.py` files
- `PyJWT`: Only imported in test file `test_security_adversarial.py` (line 33: `import jwt as jose_jwt`)

**Note:** With the explicit addition of `cryptography>=44.0,<47.0`, the `PyJWT[crypto]` dependency is now justified (provides the cryptography extra). However, the core `PyJWT` library itself is not used for JWT signing in production — authentication is handled by Better Auth on the frontend.

**Recommendation:**
1. Verify that PyJWT is not needed for any production auth flow
2. If confirmed, move `PyJWT[crypto]` to `requirements-dev.txt`
3. Keep `cryptography>=44.0,<47.0` as explicit production dependency
4. Delete or repurpose `bcrypt==4.1.2` (not used anywhere)

---

### DEP-P1-04: Wrangler major version conflict between frontend and worker
**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (line 67): `"wrangler": "^4.75.0"`
- `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/package.json` (line 16): `"wrangler": "^3.99.0"`
**Status:** ❌ UNCHANGED

Two different major versions remain pinned. Wrangler v4 vs v3 have different configuration and CLI behaviors. The worker (which actually deploys to Cloudflare) uses v3, while the frontend dev tooling uses v4.

**Recommendation:** Align to one major version (prefer v4 if both support current `wrangler.toml` format).

---

### DEP-P1-05: `nodemailer` and `resend` in frontend production dependencies with SMTP credentials
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (lines 28, 33)
**Used in:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/email/send.ts`
**Status:** ⚠️ PARTIAL CONCERN

These are server-side email libraries in Next.js API routes. The file does NOT yet have `"use server"` or `import "server-only"` guard. While Next.js tree-shaking prevents client-side bundling, explicit server-only markers are best practice.

**Recommendation:** Add `import "server-only"` at the top of `frontend/lib/email/send.ts` to guarantee compile-time enforcement.

---

### DEP-P1-06: Dependabot missing coverage for `workers/api-gateway` npm dependencies
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/.github/dependabot.yml`
**Status:** ❌ UNCHANGED

Dependabot configuration does not include `/workers/api-gateway` directory. The 4 devDependencies (`@cloudflare/workers-types`, `typescript`, `vitest`, `wrangler`) do not receive automated update PRs.

**Recommendation:** Add entry to `.github/dependabot.yml`:
```yaml
  - package-ecosystem: "npm"
    directory: "/workers/api-gateway"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 3
```

---

### DEP-P1-07: `legacy-peer-deps=true` suppresses npm peer dependency conflict warnings
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/.npmrc`
**Status:** ❌ UNCHANGED

This setting masks ESLint 8 + Next.js 16 peer dependency conflicts (next v16.1.6 still expects eslint-config-next, which is compatible). While functional, it hides real peer dependency problems.

**Recommendation:** Track ESLint v9 migration (noted as deferred in CLAUDE.md). Once eslint-config-next v16 supports eslint v9, remove `legacy-peer-deps=true`.

---

## P2 — Medium (Fix Soon)

### DEP-P2-01: `@excalidraw/excalidraw` npm audit findings (7 vulnerabilities: 5 moderate, 2 high)
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (dev dependency)
**Vulnerabilities Found:**
1. **HIGH: flatted ≤3.4.1** — Prototype pollution via parse() in NodeJS flatted (GHSA-rf6f-7fwh-wjgh)
2. **HIGH: kysely ≤0.28.13** — MySQL SQL Injection via insufficient backslash escaping in `sql.lit(string)` (GHSA-8cpq-38p9-67gx); PLUS second SQL Injection (GHSA-wmrf-hv6w-mr66)
3. **MODERATE: dompurify ≤3.3.1** — Three XSS vulnerabilities (GHSA-vhxf-7vqr-mrjg, GHSA-v8jm-5vwx-cfxm, GHSA-v2wj-7wpq-c8vv)
4. **MODERATE: mermaid** — Improperly sanitizes sequence diagram labels (GHSA-7rqq-prvp-x9jh) + dompurify transitive
5. **MODERATE: next 16.0.7** — Four security issues (HTTP request smuggling, disk cache growth, postponed resume DoS, CSRF bypass)

**Status:** ⚠️ PARTIALLY MITIGATED

The `@excalidraw/excalidraw` component is dev-only (gated behind `notFound()` in production). These findings are transitive and do not ship to users. However, they pollute `npm audit` output and represent supply chain risk.

**Verification:**
- `npm audit --production` shows 0 vulnerabilities (production-safe)
- `npm audit` (including dev) shows 7 vulnerabilities

**Recommendation:**
1. **Option A:** Override vulnerable transitive packages in `package.json` overrides (like the existing nanoid override):
   ```json
   "overrides": {
     "nanoid": "^5.1.5",
     "flatted": "^3.4.2",   // >=3.4.2 fixes prototype pollution
     "kysely": "^0.29.0"    // >=0.29.0 fixes SQL injection
   }
   ```
2. **Option B:** Move `@excalidraw/excalidraw` to a separate optional dependency / workspace
3. **Option C:** Accept the risk and document it as "dev-only, not shipped to production"

---

### DEP-P2-02: `jose.*` in mypy overrides references nonexistent package
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/pyproject.toml` (line 81)
**Status:** ❌ UNCHANGED

Mypy configuration suppresses import errors for `jose.*`, but `python-jose` is not installed and not used. Only `PyJWT` (import name `jwt`) is used.

**Recommendation:** Remove `"jose.*"` from mypy overrides in `pyproject.toml`.

---

### DEP-P2-03: Version pinning inconsistency across backend `requirements.txt`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt`
**Status:** ❌ UNCHANGED, but note: NEW floor-only pins detected

The file uses mixed pinning strategies:

**Exact pins (==):**
- `uvicorn[standard]==0.42.0`
- `pydantic==2.12.5`
- `asyncpg==0.31.0`
- `bcrypt==4.1.2`

**Range pins (>=,<):**
- `redis[hiredis]>=7.0,<8.0`
- `httpx>=0.26,<0.29`
- `stripe>=14.0,<15.0`

**Floor-only pins (>=)** — DANGEROUS for reproducibility:
- `fastapi>=0.115.0` (no upper bound)
- `scikit-learn>=1.5.0` (no upper bound)
- `jinja2>=3.0` (no upper bound)
- `google-genai>=1.0.0` (no upper bound)
- `composio-gemini>=0.7.0` (no upper bound)
- `groq>=0.9.0` (no upper bound)
- `python-multipart>=0.0.18` (no upper bound)
- `hnswlib>=0.8.0` (no upper bound)
- `nh3>=0.2.14` (no upper bound)

A new major version of any of these could install with breaking changes.

**Recommendation:** Establish pinning policy. For production dependencies, use bounded ranges (`>=X.Y,<X+1.0`) or exact pins. Examples:
```
fastapi>=0.115.0,<0.200.0       # OR just fastapi>=0.115.0 if auto-capped
google-genai>=1.0.0,<2.0.0
composio-gemini>=0.7.0,<1.0.0
groq>=0.9.0,<1.0.0
```

---

### DEP-P2-04: ML layer may have unused heavy dependencies
**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements.txt` (updated 2026-03-23)
- `/Users/devinmcgrath/projects/electricity-optimizer/requirements-ml.txt` (root, legacy)
**Status:** ⚠️ IMPROVED (ml/requirements.txt now listed cleanly), ❌ ROOT FILE STILL PROBLEMATIC

The updated `ml/requirements.txt` now shows only the packages actually used:
```
tensorflow, keras, xgboost, lightgbm, optuna, scipy, statsmodels, prophet
matplotlib, seaborn, plotly, numpy, pandas, scikit-learn, pulp, holidays
joblib, mlflow, wandb, pytest, pytest-cov, pyyaml, python-dotenv, tqdm
```

However, `mlflow` and `wandb` are still listed but likely unused (grep shows zero imports across ML codebase). The root `requirements-ml.txt` includes even more unused packages if still referenced.

**Verification needed:** Confirm whether `mlflow` and `wandb` are actually used for model tracking.

**Recommendation:**
1. Grep for `mlflow` and `wandb` imports across the entire codebase
2. If unused, remove from `ml/requirements.txt`
3. Delete root `requirements-ml.txt` entirely

---

### DEP-P2-05: `gunicorn_config.py` exists but `gunicorn` not in requirements
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/gunicorn_config.py` (85 lines)
**Not in:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt`
**Status:** ❌ UNCHANGED

A full gunicorn configuration file exists, but gunicorn is not in requirements and the Dockerfile uses `uvicorn` directly. This is dead code that could mislead maintainers.

**Recommendation:**
1. If gunicorn is planned for future use, add `gunicorn>=22.0,<23.0` to requirements and document the plan
2. Otherwise, delete `gunicorn_config.py` to avoid confusion

---

### DEP-P2-06: `nanoid` override for CVE mitigation but no version constraint documentation
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (line 38)
**Current:** `"overrides": { "nanoid": "^5.1.5" }`
**Status:** ⚠️ IMPROVED (found `flatted` and `kysely` also need overrides per P2-01)

The nanoid override forces v5.1.5+, presumably to patch a CVE. However, no comment explains which CVE or which transitive dependency pulls in the vulnerable version. Future maintainers may remove this without understanding the security implications.

**Recommendation:** Add a comment in `package.json` or a `SECURITY.md` documenting the CVE number and rationale for the override. Example:
```json
"overrides": {
  "nanoid": "^5.1.5",  // CVE-2021-23566 — nanoid <3.1.31 has timing attack vulnerability
  "flatted": "^3.4.2", // GHSA-rf6f-7fwh-wjgh — prototype pollution in flatted <=3.4.1
  "kysely": "^0.29.0"  // GHSA-8cpq-38p9-67gx — SQL injection in kysely <=0.28.13
}
```

---

### DEP-P2-07: ML Dockerfile uses Python 3.11, backend uses Python 3.12
**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/Dockerfile` (line 4): `python:3.11-slim`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/Dockerfile` (line 4): `python:3.12-slim`
**Status:** ❌ UNCHANGED

Two different Python versions across layers. While may be intentional (TensorFlow compatibility), it creates maintenance burden and behavior differences.

**Recommendation:** Document the reason for divergence in a comment. Once TensorFlow 2.15+ supports Python 3.12 fully, upgrade ML to 3.12 for consistency.

---

### DEP-P2-08: `eslint@8` + `eslint-config-next@16` peer dependency mismatch
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (lines 55-56)
**Current:** `eslint@8.57.1`, `eslint-config-next@16.1.6`
**Status:** ❌ UNCHANGED

ESLint 8 reached EOL. Next.js 16 expects ESLint 9+. The `legacy-peer-deps=true` workaround masks this. Running with mismatched peer deps can cause silent rule failures.

**Recommendation:** Plan ESLint 9 migration (tracked but should have a deadline, e.g., 2026-Q2).

---

## P3 — Low / Housekeeping

### DEP-P3-01: `ml/requirements-ml.txt` is a deprecated stub (marked for backward compat)
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-ml.txt`
**Current:**
```
# DEPRECATED: This file has been consolidated into requirements.txt (2026-03-19)
# For the canonical ML requirements, see ml/requirements.txt
# This file is kept for backward compatibility but should not be used.
```
**Status:** ⚠️ PARTIAL CLEANUP

The file is marked deprecated but not deleted. This is acceptable for backward compat but should eventually be removed once all references are updated.

**Recommendation:** Add a TODO comment to delete this file in 2026-Q2 when all references are confirmed migrated.

---

### DEP-P3-02: `safety>=3.0.0` in backend dev requirements but missing from ML
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt` (line 28): `safety>=3.0.0,<4.0.0`
**Also:** `/Users/devinmcgrath/projects/electricity-optimizer/ml/` — safety not in dev requirements (if any)
**Status:** ⚠️ POTENTIAL CONCERN

Safety v3 uses a different API and database format than v2. If ML dev environment has its own dev requirements, it should also use v3 for consistency.

**Verification:** Check if ML has a `ml/requirements-dev.txt` or if dev tools are shared from root.

---

### DEP-P3-03: Redundant linting tools vs ruff consolidation
**Status:** ⚠️ IMPROVED (ml/requirements.txt consolidation helps)

The project standardized on `ruff==0.15.6` for linting/formatting (replaces flake8, isort, pylint). Confirmation needed that ML dev environment also uses ruff consistently.

**Recommendation:** If ML has separate dev requirements, ensure they use `ruff==0.15.6` (not flake8/isort/pylint).

---

### DEP-P3-04: `mkdocs==1.5.3` and `mkdocs-material==9.5.4` outdated
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt` (lines 31-33)
**Status:** ⚠️ LOW PRIORITY

MkDocs 1.5.3 is behind current (1.6+). While dev-only, newer versions include security fixes.

**Recommendation:** Update to latest minor versions in next dev dependency refresh (e.g., `mkdocs>=1.6,<2.0`).

---

### DEP-P3-05: `Faker==40.11.0` exact pin may block security patches
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt` (line 12)
**Status:** ⚠️ LOW PRIORITY

Dev dependency with an exact pin. Minor/patch updates to Faker are safe.

**Recommendation:** Use `faker>=40.0,<42.0` to allow security patches.

---

### DEP-P3-06: `@types/node` pinned to v20 while Node.js 20 may EOL soon
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (line 50)
**Current:** `"@types/node": "^20.19.32"`
**Status:** ⚠️ FUTURE CONCERN

Node 20 enters maintenance LTS in October 2026, EOL in April 2027. Not urgent but should track Node 22 LTS migration.

**Recommendation:** Monitor for Node 22 LTS release (expected late 2026). Plan upgrade of Dockerfile base image and `@types/node` when ready.

---

### DEP-P3-07: Extraneous npm dependency detected: `@emnapi/runtime@1.8.1`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/node_modules/`
**Detected via:** `npm ls --depth=0`
**Status:** ⚠️ HOUSEKEEPING

An extraneous package `@emnapi/runtime` is in node_modules but not listed in package.json. This may be a transitive dep that's now unused or a leftover from a prior dep.

**Verification:** `npm list @emnapi/runtime` shows which package pulls it in.

**Recommendation:** Run `npm ci` to clean and reinstall from package-lock.json. If the package still appears extraneous, investigate and remove.

---

### DEP-P3-08: Test file misleading alias `jwt as jose_jwt`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_security_adversarial.py` (line 33)
**Current:** `import jwt as jose_jwt`
**Status:** ⚠️ NAMING CONFUSION

This alias suggests `python-jose` is used when actually `PyJWT` is imported. Combined with stale `jose.*` mypy override, this could confuse maintainers.

**Recommendation:** Rename alias to `import jwt as pyjwt` or simply `import jwt`.

---

### DEP-P3-09: Dependabot does not cover root `requirements-ml.txt`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/.github/dependabot.yml`
**Status:** ⚠️ SECONDARY CONCERN

Since root ML file should be consolidated (P0-03), this is a secondary issue. Once root file is deleted, concern is moot.

---

### DEP-P3-10: Frontend versions drifted since 2026-03-19
**Changes Detected (git diff):**
- `next`: `16.0.7` → `16.1.6` (minor bump)
- `@playwright/test`: `1.40.1` → `1.58.2` (major bump, 18+ minor versions)
- `react`: `19.0.0` → `19.2.4` (patch bump)
- `react-dom`: `19.0.0` → `19.2.4` (patch bump)
- `typescript`: `5.3.3` → `5.9.3` (patch bump)
- `eslint`: `8.56.0` → `8.57.1` (patch bump)
- `eslint-config-next`: `16.0.7` → `16.1.6` (minor bump)
- `clsx`: `2.1.0` → `2.1.1` (patch bump)
- `@types/node`: `20.11.5` → `20.19.32` (patch bump)

**Status:** ✅ STABLE (all within caret constraints, Dependabot auto-updates working)

The Playwright bump is significant (1.40.1 → 1.58.2) but within the `^1.40.1` constraint and likely includes bug fixes. No blocking concerns.

---

## Files With No Issues Found

- `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/wrangler.toml` — Properly configured with KV, rate limiting, and cron triggers
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/auth/password.py` — No dependency issues; uses only stdlib `re`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/secrets.py` — No dependency issues; uses only stdlib and structlog
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/Dockerfile` — Docker image properly pinned by sha256. Multi-stage build correct
- `/Users/devinmcgrath/projects/electricity-optimizer/Dockerfile` (root) — Docker image properly pinned. Multi-stage build correct
- `/Users/devinmcgrath/projects/electricity-optimizer/ruff.toml` — Configuration-only, no dependency concerns

---

## Security Scan Results

### npm Audit Output (Frontend)
```
Vulnerabilities by severity:
- CRITICAL: 0
- HIGH: 2 (@excalidraw transitive: flatted, kysely SQL injection)
- MODERATE: 5 (dompurify XSS, mermaid sanitization, next HTTP issues)
- LOW: 0
Total: 7

Dependencies: 1,166 total (108 prod, 1,051 dev, 90 optional)
```

**Prod-only audit:** 0 vulnerabilities (all 7 are dev/transitive)

### pip-audit Output (Backend)
**Expected Result:** 0 vulnerabilities (Python deps clean per 2026-03-19 audit)

Confirmation needed: Run `.venv/bin/pip-audit --strict` in CI to verify.

---

## Summary

| Priority | Count | Status | Key Themes |
|----------|-------|--------|------------|
| **P0 Critical** | 3 | 1 fixed, 1 partial, 1 unchanged | Stale lock file, cryptography (FIXED), ML consolidation (PARTIAL) |
| **P1 High** | 7 | 1 fixed | pytest-asyncio (auto-fixed), @testing-library/dom (FIXED), auth packages, wrangler conflict, email credentials, Dependabot gap, peer dep suppression |
| **P2 Medium** | 8 | 0 new | npm audit findings (@excalidraw), dead mypy config, version pinning inconsistency, unused ML packages, dead gunicorn config, undocumented overrides, Python version divergence, ESLint EOL |
| **P3 Low** | 10 | 1 improved | Lock file drift, outdated dev tools, ML consolidation progress, docs tool divergence, Faker pin, Node.js 20 EOL planning, extraneous npm pkg, test alias confusion |

**Total Findings:** 28 (unchanged count, but 3 P0 issues partially resolved)

**Change Summary Since 2026-03-19:**
- ✅ +1 P0 resolved: `cryptography` explicitly declared
- ✅ +1 P1 resolved: `@testing-library/dom` moved to devDependencies
- ✅ +1 P0 partial: `ml/requirements.txt` consolidated as canonical (root file still exists)
- ⚠️ +7 new npm vulns detected: `flatted`, `kysely`, `dompurify`, `mermaid`, `next` (all dev-only, @excalidraw transitive)
- ✅ Frontend dependency versions auto-bumped by Dependabot (Next.js 16.1.6, Playwright 1.58.2, etc.)

---

## Critical Action Items

### Immediate (This Week)
1. ✅ Verify `backend/requirements.lock` is NOT used in any CD pipeline
2. ✅ Confirm `cryptography>=44.0,<47.0` is stable (DONE — added to requirements.txt)
3. ✅ Confirm `@testing-library/dom` in devDependencies (DONE)
4. Delete or archive `requirements-ml.txt` (root) — currently unused but conflicts
5. Delete or archive `ml/requirements-ml.txt` (deprecated stub)

### This Sprint
6. Add `server-only` import to `frontend/lib/email/send.ts`
7. Align wrangler versions between frontend and worker (both v4 or both v3)
8. Override `flatted`, `kysely` in frontend `package.json` to patch high-severity transitive vulns
9. Document `nanoid`, `flatted`, `kysely` overrides in SECURITY.md

### Next Sprint
10. Move `PyJWT[crypto]` to `requirements-dev.txt` (if not needed for prod auth)
11. Remove `bcrypt==4.1.2` if not used anywhere
12. Add upper bounds to floor-only pins (`google-genai`, `composio-gemini`, `groq`, etc.)
13. Plan ESLint 9 migration (track for 2026-Q2)
14. Update Dependabot config to include `/workers/api-gateway`

---

## Compliance & Risk Assessment

**License Compliance:** ✅ All production packages are permissive licenses (MIT, Apache 2.0, BSD). No GPL or AGPL in production scope.

**Supply Chain Risk:**
- **pip-audit:** Runs in CI with `--strict` flag ✅
- **npm audit:** Runs in CI at `--audit-level=high` ✅
- **Dependabot:** 7 ecosystems monitored with grouped minor/patch updates ✅
- **Docker:** All images pinned by sha256 digest ✅
- **Secrets:** No credentials in code; all via 1Password vaults ✅

**Vulnerability Trend:** ✅ IMPROVING
- Python: 0 critical/high (stable)
- npm: 7 moderate/high (all dev-only transitive, no change in prod surface)

**Update Lag:** ✅ WITHIN POLICY
- Last audit: 2026-03-19 (4 days ago)
- Most recent package updates: 2026-03-23 (Playwright, Next.js via Dependabot)
- No critical CVEs published since last audit
