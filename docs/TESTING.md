# Testing Guide

**Last Updated**: 2026-03-06
**Overall Test Coverage**: 82%+
**Backend Tests**: 1,416 passed, 2 skipped (pytest, 57 test files) — includes 9 new Phase 2 tests (8 alerts + 5 sync-connections + 3 scrape-rates auto-discovery, minus 7 refactored)
**Frontend Tests**: 1391 across 95 suites (Jest)
**ML Tests**: 611 passed, 55 skipped (pytest)
**E2E Tests**: 634 passed, 5 skipped (Playwright)
**Total**: 3,409+ tests passing

---

## Test Suite Overview

| Test Type | Count | Coverage | Framework |
|-----------|-------|----------|-----------|
| **Backend Unit/Integration** | 1,416 passed, 2 skipped | 86%+ | pytest |
| **Frontend Component + Lib Tests** | 1391 (95 suites) | 78%+ | Jest + RTL |
| **Accessibility Tests** | 51 (included in frontend) | WCAG 2.1 AA | jest-axe |
| **ML Inference + Training** | 611 passed, 55 skipped | 82%+ | pytest |
| **E2E Tests** | 634 passed, 5 skipped | Critical flows | Playwright |
| **Security Tests** | 156 | 91%+ | pytest |
| **Load Tests** | N/A | 1000+ users | Locust |
| **Performance Tests** | 31 | API/ML | pytest |

---

## Python Virtual Environment Setup

The backend and ML tests require a Python virtual environment. **Do not use system Python** -- it is missing required dependencies (fastapi, httpx, pydantic, pytest-asyncio).

```bash
# Create venv with Python 3.12 (Homebrew)
python3.12 -m venv .venv

# Activate venv
source .venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Install ML dependencies (if running ML tests)
pip install -r ml/requirements.txt

# Verify correct Python
which python
# Should output: /path/to/electricity-optimizer/.venv/bin/python
```

The venv lives at `.venv/` in the project root. Always activate it before running any Python tests.

---

## Quick Start

### Run All Tests

```bash
# Activate venv first
source .venv/bin/activate

# Run all tests with coverage
make test

# Or run each test suite separately
make test-backend
make test-frontend
make test-security
make test-e2e
```

### Run Specific Test Categories

```bash
# Backend tests (1407 passed, 2 skipped)
source .venv/bin/activate
cd backend && pytest tests/ -v

# Frontend unit tests (1391 tests across 95 suites)
cd frontend && npm test

# E2E tests
cd frontend && npx playwright test

# Security tests
source .venv/bin/activate
pytest tests/security/ -v

# Performance tests
source .venv/bin/activate
pytest tests/performance/ -v

# Load tests
cd tests/load && ./run_load_test.sh quick
```

---

## Test Categories

### 1. Backend Unit and Integration Tests

**Location**: `backend/tests/`
**Count**: 1407 passed, 2 skipped
**Coverage Target**: 86%+

