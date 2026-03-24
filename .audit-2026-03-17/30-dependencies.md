# Audit Report: Dependencies
## Date: 2026-03-17

---

### Executive Summary

The RateShift dependency tree is in generally good shape following the Dependency Upgrade Track completed on 2026-03-17. Core production dependencies (Next.js 16, React 19, FastAPI, Pydantic v2, SQLAlchemy 2.x, Stripe v14, Sentry v2) are all at current major versions. The pip-audit baseline is clean and the npm audit previously confirmed 0 HIGH/CRITICAL issues.

Three areas require attention before launch:

1. **`@excalidraw/excalidraw` is a `devDependency` shipping vulnerable transitive packages** (`nanoid 3.3.3`, CVE-2021-23566). Because Excalidraw is loaded via dynamic import behind a dev-only route guard (`notFound()` in production), the runtime attack surface is absent — but the npm audit advisory count is owned by this package and the `nanoid 3.3.3` pinned copy cannot be overridden without forking the upstream lock file.

2. **`requirements.prod.txt` is severely stale and version-diverged from `backend/requirements.txt`**. It references `uvicorn==0.27.0` (current: 0.42.0), `redis==5.0.1` (current: 7.x), `sqlalchemy==2.0.25` (current: 2.0.48), `pydantic-settings==2.2.0` (current: 2.13.1), and `numpy==1.26.3` (behind the `>=2.0` constraint in the main file). If this file is ever activated, it will run with a version set that lags the test suite by months and has likely already received security patches.

3. **ESLint 8.57.1** is explicitly deprecated (`"This version is no longer supported"`) in its own npm install output. The upgrade to ESLint v9/v10 was deliberately deferred but should be tracked as a scheduled item.

Outside these three areas, no P0-level known CVEs with active exploits were found in directly-depended-upon packages.

---

### Findings

#### P0 — Critical

No P0 findings. No known CVEs with active exploits were found in directly-used runtime packages. The `nanoid 3.3.3` vulnerability (CVE-2021-23566) is inside a `devDependency` nested within `@excalidraw/excalidraw`, which itself is guarded by `notFound()` in production builds. It does not reach production runtime. Reclassify to P1 if the dev guard is ever relaxed.

---

#### P1 — High

**P1-01: `nanoid 3.3.3` pinned inside `@excalidraw/excalidraw` — CVE-2021-23566**

- **Package**: `node_modules/@excalidraw/excalidraw/node_modules/nanoid` — version `3.3.3`
- **Vulnerability**: CVE-2021-23566 (moderate) — predictable random IDs when `customAlphabet` is called with a non-power-of-2 alphabet length in affected nanoid 3.x versions below 3.3.4.
- **Source**: `@excalidraw/excalidraw@0.18.0` pins `nanoid@3.3.3` in its own nested `node_modules`. npm cannot hoist a fix without a lockfile change in the excalidraw package itself.
- **A second copy**: `@excalidraw/mermaid-to-excalidraw` pins `nanoid@4.0.2` (not vulnerable).
- **Risk context**: `@excalidraw/excalidraw` is declared as a `devDependency` and is loaded only inside `frontend/components/dev/ExcalidrawWrapper.tsx` via `next/dynamic` with `ssr: false`. The component file confirms it is dev-only and guarded via `notFound()` at the route level. The vulnerable nanoid copy is never imported by production bundles.
- **Action**: This is the primary driver of the 5 remaining npm audit advisories noted in project context. The fix requires `@excalidraw/excalidraw` to release an update that bumps its internal nanoid. Monitor `@excalidraw/excalidraw` releases. If a version `>0.18.0` is released with nanoid `>=3.3.4`, upgrade. As a fallback, consider replacing the Excalidraw integration with an alternative diagram tool if no update arrives within 60 days of launch.
- **Short-term mitigation**: Add an `overrides` entry in `frontend/package.json` to force-resolve `nanoid` to `>=3.3.4` globally. Note this may break Excalidraw's own rendering in the dev environment — test manually.

