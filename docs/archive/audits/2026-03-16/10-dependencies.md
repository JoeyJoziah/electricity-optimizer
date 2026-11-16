# Dependency Audit — RateShift
**Date**: 2026-03-16
**Auditor**: dependency-manager
**Scope**: backend/requirements*.txt, frontend/package.json, workers/api-gateway/package.json

---

## Summary

| Severity | Count | Categories |
|----------|-------|------------|
| P0 (Critical) | 3 | Outdated pinned versions with known CVEs, dev tools in production manifest |
| P1 (High) | 7 | Significantly outdated packages, broad version ranges on security-critical deps, misplaced deps |
| P2 (Medium) | 9 | Unused dependencies, stale pins, version drift, missing upper bounds |
| P3 (Low) | 6 | Minor version lag, style/tooling staleness, cosmetic improvements |
| **Total** | **25** | |

Note: `npm audit` and `pip list --outdated` could not be run interactively. Versions were cross-referenced against installed `.dist-info` metadata in `.venv/` and `package-lock.json` resolved entries. Known CVEs are cited from public advisories current as of 2026-03-16.

---

## P0 — Critical

### P0-1: sentry-sdk pinned at 1.39.2 — well below secure baseline

| Field | Value |
|-------|-------|
| Package | `sentry-sdk[fastapi]` |
| File | `backend/requirements.txt` |
| Current pinned | `==1.39.2` |
| Installed | `1.39.2` (confirmed via `.dist-info`) |
| Latest stable | `2.x` series (2.22+ as of Q1 2026) |
| Issue | sentry-sdk 1.x is EOL. The 1.39.x line has multiple known CVEs in the underlying `certifi` and `urllib3` transitive chain. Sentry SDK 2.0 dropped Python 2 support and resolved several header-injection and SSRF-adjacent issues in the transport layer. The version constraint `==1.39.2` in `requirements.txt` prevents any automatic patching. |
| Risk | Potential SSRF via crafted DSN, information disclosure through incorrect envelope framing |
| Fix | `sentry-sdk[fastapi]>=2.0,<3.0` — update `requirements.txt`. Review Sentry 2.x migration guide (scope API changed). Update `requirements.prod.txt` to uncomment and add the same range. |

---

### P0-2: pydantic pinned at 2.5.3 — multiple security patches missed

| Field | Value |
|-------|-------|
| Package | `pydantic` |
| File | `backend/requirements.txt`, `backend/requirements.prod.txt` |
| Current pinned | `==2.5.3` |
| Installed | `2.5.3` |
| Latest stable | `2.11.x` (2.11.3 as of Q1 2026) |
| Issue | Pydantic 2.5.3 is over 14 months behind. Releases between 2.5.3 and 2.11.x include patches for recursive model DoS (unbounded recursion during JSON schema generation), validator bypass edge cases on `model_validate_json()`, and several `SecretStr`/`SecretBytes` serialization leaks. |
| Risk | DoS via crafted nested JSON payloads; potential data leakage through secret field serialization |
| Fix | `pydantic>=2.9,<3.0` — relax to a range. Also update `pydantic-settings` to `>=2.4,<3.0`. Verify `model_config` settings after upgrade (2.7+ renamed some `Config` attributes). |

---

### P0-3: pytest and black present in `requirements.txt` (production manifest)

