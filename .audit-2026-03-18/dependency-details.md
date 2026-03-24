# RateShift Dependency Audit — Technical Details

**Date**: 2026-03-18
**Scope**: Detailed package analysis, version mappings, and implementation notes

---

## Python Backend Dependencies (Complete Manifest)

### Production Dependencies (`backend/requirements.txt`)

#### Web Framework & ASGI
```
fastapi>=0.115.0                              # Modern async web framework (v115, Jan 2025)
uvicorn[standard]==0.42.0                     # ASGI server with performance extras
pydantic==2.12.5                              # Data validation + serialization (v2 required)
pydantic-settings==2.13.1                     # Settings management from environment
```

**Rationale**:
- FastAPI ≥0.115 required for middleware fixes
- Uvicorn pinned for reproducibility (production critical)
- Pydantic v2 mandatory (major API changes from v1)

#### Database
```
asyncpg==0.31.0                               # PostgreSQL async driver (native binary)
sqlalchemy[asyncio]==2.0.48                   # ORM with async support
redis[hiredis]>=7.0,<8.0                      # Cache + rate limiting backend
```

**Implementation Notes**:
- `asyncpg` pinned to avoid connection pool behavior changes
- `sqlalchemy[asyncio]` required for `AsyncSession`
- Redis v7+ for performance (skip v5)
- `hiredis` extra for C-based parsing (10x faster)

#### HTTP Client
```
httpx>=0.26,<0.29                             # Async HTTP client (modern constraint)
```

**Use Cases**:
- EIA, NREL, weather API calls
- Geocoding services (OpenWeatherMap + Nominatim)
- Utility API integrations
- Diffbot rate extraction

#### Authentication & Security
```
PyJWT[crypto]>=2.8,<3.0                       # JWT tokens with cryptography backend
python-multipart>=0.0.18                      # File upload parsing for bill PDFs
bcrypt==4.1.2                                 # Password hashing (pinned for reproducibility)
```

**Security Notes**:
- `PyJWT[crypto]` enables RS256/ES256 signatures
- `bcrypt==4.1.2` latest stable, no known vulnerabilities
- Paired with `cryptography==46.0.5` (transitive)

#### Configuration
```
python-dotenv==1.0.0                          # .env file parsing
```

#### Data Validation & Serialization
```
email-validator==2.3.0                        # RFC 5321 compliance
python-dateutil==2.9.0.post0                  # Timezone-aware datetime handling
```

#### Monitoring & Logging
```
prometheus-client==0.24.1                     # Metrics export (Grafana Cloud)
sentry-sdk[fastapi]>=2.0,<3.0                 # Error tracking + session replay
structlog==25.5.0                             # Structured logging (JSON output)
```

**Integration Notes**:
- `sentry-sdk[fastapi]` auto-instruments FastAPI
- Structlog configured for Grafana Loki
- Prometheus metrics on `/metrics` endpoint

#### OpenTelemetry (Optional, OTEL_ENABLED=true)
```
opentelemetry-api>=1.20.0,<2.0                # Tracing API
opentelemetry-sdk>=1.20.0,<2.0                # Tracing SDK
opentelemetry-instrumentation-fastapi>=0.41b0 # FastAPI spans (BETA)
opentelemetry-instrumentation-sqlalchemy>=0.41b0  # SQL query spans (BETA)
opentelemetry-instrumentation-httpx>=0.41b0  # HTTP request spans (BETA)
opentelemetry-exporter-otlp-proto-http>=1.20.0,<2.0  # OTLP HTTP exporter
```

**Status**: BETA packages are acceptable (non-critical path, feature-gated)

#### Payments
```
stripe>=14.0,<15.0                            # Payment processing SDK (v14, Mar 2025)
```

**API Contract**: v14 corrects `error.error` namespace (tested in `test_stripe_service.py`)

#### Email
```
resend>=2.0,<3.0                              # Primary transactional email (faster)
aiosmtplib>=3.0,<4.0                          # Fallback Gmail SMTP
jinja2>=3.0                                   # Email template rendering
```

#### Machine Learning
```
numpy>=2.0,<3.0                               # Numerical computing (v2 compatible with pandas 2.2+)
pandas>=2.2,<3.0                              # Data manipulation
scikit-learn>=1.5.0                           # ML algorithms (tree, ensemble, preprocessing)
```

**Rationale**:
- NumPy v2 → pandas v2.2+ compatibility achieved post-2025
- scikit-learn ≥1.5 for latest estimators

