# Dependency Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remediate 13 npm vulnerabilities (3 HIGH), upgrade 73 outdated Python packages and 16 outdated npm packages, with zero test regressions and staged deployment validation.

**Architecture:** Four-phase approach — Phase 1 fixes security vulns and safe patches; Phase 2 handles medium-risk backend upgrades (sentry, stripe, redis); Phase 3 tackles frontend major versions (tailwind, zustand, recharts); Phase 4 upgrades the ML stack (numpy, pandas). Each phase is a separate commit with full test suite validation. Dependabot continues handling minor/patch after this.

**Tech Stack:** Python 3.12 (FastAPI), Node.js (Next.js 16 + React 19), pip + npm, pytest + jest, Dependabot (weekly Monday minor/patch)

**Conductor Track:** `dependency-upgrade_20260317`

---

## Pre-flight: Snapshot Current State

### Task 0: Baseline Test Counts

**Files:**
- Read: `backend/requirements.txt`
- Read: `backend/requirements-dev.txt`
- Read: `frontend/package.json`

**Step 1: Run full backend test suite and record count**

Run: `.venv/bin/python -m pytest backend/tests/ -x -q --tb=short 2>&1 | tail -5`
Expected: 2,663 passed

**Step 2: Run full frontend test suite and record count**

Run: `cd frontend && npm test -- --ci --watchAll=false 2>&1 | tail -10`
Expected: 2,024 tests (152 suites)

**Step 3: Record npm audit baseline**

Run: `cd frontend && npm audit 2>&1 | tail -5`
Expected: 13 vulnerabilities (4 low, 6 moderate, 3 high)

**Step 4: Record pip-audit baseline**

Run: `.venv/bin/python -m pip_audit -r backend/requirements.txt 2>&1 | tail -3`
Expected: No known vulnerabilities found

---

## Phase 1: Security Fixes + Safe Patches (Low Risk)

### Task 1: Upgrade jest to v30 (fixes 7 of 13 npm vulns)

**Files:**
- Modify: `frontend/package.json` (lines 51-53: jest, jest-environment-jsdom, @types/jest)
- Modify: `frontend/jest.config.js` (if any API changes)
- Test: All frontend test suites

**Step 1: Update package.json jest versions**

Change in `frontend/package.json`:
```json
"jest": "^30.3.0",
"jest-environment-jsdom": "^30.3.0",
"@types/jest": "^30.0.0",
```

These should already be in package.json at these caret ranges. The installed versions are locked to 29.x. We need to update `package-lock.json`.

**Step 2: Install updated packages**

Run: `cd frontend && npm install`
Expected: jest@30.x installed, lock file updated

**Step 3: Check for jest 30 breaking changes in config**

Read `frontend/jest.config.js` — jest 30 changes:
- `moduleNameMapper` syntax is the same
- `testEnvironment: 'jsdom'` is the same
- `transform` config may need update if using custom transformers
- `fakeTimers` config is the same

Most configs work unchanged. Fix any issues found.

**Step 4: Run full frontend test suite**

Run: `cd frontend && npm test -- --ci --watchAll=false 2>&1 | tail -20`
Expected: 2,024 tests passing (152 suites). Fix any failures.

**Step 5: Verify npm audit improvement**

Run: `cd frontend && npm audit 2>&1 | tail -5`
Expected: 7 fewer vulnerabilities (minimatch, flatted, immutable, @tootallnate/once, jsdom, http-proxy-agent chain resolved)

**Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/jest.config.js
git commit -m "chore(deps): upgrade jest 29→30, fix 7 npm vulnerabilities

