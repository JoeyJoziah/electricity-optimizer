# Audit Report: Infrastructure & Deployment
**Date:** 2026-03-23
**Scope:** Docker, CI/CD, GHA workflows, deployment config, monitoring
**Files Reviewed:**
- `/Users/devinmcgrath/projects/electricity-optimizer/Dockerfile` (root — Render production image)
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/Dockerfile` (backend — docker-compose target)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/Dockerfile`
- `/Users/devinmcgrath/projects/electricity-optimizer/docker-compose.yml`
- `/Users/devinmcgrath/projects/electricity-optimizer/docker-compose.prod.yml`
- `/Users/devinmcgrath/projects/electricity-optimizer/.dockerignore`
- `/Users/devinmcgrath/projects/electricity-optimizer/render.yaml`
- `/Users/devinmcgrath/projects/electricity-optimizer/workers/api-gateway/wrangler.toml`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/gunicorn_config.py`
- `.github/dependabot.yml`
- `.github/actions/retry-curl/action.yml`
- `.github/actions/notify-slack/action.yml`
- `.github/actions/validate-migrations/action.yml`
- `.github/actions/warmup-backend/action.yml`
- `.github/actions/wait-for-service/action.yml`
- `.github/actions/setup-python-env/action.yml`
- `.github/actions/setup-node-env/action.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/_backend-tests.yml`
- `.github/workflows/deploy-production.yml`
- `.github/workflows/deploy-worker.yml`
- `.github/workflows/e2e-tests.yml`
- `.github/workflows/self-healing-monitor.yml`
- `.github/workflows/daily-data-pipeline.yml`
- `.github/workflows/db-backup.yml`
- `.github/workflows/secret-scan.yml`
- `.github/workflows/owasp-zap.yml`
- `.github/workflows/code-analysis.yml`
- `.github/workflows/fetch-weather.yml`
- `.github/workflows/sync-connections.yml`
- `.github/workflows/dunning-cycle.yml`
- `.github/workflows/kpi-report.yml`
- `.github/workflows/market-research.yml`
- `.github/workflows/scrape-portals.yml`
- `.github/workflows/scrape-rates.yml`
- `.github/workflows/model-retrain.yml`
- `.github/workflows/nightly-learning.yml`
- `.github/workflows/detect-rate-changes.yml`
- `.github/workflows/fetch-heating-oil.yml`
- `.github/workflows/gateway-health.yml`
- `.github/workflows/fetch-gas-rates.yml`
- `.github/workflows/utility-type-tests.yml`
- `.github/workflows/price-sync.yml`
- `.github/workflows/observe-forecasts.yml`
- `.github/workflows/check-alerts.yml`
- `.github/workflows/scan-emails.yml`
- `.github/workflows/data-retention.yml`
- `.github/workflows/data-health-check.yml`
- `.github/workflows/update-visual-baselines.yml`

---

## P0 — Critical (Fix Immediately)

### P0-01: Two Conflicting Production Dockerfiles — Render Uses Wrong One

**Files:** `render.yaml` line 6, `Dockerfile` (root), `backend/Dockerfile`

`render.yaml` specifies:
```yaml
dockerfilePath: ./backend/Dockerfile
dockerContext: ./backend
```

This means Render builds from `backend/Dockerfile`, which is the multi-stage file with a `development` / `builder` / `production` trio. The root `Dockerfile` (used by CI's docker-build job in `ci.yml` lines 397-406 with `file: ./backend/Dockerfile` and `context: ./backend`) is *also* `backend/Dockerfile`, but there is a separate root-level `Dockerfile` that diverges significantly.

The root `Dockerfile` uses `uvicorn` with 1 worker and `--timeout-graceful-shutdown 30`. The `backend/Dockerfile` production stage uses `uvicorn` with 2 workers and `--no-access-log`. These are different operational behaviors. The root `Dockerfile` is what docker-compose references by default when context is `.` (root), but it specifies no `target` stages named `development` or `production` for the backend — it IS the backend-only Dockerfile.

The existence of two separate Dockerfiles for the same service with different CMD behaviors means the image tested in CI (via `docker-compose.yml` with `context: ./backend`) may not match what is manually run from the root. The root `Dockerfile` will silently run a single-worker uvicorn with graceful shutdown settings that differ from `backend/Dockerfile`. This is a maintenance hazard and source of production/CI divergence.

**Fix:** Remove or rename the root `Dockerfile` with a comment redirecting to `backend/Dockerfile`. Only one canonical production Dockerfile should exist per service.

---

### P0-02: `wrangler.toml` Exposes Render Internal Origin URL in Public Repository

**File:** `workers/api-gateway/wrangler.toml` line 40

```toml
ORIGIN_URL = "https://electricity-optimizer.onrender.com"
```

This value is committed to the public git repository. Any attacker can send requests directly to `electricity-optimizer.onrender.com` and bypass the CF Worker's rate limiting (120/30/600 per minute), bot detection, CORS enforcement, and internal auth header injection. Render free tier does not support IP allowlisting as a mitigation. This finding was raised in audits on 2026-03-16, 2026-03-17, and 2026-03-18 and remains unresolved as of this audit.

Note: `ALLOWED_ORIGINS` being committed is acceptable since it is public domain information, but `ORIGIN_URL` being the internal bypass route is the risk.

**Fix:** Move `ORIGIN_URL` to a wrangler secret (`wrangler secret put ORIGIN_URL`) and remove it from `wrangler.toml`. The toml `[vars]` section is committed to the repo; secrets are stored encrypted in Cloudflare's platform and never in source control.

---

### P0-03: E2E Tests Apply Only First 3 Migrations — 57 Migrations Not Applied

**File:** `.github/workflows/e2e-tests.yml` lines 99-102

```yaml
- name: Set up database
  run: |
    PGPASSWORD=postgres psql ... -f backend/migrations/init_neon.sql
    PGPASSWORD=postgres psql ... -f backend/migrations/002_gdpr_auth_tables.sql
    PGPASSWORD=postgres psql ... -f backend/migrations/003_reconcile_schema.sql
