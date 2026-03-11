# RateShift API Reference

**Base URL**: `https://api.rateshift.app/api/v1`
**Version**: 1.0
**Last Updated**: 2026-03-11

## Overview

The RateShift API provides programmatic access to electricity price data, supplier information, billing, alerts, recommendations, and AI agent capabilities. All endpoints return JSON unless noted.

### Authentication

- **Session-based**: Standard endpoints use `better-auth.session_token` httpOnly cookie (automatically set by Neon Auth)
- **Internal endpoints**: Require `X-API-Key` header; excluded from the 30-second request timeout
- **Public endpoints**: Some endpoints (e.g., supplier registry) are unauthenticated

### Rate Limiting

Enforced by Cloudflare Worker at `api.rateshift.app`:
- **Standard tier**: 120 requests/minute
- **Strict tier**: 30 requests/minute (some endpoints)
- **Internal tier**: 600 requests/minute (requires X-API-Key)

Agent endpoints have **per-user daily limits by subscription tier**:
- Free: 3 queries/day
- Pro: 20 queries/day
- Business: unlimited

### Response Format

Successful responses use status code 200 unless noted. Errors return standard JSON:

```json
{
  "detail": "Error message"
}
```

Validation errors (400/422) include detailed field information:

```json
{
  "detail": [
    {
      "type": "field_required",
      "loc": ["body", "region"],
      "msg": "Field required"
    }
  ]
}
```

---

## Prices Endpoints

### GET /prices/current

Get current electricity prices for a region.

**Query Parameters:**
- `region` (required): PriceRegion code (e.g., `uk`, `germany`, or US state like `us_ct`)
- `supplier` (optional): Filter by specific supplier name
- `limit` (optional): Max results (1–100, default 10)

**Response:**
```json
{
  "price": {
    "ticker": "ELEC-UK",
    "current_price": 0.2845,
    "currency": "USD",
    "region": "uk",
    "supplier": "Eversource Energy",
    "updated_at": "2026-03-11T14:30:00Z",
    "is_peak": true,
    "carbon_intensity": 185.5
  },
  "prices": null,
  "region": "uk",
  "timestamp": "2026-03-11T14:30:15Z",
  "source": "live"
}
```

**Error Codes:**
- `404`: No price found for supplier
- `422`: Invalid region parameter

---

### GET /prices/history

Get historical electricity prices with pagination.

**Query Parameters:**
- `region` (required): Price region
- `days` (optional): Number of days of history (1–365, default 7)
- `supplier` (optional): Filter by supplier name
- `start_date` (optional): ISO 8601 start date (inclusive)
- `end_date` (optional): ISO 8601 end date (inclusive)
- `page` (optional): Page number (1-based, default 1)
- `page_size` (optional): Records per page (1–100, default 24 = 1 day hourly)

**Response:**
```json
{
  "region": "uk",
  "supplier": null,
  "start_date": "2026-03-04T00:00:00Z",
  "end_date": "2026-03-11T00:00:00Z",
  "prices": [
    {
      "region": "uk",
      "supplier": "Eversource Energy",
      "price_per_kwh": 0.2600,
      "timestamp": "2026-03-10T23:00:00Z",
      "currency": "USD",
      "is_peak": false,
      "carbon_intensity": 165.2
    }
  ],
  "average_price": 0.2717,
  "min_price": 0.2400,
  "max_price": 0.3200,
  "source": "live",
  "total": 168,
  "page": 1,
  "page_size": 24,
  "pages": 7
}
```

**Notes:**
- `start_date`/`end_date` take priority over `days` parameter
- Both dates default to UTC if no timezone is provided
- `start_date` must be before `end_date`

---

### GET /prices/forecast

Get electricity price forecast (Pro+ tier required).

**Authentication**: Required (Pro tier minimum)

**Query Parameters:**
- `region` (required): Price region
- `hours` (optional): Forecast horizon in hours (1–168, default 24)
- `supplier` (optional): Filter by supplier

