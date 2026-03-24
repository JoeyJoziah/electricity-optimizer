# Audit Report: Dependencies & Vulnerabilities
**Date:** 2026-03-19
**Scope:** Python, npm, and ML dependencies across all layers
**Files Reviewed:**
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.lock`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/pyproject.toml`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/Dockerfile`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/gunicorn_config.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/.npmrc`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/Dockerfile`
- `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/package.json`
- `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/wrangler.toml`
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-ml.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-dev.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/Dockerfile`
- `/Users/devinmcgrath/projects/electricity-optimizer/requirements-ml.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/Dockerfile`
- `/Users/devinmcgrath/projects/electricity-optimizer/ruff.toml`
- `/Users/devinmcgrath/projects/electricity-optimizer/.github/dependabot.yml`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/utils/encryption.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/auth/__init__.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/auth/password.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/auth.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/secrets.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/email/send.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/auth/server.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/.github/workflows/_backend-tests.yml`
- `/Users/devinmcgrath/projects/electricity-optimizer/render.yaml`

***

## P0 — Critical (Fix Immediately)

### DEP-P0-01: `requirements.lock` massively stale — production may be running insecure versions
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.lock`
**Severity:** CRITICAL

The lock file records resolved versions that diverge from `requirements.txt` by multiple major versions. If anything uses this lock file for reproducible builds, production could be running dangerously outdated packages:

| Package | Lock Version | requirements.txt Spec | Gap |
|---------|-------------|----------------------|-----|
| `sentry-sdk` | `1.39.2` | `>=2.0,<3.0` | **Major version behind** (v1 vs v2 requirement) |
| `stripe` | `7.14.0` | `>=14.0,<15.0` | **Major version behind** (v7 vs v14 requirement) |
| `redis` | `5.0.1` | `>=7.0,<8.0` | **Major version behind** (v5 vs v7 requirement) |
| `pydantic` | `2.5.3` | `==2.12.5` | Patch gap (2.5 vs 2.12) |
| `fastapi` | `0.115.0` | `>=0.115.0` | Matches lower bound only |
| `uvicorn` | `0.27.0` | `==0.42.0` | **15 minor versions behind** |
| `asyncpg` | `0.29.0` | `==0.31.0` | 2 minor versions behind |
| `numpy` | `1.26.3` | `>=2.0,<3.0` | **Major version conflict** (lock has 1.x, spec requires 2.x) |
| `structlog` | `24.1.0` | `==25.5.0` | Major version behind |
| `pytest` | `7.4.4` | `==9.0.2` (dev) | 2 major versions behind |

**Risk:** If a deployment script or Docker build references the lock file instead of `requirements.txt`, the application runs with known-vulnerable versions. The `sentry-sdk` v1 branch no longer receives security patches.

**Recommendation:** Either regenerate the lock file (`pip freeze > requirements.lock` from a clean install of current `requirements.txt`) or delete it entirely if it is not used by any build pipeline. Verify which file the Dockerfile and Render build actually consume.

### DEP-P0-02: `cryptography` not declared as direct dependency
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt`
**Used in:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/utils/encryption.py` (line 13: `from cryptography.hazmat.primitives.ciphers.aead import AESGCM`)

The `cryptography` package is directly imported for AES-256-GCM field-level encryption but is not listed in `requirements.txt`. It currently installs as a transitive dependency of `PyJWT[crypto]`, but this is fragile. If `PyJWT[crypto]` is ever replaced or its extras change, encryption silently breaks in production.

**Recommendation:** Add `cryptography>=44.0,<47.0` as an explicit dependency in `backend/requirements.txt` with a comment indicating its use for AES-256-GCM encryption.