```json
// frontend/package.json
"overrides": {
  "nanoid": "^3.3.11"
}
```

**P1-02: `requirements.prod.txt` is severely stale — version skew risk**

- **File**: `backend/requirements.prod.txt`
- **Issue**: This file was last updated when the project was still using uvicorn 0.27, redis 5.0.1, SQLAlchemy 2.0.25, pydantic-settings 2.2.0, and numpy 1.26.3. The canonical `backend/requirements.txt` has moved to uvicorn 0.42.0, redis 7.x, SQLAlchemy 2.0.48, pydantic-settings 2.13.1, and numpy >=2.0. The delta spans 3-15 months of upstream releases across security-sensitive packages.
- **Specific stale entries and their risks**:
  - `uvicorn==0.27.0` — Many CVE fixes and HTTP/1.1 request-smuggling hardening were merged between 0.27 and 0.42. (15 minor/patch releases behind.)
  - `redis==5.0.1` — Jumped two major versions (5.x → 7.x) in the main file. The Lua TTL bug fix described in CLAUDE.md patterns was applied to the production codebase; if prod ever used the old redis client it may lack the corresponding server-side fix awareness.
  - `sqlalchemy==2.0.25` — 23 patch releases behind 2.0.48; includes async pool and type-coercion bug fixes.
  - `numpy==1.26.3` — Pinned at a version that is incompatible with the `>=2.0,<3.0` constraint now in the main requirements file, creating an install conflict if both files are used together.
  - `sentry-sdk` — Commented out entirely in prod file; Sentry v2 auto-instrumentation was a major upgrade tracked in milestones.
- **Action**: Either delete `requirements.prod.txt` (if it is dead code — verify in `render.yaml` and Dockerfile), or sync it to match `backend/requirements.txt`. The "minimal footprint" goal it serves is worth preserving but must be kept synchronized.

```bash
# Verify if render.yaml references requirements.prod.txt
grep -r "requirements.prod" /Users/devinmcgrath/projects/electricity-optimizer/
```

**P1-03: ESLint 8.57.1 — explicitly deprecated upstream**

- **Package**: `eslint@8.57.1` (locked), `eslint-config-next@16.0.7`
- **Issue**: npm outputs `"This version is no longer supported. Please see https://eslint.org/version-support for other options."` on every install. ESLint 8.x reached EOL; no further security patches will be backported to this branch. The project deferred ESLint v10 to a separate track.
- **Risk**: Any future ESLint plugin CVE will not receive a patch for v8. Additionally, the `@typescript-eslint` rule set for ESLint 8 may have unpatched rules that allow bypassing lint checks on security-relevant patterns (e.g., unsafe type assertions).
- **Action**: Schedule the ESLint v9/v10 migration track within the next 30 days. ESLint v9 has a compatibility utility (`@eslint/eslintrc`) that converts legacy flat-config. Next.js 16 `eslint-config-next` already ships v9-compatible defaults.

---

#### P2 — Medium

**P2-01: `@playwright/test` pinned at `^1.40.1`, resolved to `1.58.2` — version divergence**

- **Package**: `@playwright/test@1.40.1` (declared min) vs `1.58.2` (installed). The lock file resolves to a version 18 patch releases ahead of the declared minimum.
- **Issue**: The declared range `^1.40.1` means any developer running `npm install` on a fresh clone will install `1.58.2` (the current latest within that range), which is fine. However, CI likely pins the installed version from the lockfile. This is not a vulnerability — it is a documentation hygiene issue. The declared version in `package.json` should match the team's actual minimum tested version.
- **Action**: Update `@playwright/test` declared version to `^1.58.2` to reflect the actual installed baseline. Low-risk change.

**P2-02: `tailwindcss@3.4.1` declared while v4 is current**

