# Backend Codemap

> Auto-generated: 2026-02-10

## Directory Structure

```
backend/
├── main.py                          # FastAPI app entry point
├── config/
│   ├── settings.py                  # Pydantic-settings config (env vars)
│   └── database.py                  # DB sessions (TimescaleDB, Redis)
├── api/v1/
│   ├── prices.py                    # Price endpoints (GET/POST /prices, /refresh)
│   ├── suppliers.py                 # Supplier comparison endpoints
│   ├── beta.py                      # Beta signup + welcome email
│   └── ...
├── routers/
│   └── predictions.py               # ML prediction endpoints (/predict/price, /model-info)
├── models/
│   └── price.py                     # Pydantic models (Price, PriceRegion, PriceForecast)
├── repositories/
│   └── price_repository.py          # DB CRUD (bulk_create, get_by_region)
├── services/
│   └── email_service.py             # Email sending (SendGrid + SMTP fallback)
├── integrations/pricing_apis/
│   ├── base.py                      # PricingRegion enum, PriceData, APIError
│   ├── service.py                   # PricingService (unified multi-API interface)
│   ├── nrel.py                      # NREL client (US regions, CT→ZIP 06510)
│   ├── flatpeak.py                  # Flatpeak client (UK/EU regions)
│   ├── iea.py                       # IEA client (global fallback)
│   ├── cache.py                     # PricingCache
│   ├── rate_limiter.py              # RateLimiter
│   └── __init__.py                  # create_pricing_service_from_settings()
├── templates/emails/
│   └── welcome_beta.html            # Jinja2 HTML email template
├── tests/
│   ├── conftest.py                  # Shared fixtures
│   ├── test_models.py               # Price model tests
│   ├── test_services.py             # Service layer tests
│   ├── test_repositories.py         # Repository tests
│   └── test_integrations.py         # API integration tests
└── requirements.txt                 # Python deps (sendgrid, aiosmtplib, jinja2)
```

## Key Integration Points

### POST /api/v1/prices/refresh (prices.py)
- **Requires `X-API-Key` header** (authenticated via `verify_api_key` dependency)
- Calls `create_pricing_service_from_settings()` → `PricingService`
- Fetches prices via `compare_prices()` for 6 regions: US_CT, US_CA, US_NY, UK, GERMANY, FRANCE
- Converts `PriceData` → `Price` model via region_map
- Bulk inserts via `price_repository.bulk_create()`
- Handles `APIError`, `RateLimitError` with structured logging

### POST /api/v1/ml/predict/price (predictions.py)
- `_load_model()` tries EnsemblePredictor → PricePredictor → None
- Cached in `_model_cache` dict (avoids reload per request)
- Falls back to `_simulate_forecast()` if no model found
- Writes `model:last_updated` to Redis after successful inference

### GET /api/v1/ml/predict/model-info (predictions.py)
- Reads `model:last_updated` from Redis
- Falls back to current UTC time if key not found

### POST /api/v1/beta/signup (beta.py)
- Creates beta signup record
- Calls `EmailService.render_template("welcome_beta.html")`
- Calls `EmailService.send()` (SendGrid → SMTP → log warning)
- Never crashes signup flow on email failure

## Region Routing

### PricingRegion (base.py) → PriceRegion (models/price.py)
Two separate enums for different layers:

| PricingRegion (API layer) | PriceRegion (DB layer) | Routing |
|---------------------------|------------------------|---------|
| US_CT                     | us_ct                  | NREL    |
| US_CA                     | us_ca                  | NREL    |
| US_NY                     | us_ny                  | NREL    |
| UK                        | uk                     | Flatpeak|
| GERMANY                   | germany                | Flatpeak|
| FRANCE                    | france                 | Flatpeak|

### PricingService._get_primary_client() routing:
- EU regions → Flatpeak (primary) → IEA (fallback)
- US regions (incl. US_CT) → NREL (primary) → IEA (fallback)
- Other → IEA

## Configuration (settings.py)

### Email Settings
| Setting | Env Var | Default |
|---------|---------|---------|
| sendgrid_api_key | SENDGRID_API_KEY | None |
| smtp_host | SMTP_HOST | None |
| smtp_port | SMTP_PORT | 587 |
| smtp_username | SMTP_USERNAME | None |
| smtp_password | SMTP_PASSWORD | None |
| email_from_address | EMAIL_FROM_ADDRESS | noreply@electricity-optimizer.app |
| email_from_name | EMAIL_FROM_NAME | Electricity Optimizer |

### ML Settings
| Setting | Env Var | Default |
|---------|---------|---------|
| model_path | MODEL_PATH | None |
| model_forecast_hours | MODEL_FORECAST_HOURS | 24 |

## Test Commands
```bash
# Run all backend tests (use venv)
.venv/bin/python -m pytest backend/tests/ -v

# Frontend tests
cd frontend && npx jest
```

**Test status:** 293 passing, 0 regressions from 2026-02-10 changes.