```

The E2E test suite spins up a local Postgres service and applies only migrations 001-003 of a known 60-migration schema. The production database has 53 public tables from 60 total migrations. E2E tests therefore run against a schema that is missing all tables created by migrations 004-060 — including `payment_retry_history` (024), `community_posts/votes/reports` (049-050), `notification_dedup_index` (053), `stripe_customer_id_unique` (056), `oauth_tokens_bytea` (059), and `updated_at_triggers` (060). Any E2E test that exercises endpoints touching those tables will either silently succeed against a stub schema or fail with misleading errors.

**Fix:** Replicate the migration-check job approach from `ci.yml` lines 362-373 — apply ALL migrations in sequence. A loop is already proven in CI: `for f in $(ls backend/migrations/[0-9]*.sql | sort); do psql ... -f "$f"; done`.

---

## P1 — High (Fix This Sprint)

### P1-01: `detect-rate-changes.yml` Has No `timeout-minutes` on Its Job

**File:** `.github/workflows/detect-rate-changes.yml`

The `detect` job has no `timeout-minutes` specified at the job level. All other cron/data workflows in the project specify explicit timeouts (e.g., `fetch-weather.yml` line 18: `timeout-minutes: 5`, `daily-data-pipeline.yml` line 17: `timeout-minutes: 20`). Without an explicit timeout, the GHA default of 360 minutes applies. If this job hangs (e.g., backend never responds, retry loop stalls), it will consume 6 hours of runner minutes before GHA forcibly cancels it, significantly inflating monthly GHA usage and potentially blocking other queued runs in the same concurrency group.

**Fix:** Add `timeout-minutes: 10` to the `detect` job in `detect-rate-changes.yml`.

---

### P1-02: `scrape-portals.yml` Uses Undeclared `retry-delay` Input

**File:** `.github/workflows/scrape-portals.yml` line 38

```yaml
retry-delay: "10"
```

The `retry-curl` composite action (`retry-curl/action.yml`) defines no `retry-delay` input — the valid input for controlling the initial delay is `initial-delay` (line 22 of `retry-curl/action.yml`). Passing an undeclared input to a composite action silently ignores it; GHA does not error on unknown inputs to composite actions. The effect is that `scrape-portals.yml` believes it is configuring a 10-second retry delay but is actually using the composite default of `initial-delay: 5` seconds. This is a silent misconfiguration.

**Fix:** Change `retry-delay: "10"` to `initial-delay: "10"` in `scrape-portals.yml` line 38.

---

### P1-03: `model-retrain.yml` Does Not Actually Retrain — Validates Pipeline Only

**File:** `.github/workflows/model-retrain.yml` lines 33-45

The "Weekly Model Retraining" workflow runs a Python snippet that instantiates the forecaster and prints parameter counts but does not fetch real training data, does not call `forecaster.fit()`, and does not save any model artifact. The inline comment on line 38 says "In production, data would be fetched from TimescaleDB. For now, this validates the training pipeline runs." This workflow has been in this state since initial implementation and consumes runner minutes weekly (~30 min timeout) without performing actual model retraining.

There is no model artifact upload, no connection to the production database (`DATABASE_URL` is not passed as an env var to the retraining step), and no deployment of the retrained model back to the application.

**Fix:** Either (a) implement actual retraining with `DATABASE_URL` passed from secrets, model artifact upload to R2/S3, and deployment via a backend endpoint; or (b) if the feature is not ready, convert to `workflow_dispatch`-only (remove the schedule) to stop burning ~120 min/month on a no-op.

---

### P1-04: `deploy-production.yml` Rollback Uses Hard-Coded Render Service ID

**File:** `.github/workflows/deploy-production.yml` lines 192-194

```yaml
env:
  RENDER_API_BASE: https://api.render.com/v1
  BACKEND_SERVICE_ID: srv-d649uhur433s73d557cg
