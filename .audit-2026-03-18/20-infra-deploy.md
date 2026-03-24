# Infrastructure & Deployment Audit — RateShift
**Audit Date:** 2026-03-18
**Auditor:** DevOps Engineer (Claude Sonnet 4.6)
**Scope:** Dockerfiles, CI/CD pipelines, deployment configuration, operational readiness
**Files Reviewed:** 4 Dockerfiles, 2 compose files, render.yaml, wrangler.toml, 34 GHA workflow files, .dependabot.yml, Makefile, Procfile, runtime.txt, next.config.js, .pre-commit-config.yaml, .zap/rules.tsv, 7 composite actions

---

## Executive Summary

The RateShift infrastructure is well-architected for a free-tier SaaS product with strong CI/CD fundamentals: migration gates before deploy, automated rollback via Render API, self-healing issue creation, Slack alerting, and a solid composite action library. The deployment pipeline is logically sound and the security posture is above average for a startup-stage product.

However, several issues warrant immediate attention: base images are not pinned by digest (supply chain risk), the production Dockerfile used by Render differs materially from the dedicated `backend/Dockerfile`, no database backup automation exists for the Neon-managed database, staging is effectively phantom infrastructure (no Render staging service provisioned), the `keepalive.yml` workflow runs 24x/day consuming ~48 GHA minutes/month without alerting, and the `model-retrain.yml` Sunday cron collides with both `data-retention.yml` and `owasp-zap.yml` at 04:00–05:00 UTC.

**Finding counts:** 4 P0 | 7 P1 | 11 P2 | 8 P3

---

## P0 — Critical (Immediate Action Required)

### P0-1: Base Docker Images Not Pinned by Digest — All Four Dockerfiles
**Files:** `Dockerfile:2,18`, `backend/Dockerfile:4,51`, `frontend/Dockerfile:4`, `ml/Dockerfile:4`

All base images use mutable floating tags, not immutable SHA-256 digests. A compromised upstream image or accidental tag mutation silently flows into production.

```
# Current (unsafe)
FROM python:3.12-slim as builder          # Dockerfile:2
FROM python:3.12-slim                     # Dockerfile:18
FROM python:3.12-slim as base             # backend/Dockerfile:4
FROM python:3.12-slim as production       # backend/Dockerfile:51
FROM node:20-alpine AS base               # frontend/Dockerfile:4
FROM python:3.11-slim as base             # ml/Dockerfile:4
```

None of the six `FROM` directives include a SHA-256 digest. The `_docker-build-push.yml` reusable workflow uses `aquasecurity/trivy-action@0.28.0` for image scanning after push, but that action's own tag is not digest-pinned either. Furthermore, `docker-compose.yml` uses `prom/prometheus:latest` and `grafana/grafana:latest` and `oliver006/redis_exporter:latest` (lines 95, 114, 151), which is `latest` pinned in prod compose only partially — `prometheus:v2.51.0` and `grafana:10.4.1` are pinned in `docker-compose.prod.yml` but `latest` remains in the dev compose.

**Risk:** Supply chain attack via compromised upstream image. The `trivy` scan would catch known CVEs but not malicious code injected after tagging.

**Recommendation:** Pin every base image with `FROM python:3.12-slim@sha256:<digest>`. Use `docker buildx imagetools inspect python:3.12-slim --format '{{.Manifest.Digest}}'` to get current digests. Re-pin monthly via Dependabot's `docker` ecosystem support (add a `docker` entry to `.github/dependabot.yml`).

---

### P0-2: Production Dockerfile Mismatch — Root vs. backend/Dockerfile
**Files:** `Dockerfile`, `backend/Dockerfile`, `render.yaml:5`

`render.yaml` specifies `dockerfilePath: ./Dockerfile` (the root Dockerfile), but the project also maintains `backend/Dockerfile` which has a production stage with meaningfully different configuration:

| Characteristic | Root `Dockerfile` (used by Render) | `backend/Dockerfile` production stage |
|---|---|---|
| Workers | 1 (CMD line 54) | 4 (CMD line 90) |
| No-access-log | Not set | `--no-access-log` flag present |
| `PYTHONFAULTHANDLER` | Not set | Set to 1 |
| `libpq-dev` installed | No | Yes (line 63) |
| `postgresql-client` | No | Yes (line 14) |
| `compileall -b` optimization | No | Yes (line 48) |
| Source of truth | Used in prod | Not used in prod |

The root `Dockerfile` runs `--workers 1` in production (line 54). This means Render is running single-threaded uvicorn with only Python's GIL concurrency. The `backend/Dockerfile` runs 4 workers which would double or quadruple throughput for CPU-bound work. Additionally the root Dockerfile copies with `COPY backend/ .` (line 34) from the repo root context, while `backend/Dockerfile` uses `COPY . .` from the backend context — these have different COPY semantics and layer caching behavior.

**Risk:** The production service is running an effectively abandoned Dockerfile that does not reflect the team's intended production configuration. Single-worker uvicorn is a significant throughput limitation.

**Recommendation:** Consolidate to `backend/Dockerfile` and update `render.yaml` to point to it with the correct context. Verify whether `--workers 4` is correct for Render's free-tier memory constraints (512MB). Even 2 workers would be a 2x improvement.

---

### P0-3: No Database Backup Automation for Neon Production Database
**Files:** `Makefile:172-181`, `render.yaml:116-127`, absence of any backup workflow

