# Audit Report: Infrastructure & Deployment
**Date:** 2026-03-19
**Scope:** Docker, CI/CD pipelines, deployment config, infrastructure setup
**Files Reviewed:**
- `Dockerfile` (root)
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `ml/Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `render.yaml`
- `Procfile`
- `runtime.txt`
- `Makefile`
- `.dockerignore` (root)
- `backend/.dockerignore`
- `frontend/.dockerignore`
- `ml/.dockerignore`
- `.github/dependabot.yml`
- `.github/actions/retry-curl/action.yml`
- `.github/actions/notify-slack/action.yml`
- `.github/actions/warmup-backend/action.yml`
- `.github/actions/setup-python-env/action.yml`
- `.github/actions/setup-node-env/action.yml`
- `.github/actions/validate-migrations/action.yml`
- `.github/actions/wait-for-service/action.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy-production.yml`
- `.github/workflows/deploy-worker.yml`
- `.github/workflows/_backend-tests.yml`
- `.github/workflows/e2e-tests.yml`
- `.github/workflows/daily-data-pipeline.yml`
- `.github/workflows/self-healing-monitor.yml`
- `.github/workflows/secret-scan.yml`
- `.github/workflows/check-alerts.yml`
- `.github/workflows/price-sync.yml`
- `.github/workflows/observe-forecasts.yml`
- `.github/workflows/fetch-weather.yml`
- `.github/workflows/market-research.yml`
- `.github/workflows/sync-connections.yml`
- `.github/workflows/dunning-cycle.yml`
- `.github/workflows/kpi-report.yml`
- `.github/workflows/scrape-portals.yml`
- `.github/workflows/scrape-rates.yml`
- `.github/workflows/scan-emails.yml`
- `.github/workflows/nightly-learning.yml`
- `.github/workflows/detect-rate-changes.yml`
- `.github/workflows/data-retention.yml`
- `.github/workflows/data-health-check.yml`
- `.github/workflows/db-backup.yml`
- `.github/workflows/model-retrain.yml`
- `.github/workflows/code-analysis.yml`
- `.github/workflows/fetch-gas-rates.yml`
- `.github/workflows/fetch-heating-oil.yml`
- `.github/workflows/owasp-zap.yml`
- `.github/workflows/gateway-health.yml`
- `.github/workflows/utility-type-tests.yml`
- `.github/workflows/update-visual-baselines.yml`
- `backend/gunicorn_config.py`

***

## P0 -- Critical (Fix Immediately)

### 1. Root `.dockerignore` does not exclude `.env` -- secrets may be baked into Docker images
**File:** `/.dockerignore`, lines 10-12
**Details:** The root `.dockerignore` excludes `.env.test` and `backend/.env` but does NOT exclude the root `.env` file. The root `Dockerfile` (used by Render via `render.yaml`) runs `COPY backend/ .` from the project root context. If `.env` exists in the project root (and it does -- confirmed via glob), it could be copied into the Docker build context and potentially into the final image layer.

The root `.env` typically contains `DATABASE_URL`, `REDIS_PASSWORD`, `JWT_SECRET`, and all API keys for local development. If this file is present during a Docker build (e.g., CI or local `docker compose build`), those secrets become embedded in the image filesystem.

**Recommendation:** Add `.env` (without path prefix) to `/.dockerignore`:
```
.env
.env.*
!.env.example
```

### 2. `detect-rate-changes.yml` passes `api-key` input to `retry-curl`, but `retry-curl` has no such input
**File:** `.github/workflows/detect-rate-changes.yml`, line 28
**Details:** The workflow uses:
```yaml
uses: ./.github/actions/retry-curl
with:
  url: ${{ secrets.BACKEND_URL }}/api/v1/internal/detect-rate-changes
  method: POST
  api-key: ${{ secrets.INTERNAL_API_KEY }}
```
The `retry-curl` composite action defines inputs `url`, `method`, `headers`, `body`, `max-retries`, `initial-delay`, `max-delay`, and `timeout`. There is no `api-key` input. GitHub Actions silently ignores unknown inputs, meaning this workflow makes requests **without any authentication header**. The internal endpoint requires `X-API-Key`, so this endpoint call will fail with 401/403 on every invocation.

All other workflows correctly pass the API key via the `headers` input:
```yaml
headers: |
  X-API-Key: ${{ secrets.INTERNAL_API_KEY }}
  Content-Type: application/json