**Test Files** (57 files):
- `test_api.py` - API endpoint tests
- `test_api_billing.py` - Stripe billing endpoint tests (33 tests)
- `test_api_predictions.py` - ML prediction endpoint tests
- `test_api_recommendations.py` - Recommendation endpoint tests (20 tests)
- `test_api_user.py` - User preference endpoint tests
- `test_services.py` - Service layer tests
- `test_repositories.py` - Data access tests
- `test_models.py` - Data model tests
- `test_integrations.py` - External API tests
- `test_auth.py` - Authentication tests
- `test_security.py` - Security tests
- `test_security_adversarial.py` - Adversarial security tests (42 tests)
- `test_gdpr_compliance.py` - GDPR compliance tests
- `test_alert_service.py` - Alert service tests
- `test_stripe_service.py` - Stripe service tests (+6 new: payment_failed handler with customer resolution, two-stage webhook guard)
- `test_weather_service.py` - Weather service tests
- `test_config.py` - Settings validation tests
- `test_observation_service.py` - Forecast recording, actuals backfill, recommendation tracking, accuracy metrics (31 tests)
- `test_learning_service.py` - Rolling accuracy, bias detection, ensemble weight tuning, bias correction vectors, full learning cycle (32 tests)
- `test_hnsw_vector_store.py` - HNSW vector store singleton, search, fallback, pruning
- `test_api_internal.py` - Internal API endpoints (observe-forecasts, learn, observation-stats, +9 new Phase 2 tests: 8 alert + 1 sync-connections)
- `test_api_regulations.py` - State regulation API endpoints
- `test_load.py` - Load/stress test helpers
- `test_multi_utility.py` - Multi-utility expansion tests (39 tests)
- `test_performance.py` - Performance tests (query count, cache, async Stripe) (31 tests)
- `test_connections.py` - Connection endpoint tests (create, list, delete, label update, rates) (40 tests)
- `test_connection_service.py` - Connection service layer tests (51 tests)
- `test_bill_upload.py` - Bill upload and parse tests (file validation, multipart upload, parse status)
- `test_email_oauth.py` - Email OAuth tests: state gen/verify, consent URLs, token encryption, Gmail/Outlook scanning, callback flow, endpoint tests (70 tests across 13 classes)
- `test_connection_analytics.py` - Analytics service tests: rate comparison, history, savings, stale connections, rate changes (39 tests across 8 classes)
- `test_middleware_asgi.py` - Pure ASGI middleware tests: security headers, rate limiting, body size limit, timeout exclusion, SSE streaming through full middleware stack (9 tests)
- `test_api_alerts.py` - Alert endpoint tests (create, list, delete, trigger)
- `test_api_health.py` - Health endpoint tests (DB/Redis/service checks)
- `test_api_prices_analytics.py` - Price analytics endpoint tests
- `test_feature_flags.py` - Feature flag service tests
- `test_maintenance_service.py` - Maintenance service tests (21 tests: activity log cleanup, upload cleanup with FK cascade, file removal, OSError suppression, endpoint integration)
- `test_migrations.py` - Migration file validation tests
- `test_notifications.py` - Notification service tests
- `test_resilience.py` - Resilience and error recovery tests
- `test_savings_service.py` - Savings service tests (52 tests)
- `test_supplier_cache.py` - Supplier caching layer tests (25 tests)
- `test_forecast_observation_repository.py` - Forecast observation data access tests (+8 new tests)

**Running**:
```bash
source .venv/bin/activate
cd backend
pytest tests/ -v --cov=. --cov-report=html
```

### 2. Frontend Component + Library Tests

**Location**: `frontend/__tests__/` and `frontend/lib/`
**Count**: 1391 tests across 95 suites
**Coverage Target**: 78%+

**Accessibility Testing**: 51 tests using `jest-axe` for automated WCAG 2.1 AA compliance checks. Tests are located in `__tests__/a11y/` and cover color contrast, ARIA attributes, keyboard navigation, focus management, and semantic HTML across all major components.

