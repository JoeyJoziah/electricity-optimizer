# Specification 04: Data, Infrastructure, and Security Layer

> SPARC Phase: Specification | Version: 1.0 | Date: 2026-02-22
>
> **Note (2026-02-24):** This spec predates the refactoring roadmap (2026-02-23). Key changes since: Celery removed, TimescaleDB replaced by Neon PostgreSQL, JWT auth replaced by Neon Auth (Better Auth sessions), `ci.yml`/`deploy.yml` workflows deleted, session cache key upgraded to SHA-256. See [REFACTORING_ROADMAP.md](REFACTORING_ROADMAP.md) for the full change log.

## 1. Infrastructure Overview

Nine services (dev) or ten (prod adds `celery-worker`) on a single Docker bridge network.

```
Service             Image                       Port   Depends On        Prod Limits
backend             ./backend Dockerfile        8000   redis,timescaledb  1CPU/512M
frontend            ./frontend Dockerfile       3000   backend            0.5CPU/256M
redis               redis:7-alpine              6379   --                 0.25CPU/128M
timescaledb         timescale/timescaledb:pg15   5432   --                 1CPU/1G
celery-worker(prod) ./backend Dockerfile        --     redis,backend      0.5CPU/256M
prometheus          prom/prometheus:latest       9090   --                 0.25CPU/256M
grafana             grafana/grafana:latest       3001   prometheus         0.25CPU/256M
node-exporter       prom/node-exporter          9100   --                 0.1CPU/64M
redis-exporter      oliver006/redis_exporter    9121   redis              0.1CPU/32M
postgres-exporter   postgres-exporter           9187   timescaledb        0.1CPU/32M
```

**Volumes**: `redis-data` (AOF), `timescale-data` (pgdata), `prometheus-data` (TSDB, 15d dev/30d prod), `grafana-data`, `backend-cache` (dev only). Prod mounts configs as `:ro`.

**Health checks**: backend `curl /health` 30s/10s/3 retries; redis `redis-cli ping` 10s/3s/3; timescaledb `pg_isready` 10s/5s/5. Prod `start_period` increased to 30s.

**Prod extras**: resource limits, restart-on-failure (max 3, 120s window), JSON logging (max-size 10m, max-file 3), Redis `maxmemory 100mb allkeys-lru`.

## 2. Database Schema

Neon PostgreSQL (project `holy-pine-81107663`, branch `main`). All PKs are UUID via `gen_random_uuid()`.

```
users ──< auth_sessions      (FK CASCADE)     suppliers ──< tariffs  (FK CASCADE)
users ──< consent_records    (FK CASCADE)     (standalone) electricity_prices
users ──< activity_logs      (FK SET NULL)    (standalone) beta_signups
users  .  deletion_logs      (no FK, immutable audit)
users  .  login_attempts     (keyed by email/IP, no FK)
```