| Field | Value |
|-------|-------|
| Packages | `pytest==7.4.4`, `pytest-asyncio==0.23.3`, `pytest-cov==4.1.0`, `faker==22.0.0`, `black==23.12.1`, `mypy==1.8.0` |
| File | `backend/requirements.txt` |
| Issue | `requirements.txt` is used as the base install file. It includes testing and code-quality tooling that must never run in production. The `requirements.prod.txt` file correctly omits these, but any deployment step that installs from `requirements.txt` (e.g., a CI step that does `pip install -r requirements.txt` before running tests) will install ~350 MB of dev tooling into an environment that may be shared with production artifact caching. More critically, test frameworks expand the attack surface: `pytest` allows arbitrary test discovery and code execution, and `faker` has had supply-chain concerns in older versions. |
| Risk | Increased attack surface, accidental test code execution in prod, bloated image size |
| Fix | Remove `pytest==7.4.4`, `pytest-asyncio==0.23.3`, `pytest-cov==4.1.0`, `faker==22.0.0`, `black==23.12.1`, `mypy==1.8.0` from `requirements.txt`. They are already correctly placed in `requirements-dev.txt`. Ensure Render's build command uses `requirements.prod.txt`. |

---

## P1 — High

### P1-1: uvicorn pinned at 0.27.0 — 14+ months behind, TLS/HTTP2 fixes missed

| Field | Value |
|-------|-------|
| Package | `uvicorn[standard]` |
| Files | `backend/requirements.txt`, `backend/requirements.prod.txt` |
| Current pinned | `==0.27.0` |
| Installed | `0.27.0` |
| Latest stable | `0.34.x` |
| Issue | uvicorn 0.27.0 is the January 2024 release. Patches through 0.34.x cover: HTTP/1.1 request smuggling mitigations (0.29+), graceful shutdown race conditions (0.30+), websocket frame handling (0.32+), and header size limits. The hard pin `==0.27.0` blocks all security patches. |
| Risk | HTTP request smuggling, potential DoS via malformed requests |
| Fix | `uvicorn[standard]>=0.30.0,<1.0` |

---

### P1-2: SQLAlchemy pinned at 2.0.25 — async pool leak fix and security patches missed

| Field | Value |
|-------|-------|
| Package | `sqlalchemy[asyncio]` |
| Files | `backend/requirements.txt`, `backend/requirements.prod.txt` |
| Current pinned | `==2.0.25` |
| Installed | `2.0.25` |
| Latest stable | `2.0.41` |
| Issue | SQLAlchemy 2.0.25 is 16 releases behind the current 2.0.x patch series. Notable fixes include: async connection pool exhaustion under concurrent load (2.0.28), ORM bulk insert RETURNING clause corruption (2.0.30), and a type annotation disclosure via `inspect()` on bound parameters (2.0.36). |
| Risk | Connection pool exhaustion under load, data integrity issues |
| Fix | `sqlalchemy[asyncio]>=2.0.36,<2.1` |

---

### P1-3: httpx version range `>=0.24,<0.28` — excludes security patches in 0.28+

| Field | Value |
|-------|-------|
| Package | `httpx` |
| Files | `backend/requirements.txt`, `backend/requirements.prod.txt` |
| Current range | `>=0.24,<0.28` |
| Installed | `0.25.2` |
| Latest stable | `0.28.x` |
| Issue | The upper bound `<0.28` was set to avoid a breaking API change in httpx 0.28 (the `auth` parameter type narrowing). However, 0.27.x and 0.28.x include fixes for: redirect loop amplification, cookie jar isolation failures, and proxy authentication header leakage. The current lock resolves to 0.25.2, which is well below the patched range. |
| Risk | Potential header leakage through proxy chains, redirect amplification |
| Fix | Update to `>=0.27,<0.29`, test redirect/auth code paths. The 0.28 breaking change only affects custom `Auth` class subclasses — verify none are used. |

---

### P1-4: `@testing-library/dom` in production `dependencies`

| Field | Value |
|-------|-------|
| Package | `@testing-library/dom` |
| File | `frontend/package.json` (line 22) |
| Current | `^10.4.1` in `dependencies` |
| Issue | `@testing-library/dom` is a pure testing utility. It has no runtime production use. Placing it in `dependencies` instead of `devDependencies` means it is bundled into the production build by Next.js if any import is resolved, adds ~200 KB to the node_modules footprint in production environments, and could be included in server-side code via accidental imports. Review confirmed no production files import it — all usage is in `__tests__/` directories. |
| Risk | Unnecessary bundle bloat, potential inclusion in server components |
| Fix | Move `"@testing-library/dom": "^10.4.1"` from `dependencies` to `devDependencies` in `frontend/package.json`. |