### DEP-P0-03: Three ML requirements files with conflicting version constraints
**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-ml.txt`
- `/Users/devinmcgrath/projects/electricity-optimizer/requirements-ml.txt` (root)

These three files specify mutually incompatible version ranges for shared packages:

| Package | `ml/requirements.txt` | `ml/requirements-ml.txt` | `requirements-ml.txt` (root) |
|---------|----------------------|--------------------------|------------------------------|
| `numpy` | `>=1.24.0` (no upper) | `>=1.26.0` (no upper) | `>=1.24.0,<2.0.0` |
| `tensorflow` | `>=2.13.0` (no upper) | `>=2.15.0,<3.0` | `>=2.15.0,<2.17.0` |
| `keras` | `>=2.13.0` | `>=2.15.0` | `>=3.0.0` |
| `scikit-learn` | `>=1.3.0` | `>=1.4.0` | `>=1.3.0` |
| `prophet` | `>=1.1.4` | `>=1.1.5` | `>=1.1.4` |
| `holidays` | `>=0.40` | `>=0.40` | `>=0.37` |
| `xgboost` | `>=1.7.0` | `>=2.0.3` | `>=2.0.0` |
| `lightgbm` | `>=4.0.0` | `>=4.3.0` | `>=4.2.0` |

The `keras` conflict is the most dangerous: root `requirements-ml.txt` requires `>=3.0.0` while `ml/requirements.txt` requires `>=2.13.0` and `ml/requirements-ml.txt` requires `>=2.15.0`. Keras 3 is a breaking API change from Keras 2. The `numpy` conflict (`<2.0.0` in root vs `>=2.0` in backend) means the root ML file is incompatible with the backend.

**Recommendation:** Consolidate to a single authoritative ML requirements file. The root `requirements-ml.txt` and `ml/requirements.txt` appear to be stale predecessors of `ml/requirements-ml.txt`. Archive or delete the redundant files and update the ML Dockerfile to reference the single canonical file.

***

## P1 — High (Fix This Sprint)

### DEP-P1-01: `pytest-asyncio==1.3.0` is an invalid/phantom version pin
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt` (line 7)

The package `pytest-asyncio` has never had a version `1.3.0`. The most recent release series is `0.2x.x`. The lock file shows `0.23.3` was actually installed. This pin will cause a `pip install` failure on a fresh environment.

**Recommendation:** Change to `pytest-asyncio>=0.24.0,<1.0` or pin to the exact version confirmed working (e.g., `pytest-asyncio==0.24.0`).

### DEP-P1-02: `@testing-library/dom` in production dependencies
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (line 23)

`@testing-library/dom` is a testing utility listed under `dependencies` instead of `devDependencies`. It is not imported anywhere in production source code. This package and its transitive dependencies ship to production bundles if tree-shaking misses them, increasing bundle size and attack surface.

**Recommendation:** Move `"@testing-library/dom": "^10.4.1"` from `dependencies` to `devDependencies`.

### DEP-P1-03: `bcrypt==4.1.2` and `PyJWT[crypto]` declared but never imported
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt` (lines 18, 20)

Neither `bcrypt` nor `PyJWT` is imported anywhere in the production backend code. Authentication is handled by Better Auth on the frontend. The only reference to `jwt` is in `test_security_adversarial.py` (a test file). These are unnecessary production dependencies that increase attack surface and Docker image size.

- `bcrypt==4.1.2`: Zero imports across all backend `.py` files.
- `PyJWT[crypto]`: Only imported in a test file (`import jwt as jose_jwt` in `test_security_adversarial.py`).

**Recommendation:** Move `PyJWT[crypto]` to `requirements-dev.txt` (it is a test dependency). Remove `bcrypt` entirely unless a future feature needs it. Note: `cryptography` will need to be declared explicitly (see P0-02) since it currently comes in via `PyJWT[crypto]`.

### DEP-P1-04: Wrangler major version conflict between frontend and worker
**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (line 67): `"wrangler": "^4.75.0"`
- `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/package.json` (line 16): `"wrangler": "^3.99.0"`

Two different major versions of wrangler are pinned. The worker that actually runs on Cloudflare uses wrangler v3, while the frontend (which includes wrangler as a devDependency presumably for local development) uses v4. This creates configuration format divergence risk -- wrangler v4 may generate or expect different `wrangler.toml` syntax.

**Recommendation:** Align both to the same major version. If wrangler v4 is stable, upgrade the worker. If wrangler v3 is required for the worker's `wrangler.toml` format, downgrade the frontend's devDependency. Consider whether wrangler belongs in the frontend at all.

### DEP-P1-05: `nodemailer` and `resend` in frontend production dependencies with SMTP credentials
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (lines 29, 34)
**Used in:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/email/send.ts`