#### Vector Search
```
hnswlib>=0.8.0                                # HNSW approximate nearest neighbor search
```

**Configuration**: Max 100K vectors per store (memory constraint for Python GIL)

#### Sanitization
```
nh3>=0.2.14                                   # XSS sanitization (Rust-based, replaces bleach)
```

**Why Not Bleach**:
- Bleach deprecated as of 2023
- nh3 is faster (Rust native code)
- Same API surface for drop-in replacement

#### AI Agent (Primary: Gemini, Fallback: Groq, Tools: Composio)
```
google-genai>=1.0.0                           # Gemini 2.5 Flash SDK (free tier 10 RPM/250 RPD)
composio-gemini>=0.7.0                        # Composio tool integration for Gemini
groq>=0.9.0                                   # Groq Llama 3.3 70B fallback (free tier)
```

**Architecture**:
- Primary: Gemini (cheaper, faster)
- Fallback: Groq on 429 rate limit
- Tools: 16 connected apps via Composio (gmail, github, firecrawl, sentry, stripe, etc.)
- Rate limits: Free=3/day, Pro=20/day, Business=unlimited
- SSE streaming: `POST /agent/query`
- Async jobs: `POST /agent/task`

---

### Development Dependencies (`backend/requirements-dev.txt`)

#### Testing
```
pytest==9.0.2                                 # Test framework (pinned for reproducibility)
pytest-cov==7.0.0                             # Coverage reporting
pytest-asyncio==1.3.0                         # AsyncIO test support
pytest-mock==3.15.1                           # Mocking fixtures
pytest-timeout==2.4.0                         # Test timeout enforcement
pytest-xdist==3.8.0                           # Parallel test execution
httpx>=0.26,<0.29                             # HTTP test utilities (same as prod)
faker==40.11.0                                # Fake data generation (users, dates, etc.)
factory-boy==3.3.3                            # Object factories for tests
freezegun==1.5.5                              # Time mocking
```

**Test Coverage**: 2,686 backend tests across 7 test files

#### Type Checking
```
mypy==1.19.1                                  # Static type checker
types-redis>=4.6.0.20241004                   # Redis type stubs
types-python-dateutil==2.9.0.20260305         # dateutil type stubs
```

#### Linting & Formatting
```
ruff==0.15.6                                  # Fast linter + formatter (replaces flake8 + isort)
black==26.3.1                                 # Code formatter (opinionated)
isort==8.0.1                                  # Import sorting
```

**CI Integration**:
- `ruff check --fix` auto-fixes linting errors
- Black formatting enforced on PR
- isort import order managed

#### Security Scanning
```
bandit==1.9.4                                 # Static security analyzer
safety>=3.0.0,<4.0.0                          # Dependency vulnerability scanner
```

#### Documentation
```
mkdocs==1.5.3                                 # Documentation generator
mkdocs-material==9.5.4                        # Material theme
mkdocstrings[python]==0.24.0                  # Docstring integration
```

#### Debugging
```
ipdb==0.13.13                                 # Enhanced debugger
rich==14.3.3                                  # Terminal formatting (logging)
```

#### Pre-commit Hooks
```
pre-commit==4.5.1                             # Git hooks framework
```

**Configuration**: `.pre-commit-config.yaml` with ruff + black + mypy

---

## Python ML Dependencies

### ML Core (`ml/requirements.txt`) — Baseline

```
numpy>=1.24.0, pandas>=2.0.0, scipy>=1.10.0, scikit-learn>=1.3.0
tensorflow>=2.13.0, keras>=2.13.0
xgboost>=1.7.0, lightgbm>=4.0.0
pulp>=2.7.0 (optimization)
statsmodels>=0.14.0, prophet>=1.1.4 (time series)
transformers>=4.30.0, torch>=2.0.0 (sentiment analysis)
holidays>=0.40 (calendar data)
matplotlib, seaborn, plotly (visualization)
tqdm>=4.65.0, joblib>=1.3.0 (utilities)
```

### ML Pinned (`ml/requirements-ml.txt`) — Production

```
tensorflow>=2.15.0,<3.0                       # Deep learning (pinned major)
keras>=3.0.0                                  # Keras 3.0+ API
xgboost>=2.0.3                                # Gradient boosting
lightgbm>=4.3.0                               # LightGBM
optuna>=3.5.0                                 # Hyperparameter tuning
numpy>=1.26.0                                 # Numerical (not <2.0)
pandas>=2.1.0                                 # Data manipulation
scikit-learn>=1.4.0                           # ML algorithms
statsmodels>=0.14.0, prophet>=1.1.5           # Time series
category-encoders>=2.6.0                      # Feature encoding
shap>=0.43.0, lime>=0.2.0                     # Model interpretation
mlflow>=2.9.0, wandb>=0.16.0                  # Experiment tracking
```

