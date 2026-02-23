# Testing Guide

**Last Updated**: 2026-02-23
**Overall Test Coverage**: 80%+
**Backend Tests**: 572 (pytest)
**Frontend Tests**: 346 across 17 suites (Jest)
**ML Tests**: 105 + 2 skipped (pytest)
**E2E Tests**: 805 across 11 specs x 5 browsers (Playwright)

---

## Test Suite Overview

| Test Type | Count | Coverage | Framework |
|-----------|-------|----------|-----------|
| **Backend Unit/Integration** | 572 | 85%+ | pytest |
| **Frontend Component + Lib Tests** | 346 (17 suites) | 70%+ | Jest + RTL |
| **ML Inference + Training** | 105 (+2 skipped) | 80%+ | pytest |
| **E2E Tests** | 805 (161 per browser x 5) | Critical flows | Playwright |
| **Security Tests** | 144 | 90%+ | pytest |
| **Load Tests** | N/A | 1000+ users | Locust |
| **Performance Tests** | 20+ | API/ML | pytest |

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
# Backend tests (540 tests)
source .venv/bin/activate
cd backend && pytest tests/ -v

# Frontend unit tests (346 tests across 17 suites)
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
**Count**: 572
**Coverage Target**: 85%+

**Test Files**:
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
- `test_stripe_service.py` - Stripe service tests
- `test_weather_service.py` - Weather service tests
- `test_config.py` - Settings validation tests

**Running**:
```bash
source .venv/bin/activate
cd backend
pytest tests/ -v --cov=. --cov-report=html
```

### 2. Frontend Component + Library Tests

**Location**: `frontend/__tests__/` and `frontend/lib/`
**Count**: 346 tests across 17 suites
**Coverage Target**: 70%+

**Component Test Suites** (`__tests__/`):
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
- `components/ui/*.test.tsx` - UI primitives (Badge, Button, Card, Input, Skeleton)
- `integration/dashboard.test.tsx` - Dashboard integration

**Library Test Suites** (`lib/`):
- `lib/utils/__tests__/format.test.ts` - 46 tests for all 9 format utility functions
- `lib/utils/__tests__/calculations.test.ts` - 46 tests for all 8 calculation functions
- `lib/api/__tests__/client.test.ts` - 30 tests for API client + ApiClientError

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
**Count**: 161 tests per browser x 5 browser projects = 805 total
**Last Run**: 431 passed, 374 skipped, 0 failed (2026-02-23)

**Test Files** (11 specs):
- `authentication.spec.ts` - Auth flows (login, OAuth, magic link)
- `billing-flow.spec.ts` - Stripe checkout, pricing tiers
- `dashboard.spec.ts` - Dashboard widgets, navigation, error handling
- `full-journey.spec.ts` - End-to-end user journey (landing -> dashboard -> optimize)
- `gdpr-compliance.spec.ts` - Cookie consent, data export/deletion
- `load-optimization.spec.ts` - Appliance scheduling, savings projections
- `onboarding.spec.ts` - Signup navigation, post-onboarding dashboard
- `optimization.spec.ts` - Quick add, custom appliance, flexibility toggle
- `sse-streaming.spec.ts` - SSE connection, price updates, error recovery
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

**Skipped Tests**: ~75 per browser are skipped for unimplemented features:
- Better Auth (signIn/signUp use client directly, not mockable via route interception)
- `/onboarding` page (not yet implemented)
- Multi-step switching wizard testids (supplier-card-*, filter/sort testids)
- Optimization testids (schedule-block-*, price-zone-*, optimization-score)
- Cookie banner interactions (not visible on Chromium)
- Recurring schedule and smart notification UIs

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

### 4. Load Tests

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

### 5. Performance Tests

**Location**: `tests/performance/`

**Test Files**:
- `test_api_latency.py` - API endpoint latency tests
- `test_model_inference.py` - ML model performance tests

**Running**:
```bash
source .venv/bin/activate
pytest tests/performance/ -v -s
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

### 6. Security Tests

**Location**: `tests/security/`

**Test Files**:
- `test_auth_bypass.py` - Authentication security
- `test_sql_injection.py` - SQL injection protection
- `test_rate_limiting.py` - Rate limiting validation

**Running**:
```bash
source .venv/bin/activate
pytest tests/security/ -v
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

## CI/CD Integration

### GitHub Actions Workflows

1. **Test Workflow** (`.github/workflows/test.yml`)
   - Runs on every PR and push to main/develop
   - Backend tests (Python 3.11, with PostgreSQL + Redis services)
   - ML tests (Python 3.11)
   - Frontend tests (Node 20) with lint, test, and build steps
   - Security scan (Bandit + Safety)
   - Docker build verification
   - Enforces coverage reporting via Codecov

2. **E2E Test Workflow** (`.github/workflows/e2e-tests.yml`)
   - Runs Playwright E2E tests
   - Runs Lighthouse audits
   - Daily scheduled runs at 2 AM UTC

3. **Load Test Workflow** (On demand)
   - Triggered by `load-test` label on PR
   - Runs quick load test scenario

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

Loki Mode orchestration components can be tested independently without affecting the main test suites. The existing test counts (572 backend, 346 frontend, 105 ML) remain unchanged with Loki Mode active. The former test ordering issue (23+ tests failing in full suite) has been resolved via `reset_rate_limiter` and improved `mock_sqlalchemy_select` fixtures in `conftest.py`.

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
- All 572 backend, 346 frontend, and 105 ML tests continue to pass with Loki Mode installed

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

**Last Updated**: 2026-02-23