**Response:**
```json
{
  "region": "uk",
  "forecast": {
    "region": "uk",
    "generated_at": "2026-03-11T14:30:00Z",
    "horizon_hours": 24,
    "prices": [
      {
        "region": "uk",
        "supplier": "Eversource Energy",
        "price_per_kwh": 0.2750,
        "timestamp": "2026-03-11T15:00:00Z",
        "currency": "USD",
        "is_peak": true,
        "carbon_intensity": 192.1
      }
    ],
    "confidence": 0.87,
    "model_version": "v2.1.0"
  },
  "generated_at": "2026-03-11T14:30:00Z",
  "horizon_hours": 24,
  "confidence": 0.87,
  "source": "live"
}
```

**Error Codes:**
- `404`: No forecast available for region

---

### GET /prices/compare

Compare supplier prices in a region.

**Query Parameters:**
- `region` (required): Price region

**Response:**
```json
{
  "region": "uk",
  "timestamp": "2026-03-11T14:30:15Z",
  "suppliers": [
    {
      "ticker": "ELEC-UK",
      "current_price": 0.2400,
      "currency": "USD",
      "region": "uk",
      "supplier": "Eversource Energy",
      "updated_at": "2026-03-11T14:30:00Z",
      "is_peak": true,
      "carbon_intensity": 180.0
    }
  ],
  "cheapest_supplier": "Eversource Energy",
  "cheapest_price": 0.2400,
  "average_price": 0.2717,
  "source": "live"
}
```

---

### POST /prices/refresh

Trigger price data refresh (internal use).

**Authentication**: Required (X-API-Key header)

**Request**: Empty body

**Response:**
```json
{
  "message": "Price sync triggered successfully",
  "records_synced": 127
}
```

**Notes:**
- Called by GitHub Actions price-sync workflow every 6 hours
- Internal endpoint; excluded from 30-second timeout

---

## Suppliers Endpoints

### GET /suppliers

List energy suppliers with optional filtering.

**Query Parameters:**
- `region` (optional): Filter by region code (e.g., `us_ct`, `us_ma`)
- `utility_type` (optional): Filter by type (`electricity`, `natural_gas`, `heating_oil`, `propane`, `community_solar`)
- `green_only` (optional): Filter for green energy providers (default false)
- `page` (optional): Page number (default 1)
- `page_size` (optional): Items per page (1–100, default 20)

**Response:**
```json
{
  "suppliers": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Eversource Energy",
      "regions": ["us_ct", "us_ma", "us_nh"],
      "utility_types": ["electricity"],
      "api_available": true,
      "rating": 4.2,
      "review_count": 1254,
      "is_active": true
    }
  ],
  "total": 127,
  "page": 1,
  "page_size": 20,
  "region": null,
  "utility_type": null
}
```

**Notes:**
- Results cached in Redis for 1 hour

---

### GET /suppliers/registry

List suppliers with API integration available.

**Query Parameters:**
- `region` (optional): Filter by region
- `utility_type` (optional): Filter by utility type

**Response:**
```json
{
  "suppliers": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Eversource Energy",
      "region": "us_ct",
      "utility_type": "electricity"
    }
  ]
}
```

**Notes:**
- Used by DirectLoginForm dropdown to show connectable providers
- Returns only suppliers with `api_available=true`

---

### GET /suppliers/{supplier_id}

Get detailed information about a supplier.