### Root ML (`requirements-ml.txt`) — Locked Constraints

```
tensorflow>=2.15.0,<2.17.0                    # Constrain major.minor
keras>=3.0.0                                  # Locked to 3.0+ for new API
numpy>=1.24.0,<2.0.0                          # Prevents 2.x (different from backend!)
pandas>=2.0.0                                 # Broad range
xgboost>=2.0.0                                # v2+
lightgbm>=4.2.0
scikit-learn>=1.3.0
```

**Issue**: NumPy v1 vs v2 conflict across codebases (resolvable, low impact)

---

## JavaScript Frontend Dependencies

### Production (`frontend/package.json`)

```json
{
  "@microsoft/fetch-event-source": "^2.0.1",     // SSE client
  "@neondatabase/serverless": "^1.0.2",          // Neon pooled connection
  "@tanstack/react-query": "^5.90.21",           // Server state management
  "@testing-library/dom": "^10.4.1",             // DOM testing
  "better-auth": "^1.5.5",                       // OAuth/session auth (v1.5.5 recent fix)
  "clsx": "^2.1.0",                              // Classname utility
  "date-fns": "^4.1.0",                          // Date utilities
  "lucide-react": "^0.577.0",                    // Icon library
  "next": "^16.0.7",                             // React framework
  "nodemailer": "^8.0.2",                        // Email SMTP fallback
  "react": "^19.0.0",                            // UI library
  "react-dom": "^19.0.0",                        // DOM renderer
  "react-onesignal": "^3.5.1",                   // Push notifications
  "recharts": "^3.8.0",                          // Chart library
  "resend": "^6.9.4",                            // Email SDK
  "tailwind-merge": "^3.5.0",                    // Tailwind conflict resolver
  "zustand": "^5.0.12"                           // Client state (auth, UI)
}
```

**Notable Versions**:
- `better-auth@1.5.5`: Scrypt password regen, signOut full-page reload fix
- `recharts@3.x`: TypeScript support, new chart types
- `zustand@5.x`: Latest API with middleware support
- `date-fns@4.x`: Small bundle size improvements

### Development (`frontend/package.json`)

```json
{
  "@axe-core/playwright": "^4.11.1",             // A11y testing
  "@excalidraw/excalidraw": "^0.18.0",           // Whiteboard component
  "@playwright/test": "^1.40.1",                 // E2E browser testing
  "@testing-library/jest-dom": "^6.9.1",         // Jest matchers
  "@testing-library/react": "^16.3.2",           // React testing utilities
  "@testing-library/user-event": "^14.6.1",      // User interaction simulation
  "@types/*": "Latest",                          // TypeScript definitions
  "autoprefixer": "^10.4.27",                    // CSS prefix tool
  "eslint": "^8.56.0",                           // Linter (v8, v10 deferred)
  "eslint-config-next": "^16.0.7",               // Next.js ESLint config
  "husky": "^9.1.7",                             // Git hooks
  "jest": "^30.3.0",                             // Unit testing
  "jest-environment-jsdom": "^30.3.0",           // DOM environment for Jest
  "jest-axe": "^10.0.0",                         // A11y assertions
  "lint-staged": "^16.4.0",                      // Pre-commit linting
  "openapi-typescript": "^7.13.0",               // API type generation
  "postcss": "^8.5.8",                           // CSS processing
  "prettier": "^3.8.1",                          // Code formatter
  "tailwindcss": "^3.4.1",                       // Utility CSS
  "typescript": "^5.3.3",                        // Type checker
  "wrangler": "^4.75.0"                          // Cloudflare Worker CLI
}
```

**Testing Stack**:
- Jest 30.3 + jest-environment-jsdom 30.3 (2026-03 versions)
- Playwright 1.40.1 (E2E on 5 browsers)
- Accessibility: axe-core + jest-axe

### .npmrc Configuration

```
legacy-peer-deps=true
```

**Why**: ESLint 8 + Next.js 16 have peer dependency conflict
- ESLint 8 expects certain plugin versions
- Next.js 16 pulls newer versions
- Override allows both to coexist
- **Plan**: Defer ESLint v10 migration (requires significant reconfig)