Server-side email sending packages (`nodemailer`, `resend`) are in the frontend's production `dependencies`. While these are used in Next.js API routes (server-side only), the `send.ts` file does not include a `"use server"` directive. The SMTP password is read from `process.env.SMTP_PASSWORD` (line 77) with no explicit server-only boundary.

**Risk:** If `send.ts` is accidentally imported from a client component, the SMTP credentials configuration code could be bundled and exposed. Next.js tree-shakes server-only code, but without the `"use server"` directive or `import "server-only"` guard, this is not guaranteed.

**Recommendation:** Add `import "server-only"` at the top of `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/email/send.ts` to prevent client-side bundling. Install the `server-only` package if not already present.

### DEP-P1-06: Dependabot missing coverage for `workers/api-gateway` npm dependencies
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/.github/dependabot.yml`

The Dependabot configuration monitors pip (backend, ml), npm (frontend), Docker, and GitHub Actions -- but does not include the `workers/api-gateway` directory for npm updates. The worker has 4 devDependencies (`@cloudflare/workers-types`, `typescript`, `vitest`, `wrangler`) that will not receive automated update PRs.

**Recommendation:** Add an entry to `.github/dependabot.yml`:
```yaml
  - package-ecosystem: "npm"
    directory: "/workers/api-gateway"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 3
```

### DEP-P1-07: `legacy-peer-deps=true` suppresses npm peer dependency conflict warnings
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/.npmrc` (line 1)

This setting masks real peer dependency conflicts. The known issue is `eslint@8` vs `eslint-config-next@16` (which expects eslint 9+). While documented in CLAUDE.md, this is a technical debt that silently allows broken peer relationships.

**Recommendation:** Upgrade to ESLint v9+ and remove the `legacy-peer-deps=true` workaround. This eliminates the need to suppress peer dep errors and ensures all packages are compatible.

***

## P2 — Medium (Fix Soon)

### DEP-P2-01: `@excalidraw/excalidraw` known vulnerabilities (5 remaining npm audit findings)
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (line 43)

Per CLAUDE.md notes: "npm vulns 13->5 (all @excalidraw transitive, 0 HIGH)". Five moderate-or-below npm audit findings persist as transitive dependencies of `@excalidraw/excalidraw`. While the component is dev-only (gated behind `notFound()` in production per the component comment), these findings appear in every `npm audit` run.

**Recommendation:** Either override the vulnerable transitive packages in `package.json` overrides (similar to the `nanoid` override already present), or move `@excalidraw/excalidraw` to an optional dependency / separate workspace so it does not pollute the main audit.

### DEP-P2-02: `jose.*` in mypy overrides references nonexistent package
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/pyproject.toml` (line 81)

The mypy configuration suppresses import errors for `jose.*`, but `python-jose` is not installed and not used anywhere. The project uses `PyJWT` (import name `jwt`), not `python-jose` (import name `jose`). This is dead configuration from a prior dependency choice.

**Recommendation:** Remove `"jose.*"` from the mypy overrides list.

### DEP-P2-03: Version pinning inconsistency across backend `requirements.txt`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt`

The file uses a mix of pinning strategies with no clear policy:
- **Exact pins (==):** `uvicorn==0.42.0`, `pydantic==2.12.5`, `asyncpg==0.31.0`, `bcrypt==4.1.2`, `python-dotenv==1.0.0`, etc.
- **Range pins (>=,<):** `redis>=7.0,<8.0`, `httpx>=0.26,<0.29`, `PyJWT>=2.8,<3.0`, `stripe>=14.0,<15.0`
- **Floor-only pins (>=):** `fastapi>=0.115.0`, `scikit-learn>=1.5.0`, `jinja2>=3.0`, `google-genai>=1.0.0`, `composio-gemini>=0.7.0`, `groq>=0.9.0`
- **Caret-like pins:** `sentry-sdk>=2.0,<3.0` (range bounded)