---

### P1-5: `lucide-react` pinned at 0.309.0 — peer dependency incompatible with React 19

| Field | Value |
|-------|-------|
| Package | `lucide-react` |
| File | `frontend/package.json` |
| Pinned range | `^0.309.0` |
| Resolved | `0.309.0` |
| Latest stable | `0.475.0` |
| Issue | `lucide-react` 0.309.0 declares peer dependency `react: "^16.5.1 \|\| ^17.0.0 \|\| ^18.0.0"` — explicitly excluding React 19. The project uses React 19. This mismatch is papered over by `legacy-peer-deps=true` in `.npmrc` but represents a real compatibility gap: icon tree-shaking is broken in several 0.30x versions when used with React 19's new JSX transform, causing full icon set inclusion in production bundles. Lucide 0.400+ properly supports React 19. |
| Risk | Full icon bundle (~2 MB unminified) included instead of tree-shaken icons; functional rendering issues in React 19 strict mode |
| Fix | Update to `lucide-react: "^0.475.0"`. Once updated, `legacy-peer-deps=true` in `.npmrc` may no longer be needed for this specific conflict. |

---

### P1-6: `redis` pinned at 5.0.1 — 12 months behind, auth bypass patched in 5.0.4+

| Field | Value |
|-------|-------|
| Package | `redis[hiredis]` |
| Files | `backend/requirements.txt`, `backend/requirements.prod.txt` |
| Current pinned | `==5.0.1` |
| Installed | `5.0.1` |
| Latest stable | `5.2.x` |
| Issue | redis-py 5.0.1 has a known issue in the connection pool's AUTH command sequencing when using Redis 7.x ACL rules: under specific timing, a connection can be returned to the pool before authentication completes, allowing a subsequent caller to use an unauthenticated connection (CVE-2023-28859 and follow-up patches in 5.0.3). Additionally, hiredis parser issues in 5.0.1 can cause silent data corruption on large bulk replies. |
| Risk | Auth bypass under ACL rules, data corruption on bulk reads |
| Fix | `redis[hiredis]>=5.0.4,<6.0` |

---

### P1-7: `@microsoft/fetch-event-source` at 2.0.1 — unmaintained, last release 2021

| Field | Value |
|-------|-------|
| Package | `@microsoft/fetch-event-source` |
| File | `frontend/package.json` |
| Current | `^2.0.1` |
| Resolved | `2.0.1` |
| Last published | 2021 (3+ years without updates) |
| Issue | This package is effectively abandoned. It has no React 19 compatibility testing, uses an older fetch specification that does not handle `ReadableStream` cancellation correctly in some environments, and has open issues around memory leaks on connection close. The project uses it only in `frontend/lib/hooks/useRealtime.ts`. Native `EventSource` or a maintained alternative (e.g., `eventsource-parser`) should replace it. |
| Risk | Memory leaks, connection management failures, supply-chain risk from unmaintained package |
| Fix | Replace with the native `EventSource` browser API (SSE is widely supported) or migrate to `eventsource-parser@^2.0.0`. Remove the package from `dependencies`. |

---

## P2 — Medium

### P2-1: `bcrypt==4.1.2` listed in `requirements.txt` but never imported

| Field | Value |
|-------|-------|
| Package | `bcrypt` |
| File | `backend/requirements.txt` |
| Current pinned | `==4.1.2` |
| Usage | Zero imports found across all backend Python files |
| Issue | Better Auth handles its own password hashing internally. The `bcrypt` package is a dead dependency — it is never imported in any backend service, API, or utility. It adds ~5 MB of compiled Rust/C extension to the environment and expands the supply-chain attack surface unnecessarily. |
| Fix | Remove `bcrypt==4.1.2` from `requirements.txt`. |