```

The Render backend service ID is hard-coded as a workflow env var rather than a secret. While this specific ID is not secret (Render service IDs are not sensitive credentials), hard-coding it means that if the service is ever recreated (e.g., after a Render free-tier reset, service deletion, or plan upgrade with a new service), the rollback mechanism silently stops working. The value also appears in the deploy-production.yml file committed to the repo.

Additionally, the rollback job does not receive the `SLACK_INCIDENTS_WEBHOOK_URL` secret via explicit `secrets:` inheritance — it relies on the default `secrets: inherit` behavior (which is not set on this workflow), meaning the Slack notification at line 279-284 may fail silently if the secret is not available to the `rollback` job.

**Fix:** Move `BACKEND_SERVICE_ID` to a repository secret named `RENDER_BACKEND_SERVICE_ID`. Add `secrets: inherit` or explicit secret passing to ensure Slack notifications work from the rollback job.

---

### P1-05: `render.yaml` `db-maintenance` Cron Uses Wrong Dockerfile Path

**File:** `render.yaml` lines 116-127

The `db-maintenance` Render cron job specifies:
```yaml
dockerfilePath: ./backend/Dockerfile
dockerContext: ./backend
```

This is consistent with the web service definition. However, `db_maintenance.py` is at `backend/scripts/db_maintenance.py` and is invoked as `python scripts/db_maintenance.py` with `dockerContext: ./backend`. The script path is relative to the working directory inside the container. The `backend/Dockerfile` sets `WORKDIR /app` and copies all of `backend/` to `/app`. So the invocation is `python scripts/db_maintenance.py` inside `/app`, which should resolve to `/app/scripts/db_maintenance.py`. This is correct as long as the script is not excluded from the Docker image.

However, `.dockerignore` line 43 contains `scripts/`. This means the `scripts/` directory is excluded from the Docker image built by the root `Dockerfile`. Since `render.yaml` uses `backend/Dockerfile` with `dockerContext: ./backend`, and `.dockerignore` applies to the build context, the `scripts/` exclusion excludes the `backend/scripts/` directory from the image — meaning `db_maintenance.py` is not present in the container, and the db-maintenance cron will always fail with `ModuleNotFoundError` or file-not-found.

**Fix:** Add a `.dockerignore` exception: change `scripts/` to a scoped exclusion that does not apply when building from the `./backend` context, or create a separate `.dockerignore` inside `backend/` that does not exclude `scripts/`. Alternatively, remove `scripts/` from the root `.dockerignore` (the root `Dockerfile` does not need scripts excluded since it only copies `backend/`).

---

### P1-06: `self-healing-monitor.yml` Monitors `scan-emails`, `nightly-learning`, `detect-rate-changes` as Independent Workflows, But These Were Consolidated Into `daily-data-pipeline.yml`

**File:** `.github/workflows/self-healing-monitor.yml` lines 43, 48, and the auto-close case statements at lines 184, 189

The self-healing monitor tracks `scan-emails.yml`, `nightly-learning.yml`, and `detect-rate-changes.yml` as separate workflows to monitor for failures. However, per CLAUDE.md and the cron comments in each file, these workflows no longer have scheduled cron triggers — their crons were moved to `daily-data-pipeline.yml`. The workflows still run only via `workflow_dispatch`. This means:

1. The monitor will query GHA for runs of these three workflows looking for failures in the last 24 hours, but since they only run on manual dispatch, the failure count will be 0 indefinitely. The monitor is tracking ghost workflows that never fail automatically.
2. If `daily-data-pipeline.yml` fails, the individual step failures (scan-emails, nightly-learning, detect-rate-changes) are NOT surfaced as separate failures — they fail atomically as part of the pipeline job. The monitor tracks `daily-data-pipeline.yml` separately (line 51) which handles the pipeline failure, but the granularity for which step failed is lost.

**Fix:** Remove `scan-emails.yml`, `nightly-learning.yml`, and `detect-rate-changes.yml` from the self-healing monitor matrix. Ensure `daily-data-pipeline.yml` is monitored at sufficient severity (currently `warning` at line 51, which is appropriate). Consider adding step-level failure reporting within `daily-data-pipeline.yml` itself (each step already has `retry-curl` + `notify-slack` on failure).

---

### P1-07: `code-analysis.yml` Security Step Has No `continue-on-error` But Can Fail Non-Deterministically

**File:** `.github/workflows/code-analysis.yml` lines 50-64

The "Security scan" step runs `claude-flow security scan` without `|| true`, and if it finds high/critical findings, the subsequent "Check for high-severity findings" step exits with code 1, blocking the PR. However, `claude-flow security scan` is a third-party CLI tool installed fresh each run via `npm install -g claude-flow@latest` (line 28). If the claude-flow package has a breaking release, the security scan fails to install or run, blocking all PRs to `main`. The step on line 50 has no `continue-on-error: true` and no version pin on the `claude-flow` installation.

**Fix:** Pin the claude-flow version (`npm install -g claude-flow@<version>`) and add `continue-on-error: true` to steps that invoke the tool (or alternatively, use a locked version from the project's own devDependencies).

---

## P2 — Medium (Fix Soon)

### P2-01: `docker-compose.yml` Dev Backend Uses Wrong Build Context

**File:** `docker-compose.yml` lines 13-16

```yaml
build:
  context: ./backend
  dockerfile: Dockerfile
  target: development