The `Makefile` has `backup`, `backup-full`, and `restore` targets (lines 172-181) that call `./scripts/backup.sh` and `./scripts/restore.sh`. These scripts back up a local PostgreSQL container. The production database is Neon PostgreSQL (`cold-rice-23455092`) — a fully managed service. However:

1. No GHA workflow calls Neon's backup API or exports a pg_dump to a cold storage bucket.
2. The `render.yaml` db-maintenance cron job (lines 116-127) runs `scripts/db_maintenance.py` for vacuuming and index maintenance but does not include backup.
3. The 53-table schema with financial data (Stripe subscriptions, payment history, dunning cycles) has no documented RTO/RPO targets.
4. Neon's free tier provides point-in-time restore for 7 days only. There is no export to S3/GCS/R2 for longer retention or cross-provider DR.

**Risk:** Extended database corruption or accidental mass-delete (e.g., a migration error or GDPR bulk deletion bug) beyond Neon's 7-day PITR window results in permanent data loss. The project has no documented recovery procedure beyond Neon's built-in PITR.

**Recommendation:** Add a weekly GHA workflow that runs `pg_dump` against the Neon direct endpoint and uploads to Cloudflare R2 (free tier: 10GB storage, zero egress fees — fits the $0/mo budget). Document RTO/RPO. Add a restore verification job that restores to a branch and validates row counts.

---

### P0-4: Bandit High-Severity Findings Are Warnings, Not Failures in CI
**Files:** `ci.yml:300-307`, `deploy-production.yml:84`

In `ci.yml`, the `security-scan` job (lines 300-307) uses:
```yaml
bandit -r . -f json -o ../bandit-report.json -ll --severity-level high || {
  echo "::warning::Bandit found high-severity issues"
}
```

The `|| { echo "::warning::..." }` pattern swallows the non-zero exit code. Bandit exits non-zero on findings but the job continues successfully. The `::warning::` annotation appears in the GHA log but does not fail the job or block the PR merge.

Notably, `deploy-production.yml:84` does correctly fail on Bandit findings:
```yaml
bandit -r . -ll --severity-level high -f txt
```
But this only runs at release time, not on every PR.

**Risk:** High-severity security issues in backend code (e.g., SQL injection, hardcoded credentials, insecure deserialization) can be merged to `main` without any hard gate. The PR security check is effectively advisory only.

**Recommendation:** Remove the `|| { echo "::warning::..." }` fallback from `ci.yml:304-306`. Let bandit exit non-zero and fail the job. If there are known false positives, add `.bandit` suppression comments in code with documented justification.

---

## P1 — High Severity (Fix Within 1 Week)

### P1-1: Staging Environment Is Phantom Infrastructure
**Files:** `deploy-staging.yml:75-96`, `deploy-staging.yml:112`

The staging deployment workflow conditionally triggers deploy hooks:
```yaml
if [ -n "${RENDER_HOOK_BACKEND}" ]; then
  echo "Triggering Render staging backend deploy..."
else
  echo "No staging backend deploy hook configured — skipping"
fi
```

And smoke tests are also conditional:
```yaml
if: ${{ secrets.STAGING_API_URL != '' }}
```

The `CLAUDE.md` and MEMORY.md make no mention of a Render staging service. The `render.yaml` defines only one `web` service (`electricity-optimizer`, plan: free) and one `cron` service. There is no staging Render service. The staging workflow builds Docker images to GHCR with `staging` and `staging-sha` tags but has no actual deployment target.

**Risk:** Every push to `develop` triggers Docker image builds and pushes (consuming GHA minutes and GHCR storage) but deploys to nothing. PRs have no staging environment for manual QA. The "deploy to staging" environment name in the workflow creates a false sense of a tested promotion path.

**Recommendation:** Either provision a real Render staging service (or use Vercel preview deployments for frontend + a Render staging service for backend), or acknowledge that staging is intentionally skipped and remove the `deploy-staging.yml` workflow to eliminate the phantom image build cost. Document the decision in CLAUDE.md. At minimum, delete the staging smoke-test job which currently silently passes by doing nothing.

---

### P1-2: `keepalive.yml` Consumes ~720 GHA Minutes/Month Without Value
**Files:** `keepalive.yml`

The keepalive workflow runs every hour (`cron: '0 * * * *'`), 24 times per day, 730 times per month. Each run:
1. Spins up an `ubuntu-latest` runner (billed at 1 minute minimum)
2. Runs one curl with `--max-time 30`
3. Issues a `::warning::` annotation on non-200 but does NOT call `notify-slack`
4. Always exits 0 (no failure path)

Estimated cost: ~730 GHA minutes/month. The project's stated GHA budget target is ~1,283 min/mo total. This single workflow represents approximately 57% of that budget doing nothing but pinging a health endpoint that UptimeRobot already monitors (as noted in `gateway-health.yml:6`: "UptimeRobot covers real-time monitoring").

Additionally, the keepalive is pinging `https://api.rateshift.app/health` which goes through the Cloudflare Worker edge — not directly to the Render origin. This does not actually prevent Render's free-tier cold start (which requires direct hits to the Render origin URL).

**Risk:** GHA budget overrun; ineffective cold-start prevention; silent failures (no Slack alert on non-200).

**Recommendation:** Either remove `keepalive.yml` entirely and rely on UptimeRobot for uptime monitoring, or reduce frequency to every 4-6 hours (matching the CF Worker cron trigger frequency) and add a `notify-slack` step on failure. If cold-start prevention is the goal, use the Render origin URL (`https://electricity-optimizer.onrender.com`), not the CF Worker URL.