Resolves: minimatch ReDoS (HIGH), flatted DoS (HIGH), immutable
prototype pollution (HIGH), jsdom transitive chain (4 LOW)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 2: Upgrade safe Python patch versions

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/requirements-dev.txt`
- Test: Full backend test suite

**Step 1: Bump patch/minor versions in requirements.txt**

Update these pins (all non-breaking):
```
# requirements.txt changes:
uvicorn[standard]==0.42.0          # was 0.27.0 (minor, no breaking)
pydantic-settings==2.13.1          # was 2.2.0 (minor, settings API stable)
asyncpg==0.31.0                    # was 0.29.0 (minor, connection pool fixes)
sqlalchemy[asyncio]==2.0.48        # was 2.0.25 (patch, bug fixes)
email-validator==2.3.0             # was 2.1.0 (minor, validation fixes)
python-dateutil==2.9.0.post0       # was 2.8.2 (minor)
prometheus-client==0.24.1          # was 0.19.0 (minor, new metrics)
structlog==25.5.0                  # was 24.1.0 (minor, new processors)
```

**Step 2: Bump patch/minor versions in requirements-dev.txt**

```
# requirements-dev.txt changes:
pytest-mock==3.15.1                # was 3.12.0
pytest-timeout==2.4.0              # was 2.2.0
pytest-xdist==3.8.0                # was 3.5.0
faker==40.11.0                     # was 22.0.0 (minor API, providers stable)
factory-boy==3.3.3                 # was 3.3.0
freezegun==1.5.5                   # was 1.4.0
types-python-dateutil==2.9.0.20260305  # was 2.8.19.14
rich==14.3.3                       # was 13.7.0 (minor, console API stable)
pre-commit==4.5.1                  # was 3.6.0 (minor, hook runner stable)
```

**Step 3: Install updated packages**

Run: `.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt -q`
Expected: Clean install, no conflicts

**Step 4: Run full backend test suite**

Run: `.venv/bin/python -m pytest backend/tests/ -x -q --tb=short 2>&1 | tail -5`
Expected: 2,663 passed

**Step 5: Commit**

```bash
git add backend/requirements.txt backend/requirements-dev.txt
git commit -m "chore(deps): bump 17 Python packages to latest minor/patch

SQLAlchemy 2.0.48, asyncpg 0.31, uvicorn 0.42, pydantic-settings 2.13,
structlog 25.5, pytest-mock 3.15, faker 40.11, and 10 more.
All non-breaking. 2,663 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 3: Bump safe frontend minor versions

**Files:**
- Modify: `frontend/package.json`
- Test: Full frontend test suite

**Step 1: Update package.json with safe bumps**

```json
"@tanstack/react-query": "^5.90.21",
"nodemailer": "^8.0.2",
"resend": "^6.9.4",
"autoprefixer": "^10.4.27",
"postcss": "^8.5.8",
"@testing-library/jest-dom": "^6.9.1",
"@testing-library/react": "^16.3.2",
"@testing-library/user-event": "^14.6.1",
"@types/node": "^20.19.37",
"@types/react": "^19.2.14",
"@types/react-dom": "^19.2.3",
```

Note: Keep `@types/node` on v20 (v25 may cause type conflicts with Next.js).

**Step 2: Install**

Run: `cd frontend && npm install`

**Step 3: Run tests**

Run: `cd frontend && npm test -- --ci --watchAll=false 2>&1 | tail -10`
Expected: 2,024 tests passing

**Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(deps): bump 11 frontend packages to latest minor/patch

react-query 5.90, testing-library updates, postcss 8.5.8, types updates.
All non-breaking. 2,024 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 4: Update httpx version cap

**Files:**
- Modify: `backend/requirements.txt` (line 15)
- Modify: `backend/requirements-dev.txt` (line 8)
- Test: Full backend test suite

**Step 1: Bump httpx cap**

In `backend/requirements.txt`:
```
httpx>=0.26,<0.29
```

In `backend/requirements-dev.txt`:
```
httpx>=0.26,<0.29
```

httpx 0.28 changes: `follow_redirects` default changed from `False` to `True`. Audit all `httpx.AsyncClient()` calls to ensure redirect behavior is explicit.

**Step 2: Search for httpx usage without explicit follow_redirects**