Floor-only pins (`>=X`) are dangerous for production reproducibility. A new major version of `google-genai`, `composio-gemini`, `groq`, `scikit-learn`, or `jinja2` could install with breaking changes.

**Recommendation:** Establish a pinning policy. For production dependencies, use either exact pins or bounded ranges (`>=X.Y,<X+1.0`). At minimum, add upper bounds to `google-genai`, `composio-gemini`, `groq`, `scikit-learn>=1.5.0`, `jinja2>=3.0`, `hnswlib>=0.8.0`, `nh3>=0.2.14`, and `python-multipart>=0.0.18`.

### DEP-P2-04: ML layer has unused heavy dependencies
**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-ml.txt` (lines 42-43): `wandb>=0.16.0`
- `/Users/devinmcgrath/projects/electricity-optimizer/requirements-ml.txt` (lines 23-24, 30-31, 37-38): `transformers>=4.30.0`, `torch>=2.0.0`, `hyperopt>=0.2.7`, `shap>=0.43.0`, `lime>=0.2.0`, `pandera>=0.17.0`, `omegaconf>=2.3.0`, `category_encoders>=2.6.0`
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements.txt` (line 40): `tqdm>=4.65.0`

Grep across the entire ML codebase shows zero imports for: `wandb`, `mlflow`, `transformers`, `shap`, `lime`, `pandera`, `omegaconf`, `category_encoders`, `tqdm`, `hyperopt`. These are heavyweight packages (PyTorch alone is ~2GB, transformers ~500MB) that inflate Docker images and increase supply chain attack surface without being used.

**Recommendation:** Remove unused packages. Keep only what is actually imported: `tensorflow`, `keras`, `torch` (used in `cnn_lstm_trainer.py` and `predictor.py`), `xgboost`, `lightgbm`, `optuna`, `scipy`, `statsmodels`, `prophet`, `matplotlib`, `plotly`, `numpy`, `pandas`, `scikit-learn`, `pulp`, `holidays`, `joblib`, `pydantic`.

### DEP-P2-05: `gunicorn_config.py` exists but `gunicorn` not in requirements
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/gunicorn_config.py`
**Not in:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt`

A full 85-line gunicorn configuration file exists but gunicorn is not in `requirements.txt` and the Dockerfile uses `uvicorn` directly. The `start.sh` script has a comment: "For production with more resources, use: gunicorn -c gunicorn_config.py main:app". This dead code could mislead maintainers.

**Recommendation:** Either add `gunicorn>=22.0,<23.0` to requirements if gunicorn is planned for future use (document the plan), or remove `gunicorn_config.py` to avoid confusion.

### DEP-P2-06: `nanoid` override for CVE mitigation but no version constraint documentation
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (line 39)

The overrides section forces `"nanoid": "^5.1.5"` (presumably to patch a known CVE in older nanoid versions). However, there is no comment or documentation explaining which CVE this addresses or which transitive dependency pulls in the vulnerable version. Future maintainers may remove this override without understanding the security implications.

**Recommendation:** Add a comment in the package.json (or in a `SECURITY.md` file) documenting the CVE number and which package pulls in nanoid.