```
PSEUDOCODE table_definitions:

TABLE users (PK id UUID):
  email VARCHAR(255) UNIQUE, name VARCHAR(200), region VARCHAR(50),
  preferences JSONB DEFAULT '{}', current_supplier VARCHAR(200),
  is_active BOOL TRUE, is_verified BOOL FALSE,
  email_verified BOOL FALSE, consent_given BOOL FALSE,
  data_processing_agreed BOOL FALSE, last_login TIMESTAMPTZ,
  login_count INT 0, failed_login_attempts INT 0, locked_until TIMESTAMPTZ,
  created_at/updated_at TIMESTAMPTZ (auto-trigger on updated_at)
  INDEXES: region, is_active(partial), created_at DESC

TABLE electricity_prices (PK id UUID):
  region VARCHAR(50), supplier VARCHAR(200), price_per_kwh DECIMAL(12,6) CHECK>=0,
  currency CHAR(3), timestamp TIMESTAMPTZ, is_peak BOOL, source_api VARCHAR(200)
  INDEXES: (region,timestamp DESC), supplier, timestamp DESC, (region,is_peak) partial

TABLE suppliers (PK id UUID):
  name VARCHAR(200) UNIQUE, regions TEXT[], is_active BOOL, website VARCHAR(500)
  INDEXES: is_active(partial), regions(GIN)

TABLE tariffs (PK id UUID, FK supplier_id -> suppliers CASCADE):
  name VARCHAR(200), price_per_kwh DECIMAL(12,6), standing_charge DECIMAL(12,6),
  is_available BOOL, tariff_type VARCHAR(50) DEFAULT 'variable'
  INDEXES: supplier_id, tariff_type, (supplier_id,is_available) partial

TABLE consent_records (PK id UUID, FK user_id -> users CASCADE):
  purpose VARCHAR(50), consent_given BOOL, timestamp TIMESTAMPTZ,
  ip_address VARCHAR(45), user_agent VARCHAR(500), consent_version VARCHAR(20),
  withdrawal_timestamp TIMESTAMPTZ, metadata_json JSONB
  INDEXES: user_id, (user_id,timestamp DESC), purpose, (user_id,purpose)

TABLE deletion_logs (PK id UUID, NO FK -- immutable):
  user_id UUID, deleted_at TIMESTAMPTZ, deleted_by VARCHAR(100),
  deletion_type VARCHAR(20) NOT NULL, ip_address VARCHAR(45),
  user_agent VARCHAR(500), data_categories_deleted JSONB DEFAULT '[]',
  legal_basis VARCHAR(50) DEFAULT 'user_request', metadata_json JSONB
  TRIGGER: tr_prevent_deletion_log_update RAISES EXCEPTION on UPDATE/DELETE

TABLE auth_sessions (PK id UUID, FK user_id -> users CASCADE):
  token_hash VARCHAR(64), refresh_token_hash VARCHAR(64), expires_at TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ, ip_address VARCHAR(45), user_agent VARCHAR(500),
  is_revoked BOOL FALSE, revoked_at TIMESTAMPTZ

TABLE login_attempts (PK id UUID):
  identifier VARCHAR(255), identifier_type VARCHAR(20),
  attempt_at TIMESTAMPTZ, success BOOL, ip_address VARCHAR(45),
  user_agent VARCHAR(500), failure_reason VARCHAR(100)
  FUNCTION: cleanup_old_login_attempts() deletes > 7 days

TABLE activity_logs (PK id UUID, FK user_id -> users SET NULL):
  action VARCHAR(100), resource_type VARCHAR(50), resource_id UUID,
  timestamp TIMESTAMPTZ, ip_address VARCHAR(45), user_agent VARCHAR(500),
  details JSONB, correlation_id UUID
  FUNCTION: cleanup_old_activity_logs() deletes > 2 years

TABLE beta_signups (PK id UUID):
  email VARCHAR(255) UNIQUE, name VARCHAR(200), interest TEXT
```

**ENUM**: `consent_purpose` = data_processing, marketing, analytics, price_alerts, optimization, third_party_sharing. **Grants**: `neondb_owner` gets SELECT/INSERT on audit tables; full CRUD on auth_sessions, activity_logs.

**Migrations**: `init_neon.sql` creates 7 base tables + triggers. `002_gdpr_auth_tables.sql` adds auth_sessions, login_attempts, activity_logs + user GDPR columns. `003_reconcile_schema.sql` fixes divergence: renames metadata->metadata_json, timestamp->deleted_at, deleted_categories->data_categories_deleted (TEXT[]->JSONB), adds deletion_type/legal_basis columns, adds missing FKs and indexes. All migrations are idempotent (IF NOT EXISTS guards).

## 3. Caching Layer

Redis 7-alpine with AOF persistence. Prod: maxmemory 100mb, allkeys-lru eviction. Pool: 10 connections, 5s connect timeout, keepalive enabled.