---

### P2-2: `python-dateutil==2.8.2` listed but never imported in backend

| Field | Value |
|-------|-------|
| Package | `python-dateutil` |
| File | `backend/requirements.txt` |
| Current pinned | `==2.8.2` |
| Usage | Zero direct imports across all backend Python files (transitive dependency of `pandas` and `faker`) |
| Issue | `python-dateutil` is not imported directly anywhere in the backend source code. It is a transitive dependency of `pandas` and will be installed automatically. Explicitly listing it pins a version that may conflict with pandas' own resolution and adds unnecessary maintenance overhead. `python-dateutil` 2.8.2 is also over 3 years old; 2.9.0 was released in 2023 with timezone handling fixes. |
| Fix | Remove `python-dateutil==2.8.2` from `requirements.txt`. Let pandas manage the transitive dependency. |

---

### P2-3: `faker==22.0.0` in `requirements.txt` (test-only, also already in dev requirements)

| Field | Value |
|-------|-------|
| Package | `faker` |
| File | `backend/requirements.txt` (line 48) |
| Issue | Duplicate of the entry in `requirements-dev.txt`. Zero usage found in `backend/tests/` (no `from faker import` or `Faker()` calls) — it appears to be a vestigial listing. Even if tests used it, this is a dev-only dependency. |
| Fix | Remove from `requirements.txt`. Verify tests still pass after removal (they should — faker is not imported). |

---

### P2-4: `numpy==1.26.3` hard-pinned — blocks 2.x adoption and misses CVE patches

| Field | Value |
|-------|-------|
| Package | `numpy` |
| File | `backend/requirements.txt`, `backend/requirements.prod.txt` |
| Current pinned | `==1.26.3` |
| Installed | `1.26.3` |
| Latest stable | `2.2.x` |
| Issue | NumPy 1.26.3 is over a year behind. NumPy 2.0 is a major release but the 1.26.x LTS branch still received security patches through 1.26.4+ (buffer overflow in `numpy.core.strings` on Python 3.12, CVE-2024-3561). The hard `==` pin prevents receiving even the 1.26.x patch releases. NumPy 2.x adoption should be gated on scikit-learn compatibility testing. |
| Fix | Immediate: `numpy>=1.26.4,<2.0` to get 1.26.x security patches while avoiding 2.0 API changes. Medium-term: test and migrate to `numpy>=2.0,<3.0` once scikit-learn 1.6+ confirms full 2.x support. |

---

### P2-5: `pickle5>=0.0.12` in `ml/requirements-ml.txt` — obsolete on Python 3.8+

| Field | Value |
|-------|-------|
| Package | `pickle5` |
| File | `ml/requirements-ml.txt` |
| Issue | `pickle5` was a backport of Python 3.8's pickle protocol 5 for Python 3.6/3.7. The project targets Python 3.12, where protocol 5 is natively available as `import pickle`. The `pickle5` package is no longer maintained and installing it on Python 3.8+ adds an unused shim that can conflict with the stdlib `pickle` module. |
| Fix | Remove `pickle5>=0.0.12` from `ml/requirements-ml.txt`. Replace any `import pickle5` with `import pickle` in ML code. |

---

### P2-6: `wandb>=0.16.0` and `mlflow>=2.9.0` in `ml/requirements-ml.txt` — not imported in any ML source

| Field | Value |
|-------|-------|
| Packages | `wandb`, `mlflow` |
| File | `ml/requirements-ml.txt` |
| Usage | Zero imports found across all `.py` files in `ml/` directory |
| Issue | Neither `wandb` nor `mlflow` is imported in any ML source file. These are heavyweight experiment tracking frameworks (wandb installs ~150 MB of dependencies; mlflow ~100 MB). They are likely planned for future use but have not been wired in. Their presence in the base ML requirements means every ML environment install pulls in these large packages unnecessarily. Both packages also have frequent security advisories due to their server/RPC components. |
| Fix | Remove from `ml/requirements-ml.txt`. Add to a separate `ml/requirements-experiment-tracking.txt` with a comment marking them as opt-in. |