### DEP-P2-07: ML Dockerfile uses Python 3.11, backend uses Python 3.12
**Files:**
- `/Users/devinmcgrath/projects/electricity-optimizer/ml/Dockerfile` (line 4): `python:3.11-slim`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/Dockerfile` (line 4): `python:3.12-slim`

Two different Python versions across the application layers. While this may be intentional (TensorFlow compatibility), it creates maintenance burden and potential behavior differences. The `pyproject.toml` specifies `requires-python = ">=3.11"` allowing both.

**Recommendation:** Document the reason for divergence (likely TF 2.15 compatibility). Consider upgrading ML to Python 3.12 once TensorFlow supports it fully, or pin to 3.12 in `pyproject.toml` if backend requires 3.12 features.

### DEP-P2-08: `eslint@8` + `eslint-config-next@16` peer dependency mismatch
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (lines 55-56)

`eslint-config-next@16` expects ESLint 9+, but ESLint 8 is pinned. This is noted as deferred in CLAUDE.md ("ESLint v10 deferred (separate track)") and masked by `legacy-peer-deps=true`. ESLint 8 reached EOL. Running with mismatched peer deps can cause silent rule failures.

**Recommendation:** Plan the ESLint 9 upgrade. This is tracked but should have a deadline.

***

## P3 — Low / Housekeeping

### DEP-P3-01: `email-validator==2.3.0` in requirements but `==2.1.0` in lock file
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements.txt` (line 26) vs `requirements.lock` (line 18)

Another indicator of lock file staleness (covered in P0-01). Not a separate issue, but noted for completeness. The package is transitively required by Pydantic's `EmailStr` validator; the version delta is minor.

### DEP-P3-02: `safety>=2.3.0,<4.0.0` in ml/requirements-dev.txt is outdated
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-dev.txt` (line 40)
**Also:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt` (line 28): `safety>=3.0.0,<4.0.0`

The ML dev requirements allow `safety>=2.3.0` (v2 branch), while the backend requires `safety>=3.0.0`. The `safety` tool v2 uses a different API and database format. Using v2 may miss recent vulnerability disclosures.

**Recommendation:** Align to `safety>=3.0.0,<4.0.0` in the ML dev requirements.

### DEP-P3-03: Redundant linting tools in ML dev requirements
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-dev.txt` (lines 15-19)

The ML dev requirements include `flake8`, `black`, `isort`, `mypy`, and `pylint`. The project root uses `ruff` (which replaces flake8, isort, and parts of pylint). The backend dev requirements already use `ruff==0.15.6`. Having both ruff and flake8/isort/pylint creates conflicting style enforcement.

**Recommendation:** Replace `flake8`, `isort`, and `pylint` with `ruff` in the ML dev requirements to match the rest of the project.

### DEP-P3-04: `mkdocs==1.5.3` and `mkdocs-material==9.5.4` outdated
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt` (lines 31-33)

MkDocs 1.5.3 is behind current (1.6+). While dev-only, newer versions include security fixes for XSS in certain rendering contexts. MkDocs-material 9.5.4 is similarly behind.

**Recommendation:** Update to latest minor versions in next dev dependency refresh.

### DEP-P3-05: `Faker==40.11.0` exact pin may block security patches
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt` (line 12)

Dev dependency with an exact pin. Minor/patch updates to Faker are safe and may include dependency updates.

**Recommendation:** Use `faker>=40.0,<42.0` or a similar range.

### DEP-P3-06: `sphinx` + `sphinx-rtd-theme` in ML dev requirements alongside `mkdocs` in backend
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-dev.txt` (lines 26-28)
**Also:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/requirements-dev.txt` (lines 31-33)

Two different documentation systems: Sphinx for ML, MkDocs for backend. This creates onboarding friction and maintenance burden.

**Recommendation:** Standardize on one documentation system across the project.

### DEP-P3-07: `jupyter>=1.0.0` and `ipykernel>=6.25.0` in ML dev requirements
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/ml/requirements-dev.txt` (lines 31-32)

These are interactive development tools. `jupyter>=1.0.0` installs the entire Jupyter ecosystem including the notebook server, which historically has had security vulnerabilities. These should never be deployed but the wide version range means potentially vulnerable versions could install.

**Recommendation:** Pin to recent versions: `jupyter>=1.0.0,<1.2.0` and ensure these are never included in production images.

### DEP-P3-08: Test file aliases `jwt` as `jose_jwt` creating confusion
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_security_adversarial.py` (line 33)

```python
import jwt as jose_jwt
```

This misleading alias suggests `python-jose` is used when actually `PyJWT` is imported. Combined with the stale `jose.*` mypy override (DEP-P2-02), this could confuse future maintainers into thinking python-jose is a dependency.

**Recommendation:** Rename the alias to `import jwt` (or `import jwt as pyjwt` if disambiguation is needed).

### DEP-P3-09: Dependabot does not cover root `requirements-ml.txt`
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/.github/dependabot.yml`