```

**Recommendation:** Replace the `api-key` input with the `headers` input pattern used by all other workflows.

### 3. `data-health-check.yml` re-fetches API response in a second `curl`, leaking the API key into `run` script
**File:** `.github/workflows/data-health-check.yml`, lines 34-50
**Details:** The "Validate health response" step stores `${{ secrets.INTERNAL_API_KEY }}` in the `API_KEY` environment variable and then uses it in a `curl` command within a `run:` block:
```yaml
env:
  API_KEY: ${{ secrets.INTERNAL_API_KEY }}
  API_URL: ${{ secrets.BACKEND_URL }}
run: |
  RESPONSE=$(curl -fsS -X GET \
    -H "X-API-Key: ${API_KEY}" \
    "${API_URL}/api/v1/internal/health-data")
```
While `${{ secrets.* }}` values are masked in logs by GitHub, the pattern of assigning secrets to environment variables and then using them in shell scripts is fragile. If the curl command fails with verbose error output or if `set -x` is ever added for debugging, the API key could appear in logs. More importantly, this step duplicates the API call that was already made by the `retry-curl` step above it, adding unnecessary latency and fragility.

**Recommendation:** Extend `retry-curl` to capture and output the response body (or add a `--output` parameter), eliminating the need for a second raw curl call.

***

## P1 -- High (Fix This Sprint)

### 4. `ci.yml` has no top-level `permissions` declaration -- defaults to full read/write
**File:** `.github/workflows/ci.yml`
**Details:** The CI workflow sets per-job permissions for the `changes`, `backend-lint`, and `frontend-lint` jobs, but has no top-level `permissions:` key. This means jobs without explicit permissions (e.g., `ml-tests`, `frontend-test`, `frontend-build`, `security-scan`, `migration-check`, `docker-build`, `notify-failure`) inherit the repository's default permissions, which is typically `read/write` for all scopes. This violates the principle of least privilege.

Other workflows correctly use `permissions: {}` at the top level.

**Recommendation:** Add `permissions: {}` at the top level of `ci.yml` (after `env:`), and add explicit per-job permissions only where needed (e.g., `contents: read` for checkout-only jobs).

### 5. `e2e-tests.yml` has no top-level `permissions` declaration
**File:** `.github/workflows/e2e-tests.yml`
**Details:** Same issue as `ci.yml`. The E2E tests workflow has per-job permissions on `changes` and `lighthouse` jobs, but `e2e-tests`, `load-tests`, `security-tests`, and `notify-failure` jobs inherit unconstrained default permissions.

**Recommendation:** Add `permissions: {}` at the top level.

### 6. `utility-type-tests.yml` has no `permissions` declaration at all
**File:** `.github/workflows/utility-type-tests.yml`
**Details:** This workflow triggers on push and pull_request but declares no permissions whatsoever -- neither at the workflow level nor at any job level. All jobs get the repository default, which is unnecessarily broad for a read-only test workflow.

**Recommendation:** Add `permissions: {}` at the top level.

### 7. Procfile uses `uvicorn` directly but `gunicorn_config.py` exists and is configured -- inconsistent production entry point
**File:** `Procfile`, line 1; `backend/gunicorn_config.py`
**Details:** The Procfile runs:
```
web: cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1
```
But there is a well-configured `gunicorn_config.py` with UvicornWorker, memory management (`max_requests=1000`, `max_requests_jitter=50`), graceful shutdown, and structured logging. Render uses the Procfile for native Python deployments. When using Docker (which `render.yaml` specifies), the Dockerfile CMD is used instead.

The root `Dockerfile` CMD (line 54) also uses raw `uvicorn`, bypassing gunicorn entirely. The `backend/Dockerfile` production stage (line 90) also uses raw `uvicorn`.

This means the gunicorn configuration with its worker recycling (`max_requests`), memory leak protection, and graceful shutdown hooks is **never used in production**. The `max_requests` setting is particularly important for long-running Python processes that tend to accumulate memory over time.

**Recommendation:** Either:
1. Switch the production CMD to use gunicorn: `CMD ["gunicorn", "-c", "gunicorn_config.py", "main:app"]`
2. Or remove `gunicorn_config.py` to avoid confusion, and implement periodic worker restart at the infrastructure level.

### 8. ML Dockerfile uses Python 3.11 while backend uses Python 3.12 -- version mismatch
**File:** `ml/Dockerfile`, line 4 vs `backend/Dockerfile`, line 4; `runtime.txt`, line 1
**Details:** The ML Dockerfile pins `python:3.11-slim` while all other components use Python 3.12. The `runtime.txt` specifies `python-3.12.12`. This creates potential compatibility issues if ML code is imported by the backend (which it is -- `ml/` is referenced in backend services for the ensemble predictor and HNSW vector store).

NumPy, Pandas, and TensorFlow behavior can differ between Python 3.11 and 3.12 (e.g., deprecation of `distutils`, changes in `typing`). Running tests on 3.12 in CI but deploying ML code on 3.11 in Docker means test coverage does not match runtime behavior.

**Recommendation:** Update `ml/Dockerfile` to use `python:3.12-slim` with a matching pinned digest.

### 9. `docker-compose.prod.yml` includes a local Postgres container that conflicts with Neon PostgreSQL
**File:** `docker-compose.prod.yml`, lines 138-169
**Details:** The production compose file defines a local `postgres` service and hardcodes the backend `DATABASE_URL` to point to it:
```yaml
DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/electricity
```
However, the actual production deployment uses Neon PostgreSQL (cloud-hosted), as documented extensively in CLAUDE.md and `render.yaml`. The development `docker-compose.yml` correctly uses `${DATABASE_URL}` from `.env` (which points to Neon).

If someone uses `docker-compose.prod.yml` for a production-like local deployment, they will get a completely separate database with no data, no migrations, and no schema. The `postgres-exporter` on line 281 also references this local database.

**Recommendation:** Either:
1. Remove the `postgres` service from `docker-compose.prod.yml` and use `${DATABASE_URL}` from environment (matching the dev compose approach), or
2. Rename this file to `docker-compose.local-prod.yml` and document that it simulates production locally with a separate database.

### 10. `db-backup.yml` extracts database password from connection string using `grep -oP` -- fragile parsing
**File:** `.github/workflows/db-backup.yml`, lines 297-299
**Details:** The backup verification job parses the Neon connection string using Perl-compatible regex:
```bash
DB_USER=$(echo "${{ secrets.NEON_CONNECTION_STRING }}" | grep -oP '(?<=://)[^:]+')
DB_PASS=$(echo "${{ secrets.NEON_CONNECTION_STRING }}" | grep -oP '(?<=:)[^@]+(?=@)')
DB_NAME=$(echo "${{ secrets.NEON_CONNECTION_STRING }}" | grep -oP '[^/]+$' | cut -d'?' -f1)
```
This parsing is fragile: it will break if the password contains `@` characters (URL-encoded as `%40`), if the connection string uses a different format (e.g., includes port), or if the Neon endpoint format changes. Additionally, `${{ secrets.NEON_CONNECTION_STRING }}` is used inside a `run:` block via string interpolation rather than via the `env:` mapping, which means GitHub Actions must expand the secret before shell execution. While the password is later masked with `::add-mask::`, the secret appears in the `run:` shell script literal before masking occurs.

**Recommendation:** Pass the connection string as an environment variable and use Python or a purpose-built URL parser:
```bash
python3 -c "from urllib.parse import urlparse; u=urlparse('$NEON_CONN'); print(f'{u.username}\n{u.password}\n{u.path.lstrip(\"/\")}')"
```

***

## P2 -- Medium (Fix Soon)

### 11. `docker-compose.yml` uses `prom/prometheus:latest` and `grafana/grafana:latest` -- unpinned monitoring images
**File:** `docker-compose.yml`, lines 96, 114
**Details:** The development compose file uses `:latest` tags for Prometheus and Grafana, while the production compose file correctly pins versions (`prom/prometheus:v2.51.0`, `grafana/grafana:10.4.1`). Using `:latest` in development means each `docker compose pull` may bring a breaking change, making it impossible to reproduce issues consistently.

**Recommendation:** Pin versions in `docker-compose.yml` to match `docker-compose.prod.yml`.

### 12. `redis` healthcheck in `docker-compose.yml` exposes password in process list
**File:** `docker-compose.yml`, line 85; `docker-compose.prod.yml`, line 127
**Details:** Both compose files use:
```yaml
test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
```
The `-a` flag passes the password as a command-line argument, which is visible in `ps aux` output and in Docker inspect. Redis itself logs a warning about this: `Warning: Using a password with '-a' or '-u' option on the command line interface may not be safe.`

**Recommendation:** Use the `REDISCLI_AUTH` environment variable instead:
```yaml
test: ["CMD-SHELL", "REDISCLI_AUTH=${REDIS_PASSWORD} redis-cli ping"]
```

### 13. `docker-compose.prod.yml` postgres-exporter uses `sslmode=require` for local container connection
**File:** `docker-compose.prod.yml`, line 286
**Details:** The postgres-exporter DATA_SOURCE_NAME specifies `sslmode=require`, but the local Postgres container does not have SSL configured. This will cause the exporter to fail to connect. The dev compose file does not include a postgres-exporter, so this may never have been tested.

**Recommendation:** Change to `sslmode=disable` for the local container, or configure SSL in the Postgres container.

### 14. E2E test database setup only applies 3 of 53 migrations
**File:** `.github/workflows/e2e-tests.yml`, lines 97-103
**Details:** The E2E test setup applies only `init_neon.sql`, `002_gdpr_auth_tables.sql`, and `003_reconcile_schema.sql`. The backend has 53 migrations through `053_notification_dedup_index`. This means E2E tests run against a severely outdated schema, missing tables for community posts, alerts, notifications, utility accounts, and dozens of other features. This significantly reduces E2E test coverage reliability -- any E2E test that touches features added after migration 003 is running against a schema that does not match production.

In contrast, the `migration-check` job in `ci.yml` applies ALL migrations sequentially, proving they work.

**Recommendation:** Apply all migrations in the E2E test setup, matching the approach in `ci.yml`:
```bash
PGPASSWORD=postgres psql -h localhost -U postgres -d electricity_test \
  -v ON_ERROR_STOP=1 -f backend/migrations/init_neon.sql
