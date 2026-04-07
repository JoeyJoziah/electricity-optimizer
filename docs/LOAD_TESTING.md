# Load Testing Guide

**Last Updated**: 2026-03-16
**Tool**: k6 (Grafana)
**Script**: `scripts/load_test.js`
**Target**: 2000 concurrent users, >95% success rate, p99 latency <2s

---

## Overview

The load test validates that the RateShift production infrastructure meets its
SLAs under realistic peak load. It exercises six public/semi-public API
endpoints weighted by expected real-world traffic patterns.

### SLA Thresholds

| Threshold | Target | k6 Assertion |
|---|---|---|
| p95 response time | < 1500ms | `p(95)<1500` |
| p99 response time | < 2000ms | `p(99)<2000` |
| Success rate | > 95% | `rate<0.05` (failure rate) |
| Throughput | > 100 req/s | `rate>100` |

### Scenario Weights

| Endpoint | Method | Weight | Auth | Notes |
|---|---|---|---|---|
| `/api/v1/prices/current?region=CT` | GET | 40% | Public | Redis-cached, most common |
| `/api/v1/suppliers` | GET | 20% | Public | Registry listing, 37 rows |
| `/health/live` | GET | 15% | Public | No DB I/O, fast-path only |
| `/api/v1/beta/signup` | POST | 10% | Public | Unique email per iteration |
| `/api/v1/alerts` | GET | 10% | Session (401 expected) | Auth-middleware throughput probe |
| `/api/v1/beta/verify-code` | POST | 5% | Public | DB LIKE query, 404 expected |

---

## Prerequisites

### Install k6

**macOS (Homebrew)**:
```bash
brew install k6
```

**Linux (Debian/Ubuntu)**:
```bash
sudo gpg -k
sudo gpg --no-default-keyring \
  --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 \
  --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

**Windows (Chocolatey)**:
```bash
choco install k6
```

**Docker** (no install required):
```bash
docker pull grafana/k6
```

Verify installation:
```bash
k6 version
# Expected: k6 v0.50.0 or later
```

---

## Running the Tests

All commands assume you are in the project root
(`/Users/devinmcgrath/projects/electricity-optimizer`).

### Smoke Test (50 VUs — 2 minutes)

Run this first to verify the backend is warm and the script is working.
Safe to run from a laptop; no distributed infrastructure needed.

```bash
k6 run --env SCENARIO=smoke scripts/load_test.js
```

Expected outcome: all thresholds pass, p99 < 500ms from a warm Render instance.

### Standard Test (500 VUs — ~4.5 minutes)

A mid-level regression check. Run this in CI or before deploying a performance
fix.

```bash
k6 run --env SCENARIO=standard scripts/load_test.js
```

### Full SLA Test (2000 VUs — 6 minutes)

The primary SLA validation run. **Run this from k6 Cloud** to distribute load
across multiple egress IPs and avoid saturating the backend's 100 req/min
per-IP rate limiter.

```bash
# Authenticate with k6 Cloud first (one time)
k6 login cloud --token <your-k6-cloud-token>

# Run on k6 Cloud infrastructure
k6 cloud scripts/load_test.js
```

To run locally (single IP — 429s from rate limiter are expected and tolerated
by the 95% success threshold):

```bash
k6 run scripts/load_test.js
```

### Spike Test

Validates recovery from a sudden traffic surge.

```bash
k6 run --env SCENARIO=spike scripts/load_test.js
```

### Soak Test (500 VUs — ~34 minutes)

Surfaces memory leaks, connection-pool exhaustion, and DB connection recycling
issues that only appear under sustained load.

```bash
k6 run --env SCENARIO=soak scripts/load_test.js
```

---

## Configuration Options

All options are passed as `--env` flags.

| Variable | Default | Description |
|---|---|---|
| `SCENARIO` | `full` | One of: `smoke`, `standard`, `full`, `spike`, `soak` |
| `BASE_URL` | `https://api.rateshift.app` | Backend URL to target |

**Examples**:

```bash
# Point at a staging backend
k6 run --env BASE_URL=https://staging.api.rateshift.app scripts/load_test.js

# Run smoke against local development server
k6 run --env SCENARIO=smoke --env BASE_URL=http://localhost:8000 scripts/load_test.js
```

---

## Infrastructure Constraints

Understanding these constraints helps interpret test results correctly.

### Rate Limiter (100 req/min per IP)

The FastAPI backend enforces a 100 req/min per-IP rate limit via
`RateLimitMiddleware`. Running 2000 VUs from a single IP will generate
429 responses. The script treats 429 as tolerated (not a test failure), and
the 95% success threshold accounts for a fraction of rate-limit hits.

For a clean full-scale run that avoids this, use k6 Cloud, which distributes
virtual users across multiple geographic egress points. Alternatively, run
behind a proxy pool or from multiple machines.