**Component Test Suites** (`__tests__/`, 45+ files):
- `components/ComparisonTable.test.tsx` - Supplier comparison table
- `components/PriceLineChart.test.tsx` - Price chart rendering
- `components/SavingsDonut.test.tsx` - Savings donut chart
- `components/ScheduleTimeline.test.tsx` - Schedule timeline
- `components/SupplierCard.test.tsx` - Supplier card
- `components/SwitchWizard.test.tsx` - Switching wizard (known flaky)
- `components/auth/LoginForm.test.tsx` - Login form
- `components/auth/SignupForm.test.tsx` - Signup form
- `components/charts/ForecastChart.test.tsx` - Forecast chart
- `components/gamification/SavingsTracker.test.tsx` - Savings tracker
- `components/layout/Header.test.tsx` - Header layout
- `components/layout/Sidebar.test.tsx` - Sidebar layout
- `components/layout/NotificationBell.test.tsx` - Notification bell dropdown
- `components/ui/*.test.tsx` - UI primitives (Badge, Button, Card, Input, Skeleton)
- `components/dashboard/DashboardContent.test.tsx` - Dashboard content rendering
- `components/dashboard/SetupChecklist.test.tsx` - Setup checklist widget
- `components/onboarding/*.test.tsx` - Onboarding components (RegionSelector, UtilityTypeSelector, SupplierPicker, OnboardingWizard)
- `components/prices/PricesContent.test.tsx` - Prices page content
- `components/suppliers/*.test.tsx` - Supplier components (SupplierSelector, SetSupplierDialog, SupplierAccountForm, SuppliersContent)
- `components/connections/*.test.tsx` - Connection components (Overview, MethodPicker, Card, DirectLogin, EmailFlow, BillUpload, UploadFlow, Rates, Analytics, 9 files total)
- `components/dev/DevBanner.test.tsx` - Dev mode banner rendering
- `components/dev/ExcalidrawWrapper.test.tsx` - Excalidraw dynamic import wrapper
- `components/dev/DiagramList.test.tsx` - Diagram sidebar list
- `components/dev/DiagramEditor.test.tsx` - Canvas editor with save + Ctrl+S
- `integration/dashboard.test.tsx` - Dashboard integration
- `pages/suppliers.test.tsx` - Suppliers page rendering
- `pages/prices.test.tsx` - Prices page rendering
- `hooks/useDiagrams.test.tsx` - Diagram React Query hooks (list, get, save, create)
- `hooks/useAuth.test.tsx` - Auth hooks (+4 new OneSignal push notification integration tests)
- `hooks/useOptimization.test.ts` - Optimization hooks
- `hooks/useRealtime.test.ts` - Realtime/SSE hooks
- `hooks/useSuppliers.test.ts` - Supplier hooks
- `hooks/usePrices.test.tsx` - Price hooks
- `hooks/useSavings.test.ts` - Savings hooks
- `hooks/useProfile.test.ts` - Profile hooks
- `contexts/toast-context.test.tsx` - Toast context provider
- `contexts/sidebar-context.test.tsx` - Sidebar context provider
- `utils/devGate.test.ts` - isDevMode utility
- `api/dev/diagrams/route.test.ts` - Diagram list + create API routes
- `api/dev/diagrams/name.route.test.ts` - Diagram read + save API routes
- `app/dev/layout.test.tsx` - Dev layout gate (notFound in production)
- `app/dev/architecture.test.tsx` - Architecture page integration
- `lib/config/env.test.ts` - Environment configuration validation (14 tests)

**Library Test Suites** (`lib/`, 7 files):
- `lib/utils/__tests__/format.test.ts` - 46 tests for all 9 format utility functions
- `lib/utils/__tests__/calculations.test.ts` - 46 tests for all 8 calculation functions
- `lib/api/__tests__/client.test.ts` - 30 tests for API client + ApiClientError
- `lib/api/__tests__/client-401-redirect.test.ts` - 9 tests for 401 redirect loop prevention (auth page guard, callbackUrl extraction, safety valve, counter reset, open redirect rejection)
- `lib/api/__tests__/prices.test.ts` - Price API client tests
- `lib/api/__tests__/suppliers.test.ts` - Supplier API client tests
- `contracts/api-schemas.test.ts` - API contract validation (45+ tests)
- `store/settings.test.ts` - Zustand settings store

**Running**:
```bash
cd frontend
npm test           # Watch mode
npm run test:ci    # CI mode with coverage
```

**Known Issues**:
- The SwitchWizard test suite is occasionally flaky due to timing-sensitive assertions. Re-running usually resolves failures.

### 3. E2E Tests

**Location**: `frontend/e2e/`
**Count**: 634 passed, 5 skipped, 0 failed
**Last Run**: 2026-03-03 (URI_TOO_LONG fix + redirect loop prevention tests)

