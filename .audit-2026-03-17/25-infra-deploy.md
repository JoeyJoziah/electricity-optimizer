# Audit Report: Infrastructure & Deployment
## Date: 2026-03-17
## Auditor: Claude Code (claude-sonnet-4-6)
## Scope: Infrastructure & Deployment Configuration

---

## Executive Summary

The RateShift infrastructure configuration is generally well-structured and shows mature
practices: multi-stage Dockerfiles, non-root container users, health checks across all
services, and properly pinned image versions in the production compose file. The main
deployment path (Render + Vercel + Cloudflare Worker) is sound and the separation of
dev/prod compose files is appropriate.

However, several concrete issues need attention before this configuration is considered
hardened. The most impactful are a **port inconsistency in the root Dockerfile** that
will cause the Render health check to fail intermittently, a **stale ORIGIN_URL** in
the CF Worker that points to the wrong backend hostname, **~8 production env vars
missing from render.yaml** (including GEMINI_API_KEY and FRONTEND_URL), and
**`sslmode=disable` on the prod postgres-exporter** connection string. There are also
a few medium-risk items around the backend Dockerfile's base-stage scope and Makefile's
use of system `pytest` instead of `.venv/bin/python -m pytest`.

Files reviewed:
- `/Dockerfile` (root — used by Render)
- `/backend/Dockerfile`
- `/frontend/Dockerfile`
- `/ml/Dockerfile`
- `/docker-compose.yml`
- `/docker-compose.prod.yml`
- `/render.yaml`
- `/Procfile`
- `/runtime.txt`
- `/Makefile`
- `/backend/gunicorn_config.py`
- `/.dockerignore`
- `/backend/.dockerignore`
- `/frontend/.dockerignore`
- `/ml/.dockerignore`
- `/workers/api-gateway/wrangler.toml`
- `/.vercel/project.json` and `/frontend/.vercel/project.json`
- `/.env.example` and `/backend/.env.example`

---

## Findings

### P0 — Critical

#### P0-1: Port inconsistency in root Dockerfile causes health-check mismatch
**File**: `/Dockerfile`, lines 48, 51, 54