for f in $(ls backend/migrations/[0-9]*.sql | sort); do
  PGPASSWORD=postgres psql -h localhost -U postgres -d electricity_test \
    -v ON_ERROR_STOP=1 -f "$f"
done
```

### 15. `render.yaml` uses Docker runtime but the `dockerfilePath` points to `backend/Dockerfile` which has no `--timeout-graceful-shutdown`
**File:** `render.yaml`, lines 4-6; `backend/Dockerfile`, line 90
**Details:** The `render.yaml` specifies `dockerfilePath: ./backend/Dockerfile` and `dockerContext: ./backend`. The production stage CMD in `backend/Dockerfile` is:
```
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]
```
This command does not include `--timeout-graceful-shutdown`, unlike the root `Dockerfile` which uses `--timeout-graceful-shutdown 30`. Without this flag, Render's SIGTERM during deploys may kill in-flight requests immediately. Additionally, it hardcodes port `8000` while Render injects `PORT=10000` -- the root `Dockerfile` correctly uses `${PORT:-10000}`.

There are now two Dockerfiles that could serve production. The root `Dockerfile` is better configured (dynamic port, graceful shutdown, 1 worker for free tier), but `render.yaml` points to `backend/Dockerfile`.

**Recommendation:** Either:
1. Update `render.yaml` to point to the root `Dockerfile` (which is better configured for Render), or
2. Add `--timeout-graceful-shutdown 30` and use `${PORT:-10000}` in `backend/Dockerfile` production CMD.

### 16. `backend/Dockerfile` production stage hardcodes 2 workers -- exceeds free tier memory
**File:** `backend/Dockerfile`, line 90
**Details:** The production CMD specifies `--workers 2`, but `gunicorn_config.py` (line 16) documents that the free tier (512MB RAM) should use 1 worker because "each worker costs ~80-120MB RAM". The root `Dockerfile` correctly uses `--workers 1`. Running 2 workers on a 512MB instance will cause OOM kills under load.

**Recommendation:** Change to `--workers 1` in `backend/Dockerfile` production CMD.

### 17. Frontend Dockerfile comment says "Next.js 14" but project uses Next.js 16
**File:** `frontend/Dockerfile`, line 1
**Details:** The comment reads `# Multi-stage build for Next.js 14 frontend` but the project uses Next.js 16 (per CLAUDE.md). This is a documentation-only issue but could mislead operators debugging build failures related to Next.js version differences (e.g., standalone output format changes between 14 and 16).