---

## Cloudflare Worker Dependencies

### `workers/api-gateway/package.json`

```json
{
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20260301.0",   // CF runtime types
    "typescript": "^5.7.0",                          // Type checking
    "vitest": "^2.1.0",                              // Unit testing
    "wrangler": "^3.99.0"                            // Local dev + deploy
  }
}
```

**No Production Dependencies**: CF Workers are edge-only (uses native APIs)

**Test Coverage**: 90 tests (vitest)

---

## Load Testing Dependencies

### `tests/load/requirements.txt`

```
locust>=2.20.0                                 # Load testing framework
aiohttp>=3.9.0                                 # Async HTTP client for load tests
httpx>=0.25.0                                  # Additional HTTP utilities
psutil>=5.9.0                                  # Process/system metrics
```

**Usage**: Stress testing endpoints under concurrent load
- Available via `locust -f tests/load/locustfile.py` (if defined)

---

## Dependency Conflict Resolution

### Frontend Legacy Peer Deps Workaround

**Problem**: ESLint 8 + Next.js 16 incompatible peer deps
```
ESLint 8 expects: @typescript-eslint/eslint-plugin@^4
Next.js 16 includes: @typescript-eslint/eslint-plugin@^8
```

**Solution**: `legacy-peer-deps=true` in `.npmrc`
```bash
npm install --legacy-peer-deps
```

**Impact**: NONE (both plugins compatible at runtime)

**Future Plan**:
1. ESLint v10 → allows v5+ of typescript-eslint
2. Remove `legacy-peer-deps=true`
3. Estimated 2026-Q2

---

## Security-Sensitive Package Details

### JWT Handling
```
PyJWT[crypto]>=2.8,<3.0
├─ cryptography==46.0.5
├─ Supports RS256 (RSA signatures) for OAuth
├─ Uses HMAC with configurable hash
└─ No known vulnerabilities (2026-03)
```

### Password Hashing
```
bcrypt==4.1.2
├─ Pinned for reproducibility
├─ Cost factor: 12 (standard, ~100ms per hash)
├─ No known CVEs
└─ Replaces plaintext storage (enforced since 2024)
```

### HTTP Client Security
```
httpx>=0.26,<0.29
├─ Transitive: cryptography==46.0.5
├─ TLS certificate validation: ENABLED
├─ Follows redirects: DISABLED for SSRF protection
├─ Connection pooling: Optional per request
└─ Used for: EIA, NREL, geocoding, utility APIs
```

### Stripe Integration
```
stripe>=14.0,<15.0
├─ API version: 2025-01-27 (pinned by SDK)
├─ Signature verification: HMAC-SHA256
├─ Error namespace: error.error (v14 correctness)
├─ Webhook processing: Async queue
├─ Payment states: Validated per spec
└─ No exposed secrets in code (via 1Password)
```

### Database Connections
```
asyncpg==0.31.0
├─ TLS: ENABLED in production (Neon pooled endpoint)
├─ Connection pooling: 10 default
├─ Statement caching: 100 default
├─ Type support: UUID, JSON, ARRAY native
└─ Protection: SQL injection prevention via parameterized queries

redis[hiredis]>=7.0,<8.0
├─ Authentication: REDIS_URL includes password
├─ TLS: ENABLED in production (Neon KV)
├─ Keyspace isolation: PREFIX-based namespacing
├─ Rate limiting: Atomic Lua scripts with TTL
└─ Data: Session tokens, rate limit counters only
```

---

## Build & Deployment Integration

### Backend Deployment (Render)

1. **Runtime**: Python 3.12
2. **Build Process**:
   ```bash
   pip install -r backend/requirements.txt
   alembic upgrade head  # Run migrations
   gunicorn backend.main:app --workers=4 --timeout=120
   ```
3. **Environment Vars**: 42 total (Stripe keys, API keys, feature flags, etc.)
4. **Health Check**: `GET /health` (built-in endpoint)

### Frontend Deployment (Vercel)

1. **Build Command**: `next build`
2. **Runtime**: Node.js 18+ (Vercel managed)
3. **Dependencies**: Installed via `npm ci --legacy-peer-deps`
4. **ISR**: Price data refreshed every 3600s
5. **Environment Vars**: API URLs proxied to backend via `/api/v1/*`

### Worker Deployment (Cloudflare)