**Path Parameters:**
- `supplier_id` (required): UUID of the supplier

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "name": "Eversource Energy",
  "regions": ["us_ct", "us_ma", "us_nh"],
  "tariff_types": ["fixed", "variable", "time_of_use"],
  "api_available": true,
  "rating": 4.2,
  "review_count": 1254,
  "green_energy_provider": true,
  "carbon_neutral": true,
  "is_active": true
}
```

**Error Codes:**
- `404`: Supplier not found

---

### GET /suppliers/{supplier_id}/tariffs

Get tariffs offered by a supplier.

**Path Parameters:**
- `supplier_id` (required): UUID of the supplier

**Query Parameters:**
- `utility_type` (optional): Filter by utility type
- `available_only` (optional): Show only available tariffs (default true)

**Response:**
```json
{
  "supplier_id": "550e8400-e29b-41d4-a716-446655440001",
  "supplier_name": "Eversource Energy",
  "tariffs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "supplier_id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Standard Variable",
      "type": "variable",
      "unit_rate": 0.2500,
      "standing_charge": 0.4000,
      "green_energy_percentage": 0,
      "contract_length": "rolling",
      "is_available": true
    }
  ],
  "total": 5
}
```

---

### GET /suppliers/region/{region}

Get all suppliers available in a region.

**Path Parameters:**
- `region` (required): Region code (e.g., `us_ct`, `us_ma`)

**Query Parameters:**
- `utility_type` (optional): Filter by utility type
- `green_only` (optional): Filter for green providers

**Response**: Same as `GET /suppliers`

---

### GET /suppliers/compare/{region}

Compare suppliers in a region with their best tariff prices.

**Path Parameters:**
- `region` (required): Region code

**Query Parameters:**
- `utility_type` (optional): Utility type to compare (default `electricity`)
- `tariff_type` (optional): Filter by tariff type

**Response:**
```json
{
  "region": "us_ct",
  "utility_type": "electricity",
  "suppliers": [
    {
      "supplier_id": "550e8400-e29b-41d4-a716-446655440001",
      "supplier_name": "Eversource Energy",
      "utility_types": ["electricity"],
      "cheapest_tariff": "Standard Variable",
      "unit_rate": "0.25",
      "standing_charge": "0.40",
      "rating": 4.2,
      "green_energy_provider": true
    }
  ],
  "total": 5,
  "generated_at": "2026-03-11T14:30:15Z"
}
```

---

## Alerts Endpoints

All require authentication.

### GET /alerts

List all price alert configurations for the current user.

**Response:**
```json
{
  "alerts": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": "user-uuid",
      "region": "us_ct",
      "price_below": 0.22,
      "price_above": 0.35,
      "notify_optimal_windows": true,
      "is_active": true,
      "created_at": "2026-03-10T10:00:00Z",
      "updated_at": "2026-03-11T14:30:00Z"
    }
  ],
  "total": 1
}
```

---

### POST /alerts

Create a new price alert configuration.

**Authentication**: Required

**Request Body:**
```json
{
  "region": "us_ct",
  "currency": "USD",
  "price_below": 0.22,
  "price_above": 0.35,
  "notify_optimal_windows": true
}
```

**Response**: Alert object (same as GET /alerts item)

**Validation:**
- At least one of `price_below`, `price_above`, or `notify_optimal_windows` must be specified
- Free tier users limited to 1 alert; Pro/Business unlimited

**Error Codes:**
- `403`: Free tier alert limit reached
- `422`: Invalid parameters or missing condition

---

### GET /alerts/history

Get paginated alert trigger history.

**Query Parameters:**
- `page` (optional): Page number (default 1)
- `page_size` (optional): Records per page (1–100, default 20)

**Response:**
```json
{
  "items": [
    {
      "id": "trigger-uuid",
      "alert_id": "alert-uuid",
      "triggered_at": "2026-03-11T14:15:00Z",
      "price": 0.2150,
      "condition_met": "price_below",
      "delivery_status": "sent"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "pages": 3
}
```

---

### PUT /alerts/{alert_id}

Update a price alert configuration.

**Path Parameters:**
- `alert_id` (required): Alert UUID

**Request Body**: UpdateAlertRequest (all fields optional)
```json
{
  "region": "us_ma",
  "price_below": 0.20,
  "is_active": false
}
```

**Response**: Updated alert object

**Error Codes:**
- `404`: Alert not found

---

### DELETE /alerts/{alert_id}

Delete a price alert configuration.

**Path Parameters:**
- `alert_id` (required): Alert UUID

**Response:**
```json
{
  "deleted": true,
  "alert_id": "alert-uuid"
}
```

---

## Billing Endpoints

All require authentication.

### POST /billing/checkout

Create a Stripe Checkout session for subscription.

**Request Body:**
```json
{
  "tier": "pro",
  "success_url": "https://rateshift.app/dashboard?checkout=success",
  "cancel_url": "https://rateshift.app/pricing"
}
```

**Response:**
```json
{
  "session_id": "cs_live_...",
  "checkout_url": "https://checkout.stripe.com/pay/cs_live_..."
}
```

**Validation:**
- `tier` must be `pro` or `business`
- `success_url` and `cancel_url` must use allowed domains (e.g., `rateshift.app`)

**Error Codes:**
- `400`: Invalid tier or configuration
- `503`: Stripe not configured

---

### POST /billing/portal

Create a Stripe Customer Portal session for subscription management.

**Request Body:**
```json
{
  "return_url": "https://rateshift.app/settings"
}
```

**Response:**
```json
{
  "portal_url": "https://billing.stripe.com/..."
}
```

**Error Codes:**
- `400`: No active subscription found
- `503`: Stripe not configured

---

### GET /billing/subscription

Get current subscription status.

**Response:**
```json
{
  "tier": "pro",
  "status": "active",
  "has_active_subscription": true,
  "current_period_end": "2026-04-10T14:30:00Z",
  "cancel_at_period_end": false
}
```

**Notes:**
- Returns `tier: "free"` if no active subscription
- Status values: `active`, `trialing`, `past_due`, `canceled`, `unpaid`

---

### POST /billing/webhook

Handle Stripe webhook events (no auth required).

**Request Headers:**
- `stripe-signature` (required): Signature header from Stripe

**Request Body**: Raw Stripe event JSON

**Response:**
```json
{
  "received": true,
  "event_id": "evt_..."
}
```

**Notes:**
- Security verified via webhook signature
- Processes subscription changes and payment events
- No authentication required; signature verification handles security

---

## Savings Endpoints

All require Pro+ tier authentication.

### GET /savings/summary

Get aggregated savings totals.

**Query Parameters:**
- `region` (optional): Filter by region code

**Response:**
```json
{
  "total": 1245.50,
  "weekly": 145.00,
  "monthly": 580.25,
  "streak_days": 14,
  "currency": "USD"
}
```

---

### GET /savings/history

Get paginated savings records.

**Query Parameters:**
- `page` (optional): Page number (default 1)
- `page_size` (optional): Records per page (1–100, default 20)

**Response:**
```json
{
  "items": [
    {
      "id": "savings-uuid",
      "user_id": "user-uuid",
      "region": "us_ct",
      "savings_amount": 12.50,
      "baseline_cost": 85.00,
      "optimized_cost": 72.50,
      "created_at": "2026-03-11T14:30:00Z"
    }
  ],
  "total": 287,
  "page": 1,
  "page_size": 20,
  "pages": 15
}
```

---

## Recommendations Endpoints

All require Pro+ tier authentication.

### GET /recommendations/switching

Get supplier switching recommendation.

**Response:**
```json
{
  "user_id": "user-uuid",
  "recommendation": {
    "current_supplier": "Eversource Energy",
    "recommended_supplier": "NextEra Energy",
    "estimated_annual_savings": 245.00,
    "confidence": 0.92
  },
  "message": null
}
```

**Notes:**
- Returns `message` with explanation if no recommendation available

---

### GET /recommendations/usage

Get usage timing recommendation for an appliance.

**Query Parameters:**
- `appliance` (required): Type of appliance (e.g., `electric_heater`, `ev_charger`)
- `duration_hours` (required): Duration in hours (0.25–24)

**Response:**
```json
{
  "user_id": "user-uuid",
  "appliance": "ev_charger",
  "duration_hours": 8.0,
  "optimal_start_time": "2026-03-11T22:00:00Z",
  "estimated_cost": 8.50,
  "message": null
}
```

---

### GET /recommendations/daily

Get all daily recommendations.

**Response:**
```json
{
  "user_id": "user-uuid",
  "generated_at": "2026-03-11T14:30:00Z",
  "switching_recommendation": {
    "current_supplier": "Eversource Energy",
    "recommended_supplier": "NextEra Energy",
    "estimated_annual_savings": 245.00,
    "confidence": 0.92
  },
  "usage_recommendations": [
    {
      "appliance": "ev_charger",
      "optimal_start_time": "2026-03-11T22:00:00Z",
      "estimated_cost": 8.50
    }
  ],
  "message": null
}
```

---

## Agent Endpoints

All require authentication. Rate limited per tier (free 3/day, pro 20/day, business unlimited).

### POST /agent/query

Send a prompt to RateShift AI and receive streaming response (SSE).

**Authentication**: Required

**Request Body:**
```json
{
  "prompt": "What are the best rates in Connecticut right now?",
  "context": {
    "region": "us_ct",
    "supplier": "Eversource Energy"
  }
}
```

**Response**: Server-Sent Events stream

Each event:
```json
{
  "role": "assistant",
  "content": "The current rates...",
  "model_used": "gemini-3-flash",
  "tools_used": ["price_lookup", "supplier_info"],
  "tokens_used": 150,
  "duration_ms": 1200
}
```

**Streaming**: Response ends with `[DONE]` message

**Error Codes:**
- `429`: Daily query limit reached
- `503`: AI agent not enabled

---

### POST /agent/task

Submit an async AI task for tool-heavy queries.

**Request Body**: Same as POST /agent/query

**Response:**
```json
{
  "job_id": "job-uuid"
}
```

**Status Code**: 202 (Accepted)

---

### GET /agent/task/{job_id}

Poll result of async AI task.

**Path Parameters:**
- `job_id` (required): Job UUID from task submission

**Response:**
```json
{
  "job_id": "job-uuid",
  "status": "completed",
  "result": {
    "role": "assistant",
    "content": "The current rates in Connecticut...",
    "model_used": "gemini-3-flash",
    "tools_used": ["price_lookup"],
    "tokens_used": 250
  }
}
```

**Status values**: `processing`, `completed`, `failed`, `not_found`

---

### GET /agent/usage

Get daily query usage stats.

**Response:**
```json
{
  "used": 5,
  "limit": 20,
  "remaining": 15,
  "reset_at": "2026-03-12T00:00:00Z",
  "tier": "pro"
}
```

---

## User Endpoints

All require authentication.

### GET /user/preferences

Get current user preferences.

**Response:**
```json
{
  "user_id": "user-uuid",
  "preferences": {
    "notification_enabled": true,
    "auto_switch_enabled": false,
    "green_energy_only": true,
    "region": "us_ct"
  }
}
```

---

### POST /user/preferences

Update user preferences (partial update).

**Request Body:**
```json
{
  "notification_enabled": false,
  "region": "us_ma"
}
```

**Response**: Updated preferences object

---

## Feedback Endpoint

### POST /feedback

Submit user feedback (bug report, feature request, or general comment).

**Authentication**: Required

**Request Body:**
```json
{
  "type": "bug",
  "message": "The alert notification did not trigger when the price dropped below threshold."
}
```

**Response:**
```json
{
  "id": "feedback-uuid",
  "type": "bug",
  "status": "new",
  "created_at": "2026-03-11T14:30:00Z"
}
```

**Validation:**
- `type` must be `bug`, `feature`, or `general`
- `message` must be 10–5000 characters

**Status Code**: 201 (Created)

---

## Internal Endpoints

All require `X-API-Key` header authentication. Excluded from 30-second request timeout.

### POST /internal/check-alerts

Trigger alert checking job (deduped by cooldown window).

**Authentication**: Required (X-API-Key)

**Request**: Empty body or optional filtering params

**Response:**
```json
{
  "alerts_checked": 127,
  "alerts_sent": 12,
  "errors": 0,
  "timestamp": "2026-03-11T14:30:00Z"
}
```

---

### POST /internal/fetch-weather

Fetch weather data for regions (parallelized).

**Authentication**: Required (X-API-Key)

**Request**: Empty body

**Response:**
```json
{
  "regions_updated": 51,
  "total_records": 487,
  "duration_seconds": 8.5
}
```

---

### POST /internal/market-research

Fetch market research and competitive data (Tavily + Diffbot).

**Authentication**: Required (X-API-Key)

**Request**: Empty body

**Response:**
```json
{
  "articles_collected": 45,
  "suppliers_analyzed": 23,
  "duration_seconds": 15.2
}
```

---

### POST /internal/sync-connections

Auto-sync user connections via UtilityAPI.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

**Response:**
```json
{
  "connections_synced": 87,
  "rates_extracted": 512,
  "errors": 2,
  "timestamp": "2026-03-11T14:30:00Z"
}
```

---

### POST /internal/scrape-rates

Auto-discover and scrape supplier rates.

**Authentication**: Required (X-API-Key)

**Request**: Empty body or supplier filtering

**Response:**
```json
{
  "suppliers_discovered": 12,
  "rates_scraped": 156,
  "duration_seconds": 22.3
}
```

---

### POST /internal/dunning-cycle

Execute payment dunning cycle (overdue payment escalation).

**Authentication**: Required (X-API-Key)

**Request**: Empty body

**Response:**
```json
{
  "invoices_checked": 487,
  "soft_notices_sent": 23,
  "final_notices_sent": 5,
  "dunning_completed": 3,
  "timestamp": "2026-03-11T14:30:00Z"
}
```

---

### POST /internal/kpi-report

Aggregate business metrics for reporting.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

**Response:**
```json
{
  "active_users_7d": 487,
  "total_users": 2145,
  "prices_tracked": 15234,
  "alerts_sent_24h": 345,
  "pro_subscribers": 125,
  "business_subscribers": 34,
  "estimated_mrr": 1825.50,
  "weather_freshness_hours": 2,
  "connections_active": 89,
  "connections_error": 3,
  "timestamp": "2026-03-11T14:30:00Z"
}
```

---

### GET /internal/health-data

Get database health and freshness metrics.

**Authentication**: Required (X-API-Key)

**Response:**
```json
{
  "status": "healthy",
  "tables": {
    "users": {
      "row_count": 2145,
      "last_write": "2026-03-11T14:28:00Z",
      "age_hours": 0.03
    },
    "prices": {
      "row_count": 487234,
      "last_write": "2026-03-11T14:29:00Z",
      "age_hours": 0.02
    }
  },
  "warnings": [],
  "timestamp": "2026-03-11T14:30:00Z"
}
```

---

## Health Endpoint

### GET /health

Basic liveness check.

**Authentication**: Not required

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-03-11T14:30:00Z"
}
```

---

## Common Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid parameters) |
| 401 | Unauthorized (missing/invalid auth) |
| 403 | Forbidden (insufficient tier or permission) |
| 404 | Not found (resource doesn't exist) |
| 422 | Unprocessable entity (validation error) |
| 429 | Too many requests (rate limit exceeded) |
| 500 | Internal server error |
| 503 | Service unavailable |
| 504 | Gateway timeout (30-second timeout exceeded) |

---

## Best Practices

1. **Session Management**: Session cookies are httpOnly and automatically managed by the browser. No manual JWT handling required.

2. **Pagination**: Always specify `page_size` explicitly; defaults vary by endpoint.

3. **Date Handling**: Supply ISO 8601 timestamps with timezone. If no timezone is provided, UTC is assumed.

4. **Rate Limits**: Monitor response headers for rate limit info. Agent endpoints consume quota daily.

5. **Agent Streaming**: Client should parse SSE events until receiving `[DONE]` signal.

6. **Retry Logic**: Internal endpoints should be idempotent; safe to retry on 5xx errors.

7. **Regional Codes**: Use two-letter country codes (e.g., `uk`, `de`) or `us_<state>` format (e.g., `us_ct`).

---

## SDK & Client Libraries

Currently no official SDKs. Use standard HTTP clients:
- **JavaScript/TypeScript**: Fetch API, axios, or openapi-fetch
- **Python**: requests, httpx, or httpcore
- **Go**: net/http, resty, or fasthttp

For OpenAPI/Swagger schema, contact support (Swagger disabled in production for security).