Dependabot monitors `backend/` and `ml/` for pip, but not the root-level `requirements-ml.txt`. Since this file should be consolidated (see P0-03), this is a secondary concern.

### DEP-P3-10: Frontend `@types/node` pinned to v20 while Node.js 20 may EOL
**File:** `/Users/devinmcgrath/projects/electricity-optimizer/frontend/package.json` (line 50)

`"@types/node": "^20.11.5"` -- this is a type definitions package tied to Node 20. The frontend Dockerfile uses `node:20-alpine`. Node 20 enters maintenance LTS in October 2026 and EOL in April 2027. Not urgent but should be tracked for the Node 22 migration.

**Recommendation:** Track Node 22 LTS migration. When upgrading, update both the Dockerfile base image and `@types/node`.

***

## Files With No Issues Found

- `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/wrangler.toml` -- Properly configured with appropriate KV, rate limiting, and route bindings.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/auth/password.py` -- No dependency issues; uses only stdlib `re`.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/secrets.py` -- No dependency issues; uses only stdlib and structlog.
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/Dockerfile` -- Docker image properly pinned by sha256 digest. Multi-stage build correctly separates deps/build/production stages.
- `/Users/devinmcgrath/projects/electricity-optimizer/Dockerfile` (root) -- Docker image properly pinned. Multi-stage build.
- `/Users/devinmcgrath/projects/electricity-optimizer/ruff.toml` -- Configuration-only, no dependency concerns.

***

## Summary

| Priority | Count | Key Themes |
|----------|-------|------------|
| **P0 Critical** | 3 | Stale lock file with major version drift, undeclared `cryptography` dependency, 3 conflicting ML requirements files |
| **P1 High** | 7 | Phantom `pytest-asyncio` version, test library in production deps, unused auth packages, wrangler version conflict, email credential exposure risk, Dependabot gap, peer dep suppression |
| **P2 Medium** | 8 | npm audit findings, dead mypy config, version pinning inconsistency, unused heavy ML packages, dead gunicorn config, undocumented overrides, Python version divergence, ESLint EOL |
| **P3 Low** | 10 | Lock file drift, outdated dev tools, redundant linters, misleading import alias, Dependabot gaps, docs tool divergence |

**Total Findings:** 28

### Critical Action Items (P0)
1. Regenerate or delete `backend/requirements.lock` -- it is dangerously stale with sentry-sdk v1 (EOL) and stripe v7 vs required v14.
2. Explicitly declare `cryptography` in `backend/requirements.txt` -- production encryption depends on it via transitive install only.
3. Consolidate the three ML requirements files into one canonical file to eliminate version conflicts (especially the keras 2 vs 3 conflict).

### Supply Chain Risk Assessment
- **pip-audit** runs in CI (`_backend-tests.yml`) with `--strict` flag -- good.
- **npm audit** runs in CI (`ci.yml`) at `--audit-level=high` -- good.
- **Dependabot** covers most ecosystems but misses `workers/api-gateway` npm and root ML requirements.
- Docker images are pinned by digest -- excellent practice.
- Both frontend packages are `"private": true` -- no dependency confusion risk.
- The `nanoid` override demonstrates proactive CVE mitigation.
- The `legacy-peer-deps=true` workaround is a known technical debt item.

### Positive Observations
- Docker images use sha256 digest pinning across all three Dockerfiles.
- Non-root users in all production Docker stages (appuser, mluser, nextjs).
- CI pipeline includes both `pip-audit` and `npm audit` gates.
- Dependabot configured for 7 ecosystems with grouped minor/patch updates.
- XSS sanitization uses `nh3` (Rust-based) instead of deprecated `bleach`.
- The `overrides` mechanism is used proactively for known CVEs (nanoid).