1. **Build**: `npm run build` (TypeScript compilation)
2. **Deploy**: `wrangler deploy`
3. **Runtime**: V8 isolate (no Node.js)
4. **Environment**: Secrets via 1Password API
5. **Cron Triggers**: 3 active (check-alerts/3h, stats-reset/daily, cache-purge/weekly)

---

## Dependency Scanning & Monitoring

### Automated Scanning

| Tool | Frequency | Threshold | Action |
|------|-----------|-----------|--------|
| `pip-audit` | CI (every PR) | MEDIUM+ | Block merge |
| `safety` | CI (every PR) | HIGH+ | Block merge |
| `npm audit` | CI (every PR) | HIGH+ | Block merge |
| `OWASP ZAP` | Weekly Sunday 4am | Baseline | File issue |
| Dependabot | Weekly Monday | Any | Auto-PR |

### Lock File Generation

**Backend** (Python):
```bash
cd backend
.venv/bin/pip install --upgrade -r requirements.txt
.venv/bin/pip freeze > requirements.lock
git add requirements.lock
```

**Frontend** (JavaScript):
```bash
cd frontend
npm install
git add package-lock.json
```

---

## Known Constraints & Workarounds

| Constraint | Reason | Workaround |
|-----------|--------|-----------|
| `legacy-peer-deps=true` | ESLint 8 + Next 16 | Remove on ESLint v10 |
| NumPy v1 in `requirements-ml.txt` | Legacy ML code | Migrate to v2 constraints |
| Redis v5 in `requirements.lock` | Stale lock | Regenerate lock file |
| Stripe v7 in `requirements.lock` | Stale lock | Regenerate lock file |
| `opentelemetry-*>=0.41b0` | Beta packages | Monitor for stable release |
| ML dependency fragmentation | 3 separate files | Consolidate to single source |

---

## Transitive Dependency Tree (Critical Path)

```
fastapi==0.115.0
├─ starlette==0.35.1
├─ pydantic==2.12.5
│  └─ pydantic-core==2.14.6
├─ typing-extensions>=4.0
└─ requests==2.32.5 (optional)

sqlalchemy[asyncio]==2.0.48
├─ greenlet>=3.0 (async marker)
├─ typing-extensions>=4.0
└─ sqlalchemy-util (optional)

asyncpg==0.31.0
├─ No external deps (compiled C extension)

redis[hiredis]>=7.0,<8.0
├─ hiredis==3.3.0 (C extension for parsing)

stripe>=14.0,<15.0
├─ requests==2.32.5
├─ cryptography>=0.12
└─ typing-extensions>=3.7.4

sentry-sdk[fastapi]>=2.0,<3.0
├─ certifi>=2021.10.8
├─ urllib3>=1.26.0
└─ cryptography>=1.5 (optional)

google-genai>=1.0.0
├─ httpx>=0.26
├─ pydantic>=1.7
└─ typing-extensions (optional)

groq>=0.9.0
├─ httpx>=0.26
├─ pydantic>=1.7
└─ typing-extensions (optional)

composio-gemini>=0.7.0
├─ google-genai
├─ anthropic (optional)
└─ External service clients (slack, github, etc.)
```

---

## Version Pinning Strategy

### Production (Pinned)
```
uvicorn[standard]==0.42.0                     # Exact version
pydantic==2.12.5                              # Exact version
bcrypt==4.1.2                                 # Exact version
asyncpg==0.31.0                               # Exact version
sqlalchemy[asyncio]==2.0.48                   # Exact version
```

**Rationale**: Critical infrastructure — reproducible deployments

### Production (Range Constrained)
```
fastapi>=0.115.0                              # Minimum version (minor bumps OK)
sentry-sdk[fastapi]>=2.0,<3.0                 # Major version pinned
stripe>=14.0,<15.0                            # Major version pinned
redis[hiredis]>=7.0,<8.0                      # Major version pinned
```

**Rationale**: API stability within major version

### Development (Loose)
```
pytest==9.0.2                                 # Pinned (reproducible tests)
ruff==0.15.6                                  # Pinned (stable linting)
mkdocs>=1.5.3                                 # Loose (docs non-critical)
safety>=3.0.0,<4.0.0                          # Loose (scanner updates OK)
```

**Rationale**: Dev tools stable, scanning tools can update

---

## Conclusion

RateShift's dependency management is **production-grade** with:
- Strategic pinning of critical packages
- Clear separation of concerns (dev vs prod vs ML)
- Comprehensive security scanning
- Modern package versions
- Proper handling of deprecations

The single action item is **lock file regeneration** for consistency (non-blocking).