**Test Files** (15 specs):
- `authentication.spec.ts` - Auth flows (login, OAuth, magic link, redirect loop prevention)
- `billing-flow.spec.ts` - Stripe checkout, pricing tiers
- `dashboard.spec.ts` - Dashboard widgets, navigation, error handling
- `full-journey.spec.ts` - End-to-end user journey (landing -> dashboard -> optimize)
- `gdpr-compliance.spec.ts` - Cookie consent, data export/deletion
- `load-optimization.spec.ts` - Appliance scheduling, savings projections
- `onboarding.spec.ts` - Signup navigation, post-onboarding dashboard
- `onboarding-flow.spec.ts` - New onboarding flow with region selection
- `optimization.spec.ts` - Quick add, custom appliance, flexibility toggle
- `prices.spec.ts` - Price tracking and analytics
- `settings.spec.ts` - User settings and preferences
- `sse-streaming.spec.ts` - SSE connection, price updates, error recovery
- `supplier-selection.spec.ts` - Supplier selection interface
- `supplier-switching.spec.ts` - Supplier comparison, switching wizard
- `switching.spec.ts` - Switching wizard GDPR consent flow

**Browser Projects** (5):
| Project | Device | Viewport |
|---------|--------|----------|
| chromium | Desktop Chrome | 1280x720 |
| firefox | Desktop Firefox | 1280x720 |
| webkit | Desktop Safari | 1280x720 |
| Mobile Chrome | Pixel 5 | 393x851 |
| Mobile Safari | iPhone 12 | 390x844 |

**Skipped Tests**: 5 legitimately skipped (down from 16 after E2E test healing in commit `9585625`):
- Email validation flow (requires real email delivery)
- Magic link authentication (requires real email delivery)
- GDPR compliance suite (requires cookie banner infrastructure)
- 2 mobile viewport conditional tests (feature not visible on mobile)

**Running**:
```bash
cd frontend

# Run all E2E tests (5 browsers)
npx playwright test

# Run single browser
npx playwright test --project=chromium

# Run specific test file
npx playwright test e2e/authentication.spec.ts

# Run with UI mode
npx playwright test --ui

# Run in headed mode
npx playwright test --headed

# Generate test report
npx playwright show-report
```

**Cross-Browser Notes**:
- `isMobile` fixture is used to skip tests for mobile-hidden elements (e.g., realtime indicator has `hidden sm:flex`)
- WebKit requires `click()` before `fill()` for React controlled inputs to trigger `onChange`
- Mobile Safari has different error rendering for auth failures

### 4. ML Tests

**Location**: `ml/tests/`
**Count**: 611 passed, 55 skipped (matplotlib/plotly not installed)
**Coverage Target**: 82%+

**Test Files** (16 files):
- `test_models.py` - Model architecture tests (training, evaluation, model state)
- `test_feature_engineering.py` - Feature extraction and transformation tests
- `test_optimization.py` - Load optimization and appliance scheduling tests
- `test_switching_decision.py` - Switching decision algorithm tests
- `test_milp_standalone.py` - MILP solver tests
- `test_hyperparameter_tuning.py` - Hyperparameter optimization tests
- `test_train_forecaster.py` - Forecaster training pipeline tests
- `test_cnn_lstm_trainer.py` - CNN-LSTM model training tests
- `test_training.py` - General training tests
- `test_backtesting.py` - Model backtesting tests
- `test_inference.py` - Model inference tests
- `test_metrics.py` - Performance metrics (87 tests: accuracy, MAE, RMSE, F1, precision, recall, AUC-ROC)
- `test_visualization.py` - Visualization and charting (53 tests: confusion matrix, ROC curves, feature importance)
- `test_scheduler.py` - Schedule optimization (100 tests: job scheduling, resource allocation, constraint validation)
- `test_load_shifter.py` - Load shifting strategies (77 tests: demand response, time-of-use optimization)
- `test_predictor.py` - Ensemble predictor (79 tests + 55 skipped: inference, caching, fallback behavior)