```

This references `backend/Dockerfile` with a `development` target. The `backend/Dockerfile` has a `FROM base as development` stage at line 26 that copies everything and runs `uvicorn --reload`. This is correct for local development. However, the dev backend service mounts `- ./backend:/app` as a volume (line 36), overriding the COPY in the Dockerfile. The mounted path is `./backend` → `/app`, but the `backend/Dockerfile` sets `WORKDIR /app` and copies to `/app`. This is consistent.

The issue is that the development backend also mounts `backend-cache:/root/.cache` (line 37) but the `backend/Dockerfile` creates a non-root user `appuser` (line 73). If the appuser UID/home is `/home/appuser`, the cache volume mounted at `/root/.cache` will not be used by the appuser. The dev container does not switch to appuser (unlike production), which means the dev container runs as root — inconsistent with production. Security-sensitive behaviors (file permissions, secret access patterns) will differ between dev and production.

**Fix:** The dev stage should either not create the non-root user (keeping root for dev) with a clear comment, or mount the cache to `/home/appuser/.cache`. Add a comment in `docker-compose.yml` noting that the dev container intentionally runs as root for hot-reload convenience.

---

### P2-02: `docker-compose.yml` Monitoring Services Use `latest` Image Tags (Prometheus, Grafana, Node-Exporter, Redis-Exporter)

**File:** `docker-compose.yml` lines 96, 114, 133, 150

```yaml
prometheus:
  image: prom/prometheus:latest
grafana:
  image: grafana/grafana:latest
node-exporter:
  image: prom/node-exporter:latest
redis-exporter:
  image: oliver006/redis_exporter:latest
```

The dev compose uses `:latest` for all four monitoring images. `docker-compose.prod.yml` correctly pins specific versions (prometheus:v2.51.0, grafana:10.4.1, node-exporter:v1.7.0, redis-exporter:v1.58.0). The dev `latest` tags will pull different versions on different machines, causing monitoring configuration divergence between developers and between dev/prod. A Prometheus major version change (e.g., from v2 to v3) could break scrape configs that work in prod.

**Fix:** Pin exact versions in `docker-compose.yml` matching those in `docker-compose.prod.yml`.

---

### P2-03: `render.yaml` Missing Several Production-Critical Env Vars

**File:** `render.yaml` lines 1-127

The render.yaml serves as the infrastructure-as-code definition for Render. The following env vars are documented in CLAUDE.md as used in production but are absent from `render.yaml` entirely:

- `OAUTH_STATE_SECRET` — used for HMAC-SHA256 signing of OAuth state parameters (5-part format, 10-min expiry per CLAUDE.md). Without this in render.yaml, adding a new Render service from scratch via IaC would produce a backend that silently skips state verification on OAuth flows.
- `ML_MODEL_SIGNING_KEY` — used for HMAC model integrity verification (sign on save, verify on load per CLAUDE.md patterns).
- `SLACK_INCIDENTS_WEBHOOK_URL` — referenced in GHA workflows but if backend itself needs to emit Slack notifications (incident webhooks), the absence would be silent.
- `REDIS_PASSWORD` — the `REDIS_URL` is present but the raw password is used in `gunicorn_config.py` and may be needed independently.

Additionally, `render.yaml` includes `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` as `sync: false` (lines 46-49), which are documented as placeholders with real values pending. This is acceptable but should be noted.

**Fix:** Audit all env vars in `backend/config/settings.py` and ensure every setting that has no default is listed in `render.yaml`. Add `OAUTH_STATE_SECRET` and `ML_MODEL_SIGNING_KEY` at minimum.

---

### P2-04: `_backend-tests.yml` Runs `pip-audit` Against the Full Installed Environment, Not Just Project Dependencies

**File:** `.github/workflows/_backend-tests.yml` lines 63-68

```yaml
- name: Dependency audit (pip-audit)
  run: |
    pip install pip-audit
    pip-audit --strict --desc || {
      echo "::error::pip-audit found known vulnerabilities"
      exit 1
    }