- **Package**: `tailwindcss@3.4.19` (installed, latest v3 patch), declared `^3.4.1`
- **Issue**: Tailwind CSS v4 (released 2025) is a major version with significant architecture changes (CSS-first config, oxide engine). The project is currently on the last v3 patch series, which will continue to receive security backports for a limited period. There is no active CVE, but v4 brings breaking changes to the `@apply` directive and config format that will require a migration effort. Deferring longer increases migration complexity.
- **Action**: Evaluate Tailwind v4 migration within 60–90 days. The `tailwind-merge@3.5.0` dependency already supports v4 syntax. `autoprefixer@10.4.27` is compatible with both.

**P2-03: `@types/node@20.11.5` declared while Node.js 22 LTS is current**

- **Package**: `@types/node@^20.11.5`
- **Issue**: Node.js 20 LTS (Hydrogen) reached maintenance mode on 2025-10-28 and will reach EOL on 2026-04-30. Node.js 22 LTS (Jod) is the current active LTS. The types package should track the Node version actually targeted in CI and deployment.
- **Action**: Update to `@types/node@^22` when the runtime is upgraded. Check `engines` field in `package.json` and the Vercel Node.js version setting.

**P2-04: `tensorflow>=2.15.0,<2.17.0` in `requirements-ml.txt` — capped below current stable**

- **File**: `requirements-ml.txt` (root)
- **Version cap**: `<2.17.0`
- **Issue**: TensorFlow 2.17 released in 2024 included security hardening in the C++ runtime layer and ML model deserialization (important for `.h5` / `SavedModel` files loaded from untrusted sources). The `ml/requirements-ml.txt` file is more permissive (`<3.0`) and does not have this issue. The root-level `requirements-ml.txt` is the more constrained one.
- **Action**: Align both ML requirements files. Prefer `ml/requirements-ml.txt` as the canonical source and either remove the root-level file or have it reference the canonical one.

**P2-05: `pickle5>=0.0.12` in `ml/requirements-ml.txt` — legacy backport, likely unneeded**

- **Package**: `pickle5>=0.0.12`
- **Issue**: `pickle5` is a backport of Python 3.8's pickle protocol 5 for Python 3.6/3.7. The project uses Python 3.12, where pickle protocol 5 is built-in. The `pickle5` package is therefore dead code. More importantly, it introduces a redundant serialization pathway that could cause confusion during security audits (pickle deserialization of untrusted data is a classic RCE vector). Having the package installed signals that it might be used somewhere.
- **Action**: Remove `pickle5` from `ml/requirements-ml.txt`. Verify no code imports it with `grep -r "import pickle5"`.

**P2-06: `@excalidraw/excalidraw@0.18.0` is in `devDependencies` but referenced in production component tree**

- **File**: `frontend/components/dev/ExcalidrawWrapper.tsx`
- **Issue**: The component is inside `frontend/components/dev/`, not `frontend/components/`, and uses `next/dynamic` with `ssr: false`. The route-level `notFound()` guard should prevent it from appearing in production. However, `devDependencies` in a Next.js project are included in the build step (since `next build` runs in the dev environment on CI), so the excalidraw package *is* bundled during build even if tree-shaken at runtime. Verify that Next.js actually tree-shakes this out of the production bundle.
- **Action**: Confirm with `next build --analyze` (using `@next/bundle-analyzer`) that `@excalidraw/excalidraw` does not appear in any production chunk. If it does, move it behind an environment-variable feature flag at the dynamic import level, not just a route guard.

---

#### P3 — Low

**P3-01: `mkdocs==1.5.3` and `mkdocs-material==9.5.4` in `requirements-dev.txt` — outdated**

- **Installed**: mkdocs 1.5.3 (current: 1.6.x), mkdocs-material 9.5.4 (current: 9.6.x)
- **Issue**: Minor version behind; no known CVEs. The docs are not served externally so the blast radius of any future vulnerability is minimal.
- **Action**: Bump to latest minor at next dev environment refresh. Low priority.

**P3-02: `safety>=3.0.0,<4.0.0` in `requirements-dev.txt` — version cap may miss patches**