### Neon DB Connection Pool

The backend uses a PgBouncer-compatible connection pool with `size=5,
max_overflow=10` (15 total concurrent database connections). Endpoints that
bypass the pool (`/health/live`, `/health/ready`) are weighted higher in the
test to prevent pool exhaustion from cascading into 503s on data endpoints.

### Render Free Tier Cold Start

Render free-tier services spin down after 15 minutes of inactivity. The
script's `setup()` function sends a warmup request with a 60-second timeout
to wake the backend before the ramp-up begins. If the backend is cold, expect
the first 30 seconds of results to show elevated latency (300-2000ms).

To pre-warm manually:
```bash
curl -s https://api.rateshift.app/health/live
# Wait for: {"status":"alive"}
```

---

## Interpreting Results

A passing run looks like this in the k6 summary:

```
checks.........................: 97.23% 582134 out of 598712
http_req_duration..............: avg=312ms min=18ms med=245ms max=1987ms p(90)=890ms p(95)=1231ms p(99)=1876ms
http_req_failed................: 2.77%  16578 out of 598712
http_reqs......................: 598712 1664.2/s
```

Key signals to look for:

| Signal | Healthy | Degraded |
|---|---|---|
| p99 < 2000ms | Pass | Fail — DB pool or Render CPU saturation |
| http_req_failed < 5% | Pass | Fail — check for 5xx errors |
| http_reqs rate > 100/s | Pass | Fail — Render instance not handling load |
| rate_limit_hits counter | Some 429s (expected) | Many 429s from single IP |
| slow_requests_over_1s | < 10% of total | > 20% — investigate DB query time |

### Common Failure Modes

**p99 breaches 2000ms**:
- Render free tier CPU throttled — upgrade to paid plan or vertical scale
- DB connection pool exhausted — increase `max_overflow` in config
- Missing Redis cache — check `REDIS_URL` is set and Redis is reachable

**Failure rate > 5%**:
- 429 rate-limit hits from single-IP local run — use k6 Cloud
- 503 from backend — DB or Render instance down
- 500 errors — a regression in a recently deployed endpoint

**Throughput < 100 req/s**:
- Render free tier has insufficient CPU/memory for 2000 VUs
- Think time in the script (`sleep`) is too aggressive — reduce to 0.1–0.1s

---

## CI Integration

To run the smoke test in GitHub Actions on every PR, add this job to
`.github/workflows/ci.yml`:

```yaml
load-smoke:
  name: Load Test (Smoke)
  runs-on: ubuntu-latest
  needs: [backend-tests]  # only run after unit tests pass
  if: github.event_name == 'pull_request'
  steps:
    - uses: actions/checkout@v4

    - name: Install k6
      run: |
        sudo gpg --no-default-keyring \
          --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
          --keyserver hkp://keyserver.ubuntu.com:80 \
          --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
        echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
          | sudo tee /etc/apt/sources.list.d/k6.list
        sudo apt-get update && sudo apt-get install k6

    - name: Run smoke load test
      env:
        BASE_URL: https://api.rateshift.app
      run: k6 run --env SCENARIO=smoke --env BASE_URL=$BASE_URL scripts/load_test.js
```

---

## Relationship to Existing Load Tests

The project already has a Locust-based load test suite in `tests/load/`:

| Feature | Locust (`tests/load/`) | k6 (`scripts/load_test.js`) |
|---|---|---|
| Target | Local/staging | Production |
| Peak VUs | 2000 (stress mode) | 2000 (full mode) |
| Distributed | Via Locust master/worker | Via k6 Cloud |
| Thresholds | Informal | Formal SLA assertions |
| CI-friendly | Requires Python env | Single binary |
| Dashboard | Locust web UI | k6 Cloud or Grafana |

Both suites are complementary. Use Locust for local development load testing
and exploratory performance investigation. Use the k6 script for production
SLA validation and CI regression gates.

---

## Safety Notes

- The script sends only GET requests and two public POST endpoints. It does
  not call any `DELETE`, `PUT`, or `PATCH` endpoints.
- Beta signups use `@k6test.invalid` addresses that cannot receive email.
  Backend's background welcome-email task will fail silently (by design —
  the backend catches email errors and does not surface them to the caller).
- Beta verify-code probes use randomly generated codes that will not match any
  real code in the database.
- The `/api/v1/alerts` scenario sends unauthenticated GET requests that the
  backend correctly rejects with 401. No user data is accessed.
- Internal endpoints (`/api/v1/internal/*`) are not included in the test.

---

## Related Documentation

- `docs/TESTING.md` — full test suite overview including unit/integration/E2E
- `tests/load/locustfile.py` — existing Locust load tests
- `docs/DEPLOYMENT.md` — production deployment and rollback procedures
- `docs/MONITORING.md` — UptimeRobot / Better Stack monitoring configuration