```

`pip-audit` with no arguments audits all packages in the current environment, including `pip-audit` itself and `pytest`/`pytest-asyncio`/`pytest-cov`/`pytest-xdist` installed in the preceding step. A vulnerability in a test-only tool like `pytest` (which would never be in production) would fail the CI build. The `--strict` flag makes this fail on any advisory, including those with no known fix.

This generates false positives that block PRs for non-production vulnerabilities. The correct scope is `pip-audit -r backend/requirements.txt`.

**Fix:** Change to `pip-audit -r backend/requirements.txt --strict --desc` to audit only production dependencies.

---

### P2-05: `deploy-worker.yml` Post-Deploy Smoke Test Has No Retry Logic and 5s Hardcoded Sleep

**File:** `.github/workflows/deploy-worker.yml` lines 71-79

```yaml
- name: Smoke test
  run: |
    sleep 5
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://api.rateshift.app/health)
    if [ "$STATUS" != "200" ]; then
      echo "Smoke test failed: /health returned $STATUS"
      exit 1
    fi
```

The worker deploy smoke test sleeps 5 seconds then makes a single request. Cloudflare Workers propagate globally within seconds, but CF's own deployment pipeline can occasionally take 10-30 seconds for all edge PoPs to receive the new script. A single 5-second sleep with one attempt is insufficient for a reliable production smoke test, especially given that this same workflow correctly uses the `retry-curl` composite action for all other HTTP calls. If the smoke test fails transiently, the worker deploy is marked failed and Slack is alerted with `critical` severity despite the worker being live.

**Fix:** Replace the inline `sleep 5 && curl` with the `retry-curl` composite action:
```yaml
- name: Smoke test
  uses: ./.github/actions/retry-curl
  with:
    url: https://api.rateshift.app/health
    method: GET
    max-retries: 3
    initial-delay: 10
    timeout: '30'
```

---

### P2-06: `data-health-check.yml` Makes a Second Unauthenticated-Looking Curl Call After `retry-curl`

**File:** `.github/workflows/data-health-check.yml` lines 35-41

```yaml
- name: Validate health response
  env:
    API_KEY: ${{ secrets.INTERNAL_API_KEY }}
    API_URL: ${{ secrets.BACKEND_URL }}
  run: |
    RESPONSE=$(curl -fsS -X GET \
      -H "X-API-Key: ${API_KEY}" \
      "${API_URL}/api/v1/internal/health-data")
```

The `retry-curl` step on line 26 already calls the endpoint and handles retries/failures. This second curl call re-fetches the same endpoint to parse the JSON body, because `retry-curl` only exposes the HTTP status code. This is a known design limitation of `retry-curl`. The issue is that this second call has no retry logic and will fail immediately on a cold-start 5xx from the Render free tier. If `retry-curl` warms the service and succeeds, the second raw curl is likely fine — but there is no warmup step on this workflow, so both the `retry-curl` and the raw curl can both hit a cold Render instance.

**Fix:** Add a `warmup-backend` step before the health check steps. Alternatively, add retry logic to the "Validate health response" step, or redesign to parse the response body inline within retry-curl (would require composite action changes).

---

### P2-07: `e2e-tests.yml` E2E Test Job Does Not Gate on Backend or Frontend Tests Passing

**File:** `.github/workflows/e2e-tests.yml` lines 43-46

The `e2e-tests` job depends only on `changes` to detect if frontend files changed. It does not have a `needs:` dependency on `backend-tests` or `frontend-test` from `ci.yml`. Since `e2e-tests.yml` and `ci.yml` are separate workflow files triggered by the same `push` and `pull_request` events, both can run in parallel. E2E tests can start executing against a broken backend that is currently failing unit tests. This wastes runner minutes and produces confusing failures ("E2E failed" when the real problem is a unit-level regression).

**Fix:** Either consolidate E2E into `ci.yml` as a downstream job gated on `backend-tests` and `frontend-test` results, or accept the parallel behavior as intentional (reasonable given E2E has its own service spinup and does not depend on the deployed backend). Document the intent.

---

### P2-08: `utility-type-tests.yml` Falls Through to "General Tests" Silently Without Failing

**File:** `.github/workflows/utility-type-tests.yml` lines 62-90

The utility test matrix runs two test steps. The first step (lines 62-77) attempts to run utility-specific tests, then falls back to marker-based tests, then falls back with `echo "No utility-specific marker tests found ..."` — always exiting with code 0. The second step (lines 79-90) also ends with `|| echo "Utility type tests complete ..."`, always exiting 0. This means the matrix can produce a green result even if NO tests actually ran for a given utility type.

The `utility-matrix-summary` job checks `needs.utility-tests.result` but since individual matrix jobs always exit 0, a matrix leg that ran zero tests appears as a pass.

**Fix:** Add a test count check. Run `pytest --collect-only -q -k "${{ matrix.utility_type }}"` first, count the collected tests, and fail if the count is 0 (indicating the utility type has no test coverage).

---

### P2-09: No Staging Environment Defined Anywhere

**Files:** `render.yaml`, `deploy-production.yml`, `wrangler.toml`

There is no staging environment defined in render.yaml, no CF Worker `[env.staging]` configuration in wrangler.toml, no Vercel preview environment specifically called "staging", and no GHA workflow deploying to a staging URL. The only pre-production gate is the CI test suite and the `deploy-production.yml` security/migration gate.

The absence of staging means:
1. There is no environment where `ENVIRONMENT=staging` can be set and tested end-to-end before production.
2. Database migrations cannot be tested against production schema before running on the production Neon branch.
3. The Render free-tier cold-start behavior under realistic traffic cannot be validated before releasing.

This is a known trade-off for a free-tier stack, but it should be explicitly documented.

**Fix (short-term):** Document in `render.yaml` comments and CLAUDE.md that staging is intentionally not implemented due to free-tier cost constraints, and that the migration-check CI job + ephemeral Neon branch verification in db-backup.yml serve as the migration safety gate. **Fix (long-term):** Add a `render.yaml` staging service (`plan: free`, separate service name) triggered by merges to a `staging` branch.

---

### P2-10: `Dockerfile` (Root) `HEALTHCHECK` Uses `start-period: 5s` — Too Short for Render Free Tier Cold Start

**File:** `Dockerfile` (root) line 47

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-10000}/health || exit 1
```