---

### P1-3: Sunday Cron Schedule Collisions
**Files:** `owasp-zap.yml:5`, `data-retention.yml:6`, `model-retrain.yml:5`, `scrape-portals.yml:7`

Multiple workflows are scheduled for Sunday:

| Workflow | Sunday Schedule (UTC) |
|---|---|
| `daily-data-pipeline.yml` | 03:00 (runs daily but also Sunday) |
| `owasp-zap.yml` | 04:00 |
| `data-retention.yml` | 04:00 |
| `model-retrain.yml` | 05:00 |
| `scrape-portals.yml` | 05:00 |
| `db-maintenance` (Render cron) | 03:00 |

`owasp-zap.yml` and `data-retention.yml` start at exactly the same time (Sunday 04:00 UTC). `model-retrain.yml` and `scrape-portals.yml` start at exactly the same time (Sunday 05:00 UTC). The `db-maintenance` Render cron (render.yaml:120) also fires at 03:00 UTC, same as `daily-data-pipeline.yml`.

While GitHub Actions queues concurrent jobs from different workflows (they don't block each other at the scheduler level), all these workflows simultaneously hit the Render backend with API calls, and `db-maintenance` is running `VACUUM` and `ANALYZE` at the same time as `daily-data-pipeline.yml` is calling `scrape-rates`, `scan-emails`, `learn`, and `detect-rate-changes`. Heavy writes + vacuum contention can slow both.

**Risk:** Database lock contention on Sunday mornings; potential for OWASP ZAP scan to run while data retention is actively deleting rows (creates noise in scan results); combined GHA runner demand spike on Sundays.

**Recommendation:** Stagger Sunday schedules by at least 30 minutes between each workflow. Suggested: data-retention at 01:30, daily-data-pipeline at 03:00, owasp-zap at 05:30, model-retrain at 07:00, scrape-portals at 07:00.

---

### P1-4: `detect-rate-changes.yml` Uses Deprecated `api-key` Input Format
**Files:** `detect-rate-changes.yml:28`

The `detect-rate-changes.yml` workflow (dispatch-only) uses:
```yaml
uses: ./.github/actions/retry-curl
with:
  url: ${{ secrets.BACKEND_URL }}/api/v1/internal/detect-rate-changes
  method: POST
  api-key: ${{ secrets.INTERNAL_API_KEY }}
```

The `api-key` input is not defined in the `retry-curl` composite action's `action.yml` — that action accepts `headers` (newline-delimited). Every other workflow that uses `retry-curl` passes auth via:
```yaml
headers: |
  X-API-Key: ${{ secrets.INTERNAL_API_KEY }}
  Content-Type: application/json
```

The `api-key` input will be silently ignored by the composite action. The actual API call will be made without authentication, and the `/internal/detect-rate-changes` endpoint (which requires `X-API-Key`) will return HTTP 401 or 403, causing retry-curl to exit non-zero. Since this workflow has no cron trigger (moved to `daily-data-pipeline.yml`), it only runs when manually dispatched, but any manual trigger will consistently fail.

**Risk:** Manual invocation of detect-rate-changes always fails with an authentication error. If this workflow is used during incident response, it will mislead the operator.

**Recommendation:** Replace `api-key: ${{ secrets.INTERNAL_API_KEY }}` with the standard `headers:` block pattern used in all other workflows.

---

### P1-5: `model-retrain.yml` Does Not Actually Retrain a Model
**Files:** `model-retrain.yml:34-44`

The weekly model retraining job runs:
```python
config = ModelConfig(epochs=50, batch_size=32)
forecaster = ElectricityPriceForecaster(config=config)
# In production, data would be fetched from TimescaleDB.
# For now, this validates the training pipeline runs.
print('Model retraining pipeline validated successfully')
```

This is a validation stub that instantiates the model architecture but does not load data, does not train, and does not persist any model artifact. The comment "In production, data would be fetched from TimescaleDB" indicates this is not implemented. The self-healing monitor tracks this workflow for failures (it appears in the matrix), but the workflow "succeeds" every Sunday having done nothing.

**Risk:** The ML pipeline has no automated retraining. Model drift is undetected. The self-healing monitor treats this workflow as operational when it is a no-op. Users relying on forecasts are getting predictions from an unchanging model as electricity market conditions evolve.

**Recommendation:** Either implement actual retraining (call `POST /internal/learn` with more data, or run the `ml/` training pipeline against Neon data and store model artifacts), or rename the workflow to `validate-ml-pipeline.yml` and be explicit that this is a smoke test. Remove it from the self-healing monitor matrix until it does real work.

---

### P1-6: No Image Vulnerability Scan for Render Production Deployment
**Files:** `deploy-production.yml`, `render.yaml`

The production deployment path (`deploy-production.yml`) triggers Render via deploy hook:
```yaml
curl -fsS -X POST "${RENDER_DEPLOY_HOOK}"
```

Render pulls the Docker image from the repo root `Dockerfile` and builds it internally. The image vulnerability scan (Trivy) in `_docker-build-push.yml:91-98` only runs when images are pushed to GHCR — which only happens via `deploy-staging.yml`. The production deploy path bypasses Trivy entirely.

There is no Trivy scan in `deploy-production.yml` or `_backend-tests.yml` (the reusable test workflow used by production deploys).

**Risk:** A production deploy can proceed with a base image that has CRITICAL/HIGH CVEs that would have been caught if the image were scanned. The security gate in `deploy-production.yml` only runs Bandit (static analysis) and `npm audit` — not container-level CVE scanning.

**Recommendation:** Add a Trivy scan step to the `deploy-production.yml` security gate, building the image locally (without pushing) and scanning before the Render deploy hook is triggered. Alternatively, build and push to GHCR staging in the production pipeline, scan that image, then trigger Render to pull that specific image digest.

---

### P1-7: E2E Database Setup Only Applies 3 of 53 Migrations
**Files:** `e2e-tests.yml:97-103`

The E2E test database setup step:
```yaml
- name: Set up database
  run: |
    PGPASSWORD=postgres psql -h localhost -U postgres -d electricity_test -f backend/migrations/init_neon.sql
    PGPASSWORD=postgres psql -h localhost -U postgres -d electricity_test -f backend/migrations/002_gdpr_auth_tables.sql
    PGPASSWORD=postgres psql -h localhost -U postgres -d electricity_test -f backend/migrations/003_reconcile_schema.sql
```

Only 3 migrations are applied out of 53. E2E tests run against a schema that is missing 50 migrations including:
- Migration 014: alert_tables (the `/alerts` page is an E2E test target)
- Migration 015: notifications
- Migration 024: payment_retry_history
- Migration 031-033: agent tables (the `/assistant` page is an E2E test target)
- Migration 049-051: community tables (the `/community` page is an E2E test target)

The E2E tests work because they heavily mock the API layer (the mock factory in `api-mocks.ts` intercepts requests before they hit the real backend), but the backend started in E2E CI (`uvicorn main:app`, line 108) will fail or return unexpected errors on any request that hits a table that doesn't exist in the test database.

**Risk:** E2E tests that do not use API mocks (smoke tests, security tests, load tests) may silently test against a broken database schema. New E2E tests added without API mocks will fail inconsistently.

**Recommendation:** Replace the manual 3-migration setup with the same loop used in `ci.yml:363-378` that applies all migrations in order. Extract this into a composite action `apply-migrations` for reuse.

---

## P2 — Medium Severity (Fix Within 2 Weeks)

### P2-1: `mypy` Type Check in CI Is Non-Blocking
**Files:** `ci.yml:115-116`

```yaml
- name: Type check with mypy
  run: cd backend && mypy . --ignore-missing-imports --no-strict-optional
  continue-on-error: true
```

`continue-on-error: true` means type errors never fail the CI pipeline. With 2,686 backend tests, mypy provides significant safety. The `--no-strict-optional` flag also disables null-safety checks, the most common runtime error class in Python.

**Recommendation:** Remove `continue-on-error: true`. Fix any existing mypy errors (use `# type: ignore[specific-error]` with justification comments for legitimate suppressions). Consider adding `--strict` mode incrementally per module.

---

### P2-2: Docker Compose Dev vs. Prod Environment Parity Gaps
**Files:** `docker-compose.yml:19-31`, `docker-compose.prod.yml`

The dev compose passes `DATABASE_URL` as `${DATABASE_URL}` (external Neon) while `docker-compose.prod.yml:7` uses `postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/electricity` (local PostgreSQL container). This is an explicit and documented dev/prod difference, but creates a catch: developers running the prod compose locally are testing against a different database engine config (local Postgres, no SSL) than the actual production environment (Neon, SSL required, with connection pooling).

Additionally, `docker-compose.yml` does not set resource limits on any container, while `docker-compose.prod.yml` does. A developer running the dev compose will not detect OOM conditions that could manifest in constrained production environments.

The dev compose `prometheus:latest` (line 95) vs prod compose `prometheus:v2.51.0` means developers may be testing against a different Prometheus version than production, potentially masking configuration incompatibilities.

**Recommendation:** Add `x-common-backend: &common-backend` YAML anchors to share environment variable configuration. Add a note to `docker-compose.yml` explicitly warning that Prometheus and Grafana images are unpinned. Consider adding a `docker-compose.override.yml` pattern to allow local overrides without modifying tracked files.

---

### P2-3: `render.yaml` Missing 7+ Env Vars Documented as Required
**Files:** `render.yaml`, `CLAUDE.md` (critical reminders)

`CLAUDE.md` documents 42 Render env vars. `render.yaml` declares 46 `sync: false` entries. Cross-referencing reveals:

**In CLAUDE.md as required but NOT in render.yaml:**
- `REDIS_PASSWORD` (Redis auth is configured via `REDIS_URL` which includes the password — acceptable)
- `GRAFANA_INSTANCE_ID` (mentioned in MEMORY.md but not in render.yaml)

**In render.yaml but documented as PLACEHOLDER/MISSING:**
- `GOOGLE_CLIENT_ID` — documented as placeholder
- `GOOGLE_CLIENT_SECRET` — documented as placeholder
- `UTILITYAPI_KEY` — documented as missing
- `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` — documented as missing
- `OUTLOOK_CLIENT_ID` / `OUTLOOK_CLIENT_SECRET` — documented as missing

**Missing from render.yaml entirely (not listed with `sync: false`):**
- `GRAFANA_CLOUD_OTLP_TOKEN` (or equivalent — needed for `OTEL_EXPORTER_OTLP_HEADERS`)

**Recommendation:** Add env var validation at application startup that lists all required-but-missing variables with clear error messages, not just a startup crash. Document in render.yaml which keys are "dormant" (defined but not wired to a service) to distinguish intentional absence from oversight.

---

### P2-4: `deploy-staging.yml` Environment URL Points to Production
**Files:** `deploy-staging.yml:71-72`

```yaml
environment:
  name: staging
  url: https://rateshift.app
```

The staging environment URL in the GHA environment definition points to the production URL `https://rateshift.app`, not a staging URL. This means GitHub's deployment environment tracking links all "staging" deployments to the production domain, confusing deployment history and making environment-based protection rules ambiguous.

**Recommendation:** Set `url: ${{ secrets.STAGING_FRONTEND_URL }}` or remove the `url` field until a real staging environment exists.

---

### P2-5: `wrangler.toml` ORIGIN_URL Still Points to Render Subdomain
**Files:** `workers/api-gateway/wrangler.toml:40`

```toml
[vars]
ORIGIN_URL = "https://electricity-optimizer.onrender.com"
```

This hardcodes the Render subdomain URL (not the custom domain). If the Render service is renamed or migrated, this var is silently stale. More importantly, this non-secret variable is tracked in git — any developer can see the Render origin URL, which could be used to bypass the Cloudflare Worker (rate limiting, security headers, bot detection) by hitting the Render URL directly.

**Risk:** The Render origin URL is publicly visible in the git repository. An attacker can send requests directly to `electricity-optimizer.onrender.com` to bypass CF Worker rate limiting, bot detection, CORS enforcement, and internal auth headers. The Render free plan does not support IP allowlisting.

**Recommendation:** Move `ORIGIN_URL` to a Wrangler secret (`wrangler secret put ORIGIN_URL`) so it's not tracked in git. On Render, consider adding IP allowlisting to allow only Cloudflare IP ranges (Cloudflare publishes these at `https://www.cloudflare.com/ips/`). This is the standard "orange cloud lockdown" pattern.

---

### P2-6: `code-analysis.yml` Security Scan Uses `claude-flow security scan` — Unverifiable Tool
**Files:** `code-analysis.yml:50-64`

```yaml
- name: Security scan
  run: |
    claude-flow security scan --format json > security.json
- name: Check for high-severity findings
  run: |
    if [ -f security.json ]; then
      HIGH_COUNT=$(jq '[.findings[]? | select(.severity == "high" or .severity == "critical")] | length' security.json 2>/dev/null || echo "0")
      if [ "$HIGH_COUNT" -gt "0" ]; then
        exit 1
      fi
    fi
```

This uses `claude-flow security scan` (installed via `npm install -g claude-flow@latest`) as a security gate. This is a third-party tool installed from npm at latest without any version pin or integrity check. If `claude-flow security scan` fails or produces malformed JSON, `jq` returns an error and `HIGH_COUNT` defaults to "0" — the gate silently passes. The job also uses `|| true` on several analysis steps so the workflow always succeeds.

**Risk:** The security gate can be silently bypassed by a `claude-flow` update that changes output format, a network failure installing claude-flow, or a bug in the tool. The gate is not actually blocking merges.

**Recommendation:** Replace `claude-flow security scan` with a well-established tool (Semgrep, CodeQL, or the existing Bandit). If claude-flow analysis is desired, keep it as informational-only without the `exit 1` gate. Pin the claude-flow version: `npm install -g claude-flow@<specific-version>`.

---

### P2-7: Migration Validation Check Does Not Fail the Production Gate
**Files:** `deploy-production.yml:96-108`

The `migration-gate` job (lines 96-108) in `deploy-production.yml` runs `validate-migrations` composite action. However, the `validate-migrations` action checks syntax conventions (IF NOT EXISTS, neondb_owner grants, no SERIAL) but does NOT actually apply migrations to a test database. The convention check could pass while migrations contain SQL that fails on Neon's PostgreSQL dialect.

More critically, the `deploy` job's `needs` condition (line 115-120):
```yaml
if: >-
  always() &&
  needs.test.result == 'success' &&
  needs.security-gate.result == 'success' &&
  (needs.migration-gate.result == 'success' || needs.migration-gate.result == 'skipped')
```

The `migration-gate.result == 'skipped'` clause means if migration-gate is skipped (which happens when the `if:` condition on line 100 evaluates to false), deploy still proceeds. Currently line 100 is:
```yaml
if: github.event_name == 'release' || github.event_name == 'workflow_dispatch'
```
This should never evaluate to false in practice (production only triggers on those events), but the `skipped` allowance in the deploy gate is a latent risk if `if:` conditions are modified.

**Recommendation:** Remove `|| needs.migration-gate.result == 'skipped'` from the deploy condition. Ensure migration-gate always runs for production deploys. Consider also running actual SQL validation against a Neon branch in the migration gate.

---

### P2-8: Dependabot Configured for Workers but Not for Dockerfile Base Images
**Files:** `.github/dependabot.yml`

Dependabot is configured for `pip`, `npm`, `pip` (ml), and `github-actions`, but not for Docker base images. The four Dockerfiles use `python:3.12-slim`, `node:20-alpine`, and `python:3.11-slim` — these will not receive Dependabot PRs for patch-level image updates.

**Recommendation:** Add Docker ecosystem entries to `.github/dependabot.yml`:
```yaml
- package-ecosystem: "docker"
  directory: "/"
  schedule:
    interval: "weekly"
    day: "monday"
- package-ecosystem: "docker"
  directory: "/backend"
  schedule:
    interval: "weekly"
    day: "monday"
- package-ecosystem: "docker"
  directory: "/frontend"
  schedule:
    interval: "weekly"
    day: "monday"
- package-ecosystem: "docker"
  directory: "/ml"
  schedule:
    interval: "weekly"
    day: "monday"
```

---

### P2-9: CI Postgres Version (15) Does Not Match Neon Production Version
**Files:** `_backend-tests.yml:28`, `ci.yml:344`, `e2e-tests.yml:52`

All CI test services use `postgres:15-alpine`. Neon's PostgreSQL version should be verified — Neon as of 2026 supports PostgreSQL 16 by default for new projects. If the Neon production database is PostgreSQL 16, tests running against version 15 may miss version-specific behavior differences (JSON path functions, temporal types, `MERGE` statement behavior, index scan changes).

**Recommendation:** Verify Neon project version via `SELECT version()` and align CI postgres service image accordingly. Add a note to CLAUDE.md documenting the Postgres version to prevent future drift.

---

### P2-10: OWASP ZAP Baseline Scan Has No Slack Alert on Findings
**Files:** `owasp-zap.yml`

The OWASP ZAP scan runs weekly on Sunday at 04:00 UTC with `fail_action: true` — if ZAP finds non-suppressed alerts, the workflow fails. However, there is no `notify-slack` step in the workflow on failure. The self-healing monitor tracks `owasp-zap.yml` — it is NOT in the matrix (confirmed: not listed in `self-healing-monitor.yml:33-51`). Failed ZAP scans create no GitHub issue and send no Slack notification.

**Recommendation:** Add a failure notification step:
```yaml
- name: Notify on ZAP findings
  if: failure()
  uses: ./.github/actions/notify-slack
  with:
    webhook-url: ${{ secrets.SLACK_INCIDENTS_WEBHOOK_URL }}
    workflow-name: "OWASP ZAP Security Scan"
    severity: critical
```
Also add `owasp-zap.yml` to the self-healing monitor matrix.

---

### P2-11: `data-retention.yml` Has No Warmup Step
**Files:** `data-retention.yml`

The weekly data retention cleanup calls `POST /internal/maintenance/cleanup` via `retry-curl` without a warmup step. On Render's free tier, the backend cold starts after 15 minutes of inactivity. The cleanup runs Sunday 04:00 UTC — after several low-traffic hours, the backend is almost certainly cold. The `retry-curl` default timeout is 120 seconds. Render's cold start can take 30-90 seconds. A 120s timeout minus a 90s cold start leaves only 30 seconds for the actual cleanup operation, which may time out on large datasets.

**Recommendation:** Add the `warmup-backend` composite action before the `retry-curl` call, as done in `fetch-weather.yml`, `scrape-rates.yml`, `sync-connections.yml`, `dunning-cycle.yml`, `kpi-report.yml`, and `market-research.yml`.

---

## P3 — Low Severity (Fix in Backlog)

### P3-1: `runtime.txt` Pins Patch Version — Should Pin Minor Only
**Files:** `runtime.txt`

```
python-3.12.12
```

Pinning a specific patch version (`3.12.12`) in `runtime.txt` is too specific for a Render managed runtime. When Render updates their Python buildpack, the exact patch may not be available, causing build failures. Minor version pinning (`python-3.12`) is the Render-recommended approach and allows automatic patch security updates.

**Recommendation:** Change to `python-3.12` unless there's a specific regression in a patch version that necessitates the exact pin.

---

### P3-2: `Procfile` Specifies Single Worker — Same as Root Dockerfile Issue
**Files:** `Procfile:1`

```
web: cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1
```

`Procfile` is the fallback if Render uses the native Python buildpack instead of Docker. It also specifies `--workers 1`. If Render detects a `Procfile` in certain deployment modes, it may use this instead of the Dockerfile CMD. This reinforces P0-2's single-worker concern and could be the actual command running in production if Docker build fails and Render falls back to the Procfile.

**Recommendation:** Change to `--workers 2` (safe for Render free 512MB), and add `--no-access-log` to reduce log volume. Consider removing the Procfile entirely since render.yaml specifies `runtime: docker`.

---

### P3-3: GHA Workflow Action Versions — `docker/build-push-action@v5` Available v6
**Files:** `_docker-build-push.yml:78`, `ci.yml:402`

Several action versions may have newer major releases:
- `docker/build-push-action@v5` — v6 is current (released 2024)
- `docker/metadata-action@v5` — v5 is current
- `codecov/codecov-action@v4` — v4 is current
- `aquasecurity/trivy-action@0.28.0` — minor version not latest

Dependabot should auto-PR these, but the grouping strategy (`minor-and-patch` only) will not create PRs for major version bumps like v5 → v6.

**Recommendation:** Add a `major` update type to the Dependabot `github-actions` group, or manually review and update to `docker/build-push-action@v6`.

---

### P3-4: `ml/Dockerfile` Health Check Imports TensorFlow — Not Present in Requirements
**Files:** `ml/Dockerfile:67`

```dockerfile
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 \
    CMD python -c "import tensorflow as tf; print('OK')" || exit 1
```

The health check assumes TensorFlow is installed. If TensorFlow is not in `ml/requirements.txt` (the ML stack uses an ensemble predictor with HNSW — TF may or may not be required), the health check will always fail, causing the container to be marked unhealthy immediately after start.

**Risk:** If the ML container is deployed and TensorFlow is not installed, it immediately shows as unhealthy. Docker's restart policy will restart it 3 times then stop.

**Recommendation:** Make the health check more generic: `CMD python -c "print('OK')"` or check for the actual inference module: `python -c "from inference.serve import app; print('OK')"`.

---

### P3-5: `docker-compose.yml` Mounts Backend Code as Volume — Security Anti-Pattern in Prod
**Files:** `docker-compose.yml:36-37`

```yaml
volumes:
  - ./backend:/app
  - backend-cache:/root/.cache
```

This is correct for dev (hot reload) but `backend-cache:/root/.cache` mounts the pip cache into the container at `/root/.cache` — the root user's home directory cache. The dev container runs as root (no `USER` directive in the `development` stage of `backend/Dockerfile`), which means pip packages are installed as root and cached at root's cache path.

**Recommendation:** Add a `USER appuser` directive to the `development` stage in `backend/Dockerfile` (similar to the `production` stage at line 80), and change the cache volume mount to `/home/appuser/.cache`. This prevents accidentally running as root in development and ensures dev/prod user parity.

---

### P3-6: Self-Healing Monitor Missing Workflows from Matrix
**Files:** `self-healing-monitor.yml:33-51`

The self-healing monitor matrix tracks 18 workflows. Missing from the matrix:
- `owasp-zap.yml` (weekly security scan — failures should create issues)
- `fetch-gas-rates.yml` (weekly data ingestion)
- `fetch-heating-oil.yml` (weekly data ingestion)
- `model-retrain.yml` (already tracked but does nothing — see P1-5)
- `db-maintenance` (Render cron — not monitorable via GHA API, acknowledged)
- `ci.yml` (the main CI pipeline — failures not auto-issuing)

The auto-close logic in `auto-close-resolved` uses string matching on issue titles to map back to workflow files. This is fragile — if a workflow name changes, the auto-close will not fire, leaving stale open issues.

**Recommendation:** Add `owasp-zap.yml`, `fetch-gas-rates.yml`, and `fetch-heating-oil.yml` to the matrix. Replace string-matching auto-close with storing the workflow filename in the issue body using a machine-readable marker (e.g., `<!-- workflow: check-alerts.yml -->`) and parsing that instead.

---

### P3-7: No SBOM Generation for Docker Images
**Files:** `_docker-build-push.yml`

The Docker build and push workflow does not generate a Software Bill of Materials (SBOM). Trivy scans for known CVEs, but an SBOM would enable:
- License compliance auditing
- Future CVE matching against the specific package versions at build time
- Supply chain transparency for enterprise customers

**Recommendation:** Add `sbom: true` to the `docker/build-push-action@v5` step and `provenance: true` for SLSA Level 2 compliance. These are zero-effort additions:
```yaml
- uses: docker/build-push-action@v5
  with:
    ...
    sbom: true
    provenance: mode=max
```

---

### P3-8: `update-visual-baselines.yml` Commits Directly to Branch Without PR
**Files:** `update-visual-baselines.yml:88-101`

```yaml
- name: Commit baselines
  if: steps.check.outputs.snapshot_count != '0'
  run: |
    git config user.name "github-actions[bot]"
    git commit -m "chore(e2e): update visual regression baselines [skip ci]..."
    git push
```

This workflow commits visual regression baselines directly to the ref it was triggered on (via `ref: ${{ github.ref }}`). If triggered on `main`, it commits directly to main, bypassing branch protection rules and PR review requirements. The `[skip ci]` annotation prevents CI from running on the commit, so the new baselines are not validated.

**Risk:** Visual regression baselines can be silently updated on `main` without review. A developer could accidentally regenerate baselines after a UI regression, hiding the regression in CI.

**Recommendation:** Change the workflow to open a PR with the baseline changes instead of committing directly. Use the `gh pr create` CLI. Only allow triggering from feature branches, not `main`.

---

## Summary Table

| ID | Title | Severity | File | Effort |
|---|---|---|---|---|
| P0-1 | Base images not pinned by digest | P0 | All Dockerfiles | Medium |
| P0-2 | Render uses root Dockerfile (1 worker) not backend/Dockerfile (4 workers) | P0 | Dockerfile, render.yaml | Low |
| P0-3 | No Neon database backup automation | P0 | (missing workflow) | Medium |
| P0-4 | Bandit high findings are warnings not failures in CI | P0 | ci.yml:304 | Low |
| P1-1 | Staging is phantom infrastructure | P1 | deploy-staging.yml | High |
| P1-2 | keepalive.yml consumes ~720 GHA min/mo | P1 | keepalive.yml | Low |
| P1-3 | Sunday cron schedule collisions | P1 | 4 workflow files | Low |
| P1-4 | detect-rate-changes uses wrong retry-curl input | P1 | detect-rate-changes.yml:28 | Low |
| P1-5 | model-retrain.yml does not retrain a model | P1 | model-retrain.yml | High |
| P1-6 | No Trivy scan for production Docker image | P1 | deploy-production.yml | Medium |
| P1-7 | E2E DB setup applies only 3 of 53 migrations | P1 | e2e-tests.yml:97-103 | Low |
| P2-1 | mypy is non-blocking in CI | P2 | ci.yml:116 | Low |
| P2-2 | Dev/prod compose environment parity gaps | P2 | docker-compose*.yml | Low |
| P2-3 | render.yaml missing/placeholder env vars documented | P2 | render.yaml | Low |
| P2-4 | deploy-staging.yml environment URL points to production | P2 | deploy-staging.yml:72 | Low |
| P2-5 | ORIGIN_URL in wrangler.toml is public git-tracked | P2 | wrangler.toml:40 | Low |
| P2-6 | code-analysis.yml security gate is bypassable | P2 | code-analysis.yml | Medium |
| P2-7 | Migration gate allows skipped result to proceed | P2 | deploy-production.yml:120 | Low |
| P2-8 | Dependabot not configured for Docker base images | P2 | .github/dependabot.yml | Low |
| P2-9 | CI Postgres 15 may not match Neon prod version | P2 | _backend-tests.yml:28 | Low |
| P2-10 | OWASP ZAP has no Slack alert on failure | P2 | owasp-zap.yml | Low |
| P2-11 | data-retention.yml missing warmup step | P2 | data-retention.yml | Low |
| P3-1 | runtime.txt over-pinned to patch version | P3 | runtime.txt | Low |
| P3-2 | Procfile specifies single worker | P3 | Procfile | Low |
| P3-3 | GHA action versions not on latest major | P3 | Multiple | Low |
| P3-4 | ML Dockerfile health check assumes TensorFlow | P3 | ml/Dockerfile:67 | Low |
| P3-5 | Dev compose mounts cache at /root/.cache | P3 | docker-compose.yml:37 | Low |
| P3-6 | Self-healing monitor missing workflows | P3 | self-healing-monitor.yml | Low |
| P3-7 | No SBOM generation in Docker build pipeline | P3 | _docker-build-push.yml | Low |
| P3-8 | Visual baseline workflow commits directly to main | P3 | update-visual-baselines.yml | Low |

---

## Positive Findings (Strengths to Preserve)

The following practices are well-implemented and above industry average for a free-tier SaaS:

1. **Migration gate before deploy** — `deploy-production.yml` requires migration validation before triggering Render hook. The `validate-migrations` composite action checks sequential numbering, IF NOT EXISTS, neondb_owner, and no SERIAL/BIGSERIAL.

2. **Automated rollback via Render API** — `deploy-production.yml:185-276` fetches the last successful deploy ID and rolls back via `POST /services/{id}/deploys/{deployId}/rollback`. This is non-trivial to implement and is correctly implemented.

3. **Composite action library** — Seven well-designed composite actions (`retry-curl`, `warmup-backend`, `notify-slack`, `validate-migrations`, `wait-for-service`, `setup-python-env`, `setup-node-env`) eliminate duplicated code across 32 workflows. The `retry-curl` exponential backoff with jitter and 4xx fail-fast logic is correctly implemented.

4. **Permission minimization** — Most workflows use `permissions: {}` (deny-all). Elevated permissions (`contents: write`, `issues: write`, `packages: write`) are granted only where needed and are correctly scoped.

5. **Concurrency controls** — All workflows use `concurrency.group` with `cancel-in-progress: false` for deploying workflows and `cancel-in-progress: true` for CI — correctly preventing concurrent deploys while allowing CI cancellation on superseded commits.

6. **Self-healing monitor** — The 18-workflow matrix that auto-creates GitHub issues after 3+ failures and auto-closes when the last 3 runs succeed is a solid operational pattern.

7. **CF Worker Cron Triggers** — Moving `check-alerts`, `price-sync`, and `observe-forecasts` from GHA crons to CF Worker crons eliminates ~960 GHA minutes/month at zero additional cost.

8. **Sparse checkout usage** — Workflows that only need composite actions use `sparse-checkout: .github/actions` rather than full repository checkout, reducing checkout time and bandwidth.

9. **Change detection with `dorny/paths-filter`** — CI workflow skips backend/frontend/ML jobs when the corresponding source hasn't changed, saving significant GHA minutes on mixed-scope PRs.

10. **Multi-stage Docker builds with non-root user** — All production Docker stages create a non-root user (`appuser`/`nextjs`/`mluser`) and switch to it before running the application. The root Dockerfile (P0-2) also does this correctly at line 28-44.

11. **Security headers in next.config.js** — HSTS, X-Frame-Options DENY, X-Content-Type-Options, Permissions-Policy, and Referrer-Policy are set globally at the Next.js config level. CSP is handled per-request with nonce in middleware.ts.

12. **pip-audit in backend tests** — `_backend-tests.yml:63-68` runs `pip-audit --strict --desc` before tests, blocking known Python dependency vulnerabilities. This is correctly implemented as a hard failure (no `|| true`).

---

## Recommended Priority Order

**Week 1 (P0 items):**
1. P0-4: Fix Bandit CI gate (10-minute change, immediate security hardening)
2. P0-2: Switch render.yaml to use `backend/Dockerfile` (fixes single-worker constraint)
3. P0-1: Pin base image digests (run digest collection script, update Dockerfiles)
4. P0-3: Create `neon-backup.yml` weekly workflow with `pg_dump` → R2

**Week 2 (P1 items):**
5. P1-4: Fix detect-rate-changes.yml api-key input (2-line fix)
6. P1-2: Remove or significantly reduce keepalive.yml frequency
7. P1-7: Apply all 53 migrations in E2E database setup
8. P1-3: Stagger Sunday cron schedules
9. P1-6: Add Trivy scan to production deploy gate

**Backlog (P2-P3 items):**
10. P2-5: Move ORIGIN_URL to wrangler secret
11. P2-10: Add ZAP failure Slack notification + self-healing monitor entry
12. P2-11: Add warmup to data-retention.yml
13. P2-8: Add Docker ecosystem to Dependabot
14. P2-7: Remove migration-gate 'skipped' allowance
15. Remaining P2 and P3 items as capacity allows

---

*Generated by DevOps audit pass. Read-only analysis — no source files were modified.*