**Recommendation:** Update the comment to `# Multi-stage build for Next.js 16 frontend`.

### 18. No staging environment in deployment pipeline -- production deploys go directly from CI
**File:** `.github/workflows/deploy-production.yml`
**Details:** The deploy pipeline validates (tests, security gate, migration gate) and then deploys directly to production. There is no staging environment for integration testing against real external services (Neon, Stripe, Resend, etc.). The smoke tests run post-deploy against production. The `Makefile` has `deploy-staging` target (line 159) that calls `scripts/deploy.sh staging`, but no `scripts/deploy.sh` was found, and no staging workflow exists.

This means every production deploy is a direct push with only unit test validation. If a migration works in CI's local Postgres but fails against Neon (e.g., due to neon_auth schema differences), it will be discovered in production.

**Recommendation:** Create a staging environment (e.g., Neon branch + Render preview service) and add a staging deploy step before production.

### 19. `owasp-zap.yml` uses template expression that may not evaluate correctly
**File:** `.github/workflows/owasp-zap.yml`, line 24
**Details:** The target is specified as:
```yaml
target: ${{ secrets.RENDER_BACKEND_URL || 'https://api.rateshift.app' }}
```
GitHub Actions expression `||` with secrets can behave unexpectedly. If `RENDER_BACKEND_URL` is not set, `secrets.RENDER_BACKEND_URL` is an empty string (not `null`), so the `||` operator may not fall through to the default. Empty strings are falsy in GitHub expressions, so this should work, but the secret name `RENDER_BACKEND_URL` is different from the `BACKEND_URL` secret used everywhere else. If `RENDER_BACKEND_URL` was never configured, ZAP will scan against the hardcoded URL, which routes through the Cloudflare Worker rather than Render directly -- meaning ZAP is scanning the CF Worker's WAF behavior rather than the actual backend application.