**Running**:
```bash
source .venv/bin/activate
cd ml && pytest tests/ -v --cov=. --cov-report=html
```

### 5. Load Tests

**Location**: `tests/load/`

**Test Files**:
- `locustfile.py` - Locust user behaviors
- `stress_test.py` - Database stress testing
- `run_load_test.sh` - Test runner script

**Running**:
```bash
cd tests/load

# Quick smoke test (50 users, 1 min)
./run_load_test.sh quick

# Standard load test (500 users, 3 min)
./run_load_test.sh standard

# Full load test (1000 users, 5 min)
./run_load_test.sh full

# Stress test (2000 users, 10 min)
./run_load_test.sh stress

# Spike test (sudden traffic increase)
./run_load_test.sh spike

# Endurance test (500 users, 30 min)
./run_load_test.sh endurance
```

**Performance Targets**:
- Concurrent users: 1000+
- Success rate: >99%
- p95 latency: <500ms
- Database handles load without degradation

### 6. Performance Tests

**Location**: `backend/tests/test_performance.py`
**Count**: 31 tests
**Focus**: Query count, caching, async operations

**Test Coverage**:
- API endpoint latency (health, prices, forecasts, optimization)
- Database query optimization (N+1 prevention, prefetching)
- Redis caching effectiveness
- Async Stripe SDK integration
- Model inference performance
- Response time targets (p95, p99)

**Running**:
```bash
source .venv/bin/activate
cd backend && pytest tests/test_performance.py -v -s
```

**Performance Targets**:

| Endpoint | Target p95 |
|----------|------------|
| Health | <50ms |
| Current Prices | <200ms |
| Price History | <300ms |
| Price Forecast | <500ms |
| Optimization (simple) | <1000ms |
| Optimization (complex) | <2000ms |
| Suppliers List | <200ms |

### 7. Security Tests

**Location**: `backend/tests/security/` and adversarial tests
**Count**: 156 tests
**Coverage**: 91%+

**Test Files**:
- `test_security.py` - Core security tests (API key validation, CORS, authentication)
- `test_security_adversarial.py` - Adversarial security tests (42 tests: injection, bypass, authorization)
- `test_auth_bypass.py` - Authentication security
- `test_sql_injection.py` - SQL injection protection
- `test_rate_limiting.py` - Rate limiting validation (tested via middleware tests)
- `test_gdpr_compliance.py` - GDPR and data protection tests
- `test_middleware_asgi.py` - Security headers and middleware tests (9 tests)

**Running**:
```bash
source .venv/bin/activate
cd backend && pytest tests/test_security*.py tests/test_gdpr_compliance.py -v
```

---

## Performance Targets

### API Response Times

| Metric | Target |
|--------|--------|
| Health check p95 | <50ms |
| API endpoints p95 | <500ms |
| ML inference p95 | <2000ms |
| Overall success rate | >99% |

### Frontend Performance (Lighthouse)

| Metric | Target |
|--------|--------|
| Performance Score | 90+ |
| Accessibility Score | 90+ |
| Best Practices | 90+ |
| SEO Score | 90+ |
| First Contentful Paint | <2s |
| Largest Contentful Paint | <3s |
| Cumulative Layout Shift | <0.1 |
| Total Blocking Time | <500ms |

### Load Testing

| Metric | Target |
|--------|--------|
| Concurrent Users | 1000+ |
| Success Rate | >99% |
| p95 Latency | <500ms |
| p99 Latency | <1000ms |
| Requests/second | 500+ |

---

## Recent Test Improvements

### Frontend Review Swarm (2026-03-03, commit `c29e1d6`)

A 5-agent swarm (test-writer, code-reviewer, a11y-auditor, e2e-fixer, security-perf) performed a comprehensive frontend review that added **248 new tests**:

- Frontend tests increased from 1126 to 1374 (93 suites, up from 64)
- Added `jest-axe` dependency for automated accessibility testing
- **51 new a11y tests** in `__tests__/a11y/` covering WCAG 2.1 AA compliance (color contrast, ARIA attributes, focus management, semantic HTML)
- 29 new test files across components, hooks, pages, and accessibility
- ESLint configuration (`.eslintrc.json`) with `no-explicit-any: "warn"` and test overrides
- Reports available in `.swarm-reports/FRONTEND_REVIEW_REPORT.md`

### URI_TOO_LONG Redirect Loop Fix (2026-03-03)

Fixed a P0 bug where stale session cookies caused exponential URL growth (HTTP 414 URI_TOO_LONG). The API client's 401 handler was firing on auth pages, nesting `callbackUrl` parameters with each redirect cycle.

**Fix**: 3-layer defense in `lib/api/client.ts`:
1. Auth page guard: skip redirect when `pathname.startsWith('/auth/')`
2. CallbackUrl extraction: reuse existing `callbackUrl` instead of nesting, validated with `isSafeRedirect()`
3. Safety valve: `sessionStorage` counter stops after 3 consecutive 401 redirects

**New tests added**:
- `lib/api/__tests__/client-401-redirect.test.ts` (9 tests): redirect behavior, auth page guard, callbackUrl extraction, safety valve, counter reset, open redirect rejection
- `__tests__/hooks/useAuth.test.tsx` (+2 tests): auth page API call skipping, non-auth page API calls
- `e2e/authentication.spec.ts` (+2 E2E tests): stale cookie redirect loop prevention, callbackUrl preservation through 401 cycle

**Additional changes**:
- `lib/hooks/useAuth.tsx`: skips `getUserSupplier()`/`getUserProfile()` on `/auth/*` pages
- `app/(app)/auth/callback/page.tsx`: added `role="status"` and `aria-label` for a11y
- `playwright.config.ts`: added `retries: 1` for local runs

### E2E Test Healing (2026-03-03, commit `9585625`)

Systematic fix of previously-skipped E2E tests:

- E2E skipped tests reduced from 16 to 5 (11 tests unskipped and repaired)
- 624 E2E tests now passing, 0 failures
- Remaining 5 skips are legitimate (email delivery, GDPR infrastructure, mobile viewport conditionals)
- ESLint cleanup: 0 lint errors across the frontend codebase
- Duplicate `load-optimization.spec.ts` removed

---

## CI/CD Integration

### GitHub Actions Workflows

1. **Unified CI** (`.github/workflows/ci.yml`)
   - Runs on every PR and push to main/develop
   - Uses `dorny/paths-filter` for smart path-based job selection (only runs relevant tests)
   - Backend lint (Black, isort, flake8, mypy) + tests via reusable `_backend-tests.yml`
   - ML tests (Python 3.11) — only when `ml/` files change
   - Frontend tests (lint + Jest + build) — only when `frontend/` files change
   - Security scan (Bandit high-severity + npm audit critical) — blocks on findings
   - Docker build verification — only after tests pass
   - Concurrency: `ci-${{ github.ref }}`, cancel-in-progress: true
   - Replaces the former `test.yml`, `backend-ci.yml`, and `frontend-ci.yml` (deleted)

2. **E2E Test Workflow** (`.github/workflows/e2e-tests.yml`)
   - Runs Playwright E2E tests with proper health-check polling (no sleep calls)
   - Runs Lighthouse audits
   - Load tests (on-demand via label or workflow_dispatch)
   - Security tests (Bandit + adversarial)
   - Daily scheduled runs at 2 AM UTC
   - Uses composite actions: `setup-python-env`, `setup-node-env`, `wait-for-service`

3. **Reusable Workflows** (callable only)
   - `_backend-tests.yml` — backend tests with postgres + redis services, optional coverage/Codecov
   - `_docker-build-push.yml` — Docker build + GHCR push with metadata + GHA cache