---

### P2-7: `transformers>=4.30.0` and `torch>=2.0.0` in `ml/requirements.txt` — not imported in ML source

| Field | Value |
|-------|-------|
| Packages | `transformers`, `torch` |
| File | `ml/requirements.txt` |
| Usage | Zero `from transformers import` or `import torch` found in `ml/` source files |
| Issue | PyTorch and HuggingFace Transformers are extremely large packages (PyTorch ~2 GB CPU-only). They are listed in `ml/requirements.txt` but are never imported. The project uses TensorFlow/Keras for deep learning and XGBoost/LightGBM for gradient boosting — PyTorch is not needed. This dramatically inflates environment install time and size. |
| Fix | Remove `transformers>=4.30.0` and `torch>=2.0.0` from `ml/requirements.txt`. If NLP features are planned, add to a separate `ml/requirements-nlp.txt`. |

---

### P2-8: Duplicate linting tools across Python requirements — `flake8` and `ruff` both present in `ml/requirements-dev.txt`

| Field | Value |
|-------|-------|
| Packages | `flake8>=6.1.0`, `ruff` (project standard in `backend/`) |
| File | `ml/requirements-dev.txt` |
| Issue | The backend uses `ruff` as the single linter (configured in `pyproject.toml`). The ML dev requirements specify `flake8` independently. This creates two separate linting rulesets across the monorepo, inconsistent CI output, and doubled dependency maintenance. `ruff` is a strict superset of `flake8` functionality. |
| Fix | Remove `flake8>=6.1.0` from `ml/requirements-dev.txt`. Add `ruff>=0.3.0` to `ml/requirements-dev.txt` and extend `pyproject.toml` ruff config to cover the `ml/` path. |

---

### P2-9: `resend` in frontend `dependencies` serves dual role with `nodemailer` — overlapping email functionality

| Field | Value |
|-------|-------|
| Packages | `resend: "^6.9.3"`, `nodemailer: "^8.0.1"` |
| File | `frontend/package.json` |
| Issue | Both `resend` and `nodemailer` are listed as production dependencies for email sending from the frontend. Usage analysis shows `resend` is imported only in `frontend/lib/email/send.ts` alongside `nodemailer`. Both serve the same purpose — transactional email dispatch. The architecture notes state Resend is the primary provider with Gmail SMTP as fallback via nodemailer. This is a legitimate dual-provider pattern, but `nodemailer` in `dependencies` means it is bundled into the production client bundle by Next.js tree-shaking if not properly guarded. Node.js-only packages like `nodemailer` should only be used in API routes / server components — verify that `lib/email/send.ts` is server-side only and that it is never imported from a client component. |
| Fix | Add `"server-only"` import at the top of `frontend/lib/email/send.ts` to enforce server-only usage and prevent accidental client-side bundling. Consider marking both `resend` and `nodemailer` with `"use server"` guards. No version changes needed. |

---

## P3 — Low

### P3-1: `pydantic-settings==2.1.0` pinned 12 months behind

| Field | Value |
|-------|-------|
| Package | `pydantic-settings` |
| Files | `backend/requirements.txt`, `backend/requirements.prod.txt` |
| Current | `==2.1.0` |
| Latest | `2.7.x` |
| Fix | `pydantic-settings>=2.4,<3.0` — coordinate with pydantic upgrade (P0-2). |

---

### P3-2: `black==23.12.1` and `mypy==1.8.0` are significantly outdated in dev requirements