The `start-period` is 5 seconds. On Render free tier, Python/FastAPI cold starts can take 20-40 seconds (connection pool initialization, module imports, database connection establishment). With a 5-second start period, the health check will run 3 retries (at 30s intervals) and declare the container unhealthy before the app has finished starting. This causes unnecessary container restarts and delays.

`backend/Dockerfile` correctly uses `start-period: 5s` for the same reason it is wrong — however `docker-compose.prod.yml` backend healthcheck at line 54-59 uses `start_period: 30s`, which is the correct value.

**Fix:** Change `start-period` in the root `Dockerfile` line 47 from `5s` to `30s` to match `docker-compose.prod.yml`.

---

### P2-11: `owasp-zap.yml` Has No Slack Notification on Failure

**File:** `.github/workflows/owasp-zap.yml`

All other security and data workflows include a `notify-slack` step on failure. The OWASP ZAP baseline scan (`owasp-zap.yml`) runs weekly on Sunday 4am UTC and creates GitHub Issues on findings (`fail_action: true`) but never notifies Slack. A ZAP scan failure (or finding new high-severity issues) will create a GH issue but will not page the on-call channel, making it easy to miss.

**Fix:** Add a `notify-slack` on-failure step with `severity: warning` to `owasp-zap.yml`.

---

### P2-12: `db-backup.yml` Verify Job Uses `pg_restore` With `--exit-on-error` But `continue-on-error: true` — Failure Semantics Are Unclear

**File:** `.github/workflows/db-backup.yml` lines 189, 307-319

The verify job is marked `continue-on-error: true` (line 189) with the comment "A verification failure surfaces as a warning in Slack rather than blocking the workflow." However, if the `pg_restore` step fails with `--exit-on-error`, the step exits 1 but `continue-on-error: true` on the job means the workflow reports green overall. The Slack warning at line 356-362 is gated on `if: failure()` — but `continue-on-error: true` converts job failure to a warning, and `if: failure()` inside a `continue-on-error` job does trigger correctly for step failures. This is GHA-correct behavior, but it is non-obvious and relies on the distinction between job-level and step-level failure.

The ephemeral Neon branch cleanup (line 340) is correctly gated on `if: always()`, which is good practice.

**Fix:** Add an explicit comment in the workflow clarifying why `continue-on-error: true` + `if: failure()` Slack notification is the intended pattern (i.e., backup artifact is safe regardless of verify outcome, but we want notification). No code change required, documentation only.

---

## P3 — Low / Housekeeping

### P3-01: `notify-slack/action.yml` Uses Deprecated `attachments` API

**File:** `.github/actions/notify-slack/action.yml` lines 47-67

The Slack payload uses the legacy `attachments` array format. Slack's Block Kit API has been the preferred format since 2019, and the `attachments` field (while still functional) is deprecated for new integrations. The current payload works but Slack may eventually sunset `attachments`, and it lacks features like buttons, overflow menus, or richer formatting that Block Kit provides.

**Fix:** Migrate the payload to Block Kit format using a top-level `blocks` array with `section`, `context`, and optionally `actions` blocks. Low urgency given functionality is unchanged.

---

### P3-02: `ci.yml` `backend-lint` Job Has `contents: write` Permission but Auto-Commits to PRs Only

**File:** `.github/workflows/ci.yml` lines 64-65

```yaml
permissions:
  contents: write
```

The `backend-lint` job needs `contents: write` to auto-commit Black/isort formatting fixes on PRs. This is a broad permission granted at the job level. On push to `main`, formatting failures exit 1 (line 103-106) rather than committing, so write permission is not needed for main branch pushes. Consider scoping this to PR-only runs where possible. Not a blocking issue since GHA job-level permissions limit scope to the current workflow, but it is broader than needed for `push` events.