```
PSEUDOCODE redis_usage:

  RATE LIMITING (sorted-set sliding window):
    KEY "ratelimit:{minute|hour}:{identifier}"
    ZREMRANGEBYSCORE(0, now-window) -> ZADD(now) -> ZCARD -> EXPIRE(window)
    Limits: 100/min, 1000/hour (configurable)

  LOGIN LOCKOUT:
    KEY "login_attempts:{email_or_ip}"
    On fail: INCR + EXPIRE(15min). On success: DELETE.
    Threshold: 5 failures -> 15 min lockout.

  FALLBACK: dict-based in-memory sliding window when Redis unavailable.
    Production: raise on Redis failure. Dev: degrade gracefully.

  CELERY BROKER: Redis doubles as broker + result backend for celery-worker (prod).
```

## 4. CI/CD Pipeline

| Workflow               | Trigger                          | Key Steps                                |
|------------------------|----------------------------------|------------------------------------------|
| `ci.yml`               | push, PR (all)                   | pytest backend, npm test+build frontend  |
| `test.yml`             | push/PR main,develop             | backend+ML+frontend tests, security scan, Docker build |
| `backend-ci.yml`       | push/PR (backend/**)             | black, isort, flake8, mypy, pytest+coverage, bandit, Docker |
| `frontend-ci.yml`      | push/PR (frontend/**)            | ESLint, TS check, jest+coverage, Lighthouse, npm audit, Docker |
| `e2e-tests.yml`        | push/PR + daily 2AM              | Playwright E2E, Lighthouse, load tests, security tests |
| `deploy-staging.yml`   | push develop + manual            | test -> build+push GHCR -> deploy -> smoke tests -> Notion |
| `deploy-production.yml`| release + manual                 | validate -> test -> build+push -> backup -> deploy -> smoke -> rollback |
| `price-sync.yml`       | cron 0 */6 * * *                 | POST /prices/refresh with X-API-Key header |
| `model-retrain.yml`    | cron Sunday 2AM                  | ML pipeline validation with production data |
| `keepalive.yml`        | cron */14 * * * *                | Ping /health (prevents Render free-tier spin-down) |
| `notion-sync.yml`      | issue/PR events + */30 * * * *   | Sync GitHub issues/PRs to Notion database |

```
PSEUDOCODE deploy_production_pipeline:
  validate(version) -> test(pytest+jest, skippable) ->
  build_and_push(ghcr.io, tags: latest+version+sha) ->
  backup(pre-deploy DB snapshot) -> deploy(docker compose prod) ->
  smoke_tests(health + API endpoints, 5 retries) ->
  ON FAILURE: rollback(restore backup, restart previous images) ->
  update_notion(status) -> notify(success/failure)
```

## 5. Monitoring Stack

**Prometheus**: scrape 15s global (10s backend), retention 30d prod. Targets: backend:8000/metrics, postgres-exporter:9187, redis-exporter:9121, node-exporter:9100, celery-worker:9808, self:9090.

**Grafana**: Prometheus (default) + TimescaleDB datasources. Dashboards provisioned from `monitoring/grafana/dashboards/`. Sign-up disabled, analytics disabled in prod.

```
PSEUDOCODE alert_rules (eval 30s):

  CRITICAL:
    HighErrorRate:  rate(5xx) > 5% for 5m
    ServiceDown:    up == 0 for 2m

  WARNING (performance):
    HighAPILatency: p95 latency > 1s for 5m
    ModelInferenceHigh: inference > 1s for 10m
    ModelAccuracyDegraded: MAPE > 15% for 1h

  WARNING (infrastructure):
    HighDBConnections: connections/max > 80% for 5m
    SlowQueries: avg query > 1000ms for 10m
    RedisMemoryHigh: used/max > 90% for 5m
    RedisConnectionsHigh: clients > 100 for 5m
    HighCPU: > 85% for 10m | HighMem: > 80% for 10m | LowDisk: < 15% for 5m

  WARNING (data):
    PriceDataStale: last update > 30min for 5m
    HighSwitchingFailureRate: failures/total > 10% for 30m

  INFO:
    LowUserEngagement: actions < 10/hour for 1h
```

## 6. Security Model

### 6.1 Authentication

```
PSEUDOCODE auth_flow:
  authenticate(email, password):
    IF rate_limiter.is_locked_out(email): RETURN 429
    user = db.get_user_by_email(email)
    IF NOT user OR NOT verify_password(password, hash):
      record_login_attempt(email, FALSE)
      IF attempts >= 5: RETURN 429 (locked 15min)
      RETURN 401
    record_login_attempt(email, TRUE)  // clears counter
    token = jwt.encode({sub:user.id, exp:now+24h}, JWT_SECRET, HS256)
    INSERT auth_sessions(user_id, sha256(token), expires_at, ip, ua)
    RETURN {token, user}

  validate_token(token):
    payload = jwt.decode(token, JWT_SECRET)
    session = db.get_by_token_hash(sha256(token))
    IF NOT session OR revoked OR expired: RAISE 401
    RETURN payload
```

JWT: HS256, 24h expiry. Prod enforces secret >= 32 chars and blocks 5 known insecure defaults.

### 6.2 API Key + CORS

`INTERNAL_API_KEY` via `X-API-Key` header guards `POST /prices/refresh`. CORS origins default to localhost:3000,3001,8000; prod must set explicit domain.

### 6.3 Security Headers

All responses: X-Frame-Options DENY, X-Content-Type-Options nosniff, X-XSS-Protection, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy (disable camera/mic/geo/payment/usb), CSP (strict in prod, relaxed in dev). Prod adds HSTS max-age=31536000 includeSubDomains preload. API paths set Cache-Control no-store.

### 6.4 Rate Limiting

Middleware on all paths except /health, /metrics. Identifier: `user:sha256(token)[:16]` for authenticated, `ip:address` for anonymous. Two windows: 100/min, 1000/hour. Response includes X-RateLimit-Limit and X-RateLimit-Remaining.

### 6.5 GDPR Compliance

```
PSEUDOCODE gdpr:
  // Art 6,7: Consent
  record_consent(user_id, purpose, given, ip, ua) -> INSERT consent_records
  withdraw_all_consents(user_id) -> record FALSE for each ConsentPurpose

  // Art 15,20: Data Export
  export_user_data(user_id) -> {profile, preferences, consents, alerts, logs}

  // Art 17: Erasure
  delete_user_data(user_id, anonymize=FALSE):
    DELETE consent_records, price_alerts, recommendations
    IF anonymize: ANONYMIZE activity_logs ELSE DELETE
    DELETE user profile
    INSERT deletion_logs (immutable, type="full"|"anonymization", legal_basis="user_request")

  // Art 5(1)(e): Retention
  purge_expired_data(days=730): DELETE activity_logs older than cutoff

  // Anonymization: email->anon_{sha256[:8]}@anonymized.local, IP->zero last octet
```

### 6.6 Production Hardening

Swagger/ReDoc disabled. `.env.test` gitignored. JWT secret validated. HSTS enabled. API no-cache. Container resource limits. Read-only config mounts. Structured JSON logging.

## 7. Deployment

**Render** (free plan): `electricity-optimizer-api` (Docker, /health check) and `electricity-optimizer-frontend` (Docker). Keepalive workflow pings every 14 min.

```
PSEUDOCODE db_connection_strategy:
  DatabaseManager.initialize():
    1. Supabase client (optional, skip in dev if unconfigured)
    2. Primary DB: DATABASE_URL > TIMESCALEDB_URL priority
       Neon: ssl=require, strip sslmode/channel_binding, SQLAlchemy only (no asyncpg pool)
       TimescaleDB: asyncpg pool min=1/max=5 + SQLAlchemy engine pool_size=2/overflow=3
    3. Redis: aioredis from_url, max_connections=10
    Production: raise on any init failure. Dev: warn and continue.
```

**Key env vars** (35 total): DATABASE_URL, REDIS_URL, JWT_SECRET, INTERNAL_API_KEY (all required prod). STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET (required for billing). CORS_ORIGINS (required prod). GRAFANA_PASSWORD (required). DATA_RETENTION_DAYS=730, RATE_LIMIT_PER_MINUTE=100, RATE_LIMIT_PER_HOUR=1000 (defaults). See `.env.example` for full list.

## 8. TDD Anchors

```
PSEUDOCODE test_anchors:

  -- MIGRATIONS --
  TEST "init_neon creates 7 tables": execute SQL -> verify all tables + triggers exist
  TEST "002 adds auth tables": execute -> auth_sessions, login_attempts, activity_logs exist
  TEST "003 reconciles schema": run on init_neon-only DB -> metadata_json, deleted_at,
    data_categories_deleted(JSONB), deletion_type NOT NULL backfilled, FK added
  TEST "003 is idempotent": run twice -> no errors
  TEST "deletion_logs immutability": UPDATE/DELETE -> raises exception

  -- GDPR --
  TEST "record_consent persists audit record": consent_given=TRUE, withdrawal_timestamp=NULL
  TEST "withdraw sets timestamp": consent_given=FALSE, withdrawal_timestamp set
  TEST "withdraw_all covers all purposes": 6 withdrawal records, bulk_withdrawal=true
  TEST "export includes all categories": profile, preferences, consents, alerts, logs
  TEST "export raises UserNotFoundError for missing user"
  TEST "delete removes all data + creates immutable deletion_log"
  TEST "delete with anonymize=TRUE retains anonymized logs, type=anonymization"
  TEST "purge_expired deletes only old activity_logs"

  -- AUTH --
  TEST "login returns JWT + creates auth_session": status 200, token_hash in DB
  TEST "wrong password returns 401 + records failed attempt"
  TEST "5 failures locks account": status 429, Retry-After header
  TEST "successful login clears lockout counter"
  TEST "weak JWT_SECRET in production raises ValueError"
  TEST "dev defaults allowed in development"

  -- RATE LIMITING --
  TEST "under limit allowed": 50 requests -> all 200, X-RateLimit-Remaining decreases
  TEST "over per-minute limit rejected": 101st -> 429, Retry-After=60
  TEST "over per-hour limit rejected": 1001st -> 429, Retry-After=3600
  TEST "/health bypasses rate limiting": 200 requests -> all 200
  TEST "different tokens get separate buckets"
  TEST "in-memory fallback works without Redis"

  -- SECURITY HEADERS --
  TEST "all responses include X-Frame-Options, X-Content-Type-Options, CSP, etc."
  TEST "HSTS only in production"
  TEST "API paths set Cache-Control no-store"
  TEST "non-API paths omit no-cache"
```

## Appendix: Source Files

| Section       | Files |
|---------------|-------|
| Infra         | `docker-compose.yml`, `docker-compose.prod.yml` |
| Schema        | `backend/migrations/init_neon.sql`, `002_gdpr_auth_tables.sql`, `003_reconcile_schema.sql` |
| DB Manager    | `backend/config/database.py` |
| Settings      | `backend/config/settings.py` |
| GDPR          | `backend/compliance/gdpr.py`, `backend/compliance/repositories.py` |
| Security      | `backend/middleware/security_headers.py`, `backend/middleware/rate_limiter.py` |
| Monitoring    | `monitoring/prometheus.yml`, `monitoring/alerts.yml`, `monitoring/grafana/` |
| CI/CD         | `.github/workflows/*.yml` (12 files) |
| Deploy        | `render.yaml`, `.env.example`, `backend/.env.example` |