### CI Environment

| Tool | Version |
|------|---------|
| Python | 3.11 |
| Node.js | 20 |
| Runner | ubuntu-latest |
| PostgreSQL | PostgreSQL 15 |
| Redis | 7 Alpine |

---

## Test Data

### Fixtures

Backend fixtures are defined in `backend/tests/conftest.py`:
- `client` - FastAPI TestClient
- `mock_price_service` - Mocked price service
- `sample_prices` - Sample price data
- `auth_headers` - Authentication headers
- `mock_sqlalchemy_select` (autouse) - Patches Pydantic model class attrs for SQLAlchemy expression compatibility. Uses manual `type.__setattr__` restoration to preserve FieldInfo descriptors
- `reset_rate_limiter` (autouse) - Clears RateLimitMiddleware in-memory store between tests to prevent 429 accumulation

ML fixtures are defined in `ml/tests/conftest.py`:
- `sample_price_data` - Historical price data
- `mock_model` - Mocked ML model
- `optimization_config` - Sample optimization config

### Mock APIs

E2E tests use Playwright's route mocking. Auth mocking uses a shared helper:
```typescript
import { mockBetterAuth, setAuthenticatedState } from './helpers/auth'

// Mock all Better Auth API routes (sign-in, get-session, sign-out, etc.)
await mockBetterAuth(page, { signInShouldFail: false, sessionExpired: false })

// Set authenticated cookie state directly
await setAuthenticatedState(page)

// Mock backend API routes
await page.route('**/api/v1/prices/current**', async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ prices: [...] }),
  })
})
```

---

## Writing New Tests

### Backend Test Template

```python
import pytest
from fastapi.testclient import TestClient
from main import app

class TestNewFeature:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_feature_success(self, client):
        """Test feature works correctly."""
        response = client.get("/api/v1/new-feature")
        assert response.status_code == 200
        assert "expected_field" in response.json()

    def test_feature_validation(self, client):
        """Test feature validates input."""
        response = client.post("/api/v1/new-feature", json={"invalid": "data"})
        assert response.status_code == 422
```

### E2E Test Template

```typescript
import { test, expect } from '@playwright/test'

test.describe('New Feature', () => {
  test.beforeEach(async ({ page }) => {
    // Mock APIs
    await page.route('**/api/v1/feature**', async (route) => {
      await route.fulfill({ status: 200, body: JSON.stringify({...}) })
    })
    await page.goto('/feature')
  })

  test('user can use feature', async ({ page }) => {
    await expect(page.getByText('Feature Title')).toBeVisible()
    await page.click('button:has-text("Action")')
    await expect(page.getByText('Success')).toBeVisible()
  })
})
```

---

## Debugging Tests

### Playwright Debug Mode

```bash
# Run with debug mode
PWDEBUG=1 npx playwright test

# Run with trace viewer
npx playwright test --trace on
npx playwright show-trace trace.zip
```

### pytest Debug Mode

```bash
# Run with verbose output
pytest -v -s

# Run with debugger
pytest --pdb

# Run specific test
pytest tests/test_api.py::TestPriceEndpoints::test_get_current_prices -v
```

### View Test Reports

```bash
# Playwright HTML report
cd frontend && npx playwright show-report

# Coverage report
open htmlcov/index.html

# Load test report
open tests/load/reports/load_test_*.html
```

---

## Troubleshooting

### Common Issues

1. **ImportError / ModuleNotFoundError when running pytest**
   - You are likely using system Python instead of the venv
   - Fix: `source .venv/bin/activate` then re-run
   - Verify: `which python` should show `.venv/bin/python`

2. **Tests fail with database connection error**
   - Ensure PostgreSQL is running: `docker compose up -d postgres`
   - Check DATABASE_URL environment variable
   - For local dev without a database, most tests use mocks