**Recommendation:** Use `${{ secrets.BACKEND_URL }}` for consistency, and document whether the scan should target the CF Worker (edge layer security) or the Render backend directly.

***

## P3 -- Low / Housekeeping

### 20. `docker-compose.yml` frontend volume mount includes `/app/node_modules` anonymous volume
**File:** `docker-compose.yml`, lines 62-64
**Details:** The frontend service uses:
```yaml
volumes:
  - ./frontend:/app
  - /app/node_modules
  - /app/.next
```
The anonymous volumes for `node_modules` and `.next` prevent the host mount from overwriting container-installed dependencies. This is a common Docker development pattern but has a subtle issue: the anonymous volume persists across `docker compose up/down` cycles, meaning `npm ci` changes on the host are not reflected in the container until `docker compose down -v` is run.

**Recommendation:** Add a comment explaining the volume behavior, or use a named volume for transparency.

### 21. `model-retrain.yml` does not actually retrain -- it only validates the pipeline
**File:** `.github/workflows/model-retrain.yml`, lines 33-45
**Details:** The "Run model retraining" step creates a `ModelConfig` and `ElectricityPriceForecaster` and prints parameter count, but does not train on any data. The comment says "In production, data would be fetched from TimescaleDB." This workflow runs weekly but produces no trained model artifact. It consumes CI minutes for a validation that is already covered by `ml-tests` in `ci.yml`.

**Recommendation:** Either implement actual model retraining (fetch data from Neon, train, upload model artifact) or remove the workflow to save ~30 min/week of GHA time.