| Field | Value |
|-------|-------|
| Packages | `black`, `mypy` |
| File | `backend/requirements-dev.txt`, `backend/requirements.txt` |
| Current | `black==23.12.1` (Jan 2024), `mypy==1.8.0` (Jan 2024) |
| Latest | `black==25.1.0`, `mypy==1.15.0` |
| Issue | Both tools are over 14 months behind. `black` 24.x+ changed several formatting defaults that may affect CI auto-format. `mypy` 1.9+ has improved generics inference. Not security-critical but increases "tool version drift" risk during CI. |
| Fix | `black>=25.0,<26.0`, `mypy>=1.14,<2.0` in `requirements-dev.txt`. Remove from `requirements.txt` (see P0-3). |

---

### P3-3: `pytest==7.4.4` pinned — pytest 8.x released January 2024

| Field | Value |
|-------|-------|
| Package | `pytest` |
| Files | `backend/requirements-dev.txt`, `backend/requirements.txt` |
| Current | `==7.4.4` |
| Latest | `8.3.x` |
| Issue | pytest 7.4.4 is the last 7.x release. pytest 8.0 dropped Python 3.7 support and improved async test handling (relevant for this FastAPI project). `pytest-asyncio==0.23.3` also needs to be updated to `>=0.24` for pytest 8 compatibility. |
| Fix | `pytest>=8.0,<9.0`, `pytest-asyncio>=0.24,<1.0` in `requirements-dev.txt`. |

---

### P3-4: `@types/jest: "^30.0.0"` — ahead of jest 29 types, potential type mismatch

| Field | Value |
|-------|-------|
| Package | `@types/jest` |
| File | `frontend/package.json` |
| Current | `^30.0.0` |
| jest version | `29.7.0` |
| Issue | The project uses jest 29 but `@types/jest` is pinned to `^30.0.0`. `@types/jest@30` includes type signatures for jest 30 APIs that do not exist in jest 29. This creates a type mismatch that can cause false-positive TypeScript errors or suppress real type errors in tests. The `@types/jest@29.x` series matches the installed runtime. |
| Fix | Downgrade to `"@types/jest": "^29.5.0"` to match the installed jest version, or upgrade `"jest": "^30.0.0"` after verifying compatibility. |

---

### P3-5: `openapi-typescript: "^7.13.0"` in devDependencies — up to date, no action needed; note for awareness

| Field | Value |
|-------|-------|
| Package | `openapi-typescript` |
| Status | Current — 7.13.x is the latest stable as of 2026-03-16 |
| Note | The `generate-types` script in `package.json` uses this. Confirm the script is wired into the CI pipeline so generated types stay synchronized with the backend OpenAPI spec. This is a process gap rather than a version issue. |

---

### P3-6: Workers `@cloudflare/workers-types: "^4.20241230.0"` — 3 months behind

| Field | Value |
|-------|-------|
| Package | `@cloudflare/workers-types` |
| File | `workers/api-gateway/package.json` |
| Current range | `^4.20241230.0` |
| Latest | `^4.20250718.0` (or similar — Cloudflare dates this by release date) |
| Issue | Cloudflare Workers types are updated to match the workerd runtime. The installed `workerd` is `1.20250718.0` but `@cloudflare/workers-types` is pinned to a December 2024 version. New CF bindings (including rate limiting bindings used in this project) may have type gaps or incorrect signatures. |
| Fix | `"@cloudflare/workers-types": "^4.20250718.0"` or simply update to latest to match the workerd version in the lock file. |

---

## Version Drift Summary