3. **E2E tests timeout**
   - Increase timeout in playwright.config.ts
   - Check if backend and frontend services are running

4. **SwitchWizard test failures**
   - This suite is known to be flaky due to timing-sensitive assertions
   - Re-run the test; it usually passes on retry

5. **Load tests show high failure rate**
   - Check backend logs for errors
   - Verify rate limiting configuration
   - Ensure sufficient database connections

6. **Coverage below threshold**
   - Run `pytest --cov-report=term-missing` to see uncovered lines
   - Add tests for uncovered code paths

---

## Loki Mode Testing

Loki Mode orchestration components can be tested independently without affecting the main test suites. The existing test counts (1393 backend, 1398 frontend, 611 ML) remain unchanged with Loki Mode active. The former test ordering issue (23+ tests failing in full suite) has been resolved via `reset_rate_limiter` and improved `mock_sqlalchemy_select` fixtures in `conftest.py`.

### Event Bus Dry Run

Test event processing without side effects using the `--dry-run` flag:

```bash
loki-event-sync.sh --dry-run
```

This reads and validates events from `.loki/events/` but does not execute any sync actions or modify state. Use this to verify that events are being produced correctly during development.

### Activation Hook Test

To verify that the `PreToolUse` auto-initialization hook works correctly:

```bash
# Remove the orchestration marker to simulate a fresh session
rm -f /tmp/claude-orchestration-active

# Run the activation script manually
.claude/hooks/activate-orchestration.sh

# Verify the marker was created
ls -la /tmp/claude-orchestration-active
```

If the marker file exists after running the script, initialization succeeded. Check `.claude/logs/orchestration-init.log` for detailed output.

### Memory Verification

Query Loki Mode's IndexLayer memory to verify stored data:

```bash
PYTHONPATH="$HOME/.claude/skills/loki-mode" loki memory retrieve "query"
```

Replace `"query"` with a relevant search term (e.g., `"electricity prices"`, `"session patterns"`). This performs a vector similarity search against the `electricity-optimizer` namespace and returns matching memory entries.

### Compatibility Notes

- Loki Mode hooks run outside the test process and do not interfere with pytest, Jest, or Playwright test runners
- The `.loki/` directory is local to the project root and does not affect CI environments (no `.loki/` directory is present in CI runners)
- All 1407 backend, 1391 frontend, and 611 ML tests continue to pass with Loki Mode installed

---

### Email and Auth Testing

Email and authentication features are tested across multiple layers:

**Backend** (`backend/tests/`):
- `test_email_oauth.py` — 70 tests covering email OAuth state gen/verify, consent URLs, token encryption, Gmail/Outlook scanning, callback flow
- `test_auth.py` — 40 tests covering Neon Auth session validation, password strength, API key auth
- Email service tested via mock Resend client (no real emails sent in tests)

**Frontend** (`frontend/__tests__/`):
- `components/auth/LoginForm.test.tsx` — Login form with conditional OAuth, magic link
- `components/auth/SignupForm.test.tsx` — Signup form with email validation, error states
- `hooks/useAuth.test.tsx` — Auth hook with API call skipping on `/auth/*` pages
- `lib/config/env.test.ts` — Environment config validation including auth env vars

**E2E** (`frontend/e2e/`):
- `authentication.spec.ts` — Full auth flows including redirect loop prevention, callbackUrl preservation
- 5 legitimately skipped tests require real email delivery (verification, magic link)

---

## Maintenance

### Updating Test Dependencies

```bash
# Backend (inside venv)
source .venv/bin/activate
pip install -U pytest pytest-cov pytest-asyncio

# Frontend
cd frontend
npm update @playwright/test @testing-library/react jest
```

### Regenerating Snapshots

```bash
# Playwright snapshots
cd frontend && npx playwright test --update-snapshots

# Jest snapshots
cd frontend && npm test -- -u
```

---

**Last Updated**: 2026-03-06