### 22. `Makefile` `docs` target opens Swagger UI which is disabled in production
**File:** `Makefile`, lines 239-241
**Details:** The `make docs` target opens `http://localhost:8000/docs`, but per CLAUDE.md, Swagger/ReDoc is disabled in production. This is fine for local development but should include a comment noting the limitation.

**Recommendation:** Add a comment: `## Open API documentation (development only -- disabled in production)`

### 23. `dependabot.yml` does not include the `workers/api-gateway` npm ecosystem
**File:** `.github/dependabot.yml`
**Details:** Dependabot is configured for `pip` (backend, ml), `npm` (frontend), `docker` (backend, frontend, ml, root), and `github-actions`. However, the Cloudflare Worker in `workers/api-gateway/` has its own `package.json` and `package-lock.json` that are not covered by any Dependabot configuration. Worker dependencies (e.g., wrangler, vitest, miniflare) will not receive automated update PRs.

**Recommendation:** Add:
```yaml
- package-ecosystem: "npm"
  directory: "/workers/api-gateway"
  schedule:
    interval: "weekly"
    day: "monday"
  open-pull-requests-limit: 3
```

### 24. Backend tests in E2E workflow do not set `INTERNAL_API_KEY` env var
**File:** `.github/workflows/e2e-tests.yml`, lines 106-113
**Details:** The backend server in E2E tests is started with `DATABASE_URL`, `REDIS_URL`, `ENVIRONMENT`, and `JWT_SECRET`, but not `INTERNAL_API_KEY`. This means the backend may fail to validate internal API requests during E2E tests, or the internal endpoint guard may be disabled in test mode. This is a minor concern since E2E tests primarily test frontend behavior, not internal endpoints.

**Recommendation:** Add `INTERNAL_API_KEY: test_internal_key` to the E2E backend env for completeness.

### 25. `docker-compose.yml` maps Redis to host port 6380 (non-standard)
**File:** `docker-compose.yml`, line 76
**Details:** Redis is mapped as `6380:6379`, using port 6380 on the host. This avoids conflicts with a local Redis installation, which is good practice. However, the `REDIS_URL` in the backend environment uses `redis://:${REDIS_PASSWORD}@redis:6379/0` (internal Docker port), which is correct. No issue functionally, but developers running Redis CLI from the host must remember to use port 6380.

**Recommendation:** Add a comment: `# Host port 6380 to avoid conflicts with local Redis`

### 26. `gunicorn_config.py` `on_starting` hook logs "Electricity Optimizer" instead of "RateShift"
**File:** `backend/gunicorn_config.py`, line 63
**Details:** The log message says "Starting Electricity Optimizer API..." but the project was rebranded to "RateShift". This is cosmetic and only affects log output.

**Recommendation:** Update to "Starting RateShift API..."

### 27. Root `Dockerfile` and `backend/Dockerfile` both serve the backend -- redundant
**File:** `Dockerfile` (root); `backend/Dockerfile`
**Details:** Two Dockerfiles can build the backend for production. The root `Dockerfile` is a simpler 2-stage build tailored for Render (dynamic port, 1 worker, graceful shutdown). The `backend/Dockerfile` is a more complex 3-stage build (base, development, builder, production) with compilation and 2 workers. `render.yaml` uses the `backend/Dockerfile`. This redundancy can lead to drift where one Dockerfile is updated but not the other.

**Recommendation:** Consolidate to a single Dockerfile for the backend. If both are needed (one for Render, one for docker-compose), document the distinction clearly at the top of each file.

***

## Files With No Issues Found

