# Testing Guide

**Last Updated**: 2026-02-22
**Overall Test Coverage**: 80%+
**Backend Tests**: 338 (pytest)
**Frontend Tests**: 77 across 7 suites (Jest)

---

## Test Suite Overview

| Test Type | Count | Coverage | Framework |
|-----------|-------|----------|-----------|
| **Backend Unit/Integration** | 338 | 85%+ | pytest |
| **Frontend Component Tests** | 77 (7 suites) | 70%+ | Jest + RTL |
| **E2E Tests** | 100+ | Critical flows | Playwright |
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
# Backend tests (338 tests)
source .venv/bin/activate
cd backend && pytest tests/ -v

# Frontend unit tests (77 tests)
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
**Count**: 338
**Coverage Target**: 85%+

**Test Files**:
- `test_api.py` - API endpoint tests
- `test_services.py` - Service layer tests
- `test_repositories.py` - Data access tests
- `test_models.py` - Data model tests
- `test_integrations.py` - External API tests
- `test_auth.py` - Authentication tests
- `test_security.py` - Security tests
- `test_gdpr_compliance.py` - GDPR compliance tests

**Running**:
```bash
source .venv/bin/activate
cd backend
pytest tests/ -v --cov=. --cov-report=html
```

### 2. Frontend Component Tests

**Location**: `frontend/__tests__/`
**Count**: 77 tests across 7 suites
**Coverage Target**: 70%+

**Test Files**:
- `components/PriceLineChart.test.tsx` - Price chart tests
- `components/SupplierCard.test.tsx` - Supplier card tests
- `components/SwitchWizard.test.tsx` - Switching wizard tests (known flaky)
- `components/ComparisonTable.test.tsx` - Comparison table tests

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

**Test Files**:
- `onboarding.spec.ts` - User onboarding flow
- `authentication.spec.ts` - Auth flows (login, OAuth, magic link)
- `dashboard.spec.ts` - Dashboard interactions
- `supplier-switching.spec.ts` - Full switching flow with GDPR
- `load-optimization.spec.ts` - Appliance scheduling
- `gdpr-compliance.spec.ts` - Data export and deletion
- `switching.spec.ts` - Supplier switching scenarios
- `optimization.spec.ts` - Load optimization scenarios

**Running**:
```bash
cd frontend

# Run all E2E tests
npx playwright test

# Run with UI mode
npx playwright test --ui

# Run specific test file
npx playwright test e2e/authentication.spec.ts

# Run in headed mode
npx playwright test --headed

# Generate test report
npx playwright show-report
```

**Browser Coverage**: Chromium, Firefox, WebKit, Mobile Chrome, Mobile Safari

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
| PostgreSQL | TimescaleDB on PG 15 |
| Redis | 7 Alpine |

---

## Test Data

### Fixtures

Backend fixtures are defined in `backend/tests/conftest.py`:
- `client` - FastAPI TestClient
- `mock_price_service` - Mocked price service
- `sample_prices` - Sample price data
- `auth_headers` - Authentication headers

ML fixtures are defined in `ml/tests/conftest.py`:
- `sample_price_data` - Historical price data
- `mock_model` - Mocked ML model
- `optimization_config` - Sample optimization config

### Mock APIs

E2E tests use Playwright's route mocking:
```typescript
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
   - Ensure PostgreSQL is running: `docker compose up -d timescaledb`
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

**Last Updated**: 2026-02-22