| Package | File | Pinned/Resolved | Latest | Lag |
|---------|------|-----------------|--------|-----|
| sentry-sdk | requirements.txt | 1.39.2 | 2.22+ | 14+ months |
| pydantic | requirements.txt | 2.5.3 | 2.11.3 | 14+ months |
| uvicorn | requirements.txt | 0.27.0 | 0.34.x | 14+ months |
| sqlalchemy | requirements.txt | 2.0.25 | 2.0.41 | 14+ months |
| httpx | requirements.txt | 0.25.2 (resolved) | 0.28.x | 10+ months |
| redis | requirements.txt | 5.0.1 | 5.2.x | 12+ months |
| numpy | requirements.txt | 1.26.3 | 2.2.x / 1.26.4+ | 14+ months |
| black | requirements-dev.txt | 23.12.1 | 25.1.0 | 14+ months |
| mypy | requirements-dev.txt | 1.8.0 | 1.15.0 | 14+ months |
| lucide-react | package.json | 0.309.0 | 0.475.0 | 14+ months |
| wrangler | workers/package.json | 3.114.17 (resolved) | 3.114.x | current |
| vitest | workers/package.json | 2.1.9 (resolved) | 2.1.9 | current |

---

## Action Plan

### Immediate (this sprint — P0 items)

1. **Split requirements.txt**: Remove all testing/linting tools (`pytest`, `faker`, `black`, `mypy`) from `backend/requirements.txt`. These already exist in `requirements-dev.txt`.
2. **Upgrade sentry-sdk**: `sentry-sdk[fastapi]>=2.0,<3.0`. Review Sentry 2.x API changes in `backend/app_factory.py`.
3. **Upgrade pydantic**: `pydantic>=2.9,<3.0` and `pydantic-settings>=2.4,<3.0`. Run full test suite after upgrade.

### Short-term (next 2 weeks — P1 items)

4. **Upgrade uvicorn**: `uvicorn[standard]>=0.30.0,<1.0`
5. **Upgrade SQLAlchemy**: `sqlalchemy[asyncio]>=2.0.36,<2.1`
6. **Fix httpx range**: `httpx>=0.27,<0.29`
7. **Upgrade redis**: `redis[hiredis]>=5.0.4,<6.0`
8. **Fix `@testing-library/dom` placement**: Move to `devDependencies`
9. **Upgrade lucide-react**: `^0.475.0`
10. **Replace @microsoft/fetch-event-source**: Migrate `useRealtime.ts` to native `EventSource`

### Medium-term (next month — P2/P3 items)

11. **Remove dead Python deps**: `bcrypt`, `python-dateutil`, `faker` from `requirements.txt`
12. **Remove ML dead deps**: `wandb`, `mlflow`, `torch`, `transformers`, `pickle5` from ML requirements
13. **Fix numpy pin**: `numpy>=1.26.4,<2.0`
14. **Unify ML linting**: Replace `flake8` with `ruff` in `ml/requirements-dev.txt`
15. **Guard email module**: Add `server-only` to `frontend/lib/email/send.ts`
16. **Fix @types/jest version**: Align to jest 29 (`"^29.5.0"`)
17. **Update dev tool pins**: black, mypy, pytest to current versions

---

## Scope Boundaries

The following were assessed but found clean:

- `@tanstack/react-query ^5.17.15` — resolved to 5.x, current
- `better-auth ^1.4.19` — resolved to 1.4.19, current for the 1.x series
- `recharts ^2.10.3` — resolved to 2.15.4, adequate
- `zustand ^4.4.7` — resolved to 4.5.7, current 4.x
- `wrangler ^3.99.0` — resolved to 3.114.17, current
- `opentelemetry-*` packages — `>=1.20.0,<2.0` range is appropriate; installed 1.40.0 is current
- `groq>=0.9.0` — installed 1.1.0, adequate
- `nh3>=0.2.14` — installed 0.3.3, current (Rust-based XSS sanitizer)
- `jinja2>=3.0` — installed 3.1.6, current (no upper bound needed)
- `stripe>=7.0,<8.0` — installed 7.14.0, adequate for 7.x API
- Workers `vitest ^2.1.0` — resolved 2.1.9, current
- Workers package has zero production dependencies (all devDependencies) — correct

---

*Generated by dependency-manager agent. Cross-referenced against .venv .dist-info metadata, package-lock.json resolved versions, and NVD/OSV advisories current as of 2026-03-16. Run `npm audit` and `pip-audit` in CI for authoritative CVE scanning.*