Run: `grep -rn "AsyncClient\|httpx.get\|httpx.post" backend/ --include="*.py" | grep -v test | grep -v __pycache__`

For each call, verify `follow_redirects` is set explicitly or the default change is acceptable.

**Step 3: Install and test**

Run: `.venv/bin/pip install -r backend/requirements.txt -q && .venv/bin/python -m pytest backend/tests/ -x -q --tb=short 2>&1 | tail -5`
Expected: 2,663 passed

**Step 4: Commit**

```bash
git add backend/requirements.txt backend/requirements-dev.txt
git commit -m "chore(deps): bump httpx cap to <0.29

follow_redirects default change audited. All 2,663 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 2: Medium-Risk Backend Upgrades (Staging Test Required)

### Task 5: Upgrade Sentry SDK v1 → v2

**Files:**
- Modify: `backend/requirements.txt` (line 31)
- Modify: `backend/main.py` (sentry init)
- Modify: `backend/services/*.py` (any `sentry_sdk.capture_*` calls)
- Test: Full backend test suite

**Step 1: Read current Sentry init**

Read `backend/main.py` and find the `sentry_sdk.init()` block.

**Step 2: Update requirements.txt**

```
sentry-sdk[fastapi]>=2.0,<3.0
```

**Step 3: Update Sentry init for v2**

Key v2 changes:
- `sentry_sdk.init()` — `traces_sample_rate` and `profiles_sample_rate` are the same
- `integrations` list: FastAPI integration auto-detected in v2 (can remove explicit import)
- `before_send` callback signature unchanged
- `sentry_sdk.Hub` removed — use `sentry_sdk.Scope` instead
- `sentry_sdk.configure_scope()` → `sentry_sdk.new_scope()` or `sentry_sdk.get_current_scope()`

Search for deprecated patterns:
```bash
grep -rn "Hub\|configure_scope\|push_scope" backend/ --include="*.py" | grep -v __pycache__
```

Update each occurrence.

**Step 4: Install and test**

Run: `.venv/bin/pip install "sentry-sdk[fastapi]>=2.0,<3.0" && .venv/bin/python -m pytest backend/tests/ -x -q --tb=short`
Expected: 2,663 passed

**Step 5: Commit**

```bash
git add backend/requirements.txt backend/main.py backend/services/
git commit -m "chore(deps): upgrade sentry-sdk v1→v2

Migrated Hub→Scope, configure_scope→get_current_scope,
auto-detection for FastAPI integration. 2,663 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 6: Upgrade Stripe v7 → v14

**Files:**
- Modify: `backend/requirements.txt` (line 45)
- Modify: `backend/services/stripe_service.py`
- Modify: `backend/api/v1/webhooks.py`
- Test: All stripe-related tests

**Step 1: Read current Stripe integration**

Read:
- `backend/services/stripe_service.py`
- `backend/api/v1/webhooks.py`
- `backend/tests/test_stripe*.py`

**Step 2: Update requirements.txt**

```
stripe>=14.0,<15.0
```

**Step 3: Migrate Stripe API changes**

Key changes v7→v14:
- `stripe.api_key = ...` still works but `stripe.StripeClient(api_key)` is preferred
- Webhook signature verification: `stripe.Webhook.construct_event()` unchanged
- `stripe.Customer.create()` → `client.customers.create()`  (new pattern, old still works in v14)
- Event types unchanged for `invoice.payment_failed`, `customer.subscription.updated`
- `stripe.Subscription` → response objects are now typed differently

Strategy: Keep existing `stripe.api_key` pattern for now (still supported in v14). Focus on ensuring webhook payload shapes haven't changed.

**Step 4: Run Stripe-specific tests first**

Run: `.venv/bin/python -m pytest backend/tests/ -k "stripe" -v --tb=short`
Expected: All stripe tests pass

**Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest backend/tests/ -x -q --tb=short`
Expected: 2,663 passed

**Step 6: Commit**

```bash
git add backend/requirements.txt backend/services/stripe_service.py backend/api/v1/webhooks.py
git commit -m "chore(deps): upgrade stripe v7→v14

Validated webhook signatures, subscription events, payment flows.
Module-level stripe.api_key pattern retained (still supported).
All stripe tests + full suite passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 7: Upgrade Redis v5 → v7

**Files:**
- Modify: `backend/requirements.txt` (line 13)
- Modify: `backend/services/cache_service.py` (or wherever Redis client is created)
- Modify: Any files using Redis Lua scripts
- Test: Full backend test suite

**Step 1: Read Redis usage**

```bash
grep -rn "redis\.\|Redis\|aioredis" backend/ --include="*.py" | grep -v __pycache__ | grep -v test
```

**Step 2: Update requirements.txt**

```
redis[hiredis]>=7.0,<8.0
```

**Step 3: Migrate Redis API changes**

Key changes v5→v7:
- `Redis()` constructor args unchanged
- `redis.StrictRedis` → just `redis.Redis` (StrictRedis was alias, now deprecated)
- Lua script `EVALSHA`/`EVAL` unchanged
- Connection pool: `redis.ConnectionPool` API unchanged
- Async: `redis.asyncio.Redis` API unchanged
- `decode_responses` default unchanged (False)

Search for deprecated patterns:
```bash
grep -rn "StrictRedis" backend/ --include="*.py" | grep -v __pycache__
```

**Step 4: Test Redis-specific functionality**

Run: `.venv/bin/python -m pytest backend/tests/ -k "redis or cache or rate_limit" -v --tb=short`
Expected: All pass (especially Lua rate limiter scripts)

**Step 5: Full test suite**

Run: `.venv/bin/python -m pytest backend/tests/ -x -q --tb=short`
Expected: 2,663 passed

**Step 6: Commit**

```bash
git add backend/requirements.txt backend/services/
git commit -m "chore(deps): upgrade redis v5→v7

StrictRedis→Redis migration (if any), Lua scripts validated,
connection pool + async client confirmed working. 2,663 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 8: Upgrade remaining backend tools

**Files:**
- Modify: `backend/requirements-dev.txt`
- Test: Full backend test suite + linting

**Step 1: Bump dev tool major versions**

```
# requirements-dev.txt updates:
pytest==9.0.2              # was 7.4.4 — pytest 9 drops Python 3.8 (we're 3.12, fine)
pytest-cov==7.0.0          # was 4.1.0 — API unchanged
pytest-asyncio==1.3.0      # was 0.23.3 — auto mode default change (check)
ruff==0.15.6               # was 0.1.14 — rule codes may change
black==26.3.1              # was 23.12.1 — formatting tweaks
isort==8.0.1               # was 5.13.2 — config format change
mypy==1.19.1               # was 1.8.0 — stricter checks possible
bandit==1.9.4              # was 1.7.6 — new rules
```

**Step 2: Handle pytest-asyncio mode change**

pytest-asyncio 1.x changes `mode` default from `strict` to `auto`. Check `pyproject.toml` or `pytest.ini` for existing config:
```bash
grep -n "asyncio_mode" backend/pyproject.toml backend/pytest.ini backend/setup.cfg 2>/dev/null
```

If no explicit mode set, add to config:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

**Step 3: Handle isort v8 config**

isort v8 changes: `profile` setting works the same, but check `.isort.cfg` or `pyproject.toml`.

**Step 4: Install and run linting first**

```bash
.venv/bin/pip install -r backend/requirements-dev.txt -q
.venv/bin/python -m black --check backend/ 2>&1 | tail -5
.venv/bin/python -m isort --check-only backend/ 2>&1 | tail -5
```

Fix any formatting differences (black 26 may reformat some edge cases).

**Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest backend/tests/ -x -q --tb=short`
Expected: 2,663 passed

**Step 6: Commit**

```bash
git add backend/requirements-dev.txt backend/pyproject.toml
git commit -m "chore(deps): upgrade dev tools — pytest 9, ruff 0.15, black 26, isort 8

pytest-asyncio mode=auto, formatting normalized, mypy 1.19 clean.
2,663 tests passing, linting clean.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Phase 3: Frontend Major Version Upgrades

### Task 9: Upgrade lucide-react

**Files:**
- Modify: `frontend/package.json`
- Modify: Any files with renamed icons
- Test: Frontend test suite + visual check

**Step 1: Update package.json**

```json
"lucide-react": "^0.577.0",
```

**Step 2: Install and check for renamed icons**

Run: `cd frontend && npm install`

Check for import errors:
Run: `cd frontend && npx tsc --noEmit 2>&1 | head -30`

lucide-react renames icons periodically. Fix any import errors by checking the lucide changelog.

**Step 3: Run tests**

Run: `cd frontend && npm test -- --ci --watchAll=false`
Expected: 2,024 passing

**Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/
git commit -m "chore(deps): upgrade lucide-react 0.309→0.577

Icon import renames applied (if any). 2,024 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 10: Upgrade better-auth

**Files:**
- Modify: `frontend/package.json`
- Test: Auth-related tests + E2E login flow

**Step 1: Update package.json**

```json
"better-auth": "^1.5.5",
```

**Step 2: Install**

Run: `cd frontend && npm install`

**Step 3: Check for API changes**

better-auth 1.4→1.5 is minor. The `{data, error}` pattern is unchanged. Check:
```bash
grep -rn "authClient\|useSession\|signIn\|signUp" frontend/src/ --include="*.ts" --include="*.tsx" | head -20
```

**Step 4: Run tests**

Run: `cd frontend && npm test -- --ci --watchAll=false`
Expected: 2,024 passing

**Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(deps): upgrade better-auth 1.4→1.5

Minor version, {data, error} API pattern unchanged. 2,024 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 11: Upgrade zustand v4 → v5

**Files:**
- Modify: `frontend/package.json`
- Modify: All zustand store files
- Test: Frontend test suite

**Step 1: Read existing stores**

```bash
grep -rn "create(" frontend/src/ --include="*.ts" --include="*.tsx" | grep -i zustand
```

**Step 2: Update package.json**

```json
"zustand": "^5.0.12",
```

**Step 3: Migrate zustand v5 changes**

Key changes:
- `create` no longer accepts a function directly; requires `(set, get) => ({...})` (same as v4)
- `devtools`, `persist` middleware unchanged
- TypeScript: `StateCreator` type updated
- `useStore` hook unchanged
- `getState()`, `setState()`, `subscribe()` unchanged

Most v4 stores work unchanged. Check for edge cases.

**Step 4: Install and test**

Run: `cd frontend && npm install && npm test -- --ci --watchAll=false`
Expected: 2,024 passing

**Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/
git commit -m "chore(deps): upgrade zustand v4→v5

Store patterns validated, middleware compatible. 2,024 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 12: Upgrade date-fns v3 → v4

**Files:**
- Modify: `frontend/package.json`
- Test: Frontend test suite

**Step 1: Update package.json**

```json
"date-fns": "^4.1.0",
```

**Step 2: Check for breaking changes**

date-fns v4 changes:
- All functions now export from `date-fns` (same as v3)
- Some locale imports changed
- `format`, `parseISO`, `differenceInDays` etc. unchanged

Search for locale usage:
```bash
grep -rn "date-fns/locale" frontend/src/ --include="*.ts" --include="*.tsx"
```

**Step 3: Install and test**

Run: `cd frontend && npm install && npm test -- --ci --watchAll=false`
Expected: 2,024 passing

**Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(deps): upgrade date-fns v3→v4

Function API unchanged, locale imports validated. 2,024 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 13: Upgrade recharts v2 → v3

**Files:**
- Modify: `frontend/package.json`
- Modify: Dashboard chart components
- Test: Frontend test suite

**Step 1: Read chart components**

```bash
grep -rn "from 'recharts'" frontend/src/ --include="*.tsx"
```

**Step 2: Update package.json**

```json
"recharts": "^3.8.0",
```

**Step 3: Migrate recharts v3 changes**

Key changes:
- `ResponsiveContainer` still required
- `LineChart`, `BarChart`, `PieChart` API largely unchanged
- `Tooltip` and `Legend` may have prop changes
- CSS class names may change (check `--chart-*` token usage)

**Step 4: Install and test**

Run: `cd frontend && npm install && npm test -- --ci --watchAll=false`

Fix any component prop type errors.

**Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/
git commit -m "chore(deps): upgrade recharts v2→v3

Chart component API changes applied, --chart-* tokens preserved.
2,024 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 14: Upgrade tailwind-merge v2 → v3

**Files:**
- Modify: `frontend/package.json`
- Test: Frontend test suite

**Step 1: Update package.json**

```json
"tailwind-merge": "^3.5.0",
```

tailwind-merge v3 supports Tailwind v4. API (`twMerge`, `cn`) unchanged.

**Step 2: Install and test**

Run: `cd frontend && npm install && npm test -- --ci --watchAll=false`
Expected: 2,024 passing

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(deps): upgrade tailwind-merge v2→v3

Tailwind v4 support ready. API unchanged. 2,024 tests passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 15: Upgrade ESLint v8 → v10 (DEFERRED — optional)

> **Note:** This is the largest migration. eslint-config-next 16.x currently depends on eslint 8. Upgrading requires flat config migration. `.npmrc` has `legacy-peer-deps=true` specifically for this compat. **Defer until Next.js officially supports ESLint 10 with eslint-config-next.**

Mark as DEFERRED in conductor track.

---

## Phase 4: ML Stack Upgrades (High Risk — Careful Testing)

### Task 16: Upgrade numpy v1 → v2

**Files:**
- Modify: `backend/requirements.txt` (line 53)
- Modify: `ml/requirements.txt` (if separate)
- Test: ML test suite + backend test suite

**Step 1: Update requirements.txt**

```
numpy>=2.0,<3.0
```

**Step 2: Check for breaking changes**

numpy v2 changes:
- `np.bool`, `np.int`, `np.float` removed (use `np.bool_`, `np.int_`, `np.float64`)
- `np.string_` → `np.bytes_`
- Array promotion rules changed
- `np.in1d` → `np.isin`

Search for deprecated usage:
```bash
grep -rn "np\.bool[^_]\|np\.int[^_0-9]\|np\.float[^_0-9]\|np\.string_\|np\.in1d" backend/ ml/ --include="*.py" | grep -v __pycache__
```

Fix all occurrences.

**Step 3: Install and test ML pipeline**

Run: `.venv/bin/python -m pytest ml/tests/ -x -v --tb=short`
Expected: 611 passed

**Step 4: Test backend (uses numpy for HNSW)**

Run: `.venv/bin/python -m pytest backend/tests/ -x -q --tb=short`
Expected: 2,663 passed

**Step 5: Commit**

```bash
git add backend/requirements.txt ml/ backend/
git commit -m "chore(deps): upgrade numpy v1→v2

Migrated deprecated type aliases (np.bool→np.bool_, np.float→np.float64).
ML suite (611) + backend suite (2,663) all passing.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 17: Upgrade pandas v2 → v3

**Files:**
- Modify: `backend/requirements.txt` (line 54)
- Test: ML test suite + backend test suite

**Step 1: Update requirements.txt**

```
pandas>=3.0,<4.0
```

**Step 2: Check for breaking changes**

pandas v3 changes:
- Copy-on-Write (CoW) is now default
- `DataFrame.append()` removed (use `pd.concat()`)
- `inplace=True` deprecated on many methods
- Silent downcasting disabled
- `datetime64[ns]` → `datetime64[us]` default resolution

Search for deprecated patterns:
```bash
grep -rn "\.append(\|inplace=True\|datetime64\[ns\]" backend/ ml/ --include="*.py" | grep -v __pycache__
```

**Step 3: Fix deprecations and test**

Run: `.venv/bin/python -m pytest ml/tests/ backend/tests/ -x -q --tb=short`
Expected: 611 + 2,663 = 3,274 passed

**Step 4: Commit**

```bash
git add backend/requirements.txt ml/ backend/
git commit -m "chore(deps): upgrade pandas v2→v3

CoW default, .append→pd.concat, inplace deprecation addressed.
3,274 tests passing (ML + backend).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Post-Upgrade Validation

### Task 18: Final audit and deployment validation

**Step 1: Run npm audit — expect 6 or fewer remaining vulns**

Run: `cd frontend && npm audit 2>&1 | tail -5`
Expected: Only @excalidraw transitive vulns remaining (devDependency, low exposure)

**Step 2: Run pip-audit — expect clean**

Run: `.venv/bin/python -m pip_audit -r backend/requirements.txt`
Expected: No known vulnerabilities found

**Step 3: Run full test suites**

```bash
.venv/bin/python -m pytest backend/tests/ -x -q --tb=short
cd frontend && npm test -- --ci --watchAll=false
```

Expected: 2,663+ backend, 2,024+ frontend

**Step 4: Type check frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 5: Build frontend**

Run: `cd frontend && npm run build`
Expected: Clean build

**Step 6: Update Dependabot config (if needed)**

Verify `.github/dependabot.yml` is still correct. No changes needed — it handles minor/patch going forward.

**Step 7: Update CLAUDE.md version pins**

Update any version references in `CLAUDE.md` that cite specific package versions.

**Step 8: Commit final state**

```bash
git add -A
git commit -m "chore: post-upgrade validation — all audits clean, tests passing

npm vulns: 13→6 (remaining are @excalidraw devDep transitive).
pip-audit: clean. Backend: 2,663+. Frontend: 2,024+.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Deployment Procedure

### Pre-deploy checklist
- [ ] All 4 phases committed to feature branch
- [ ] CI pipeline green (all 32 GHA workflows)
- [ ] Backend tests: 2,663+ passing
- [ ] Frontend tests: 2,024+ passing
- [ ] ML tests: 611+ passing
- [ ] `npm audit` shows 6 or fewer vulns (all @excalidraw devDep)
- [ ] `pip-audit` clean
- [ ] Frontend builds successfully
- [ ] Type check passes

### Deployment order
1. **Backend first** (Render) — push to main, auto-deploys
2. **Monitor** — check Sentry for new errors (5 min soak)
3. **Frontend** (Vercel) — auto-deploys from main
4. **Monitor** — check CF Worker gateway-stats, Grafana traces

### Rollback plan
- Render: Redeploy previous commit via Render dashboard
- Vercel: Instant rollback via Vercel dashboard
- Database: No migrations in this track — pure dependency changes

### Post-deploy monitoring
- [ ] Sentry error rate baseline (should be unchanged)
- [ ] Stripe webhook delivery (check Stripe dashboard)
- [ ] Redis connection pool health (Grafana)
- [ ] AI agent responses working (Gemini + Groq)
- [ ] SSE streaming functional (`/agent/query`)

---

## Summary

| Phase | Tasks | Risk | Vulns Fixed | Packages Updated |
|-------|-------|------|-------------|------------------|
| 1 | 1-4 | Low | 7 npm | 29 (17 Python + 11 npm + httpx cap) |
| 2 | 5-8 | Medium | 0 | 4 major (sentry, stripe, redis, dev tools) |
| 3 | 9-14 | Medium | 0 | 6 major (lucide, better-auth, zustand, date-fns, recharts, tw-merge) |
| 4 | 16-17 | High | 0 | 2 major (numpy, pandas) |
| Final | 18 | Low | — | Validation only |
| DEFERRED | 15 | High | — | ESLint v10 (wait for Next.js support) |

**Total: 18 tasks, ~73 packages upgraded, 7 vulnerabilities fixed**