**Fix:** Split the lint job into two: a read-only check for `push` events and a write-enabled auto-fix for `pull_request` events, using `if: github.event_name == 'pull_request'` to gate the `contents: write` permission.

---

### P3-03: `dependabot.yml` Has No `github-actions` Grouping for Minor+Patch Updates

**File:** `.github/dependabot.yml` lines 79-90

The `github-actions` ecosystem entry does not have a `groups:` section, unlike pip and npm which group minor+patch updates. This means each GitHub Action patch update (e.g., `actions/checkout@v4.1.2` → `v4.1.3`) generates a separate PR rather than being grouped. With 32 workflows using multiple actions, this can generate a high volume of individual Dependabot PRs for minor actions updates.

**Fix:** Add a `groups:` section to the `github-actions` ecosystem matching the pattern used for pip/npm.

---

### P3-04: `model-retrain.yml` and `code-analysis.yml` Not in `self-healing-monitor.yml` Matrix

**File:** `.github/workflows/self-healing-monitor.yml` lines 33-52

The self-healing monitor tracks 19 workflows. `model-retrain.yml` (weekly Sunday 5am) and `code-analysis.yml` (PR-only, not a cron) are not in the matrix. `model-retrain.yml` running weekly is a legitimate cron to monitor. `fetch-gas-rates.yml` is also absent.

**Fix:** Add `model-retrain.yml` and `fetch-gas-rates.yml` to the self-healing monitor matrix. `code-analysis.yml` can be omitted since it is PR-only and failures are immediately visible.

---

### P3-05: `warmup-backend/action.yml` Matches on HTTP 2xx OR 4xx as "Responsive"

**File:** `.github/actions/warmup-backend/action.yml` line 33

```bash
if [[ "$STATUS" =~ ^[24] ]]; then
  echo "Backend is responsive (HTTP ${STATUS})"
  exit 0
fi
```

The warmup action considers the backend "responsive" if it returns any 2xx OR 4xx response (including 401, 403, 404, 429). A 404 from an uninitialized service that is still starting could be from the reverse proxy (not from the FastAPI app), giving a false-positive warm status. A 429 (rate-limited) means the backend is actually overloaded but would still be treated as "warm."

**Fix:** Only match `^2` (2xx). A properly warmed backend at `/api/v1/` should return 200 or 307. If `/api/v1/` returns 404 or 401, the backend is not fully initialized.

---

### P3-06: `docker-compose.prod.yml` Frontend Service Has No Healthcheck

**File:** `docker-compose.prod.yml` lines 66-98

The frontend service in `docker-compose.prod.yml` does not define a `healthcheck`. The backend service has one at lines 54-59. Without a healthcheck, Docker Swarm and compose v2 health-dependent startup ordering cannot use the frontend as a dependency target. Since `docker-compose.prod.yml` is for reference/potential self-hosted use, this is low severity but inconsistent with the other services.

**Fix:** Add a healthcheck to the frontend service matching the one in `frontend/Dockerfile` (which uses `wget --spider http://localhost:3000/api/health`).

---

### P3-07: `data-retention.yml` and `sync-connections.yml` Have No `warmup-backend` Step

**File:** `.github/workflows/data-retention.yml`, `.github/workflows/sync-connections.yml`

Most cron workflows that call the Render backend include a `warmup-backend` step to handle free-tier cold starts (90-second spin-up delay). `data-retention.yml` and `sync-connections.yml` directly call `retry-curl` without a warmup step. On `sync-connections.yml` (runs every 6 hours), the backend is likely already warm from other workflows, but on `data-retention.yml` (weekly), a cold start is plausible. The `retry-curl` action will retry on 5xx with exponential backoff (default max 60s between retries), which serves as an implicit warmup, but the lack of explicit warmup means the first retry burns time rather than proactively waking the service.

**Fix:** Add `warmup-backend` steps to `data-retention.yml` and `sync-connections.yml` matching the pattern in `dunning-cycle.yml` or `kpi-report.yml`.

---

### P3-08: `frontend/Dockerfile` Health Check Uses `/api/health` But Next.js App Router Likely Serves `/api/health` via Backend Proxy

**File:** `frontend/Dockerfile` line 92

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1
```

The frontend container healthcheck polls `/api/health` which, in the context of the docker-compose setup, would be proxied to the backend via Next.js rewrites. In a standalone frontend container (as built by the Dockerfile, without the backend running), this endpoint would return a proxy error, causing the frontend healthcheck to always fail. The frontend Dockerfile should health-check a frontend-native endpoint (e.g., the root `/` page or a static asset) rather than an API proxy endpoint.

**Fix:** Change the healthcheck to `wget --spider http://localhost:3000/` or a static Next.js health endpoint (`/api/frontend-health`) that does not depend on the backend.

---

## Files With No Issues Found