- **Package**: `safety` (PyPI vulnerability scanner)
- **Issue**: The `<4.0.0` upper bound may prevent picking up `3.x` patch releases that update the CVE database. The `safety` database is consulted during CI; a stale database means missed vulnerabilities.
- **Action**: Change to `safety>=3.0.0` (no upper cap) or pin to the current latest minor `>=3.3.0` to ensure the vulnerability database stays fresh with patch releases.

**P3-03: `@microsoft/fetch-event-source@2.0.1` — unmaintained upstream**

- **Package**: `@microsoft/fetch-event-source@^2.0.1` (resolved 2.0.1, last published 2021)
- **Issue**: This package has had no releases since 2021. The GitHub repo is archived/read-only. For the SSE streaming use case (AI agent queries via `POST /agent/query`), this dependency is functional but unsupported. Any future browser API change or fetch spec update will not be patched.
- **Action**: Evaluate replacing with the browser-native `EventSource` API or a maintained alternative such as `eventsource-parser` (used by Vercel's AI SDK). The risk is low today but will compound over time.

**P3-04: `react-onesignal@3.5.1` — thin wrapper over SDK with infrequent releases**

- **Package**: `react-onesignal@^3.5.1`
- **Issue**: This is a React wrapper around the OneSignal Web SDK. Version 3.5.1 has no known CVEs, but the package has infrequent updates and depends on the external OneSignal CDN script loading. If OneSignal's CDN is unavailable, push notification registration silently fails (acceptable UX degradation), but there is no pinning of the CDN script version. This is a supply-chain hygiene note, not an active vulnerability.
- **Action**: Review OneSignal's Subresource Integrity (SRI) hash support for the CDN script. Document the fail-open behavior in `known-issues.md`.

**P3-05: `legacy-peer-deps=true` in `frontend/.npmrc` — masks peer dependency conflicts**

- **File**: `frontend/.npmrc`
- **Setting**: `legacy-peer-deps=true`
- **Issue**: This flag was added to resolve `eslint@8` vs `eslint-config-next@16.x` peer conflicts. While appropriate as a temporary measure, it instructs npm to silently ignore all peer dependency constraint violations, meaning future package additions could silently install incompatible versions without warning.
- **Action**: Once ESLint v9/v10 migration is complete (see P1-03), remove `legacy-peer-deps=true` and resolve the peer dependency tree cleanly. Until then, document the specific conflict it addresses in a comment inside `.npmrc`.

**P3-06: `@cloudflare/workers-types@4.20241230.0` — dated snapshot in CF Worker**

- **File**: `workers/api-gateway/package.json`
- **Version**: `^4.20241230.0` (date-versioned, from 2024-12-30)
- **Issue**: Cloudflare Workers types are date-versioned snapshots. Three months of CF runtime API additions (including any new binding types) may be missing from the current type definitions. No CVEs, but missing types can cause silent `any` inference for new CF APIs used in the worker.
- **Action**: Update to the current snapshot (`npm update @cloudflare/workers-types` in the workers directory) and regenerate types. Run `tsc --noEmit` to catch any newly typed breaking changes.

**P3-07: Duplicate `pytest` declarations across requirements files**

- **Files**: `backend/requirements-dev.txt` (pytest==9.0.2), `ml/requirements-dev.txt` (pytest>=7.4.0), `ml/requirements-ml.txt` (pytest>=7.4.0), `tests/load/requirements.txt` (unknown)
- **Issue**: Multiple requirements files pin pytest at different constraint levels. If installed in the same virtual environment, pip will use the most restrictive constraint. The ML files allow pytest 7.4+ while the backend dev file pins to 9.0.2. This creates an inconsistency where ML test authors may assume pytest 7.x behavior while backend tests use pytest 9.x features.
- **Action**: Standardize on a single pytest constraint across all requirements files, or use a root-level `pyproject.toml` / `tox.ini` to unify test dependencies. Currently `pytest 9.0.2` from `backend/requirements-dev.txt` will dominate in a shared venv.

**P3-08: `openapi-typescript@7.13.0` — may lag behind current v7 release**

- **Package**: `openapi-typescript@^7.13.0` (devDependency)
- **Issue**: No CVEs. The generated API types are used by the frontend for type safety against the backend contract. Stale types generation tooling can produce subtly wrong output for newer OpenAPI spec features.
- **Action**: Check if a `7.x` release beyond `7.13.0` is available and update accordingly at next dev dependency refresh.

---

### Statistics

| Category | Count |
|----------|-------|
| P0 — Critical | 0 |
| P1 — High | 3 |
| P2 — Medium | 6 |
| P3 — Low | 8 |
| **Total findings** | **17** |

#### Package Counts

| Layer | File | Direct Deps |
|-------|------|-------------|
| Frontend (runtime) | `frontend/package.json` dependencies | 16 |
| Frontend (dev) | `frontend/package.json` devDependencies | 19 |
| Backend (prod) | `backend/requirements.txt` | 30 |
| Backend (dev) | `backend/requirements-dev.txt` | 21 |
| Backend (prod alt) | `backend/requirements.prod.txt` | 12 (stale) |
| ML (root) | `requirements-ml.txt` | 30 |
| ML (ml/) | `ml/requirements-ml.txt` | 25 |
| CF Worker | `workers/api-gateway/package.json` devDependencies | 4 |

#### npm audit (as of last run)
- Total advisories: **5** (all @excalidraw transitive)
- HIGH/CRITICAL: **0**
- All in `devDependencies`, not reachable at production runtime

#### pip-audit
- Status: **Clean** (0 known CVEs in installed packages per project context)

#### Key Version Status

| Package | Declared | Installed | Latest Major | Status |
|---------|----------|-----------|--------------|--------|
| Next.js | ^16.0.7 | 16.1.6 | 16 | Current |
| React | ^19.0.0 | 19.x | 19 | Current |
| TypeScript (frontend) | ^5.3.3 | 5.9.3 | 5 | Current |
| ESLint | ^8.56.0 | 8.57.1 | 9/10 | **EOL — P1** |
| Tailwind CSS | ^3.4.1 | 3.4.19 | 4 | Behind major — P2 |
| @playwright/test | ^1.40.1 | 1.58.2 | 1.58 | Declared min stale — P2 |
| better-auth | ^1.5.5 | 1.5.5 | 1.5.5 | Current |
| zustand | ^5.0.12 | 5.x | 5 | Current |
| recharts | ^3.8.0 | 3.x | 3 | Current |
| FastAPI | >=0.115.0 | 0.115.x | 0.115 | Current |
| SQLAlchemy | 2.0.48 | 2.0.48 | 2 | Current |
| Pydantic | 2.12.5 | 2.12.5 | 2 | Current |
| Stripe SDK | >=14.0,<15.0 | 14.x | 14 | Current |
| Sentry SDK | >=2.0,<3.0 | 2.x | 2 | Current |
| uvicorn (prod) | 0.42.0 (main) / **0.27.0 (prod file)** | varies | 0.42 | **P1: prod file stale** |
| tensorflow (root ML) | >=2.15.0,<2.17.0 | 2.16.x | 2.19 | P2: capped below patches |

---

### Recommended Action Order

1. **Immediate (before launch)**: Investigate `requirements.prod.txt` usage — if it is referenced by `render.yaml` or a Dockerfile, sync or delete it (P1-02).
2. **Before launch**: Add `overrides.nanoid` to `frontend/package.json` and verify excalidraw dev-only guard with bundle analysis (P1-01, P2-06).
3. **Sprint 1 post-launch**: Schedule ESLint v9 migration track (P1-03).
4. **Sprint 1 post-launch**: Remove `pickle5` from ML requirements, align TF version caps, consolidate ML requirements files (P2-04, P2-05, P3-07).
5. **Sprint 2 post-launch**: Evaluate replacing `@microsoft/fetch-event-source` with a maintained alternative (P3-03). Update `@cloudflare/workers-types` snapshot (P3-06).
6. **Ongoing**: Remove `legacy-peer-deps=true` after ESLint migration. Update `safety` upper cap in dev requirements.