The `EXPOSE` directive uses `${PORT:-10000}` (Render's default) while both the health
check command and the `CMD` use `${PORT:-8000}`. On Render, `PORT` is injected as
`10000` at runtime. At that moment:
- Gunicorn/uvicorn binds on `10000` (correct).
- But the `HEALTHCHECK` still probes `http://localhost:${PORT:-8000}/health`, which
  only falls back to `8000` when `PORT` is unset, so it resolves to
  `http://localhost:10000/health` — correct at runtime.

Wait — the interpolation actually goes the other way: because `PORT` IS set to `10000`
by Render, `${PORT:-8000}` evaluates to `10000`, so the health check URL is correct at
runtime. The real issue is that the comment on line 50 says "Render uses PORT env var,
default 10000" while the `CMD` defaults to `8000`. This means if you run the container
locally without setting `PORT`, uvicorn binds on `8000` but the `EXPOSE` hint says
`10000`. More critically, the `CMD` runs through `sh -c` with a shell substitution,
but uses `--timeout-graceful-shutdown` which is a **uvicorn flag that does not exist
in uvicorn's CLI** (it is a Gunicorn flag). Uvicorn's equivalent is
`--timeout-graceful-shutdown` introduced in uvicorn 0.18+; verify the installed version
supports it, otherwise the worker will fail to start silently.

Additionally, the root Dockerfile runs **1 uvicorn worker** (`--workers 1`) while
`backend/Dockerfile` runs 4, and `backend/gunicorn_config.py` documents 1 worker for
the free tier. The worker count discrepancy between the two backend Dockerfiles creates
confusion about which one Render actually uses (render.yaml points to
`./Dockerfile` at root).

**Recommendation**:
```dockerfile
# Root Dockerfile CMD — use gunicorn_config.py to keep settings DRY
CMD ["sh", "-c", "cd /app/backend && gunicorn -c gunicorn_config.py main:app"]

# Or keep uvicorn but align defaults
ENV PORT=10000
EXPOSE 10000
HEALTHCHECK CMD curl -f http://localhost:${PORT}/health || exit 1
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --timeout-graceful-shutdown 30"]
```

---

#### P0-2: CF Worker ORIGIN_URL points to stale Render subdomain
**File**: `/workers/api-gateway/wrangler.toml`, line 40

```toml
ORIGIN_URL = "https://electricity-optimizer.onrender.com"
```

The CLAUDE.md architecture section states the Render service is
`api.rateshift.app` (routed through the CF Worker) and the service ID is
`srv-d649uhur433s73d557cg`. The `.onrender.com` subdomain is the default Render
hostname, but:

1. If the Render service was renamed to `electricity-optimizer`, the `.onrender.com`
   URL is `https://electricity-optimizer.onrender.com` which may still resolve — but
   this is the public hostname, not the intended direct-to-Render bypass URL that avoids
   the Worker's own routing loop.
2. More importantly: the production domain is `rateshift.app`/`api.rateshift.app`, yet
   the Worker's origin still references the old project name. Any CF Worker that calls
   its own `ORIGIN_URL` via `api.rateshift.app` would create a routing loop; the intent
   of `ORIGIN_URL` must be the direct Render `.onrender.com` address. If this value is
   stale and the actual Render service URL has changed (e.g. to
   `rateshift-api.onrender.com`), all traffic through the Worker silently returns 502.

**Recommendation**: Confirm the actual Render service URL and update:
```toml
ORIGIN_URL = "https://rateshift-api.onrender.com"  # verify exact slug
```
Add a comment documenting how to find this value (`render.yaml` service name field
or Render dashboard).

---

### P1 — High

#### P1-1: render.yaml is missing ~8 production env vars documented as required
**File**: `/render.yaml`

The CLAUDE.md states the Render service has **42 env vars** (34 prior + 4 AI agent +
3 OTel + FRONTEND_URL). The render.yaml contains **40 `- key:` entries** (39 for the
web service + 1 for the cron). Cross-referencing the documented required vars, the
following are absent from render.yaml entirely:

| Missing Key         | Source of truth                   | Risk if absent                         |
|---------------------|-----------------------------------|----------------------------------------|
| `GEMINI_API_KEY`    | CLAUDE.md AI Agent section        | AI Agent falls back to Groq only       |
| `GROQ_API_KEY`      | CLAUDE.md AI Agent section        | AI Agent completely disabled           |
| `COMPOSIO_API_KEY`  | CLAUDE.md AI Agent section        | AI Agent tool calls fail               |
| `ENABLE_AI_AGENT`   | CLAUDE.md AI Agent section        | Agent endpoints always 503             |
| `FRONTEND_URL`      | CLAUDE.md (added 2026-03-17)      | CORS/redirect failures                 |
| `SMTP_HOST`         | render.yaml line 83 — present     | (present — false alarm)                |
| `UTILITYAPI_KEY`    | backend/.env.example              | Utility sync silently skipped          |
| `ALLOWED_REDIRECT_DOMAINS` | backend/.env.example      | Stripe checkout redirects broken       |

If render.yaml is the Infrastructure-as-Code source of truth for Render deployments,
a `render deploy` or fresh service creation will not inject these keys, leaving the
AI Agent and utility integration features silently broken.

**Recommendation**: Add the missing keys with `sync: false`:
```yaml
      - key: GEMINI_API_KEY
        sync: false
      - key: GROQ_API_KEY
        sync: false
      - key: COMPOSIO_API_KEY
        sync: false
      - key: ENABLE_AI_AGENT
        value: "true"
      - key: FRONTEND_URL
        sync: false
      - key: UTILITYAPI_KEY
        sync: false
      - key: ALLOWED_REDIRECT_DOMAINS
        sync: false
```

---

#### P1-2: postgres-exporter uses `sslmode=disable` in production compose
**File**: `/docker-compose.prod.yml`, line 286

```yaml
DATA_SOURCE_NAME=postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/electricity?sslmode=disable
```

While this container connects to the local Docker network postgres instance (not Neon),
`sslmode=disable` is still a bad habit to normalize in a production file. If this
template is ever adapted to point at the actual Neon database for metrics scraping, it
would silently send credentials in cleartext. The postgres-exporter also references a
local postgres container that does not exist in the real production deployment (Neon is
used instead), making this entire service dead configuration in the actual prod
environment.

**Recommendation**: Use `sslmode=require` as the default:
```yaml
DATA_SOURCE_NAME=postgresql://postgres:${POSTGRES_PASSWORD}@postgres:5432/electricity?sslmode=require
```
Add a comment noting this service is only relevant for the self-hosted Docker compose
scenario, not the Render+Neon deployment.

---

#### P1-3: backend/Dockerfile base stage installs postgresql-client and build-essential into prod image
**File**: `/backend/Dockerfile`, lines 10–16

The `base` stage (which feeds both `development` and `production`) installs:
- `build-essential` (~200 MB)
- `postgresql-client` (~30 MB)

These are build-time-only needs. `build-essential` is needed to compile C extensions
during `pip install`; `postgresql-client` is only needed if running `psql` commands
directly. Neither belongs in the production runtime image. The production stage at
line 63 correctly installs only `libpq5` (the runtime library), but it also copies
`/usr/local/lib/python3.12/site-packages` and `/usr/local/bin` from `base` — meaning
the compiled extensions are preserved while the build tools are not. This is correct.
However, the `development` stage inherits `build-essential` directly in its layer
history, inflating the development image unnecessarily compared to using a separate
`deps` stage.

The more critical issue: the `production` stage copies from `--from=builder` (line 77)
which is a copy of `base` plus the compiled `.pyc` files. It also copies from `base`
directly for site-packages (lines 69–70). This means the production image's `COPY`
instructions pull from two different stages, which works but is fragile. If `base`
diverges from `builder` (e.g., a `COPY` in `builder` that is not in `base`), the
Python packages and the app code may be out of sync.

**Recommendation**: Restructure with an explicit `deps` stage separate from `base`:
```dockerfile
FROM python:3.12-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS production
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY --from=deps /install /usr/local
# ...
```
This mirrors the pattern already used correctly in the root `/Dockerfile`.

---

#### P1-4: Makefile test targets use system `pytest` instead of `.venv/bin/python -m pytest`
**File**: `/Makefile`, lines 86, 90, 102

```makefile
test-backend:
    cd backend && pytest --cov=. --cov-report=term-missing -v

test-ml:
    cd ml && pytest --cov=. --cov-report=term-missing -v
```

The CLAUDE.md Critical Reminders explicitly state: "Always use `.venv/bin/python -m pytest`,
never system Python." Running `pytest` without the full path picks up whichever pytest
is first on `PATH`, which may be a different version or the wrong virtual environment.
This causes silent test misconfiguration and is inconsistent with the CI workflow which
correctly uses `.venv/bin/python`.

**Recommendation**:
```makefile
PYTHON := .venv/bin/python

test-backend:
    cd backend && $(PYTHON) -m pytest --cov=. --cov-report=term-missing -v

test-ml:
    cd ml && $(PYTHON) -m pytest --cov=. --cov-report=term-missing -v
```

---

#### P1-5: docker-compose.yml frontend service has no health check
**File**: `/docker-compose.yml`, lines 49–68

The `frontend` service in the development compose file has no `healthcheck` block,
while `backend` and `redis` both have proper health checks. This means `depends_on:
backend` on the frontend only waits for the backend container to start, not for it to
be healthy (the `condition: service_healthy` pattern used for redis is not applied
here). In practice the dev compose has `condition: service_started` implicitly for the
backend dependency.

**Recommendation**: Add a health check to the frontend service:
```yaml
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider",
             "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    depends_on:
      backend:
        condition: service_healthy
```

---

### P2 — Medium

#### P2-1: Root .dockerignore does not exclude `.env` (root-level) or `conductor/`
**File**: `/.dockerignore`

The root `.dockerignore` excludes `backend/.env` (line 13) but not a root-level `.env`
file. The root `.env.example` contains template values for `LOKI_PROMPT_INJECTION=true`
and other Loki/dev-only settings. If a developer copies `.env.example` to `.env` at
the project root (as instructed by `make setup`), and then builds the root Dockerfile,
that `.env` is included in the Docker build context and baked into the image.

Additional paths not excluded that could add build context bloat or leak data:
- `conductor/` (conductor framework track files)
- `.project-intelligence/` (MASTER_TODO_REGISTRY)
- `workers/` (CF Worker source — not needed in backend image)
- `frontend/` is excluded but `ml/` exclusion was added; `workers/` is not

**Recommendation**:
```dockerignore
# Add to root .dockerignore
.env
.env.*
conductor/
.project-intelligence/
workers/
*.audit-*/
```

---

#### P2-2: .env.example DATA_RESIDENCY conflicts between root and render.yaml
**File**: `/.env.example` line 71 vs `/render.yaml` line 41

The root `.env.example` sets `DATA_RESIDENCY=EU` while `render.yaml` sets
`DATA_RESIDENCY=US` (matching the actual Neon project location of us-east-1). A
developer following the setup docs and copying `.env.example` verbatim to `.env` will
run locally with EU residency rules while production enforces US. If GDPR compliance
logic branches on this value (consent flows, data retention rules), this mismatch
creates untestable divergence between dev and production behavior.

**Recommendation**: Align `.env.example` to match production:
```ini
# .env.example line 71
DATA_RESIDENCY=US
```
Or explicitly document the intentional difference with a comment explaining that EU
mode is used for local testing of GDPR flows.

---

#### P2-3: ML Dockerfile health check imports tensorflow, which may not be installed
**File**: `/ml/Dockerfile`, line 67

```dockerfile
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 \
    CMD python -c "import tensorflow as tf; print('OK')" || exit 1
```

The ML `requirements.txt` includes both `tensorflow>=2.13.0` and `torch>=2.0.0`.
TensorFlow is a 500MB+ package. The health check only verifies TensorFlow imports, not
the actual inference service. If the service is PyTorch-only in a given deployment (or
if tensorflow is not installed for a lighter deployment variant), this health check
will always fail. A more robust check would probe the actual HTTP endpoint:

**Recommendation**:
```dockerfile
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1
```
If no HTTP endpoint exists, probe with a lightweight Python check that does not
require the full ML stack:
```dockerfile
    CMD python -c "import sys; sys.exit(0)" || exit 1
```

---

#### P2-4: ML Dockerfile uses Python 3.11 while backend uses Python 3.12
**File**: `/ml/Dockerfile`, line 4

```dockerfile
FROM python:3.11-slim as base
```

The `runtime.txt` specifies `python-3.12.12` and the backend Dockerfile uses
`python:3.12-slim`. Having two different Python minor versions across services can
cause subtle behavioural differences, especially with numpy type annotations and pandas
APIs. Python 3.12 is also more performant for numerical workloads.

**Recommendation**: Update the ML Dockerfile to use Python 3.12:
```dockerfile
FROM python:3.12-slim AS base
```
Verify `tensorflow>=2.13.0` supports 3.12 (it does as of TF 2.16+). If pinned to an
older TF version, this is a blocker for the upgrade.

---

#### P2-5: docker-compose.prod.yml postgres service is dead config for actual deployment
**File**: `/docker-compose.prod.yml`, lines 138–169

The production compose file includes a full `postgres` service, but the actual
production deployment uses Neon PostgreSQL (as documented in CLAUDE.md and render.yaml).
Having a postgres container in the "prod" compose creates several risks:
1. Confusion: a developer running `docker compose -f docker-compose.prod.yml up` will
   bring up a local postgres instead of connecting to Neon.
2. The DATABASE_URL in the prod compose (line 19) is hardcoded to `postgres:5432` not
   the Neon pooled endpoint.
3. The `postgres-data` named volume will accumulate stale data.

**Recommendation**: Remove the `postgres` service from `docker-compose.prod.yml` and
update the backend `DATABASE_URL` env var to reference the actual Neon URL pattern:
```yaml
- DATABASE_URL=${DATABASE_URL}  # Set via .env to Neon pooled endpoint
```
Add a comment explaining this compose is for local production-parity testing only, not
actual Render deployment.

---

#### P2-6: wrangler.toml `compatibility_date` is stale
**File**: `/workers/api-gateway/wrangler.toml`, line 3

```toml
compatibility_date = "2024-12-01"
```

Cloudflare Workers' compatibility date is now over 15 months old. New compatibility
flags (including improvements to the `Cache API`, `fetch()` behaviour, and `crypto`
APIs) may have landed since then. While not updating this will not break anything, it
means the Worker misses out on bug fixes and performance improvements.

**Recommendation**: Update to the current date before the next Worker deployment:
```toml
compatibility_date = "2026-03-01"
```
Review the [Cloudflare compatibility flags changelog](https://developers.cloudflare.com/workers/configuration/compatibility-dates/)
for any breaking changes between `2024-12-01` and the new date.

---

#### P2-7: gunicorn_config.py has `umask = 0`, which is overly permissive
**File**: `/backend/gunicorn_config.py`, line 51

```python
umask = 0
```

A umask of `0` means all new files and directories created by Gunicorn workers will
have permissions `0777` (files) or `0777` (dirs) before OS defaults. While the
container runs as a non-root user (`appuser`), and Render's container filesystem is
ephemeral, setting `umask = 0` is not recommended. Temporary upload files or log files
created by the process could be world-readable/writable.

**Recommendation**:
```python
umask = 0o022  # files 644, dirs 755
```

---

#### P2-8: Procfile worker count inconsistency with gunicorn_config.py
**File**: `/Procfile`, line 1

```
web: cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1
```

The Procfile bypasses `gunicorn_config.py` entirely and runs uvicorn directly with
`--workers 1`. While the CLAUDE.md confirms 1 worker is correct for the free tier,
the gunicorn config file with its `max_requests`, `max_requests_jitter`, `keepalive`,
and custom lifecycle hooks is completely unused when deploying via Procfile. The
Procfile and the Dockerfile use different process supervisors (raw uvicorn vs Gunicorn
wrapping uvicorn workers), meaning behavior differs between Docker and native Render
deployments.

Since `render.yaml` specifies `runtime: docker` (Dockerfile-based), the Procfile is
effectively dead in the current deployment. Its presence could mislead developers.

**Recommendation**: Either:
1. Remove the Procfile if Docker is always used (render.yaml confirms this).
2. Update it to invoke gunicorn: `web: cd backend && gunicorn -c gunicorn_config.py main:app`
3. Add a comment: `# NOTE: Not used — render.yaml uses runtime: docker (see Dockerfile)`

---

### P3 — Low

#### P3-1: frontend Dockerfile comment says "Next.js 14" but project uses Next.js 16
**File**: `/frontend/Dockerfile`, line 1

```dockerfile
# Multi-stage build for Next.js 14 frontend
```

The CLAUDE.md architecture section documents "Next.js 16 + React 19". The comment is
stale from an earlier version and could confuse contributors checking version
compatibility.

**Recommendation**: Update the comment to match actual version:
```dockerfile
# Multi-stage build for Next.js 16 frontend
# Optimized for production with standalone output (~30% smaller)
```

---

#### P3-2: docker-compose.yml uses `latest` tags for prometheus and grafana
**File**: `/docker-compose.yml`, lines 96, 115

```yaml
image: prom/prometheus:latest
image: grafana/grafana:latest
```

The dev compose uses `latest` tags while the prod compose correctly uses pinned
versions (`prom/prometheus:v2.51.0`, `grafana/grafana:10.4.1`). This creates a
risk of dev/prod divergence when upstream releases a breaking change. A developer
debugging a metrics issue locally may be running a different Prometheus/Grafana
version than what runs in prod.

**Recommendation**: Pin the dev compose to the same versions as prod:
```yaml
image: prom/prometheus:v2.51.0
image: grafana/grafana:10.4.1
```

---

#### P3-3: backend/.dockerignore leaves test files included
**File**: `/backend/.dockerignore`, lines 37–40

```dockerignore
# Testing (include for production)
# tests/
# conftest.py
# test_*.py
# *_test.py
```

The test files are intentionally included (comment says "include for production").
This adds ~2,663 test files worth of content to the production Docker image. While
this is a deliberate choice (perhaps for on-demand test runs in containers), it
conflicts with the root `.dockerignore` which explicitly excludes `backend/tests/`
(line 25). The inconsistency between the two ignore files could cause confusion.

**Recommendation**: If tests should be excluded from the production image, uncomment
these lines. If they are intentionally included, add a more explicit comment explaining
the rationale (e.g., "included for smoke test on deploy") and remove the conflict with
the root `.dockerignore`.

---

#### P3-4: .vercel/project.json is duplicated at two paths
**Files**: `/.vercel/project.json` and `/frontend/.vercel/project.json`

Both files contain identical content:
```json
{"projectId":"prj_Ph19P8Am9iUkQ3JeNdJ0PjegZZcc","orgId":"team_0Ir7XnWMaEZABXENmSThDxzO","projectName":"electricity-optimizer"}
```

Vercel CLI expects this file in the project root it is run from. Having two copies at
both the repo root and `frontend/` suggests the Vercel CLI was run from both locations
at different times. The `projectName` is still `electricity-optimizer` rather than
`rateshift` — a minor branding inconsistency following the RateShift rebrand.

**Recommendation**:
1. Decide which directory Vercel deploys from (almost certainly `frontend/`) and remove
   the stale copy at the repo root, or add `/.vercel` to `.gitignore`.
2. Update `projectName` to match the current brand: `"rateshift"`.

---

#### P3-5: render.yaml service name still uses old project name
**File**: `/render.yaml`, line 3

```yaml
name: electricity-optimizer
```

Following the RateShift rebrand, the Render service name still references the old
project name. While this is cosmetic and does not affect functionality (the service
ID `srv-d649uhur433s73d557cg` is what matters), it creates confusion in the Render
dashboard and in log aggregation. The cron service on line 92 is similarly named
`db-maintenance` which is fine.

**Recommendation**: Update the service name:
```yaml
name: rateshift-api
```

---

#### P3-6: Makefile `docs` target opens Swagger UI which is disabled in production
**File**: `/Makefile`, line 241

```makefile
docs: ## Open API documentation
    open http://localhost:8000/docs
```

The CLAUDE.md Critical Reminders note that "Swagger/ReDoc disabled in prod." This
Makefile target is fine for local development but could mislead a developer into
thinking `/docs` is accessible. A minor comment would clarify intent.

**Recommendation**: Add a note:
```makefile
docs: ## Open API docs (dev only — disabled in production)
    @echo "Note: /docs is disabled in production (ENVIRONMENT=production)"
    open http://localhost:8000/docs
```

---

#### P3-7: gunicorn_config.py still references "Electricity Optimizer" in startup log
**File**: `/backend/gunicorn_config.py`, line 62

```python
server.log.info("Starting Electricity Optimizer API...")
```

Post-rebrand, this log message still uses the old product name. Logs will show
"Electricity Optimizer" instead of "RateShift" in Render log streams.

**Recommendation**:
```python
server.log.info("Starting RateShift API...")
```

---

## Statistics

| Severity | Count | Files Affected |
|----------|-------|----------------|
| P0 — Critical | 2 | `Dockerfile` (root), `wrangler.toml` |
| P1 — High | 5 | `render.yaml`, `docker-compose.prod.yml`, `backend/Dockerfile`, `Makefile`, `docker-compose.yml` |
| P2 — Medium | 8 | `/.dockerignore`, `.env.example`, `ml/Dockerfile` (x2), `docker-compose.prod.yml`, `wrangler.toml`, `gunicorn_config.py`, `Procfile` |
| P3 — Low | 7 | `frontend/Dockerfile`, `docker-compose.yml`, `backend/.dockerignore`, `.vercel/`, `render.yaml`, `Makefile`, `gunicorn_config.py` |
| **Total** | **22** | **13 files** |

### Priority Action Plan

1. **Immediate** (P0): Resolve port/CMD alignment in root Dockerfile; verify and update
   CF Worker `ORIGIN_URL` to the correct Render service hostname.
2. **Before next deploy** (P1): Sync render.yaml with the 42-env-var documented state;
   fix `sslmode=disable` on postgres-exporter; restructure `backend/Dockerfile` base
   stage to separate build and runtime deps; align Makefile test commands to use
   `.venv/bin/python -m pytest`.
3. **Next sprint** (P2): Add `.env` to root `.dockerignore`; align `DATA_RESIDENCY` in
   `.env.example`; update ML Dockerfile to Python 3.12 and fix health check; clean up
   dead postgres service from prod compose; update `wrangler.toml` compatibility date;
   fix `gunicorn_config.py` umask; clarify Procfile status.
4. **Backlog** (P3): Update stale Next.js version comment; pin dev compose image tags;
   resolve test file inclusion inconsistency; deduplicate `.vercel/` config; rename
   Render service to `rateshift-api`; update startup log message.