- `.github/actions/retry-curl/action.yml` — Correct exponential backoff with jitter, fail-fast on non-retryable 4xx, temp file for body to avoid shell quoting issues, proper GITHUB_OUTPUT usage.
- `.github/actions/validate-migrations/action.yml` — Four comprehensive checks (sequential numbering, IF NOT EXISTS, neondb_owner grants, no SERIAL/BIGSERIAL). Logic is sound.
- `.github/actions/setup-python-env/action.yml` — Correct pip caching with `cache-dependency-path` scoped to `requirements*.txt`.
- `.github/actions/setup-node-env/action.yml` — Correct npm caching with `cache-dependency-path` scoped to `frontend/package-lock.json`.
- `.github/actions/wait-for-service/action.yml` — Correct polling loop with elapsed-time timeout and configurable interval.
- `.github/workflows/secret-scan.yml` — Gitleaks with `fetch-depth: 0` for full history scan; correct `permissions: {}`.
- `.github/workflows/db-backup.yml` (backup job) — Excellent: custom format pg_dump, compress=9, R2 upload, lexicographic rotation of oldest 30, always-cleanup of temp files. Branch verification with Neon API is thorough.
- `.github/workflows/deploy-production.yml` (deploy + smoke-tests jobs) — Correct concurrency group with `cancel-in-progress: false`, production environment gating with URL, proper needs chain (validate → test + security-gate + migration-gate → deploy → smoke-tests), rollback on smoke failure.
- `.github/workflows/ci.yml` (changes detection) — `dorny/paths-filter@v3` for efficient path-based job skipping is well-implemented.
- `.github/workflows/self-healing-monitor.yml` (auto-close-resolved) — The auto-close logic correctly checks last 3 runs for `success` before closing issues.
- `docker-compose.prod.yml` — Well-structured: pinned image versions, resource limits on all services, `on-failure` restart policy with `max_attempts: 3`, monitoring ports bound to `127.0.0.1` only, Redis not exposed on host network.
- `.github/dependabot.yml` — Covers pip, npm (frontend), npm (workers), pip (ml), docker (backend, frontend, ml, root), github-actions. All four package ecosystems covered.
- `workers/api-gateway/wrangler.toml` — Three CF Worker cron triggers correctly replacing GHA crons (check-alerts/3h, price-sync/6h, observe-forecasts/30min offset). Native rate limiter bindings configured correctly.
- `.github/workflows/deploy-worker.yml` — Tests run before deploy (`needs: test`), `permissions: {}` (minimal), `cancel-in-progress: false` on concurrency group.
- `.github/workflows/e2e-tests.yml` (Lighthouse job) — Per-URL score table, threshold enforcement (perf 85, a11y 90, bp 85, seo 90), PR comment update/create logic with marker deduplication is thorough.

---

## Summary

**Total findings:** 20 (3 P0, 7 P1, 12 P2, 8 P3)

**Critical observations:**

The infrastructure demonstrates a mature approach to CI/CD for a free-tier stack: composite actions for retry logic and Slack notifications are consistently applied, deployment has a tested rollback path via the Render API, migration validation runs in CI and pre-deploy, secret scanning is automated via Gitleaks, and the CF Worker correctly replaces 3 GHA crons. The self-healing monitor covering 19 workflows with auto-issue creation and auto-close is a standout feature.

**Top risks by area:**

1. **Dockerfile fragmentation (P0-01):** Two Dockerfiles for the backend create operational ambiguity. The root `Dockerfile` runs 1 worker; `backend/Dockerfile` runs 2. One should be the canonical production artifact.

2. **Origin URL bypass (P0-02):** The Render `.onrender.com` URL in `wrangler.toml` has been flagged in three consecutive audits (2026-03-16, 2026-03-17, 2026-03-18) and is still unresolved. This is the highest-risk unfixed finding in the repository.

3. **E2E schema gap (P0-03):** E2E tests running against only 3 of 60 migrations means 57 migrations worth of schema changes are never tested end-to-end. This will produce false-positive green E2E runs while actual schema-dependent features are broken.

4. **Scripts excluded from Docker image (P1-05):** The `.dockerignore` `scripts/` exclusion means the Render db-maintenance cron job will fail on every execution because `db_maintenance.py` is not in the built image.

5. **Self-healing monitor tracking consolidated workflows (P1-06):** Three workflows monitored by self-healing have no cron triggers, so they never produce failures to detect. The monitor provides false coverage.

**GHA cost assessment:** Current setup at ~1,843 min/mo (per CLAUDE.md) is well-optimized given the consolidation into `daily-data-pipeline.yml` and CF Worker cron replacement. The no-op `model-retrain.yml` (P1-03) consuming ~30 min/week (~120 min/mo) is the clearest waste candidate.

**Security posture:** `permissions: {}` is consistently set on operational cron workflows (excellent). Secret handling is correct throughout — no hardcoded secrets found in workflow files. Gitleaks, Bandit, pip-audit, npm-audit, and OWASP ZAP provide multi-layer security scanning. The only remaining gap is P0-02 (ORIGIN_URL).