- `.github/workflows/check-alerts.yml` -- Clean, minimal, correct `permissions: {}`, proper `retry-curl` + `notify-slack` pattern.
- `.github/workflows/price-sync.yml` -- Clean, proper manual-only trigger after CF Worker cron migration.
- `.github/workflows/observe-forecasts.yml` -- Clean, correct pattern.
- `.github/workflows/fetch-weather.yml` -- Clean, correct 12h cron with offset.
- `.github/workflows/market-research.yml` -- Clean, correct daily cron.
- `.github/workflows/sync-connections.yml` -- Clean, correct 6h cron.
- `.github/workflows/dunning-cycle.yml` -- Clean, correct daily cron, critical severity notification.
- `.github/workflows/kpi-report.yml` -- Clean, correct daily cron.
- `.github/workflows/scrape-portals.yml` -- Clean, correct weekly cron.
- `.github/workflows/scrape-rates.yml` -- Clean, manual-only trigger.
- `.github/workflows/scan-emails.yml` -- Clean, manual-only trigger.
- `.github/workflows/nightly-learning.yml` -- Clean, manual-only trigger.
- `.github/workflows/data-retention.yml` -- Clean, correct weekly cron.
- `.github/workflows/fetch-gas-rates.yml` -- Clean, correct weekly cron.
- `.github/workflows/fetch-heating-oil.yml` -- Clean, correct weekly cron.
- `.github/workflows/secret-scan.yml` -- Clean, gitleaks with full history scan, weekly + push/PR triggers.
- `.github/workflows/deploy-worker.yml` -- Clean, tests before deploy, path-filtered trigger, smoke test, failure notification.
- `.github/workflows/daily-data-pipeline.yml` -- Clean, sequential pipeline consolidation with proper error handling.
- `.github/workflows/self-healing-monitor.yml` -- Well-designed auto-issue creation/closure system, correct permissions.
- `.github/workflows/db-backup.yml` -- Comprehensive backup with R2 upload, integrity verification via ephemeral Neon branch, rotation. (Password parsing issue noted in P1 #10.)
- `.github/workflows/update-visual-baselines.yml` -- Clean, manual-only with proper branch handling.
- `.github/workflows/code-analysis.yml` -- Clean, PR-only trigger with correct `permissions: {}`.
- `.github/actions/retry-curl/action.yml` -- Well-implemented exponential backoff with jitter, 4xx fail-fast, temp file for body, proper output handling.
- `.github/actions/notify-slack/action.yml` -- Clean severity-to-color mapping, proper secret handling.
- `.github/actions/warmup-backend/action.yml` -- Correct Render cold-start warmup pattern with configurable attempts.
- `.github/actions/setup-python-env/action.yml` -- Clean, proper pip caching.
- `.github/actions/setup-node-env/action.yml` -- Clean, proper npm caching.
- `.github/actions/validate-migrations/action.yml` -- Thorough 4-check validation (sequential numbering, IF NOT EXISTS, neondb_owner, no SERIAL).
- `.github/actions/wait-for-service/action.yml` -- Clean polling implementation.
- `backend/.dockerignore` -- Correctly excludes `.env`, `.env.local`, and development artifacts.
- `frontend/.dockerignore` -- Correctly excludes environment files, tests, and build artifacts.
- `ml/.dockerignore` -- Correctly excludes environment files, tests, and large model files.
- `runtime.txt` -- Correctly specifies `python-3.12.12`.

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| P0 Critical | 3 | Root `.env` leaking into Docker images; broken auth in `detect-rate-changes.yml`; fragile secret handling in `data-health-check.yml` |
| P1 High | 7 | Missing top-level CI permissions (3 workflows); unused gunicorn config; Python version mismatch; conflicting prod Postgres; fragile connection string parsing |
| P2 Medium | 9 | Unpinned dev images; Redis password in process list; incomplete E2E migrations; Dockerfile port/worker mismatches; no staging environment; stale comments |
| P3 Low | 8 | Missing worker Dependabot config; redundant Dockerfiles; cosmetic naming issues; dead model retrain workflow |

**Overall Assessment:** The infrastructure is well-designed for a free-tier deployment. Standout positives include:
- Excellent use of composite actions (`retry-curl`, `warmup-backend`, `validate-migrations`) for DRY CI/CD
- Strong security posture with `permissions: {}` on most workflows, gitleaks scanning, pip-audit, npm audit, OWASP ZAP, and Bandit
- Comprehensive deployment pipeline with automated rollback, smoke tests, and Slack notifications
- Well-implemented self-healing monitor with automatic issue creation/closure
- Proper Docker multi-stage builds with non-root users and health checks
- Good cost optimization via CF Worker cron triggers and consolidated daily pipeline

The critical items (P0) should be fixed immediately -- the `.env` leak and broken authentication are the most urgent. The P1 items around CI permissions and Dockerfile consistency should be addressed this sprint.
