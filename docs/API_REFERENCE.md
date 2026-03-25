# RateShift API Reference

**Base URL**: `https://api.rateshift.app/api/v1`
**Version**: 1.0
**Last Updated**: 2026-03-25

## Overview

The RateShift API provides programmatic access to multi-utility price data (electricity, gas, water, propane, heating oil, community solar), supplier information, billing, alerts, recommendations, community features, and AI agent capabilities. All endpoints return JSON unless noted.

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

## Health Endpoints

### GET /health

Basic health check with deployment metadata and uptime.

**Authentication**: Not required

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 3600,
  "database_status": "connected"
}
```

---

### GET /health/ready

Readiness check — verify all critical dependencies (database, Redis) are available.

**Authentication**: Not required

**Response:**
```json
{
  "status": "ready",
  "checks": {
    "database": true,
    "redis": true
  }
}
```

---

### GET /health/live

Liveness probe — returns 200 if application process is running.

**Authentication**: Not required

**Response:**
```json
{
  "status": "alive"
}
```

---

### GET /health/integrations

Integration health check for all external services (database, Redis, API keys).

**Authentication**: Required (X-API-Key header)

**Response:**
```json
{
  "status": "healthy",
  "integrations": {
    "database": {"status": "healthy", "latency_ms": 4.2},
    "redis": {"status": "healthy", "latency_ms": 1.1},
    "eia": {"status": "configured"},
    "stripe": {"status": "configured"}
  }
}
```

---

## Authentication Endpoints

### GET /auth/me

Get authenticated user information from session.

**Authentication**: Session required

**Response:**
```json
{
  "id": "user-uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "email_verified": true
}
```

**Error Codes:**
- `401`: No valid session

---

### POST /auth/logout

Invalidate current session.

**Authentication**: Session required

**Response:**
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

---

### POST /auth/password/check-strength

Check password strength without authentication.

**Request Body:**
```json
{
  "password": "MySecurePass123!"
}
```

**Response:**
```json
{
  "score": 4,
  "max_score": 5,
  "strength": "strong",
  "valid": true,
  "checks": {
    "min_length": true,
    "has_upper": true,
    "has_lower": true,
    "has_digits": true,
    "has_special": true
  }
}
```

---

## User Endpoints

### GET /user/preferences

Get current user preferences.

**Authentication**: Session required

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

**Authentication**: Session required

**Request Body:**
```json
{
  "notification_enabled": false,
  "region": "us_ma"
}
```

**Response**: Updated preferences object

---

### POST /user/geocode

Geocode an address to region/coordinates (dual-provider: OWM primary, Nominatim fallback).

**Authentication**: Session required

**Request Body:**
```json
{
  "address": "Hartford, CT"
}
```

**Response:**
```json
{
  "region": "us_ct",
  "latitude": 41.7658,
  "longitude": -72.6734,
  "provider": "openweathermap"
}
```

---

### GET /users

List all users (admin only).

**Authentication**: Session required (admin tier)

**Query Parameters:**
- `page` (optional): Page number (default 1)
- `page_size` (optional): Items per page (1–100, default 20)

**Response:**
```json
{
  "users": [
    {
      "id": "user-uuid",
      "email": "user@example.com",
      "subscription_tier": "pro",
      "created_at": "2026-03-10T10:00:00Z"
    }
  ],
  "total": 2145,
  "page": 1,
  "page_size": 20
}
```

---

### PUT /users/{user_id}

Update user details (admin only).

**Authentication**: Session required (admin tier)

**Request Body:**
```json
{
  "subscription_tier": "business",
  "region": "us_ny"
}
```

**Response**: Updated user object

---

## Prices Endpoints

### GET /prices/current

Get current electricity prices for a region.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): PriceRegion code (e.g., `us_ct`, `uk`)
- `supplier` (optional): Filter by specific supplier name
- `limit` (optional): Max results (1–100, default 10)

**Response:**
```json
{
  "price": {
    "ticker": "ELEC-US-CT",
    "current_price": 0.2845,
    "currency": "USD",
    "region": "us_ct",
    "supplier": "Eversource Energy",
    "updated_at": "2026-03-11T14:30:00Z",
    "is_peak": true,
    "carbon_intensity": 185.5
  },
  "region": "us_ct",
  "timestamp": "2026-03-11T14:30:15Z",
  "source": "live"
}
```

---

### GET /prices/history

Get historical electricity prices with pagination.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Price region
- `days` (optional): Number of days of history (1–365, default 7)
- `supplier` (optional): Filter by supplier name
- `start_date` (optional): ISO 8601 start date (inclusive)
- `end_date` (optional): ISO 8601 end date (inclusive)
- `page` (optional): Page number (1-based, default 1)
- `page_size` (optional): Records per page (1–100, default 24)

**Response:**
```json
{
  "region": "us_ct",
  "supplier": null,
  "start_date": "2026-03-04T00:00:00Z",
  "end_date": "2026-03-11T00:00:00Z",
  "prices": [
    {
      "region": "us_ct",
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
  "total": 168,
  "page": 1,
  "page_size": 24,
  "pages": 7
}
```

---

### GET /prices/compare

Compare electricity supplier prices in a region.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Price region

**Response:**
```json
{
  "region": "us_ct",
  "timestamp": "2026-03-11T14:30:15Z",
  "suppliers": [
    {
      "ticker": "ELEC-US-CT",
      "current_price": 0.2400,
      "currency": "USD",
      "region": "us_ct",
      "supplier": "Eversource Energy",
      "updated_at": "2026-03-11T14:30:00Z",
      "is_peak": true,
      "carbon_intensity": 180.0
    }
  ],
  "cheapest_supplier": "Eversource Energy",
  "cheapest_price": 0.2400,
  "average_price": 0.2717
}
```

---

### GET /prices/average

Get average electricity prices for a region over a period.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Price region
- `days` (optional): Number of days (default 7)

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

---

### GET /prices/stream

Server-Sent Events stream of real-time price updates.

**Authentication**: Session required

**Response**: SSE stream with price updates

Each event:
```json
{
  "id": "event-uuid",
  "timestamp": "2026-03-11T14:30:15Z",
  "region": "us_ct",
  "price": 0.2845,
  "supplier": "Eversource Energy"
}
```

---

## Price Analytics Endpoints

### GET /prices/analytics/trend

Get price trend analysis over time.

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `region` (required): Price region
- `days` (optional): Analysis period in days (default 30)

---

### GET /prices/analytics/volatility

Get electricity price volatility metrics.

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `region` (required): Price region

---

### GET /prices/analytics/forecast-accuracy

Get forecast accuracy metrics for a region.

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `region` (required): Price region

---

### GET /prices/analytics/cost-optimization

Get cost optimization recommendations based on historical data.

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `region` (required): Price region

---

## Forecast Endpoints

### GET /forecast

Multi-utility price forecast.

**Authentication**: Session required (Pro tier)

**Query Parameters:**
- `region` (required): Region code
- `utility_type` (optional): Filter by utility type
- `hours` (optional): Forecast horizon (default: 24, max: 168)

**Response:**
```json
{
  "region": "us_ct",
  "generated_at": "2026-03-11T14:30:00Z",
  "forecast": [
    {
      "timestamp": "2026-03-11T15:00:00Z",
      "electricity_price": 0.2750,
      "gas_price": 1.2345,
      "confidence": 0.87
    }
  ],
  "horizon_hours": 24
}
```

---

### GET /forecast/hourly

Hourly electricity price forecast.

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `region` (required): Price region
- `hours` (optional): Forecast horizon (1–168, default 24)

---

### GET /forecast/summary

Forecast summary with key insights.

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `region` (required): Price region

---

## Suppliers Endpoints

### GET /suppliers

List energy suppliers with optional filtering.

**Authentication**: Not required

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
  "page_size": 20
}
```

---

### GET /suppliers/registry

List suppliers with API integration available.

**Authentication**: Not required

**Query Parameters:**
- `region` (optional): Filter by region
- `utility_type` (optional): Filter by utility type

---

### GET /suppliers/{supplier_id}

Get detailed information about a supplier.

**Authentication**: Not required

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
  "green_energy_provider": true
}
```

---

### GET /suppliers/{supplier_id}/tariffs

Get tariffs offered by a supplier.

**Authentication**: Not required

**Path Parameters:**
- `supplier_id` (required): UUID of the supplier

**Query Parameters:**
- `utility_type` (optional): Filter by utility type
- `available_only` (optional): Show only available tariffs (default true)

---

### GET /suppliers/region/{region}

Get all suppliers available in a region.

**Authentication**: Not required

**Path Parameters:**
- `region` (required): Region code (e.g., `us_ct`, `us_ma`)

---

### GET /suppliers/compare/{region}

Compare suppliers in a region with their best tariff prices.

**Authentication**: Not required

**Path Parameters:**
- `region` (required): Region code

**Query Parameters:**
- `utility_type` (optional): Utility type to compare (default `electricity`)
- `tariff_type` (optional): Filter by tariff type

---

## Alerts Endpoints

All require authentication.

### GET /alerts

List all price alert configurations for the current user.

**Authentication**: Session required

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

**Authentication**: Session required

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

**Response**: Alert object

**Validation:**
- At least one of `price_below`, `price_above`, or `notify_optimal_windows` must be specified
- Free tier users limited to 1 alert; Pro/Business unlimited

---

### GET /alerts/history

Get paginated alert trigger history.

**Authentication**: Session required

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

**Authentication**: Session required

**Path Parameters:**
- `alert_id` (required): Alert UUID

**Request Body:** (all fields optional)
```json
{
  "region": "us_ma",
  "price_below": 0.20,
  "is_active": false
}
```

---

### DELETE /alerts/{alert_id}

Delete a price alert configuration.

**Authentication**: Session required

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

## Savings Endpoints

All require Pro+ tier authentication.

### GET /savings/summary

Get aggregated savings totals.

**Authentication**: Session required (Pro+)

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

**Authentication**: Session required (Pro+)

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

### GET /savings/combined

Get combined savings across all utility types.

**Authentication**: Session required (Pro+)

**Response:**
```json
{
  "total_savings": 1245.50,
  "electricity": 845.00,
  "gas": 300.00,
  "water": 45.00,
  "propane": 55.50,
  "heating_oil": 0.00
}
```

---

## Recommendations Endpoints

All require Pro+ tier authentication.

### GET /recommendations/switching

Get supplier switching recommendation.

**Authentication**: Session required (Pro+)

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

---

### GET /recommendations/usage

Get usage timing recommendation for an appliance.

**Authentication**: Session required (Pro+)

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

**Authentication**: Session required (Pro+)

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
  ]
}
```

---

## Billing Endpoints

All require authentication.

### POST /billing/checkout

Create a Stripe Checkout session for subscription.

**Authentication**: Session required

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

---

### POST /billing/portal

Create a Stripe Customer Portal session for subscription management.

**Authentication**: Session required

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

---

### GET /billing/subscription

Get current subscription status.

**Authentication**: Session required

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

---

### POST /billing/cancel

Cancel current subscription.

**Authentication**: Session required

**Response:**
```json
{
  "success": true,
  "message": "Subscription canceled"
}
```

---

## Webhook Endpoints

### POST /webhooks/stripe

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

---

## Connections Endpoints

All require Pro+ tier authentication.

### GET /connections

List all connections for the authenticated user.

**Authentication**: Session required (Pro+)

**Response:**
```json
{
  "connections": [
    {
      "id": "conn-uuid",
      "user_id": "user-uuid",
      "connection_type": "direct",
      "supplier_id": "supplier-uuid",
      "supplier_name": "Eversource Energy",
      "status": "active",
      "account_number_masked": "****5678",
      "meter_number_masked": "****1234",
      "email_provider": null,
      "label": "Home",
      "created_at": "2026-03-10T10:00:00Z",
      "last_sync_at": "2026-03-11T14:30:00Z",
      "last_sync_error": null,
      "current_rate": 0.2845
    }
  ],
  "total": 1
}
```

---

### POST /connections/direct

Create a direct (account-number) connection.

**Authentication**: Session required (Pro+)

**Request Body:**
```json
{
  "supplier_id": "supplier-uuid",
  "account_number": "123456789",
  "label": "Home"
}
```

**Response**: Connection object

---

### POST /connections/email

Create an email-based connection (Gmail or Outlook OAuth).

**Authentication**: Session required (Pro+)

**Request Body:**
```json
{
  "email_provider": "gmail",
  "supplier_id": "supplier-uuid",
  "label": "Home"
}
```

**Response:** OAuth redirect URL or connection object

---

### POST /connections/portal

Create a portal scraping connection (for utilities without API).

**Authentication**: Session required (Pro+)

**Request Body:**
```json
{
  "supplier_id": "supplier-uuid",
  "username": "encrypted-username",
  "password": "encrypted-password",
  "label": "Home"
}
```

**Response**: Connection object

---

### POST /connections/portal/{id}/scrape

Trigger manual portal scrape for a connection.

**Authentication**: Session required (Pro+)

**Path Parameters:**
- `id` (required): Connection UUID

**Response:**
```json
{
  "success": true,
  "message": "Portal scrape triggered",
  "job_id": "job-uuid"
}
```

---

### POST /connections/direct-sync

Trigger direct sync for a connection.

**Authentication**: Session required (Pro+)

**Request Body:**
```json
{
  "connection_id": "conn-uuid"
}
```

---

### GET /connections/direct-sync/{id}/status

Get status of direct sync job.

**Authentication**: Session required (Pro+)

**Path Parameters:**
- `id` (required): Connection UUID

---

### GET /connections/rates

Get extracted rates for a connection.

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `connection_id` (optional): Filter by connection UUID

**Response:**
```json
{
  "rates": [
    {
      "connection_id": "conn-uuid",
      "rate_per_kwh": 0.2845,
      "effective_date": "2026-03-01T00:00:00Z",
      "rate_type": "standard",
      "source": "bill_upload"
    }
  ]
}
```

---

### POST /connections/bills

Upload a bill image/PDF for rate extraction.

**Authentication**: Session required (Pro+)

**Request:** Multipart form data with file

**Response:**
```json
{
  "success": true,
  "extracted_rate": 0.2845,
  "extracted_date": "2026-03-01",
  "bill_id": "bill-uuid"
}
```

---

### GET /connections/bills

List uploaded bills.

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `connection_id` (optional): Filter by connection UUID

---

### DELETE /connections/{id}

Delete a connection.

**Authentication**: Session required (Pro+)

**Path Parameters:**
- `id` (required): Connection UUID

---

### PATCH /connections/{id}

Update connection label or settings.

**Authentication**: Session required (Pro+)

**Path Parameters:**
- `id` (required): Connection UUID

**Request Body:**
```json
{
  "label": "Office",
  "is_active": true
}
```

---

### GET /connections/analytics

Get analytics for connections (usage, rates, savings).

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `connection_id` (optional): Filter by connection UUID

---

## Community Endpoints

### POST /community/posts

Create a community post (AI-moderated, 10 posts/hour rate limit).

**Authentication**: Session required

**Request Body:**
```json
{
  "title": "Best time to run laundry in CT?",
  "content": "I noticed rates drop after 9pm...",
  "category": "tips"
}
```

**Response:**
```json
{
  "id": "post-uuid",
  "title": "Best time to run laundry in CT?",
  "content": "I noticed rates drop after 9pm...",
  "category": "tips",
  "author_id": "user-uuid",
  "created_at": "2026-03-11T14:30:00Z",
  "vote_count": 0,
  "hidden": false
}
```

---

### GET /community/posts

List community posts (paginated).

**Authentication**: Session required

**Query Parameters:**
- `page` (optional): Page number (default 1)
- `page_size` (optional): Items per page (default 20)
- `category` (optional): Filter by category

**Response:**
```json
{
  "posts": [
    {
      "id": "post-uuid",
      "title": "Best time to run laundry in CT?",
      "content": "I noticed rates drop after 9pm...",
      "category": "tips",
      "author_id": "user-uuid",
      "created_at": "2026-03-11T14:30:00Z",
      "vote_count": 5,
      "hidden": false
    }
  ],
  "total": 487,
  "page": 1,
  "page_size": 20,
  "pages": 25
}
```

---

### PUT /community/posts/{id}

Update a community post (author only).

**Authentication**: Session required

**Path Parameters:**
- `id` (required): Post UUID

**Request Body:**
```json
{
  "title": "Updated title",
  "content": "Updated content"
}
```

---

### POST /community/posts/{id}/vote

Vote on a community post (up or down).

**Authentication**: Session required

**Path Parameters:**
- `id` (required): Post UUID

**Request Body:**
```json
{
  "vote_type": "up"
}
```

---

### POST /community/posts/{id}/report

Report a community post (5 unique reporters auto-hides).

**Authentication**: Session required

**Path Parameters:**
- `id` (required): Post UUID

**Request Body:**
```json
{
  "reason": "spam",
  "details": "Promotional content"
}
```

---

### GET /community/stats

Get aggregated community statistics.

**Authentication**: Not required

**Response:**
```json
{
  "total_posts": 1247,
  "active_users": 345,
  "total_votes": 5678,
  "average_post_age_days": 12
}
```

---

## Community Solar Endpoints

### GET /community-solar/programs

List community solar programs by state.

**Authentication**: Not required

**Query Parameters:**
- `state` (optional): State code (e.g., `CT`)

**Response:**
```json
{
  "programs": [
    {
      "id": "program-uuid",
      "name": "CT Solar Share",
      "state": "CT",
      "provider": "Eversource",
      "savings_estimate_pct": 10.5,
      "capacity_available": true
    }
  ]
}
```

---

### GET /community-solar/savings

Get community solar savings estimates.

**Authentication**: Session required

---

### GET /community-solar/program/{program_id}

Get details about a specific community solar program.

**Authentication**: Not required

**Path Parameters:**
- `program_id` (required): Program UUID

---

### GET /community-solar/states

List states with available community solar programs.

**Authentication**: Not required

---

## CCA (Community Choice Aggregation) Endpoints

### GET /cca/detect

Detect if user's region is served by a CCA program.

**Authentication**: Session required

**Response:**
```json
{
  "region": "us_ca",
  "has_cca": true,
  "cca_name": "East Bay Community Energy"
}
```

---

### GET /cca/compare/{cca_id}

Compare CCA program with default supplier.

**Authentication**: Not required

**Path Parameters:**
- `cca_id` (required): CCA UUID

---

### GET /cca/info/{cca_id}

Get detailed information about a CCA program.

**Authentication**: Not required

**Path Parameters:**
- `cca_id` (required): CCA UUID

---

### GET /cca/programs

List all CCA programs.

**Authentication**: Not required

**Query Parameters:**
- `region` (optional): Filter by region
- `state` (optional): Filter by state

---

## Natural Gas Rates Endpoints

### GET /rates/natural-gas

Get current natural gas rates for a region.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code (e.g., `us_ct`)

**Response:**
```json
{
  "rates": [
    {
      "id": "uuid",
      "region": "us_ct",
      "price_per_therm": 1.2345,
      "supplier_name": "Southern CT Gas",
      "source": "eia",
      "recorded_at": "2026-03-13T00:00:00Z"
    }
  ]
}
```

---

### GET /rates/natural-gas/history

Get historical natural gas prices.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code
- `days` (optional): Number of days (default 30)

---

### GET /rates/natural-gas/stats

Get gas price statistics for a region.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

---

### GET /rates/natural-gas/deregulated-states

List states with deregulated natural gas markets.

**Authentication**: Not required

---

### GET /rates/natural-gas/compare

Compare natural gas suppliers in a region.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

---

## Heating Oil Endpoints

### GET /rates/heating-oil

Current heating oil prices by region.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

**Response:**
```json
{
  "rates": [
    {
      "id": "uuid",
      "region": "us_ct",
      "price_per_gallon": 3.4567,
      "supplier_name": "Local Oil Dealer",
      "recorded_at": "2026-03-13T00:00:00Z"
    }
  ]
}
```

---

### GET /rates/heating-oil/history

Get historical heating oil prices.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

---

### GET /rates/heating-oil/dealers

List heating oil dealers in a region.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

---

### GET /rates/heating-oil/compare

Compare heating oil dealers by price and service.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

---

## Propane Endpoints

### GET /rates/propane

Current propane prices by region.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

**Response:**
```json
{
  "rates": [
    {
      "id": "uuid",
      "region": "us_ct",
      "price_per_gallon": 2.1234,
      "supplier_name": "Propane Co",
      "recorded_at": "2026-03-13T00:00:00Z"
    }
  ]
}
```

---

### GET /rates/propane/history

Get historical propane prices.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

---

### GET /rates/propane/compare

Compare propane suppliers by price.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

---

### GET /rates/propane/timing

Optimal propane fill-up timing recommendation.

**Authentication**: Session required

**Query Parameters:**
- `region` (required): Region code

**Response:**
```json
{
  "region": "us_ct",
  "recommended_action": "fill_now",
  "estimated_savings": 45.50,
  "seasonal_note": "Prices trending down"
}
```

---

## Water Endpoints

Water is monitoring-only — no switching CTA (geographic monopoly).

### GET /rates/water

Current water rates by region (municipality-level tiered pricing).

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

**Response:**
```json
{
  "rates": [
    {
      "id": "uuid",
      "region": "us_ct",
      "tier": 1,
      "price_per_gallon": 0.0045,
      "municipality": "Hartford",
      "recorded_at": "2026-03-13T00:00:00Z"
    }
  ]
}
```

---

### GET /rates/water/benchmark

Compare user's water usage to regional benchmarks.

**Authentication**: Session required

**Query Parameters:**
- `region` (required): Region code

---

### GET /rates/water/tips

Water conservation tips.

**Authentication**: Not required

**Response:**
```json
{
  "tips": [
    {
      "title": "Fix leaks promptly",
      "description": "A dripping faucet can waste 3,000 gallons per year",
      "savings_estimate": 50.00
    }
  ]
}
```

---

## Rate Changes Endpoints

### GET /rate-changes

Get recent rate changes across all utility types for the current user.

**Authentication**: Session required

**Query Parameters:**
- `days` (optional): Number of days to look back (default 30)

**Response:**
```json
{
  "changes": [
    {
      "id": "change-uuid",
      "utility_type": "electricity",
      "region": "us_ct",
      "previous_rate": 0.2600,
      "new_rate": 0.2845,
      "change_percent": 9.4,
      "effective_date": "2026-03-01T00:00:00Z"
    }
  ]
}
```

---

### GET /rate-changes/history

Get paginated rate change history.

**Authentication**: Session required

**Query Parameters:**
- `page` (optional): Page number (default 1)
- `page_size` (optional): Items per page (default 20)

---

### PUT /rate-changes/{id}

Mark a rate change as read/acknowledged.

**Authentication**: Session required

**Path Parameters:**
- `id` (required): Rate change UUID

---

## Regulations Endpoints

### GET /regulations

List regulations for a region.

**Authentication**: Not required

**Query Parameters:**
- `region` (required): Region code

**Response:**
```json
{
  "regulations": [
    {
      "id": "reg-uuid",
      "region": "us_ct",
      "title": "Connecticut Public Utilities Regulatory Authority Ruling",
      "description": "Deregulation of electricity markets",
      "effective_date": "2000-01-01T00:00:00Z",
      "source_url": "https://example.com/regulation"
    }
  ]
}
```

---

### GET /regulations/{regulation_id}

Get detailed information about a regulation.

**Authentication**: Not required

**Path Parameters:**
- `regulation_id` (required): Regulation UUID

---

## Compliance Endpoints

### POST /compliance/consent

Record user consent for data processing.

**Authentication**: Session required

**Request Body:**
```json
{
  "consent_type": "marketing",
  "consented": true
}
```

---

### GET /compliance/consents

Get user's consent preferences.

**Authentication**: Session required

**Response:**
```json
{
  "consents": [
    {
      "consent_type": "marketing",
      "consented": true,
      "recorded_at": "2026-03-10T10:00:00Z"
    }
  ]
}
```

---

### GET /compliance/data-export

Export all user data in standard format.

**Authentication**: Session required

**Response:** ZIP file with JSON export

---

### GET /compliance/deletion-status

Check status of data deletion request.

**Authentication**: Session required

**Response:**
```json
{
  "status": "pending",
  "requested_at": "2026-03-10T10:00:00Z",
  "estimated_completion": "2026-03-17T10:00:00Z"
}
```

---

### DELETE /compliance/delete-data

Request full account and data deletion.

**Authentication**: Session required

**Response:**
```json
{
  "success": true,
  "message": "Data deletion scheduled",
  "deletion_date": "2026-03-17T10:00:00Z"
}
```

---

### DELETE /compliance/delete-connections

Delete all connection data (GDPR compliance).

**Authentication**: Session required

---

### POST /compliance/audit-log

Request audit log of data access events.

**Authentication**: Session required

---

## Feedback Endpoint

### POST /feedback

Submit user feedback (bug report, feature request, or general comment).

**Authentication**: Session required

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

---

## Referrals Endpoints

### GET /referrals/code

Get the current user's unique referral code.

**Authentication**: Session required

**Response:**
```json
{
  "code": "ABC123XYZ",
  "referral_url": "https://rateshift.app?ref=ABC123XYZ",
  "created_at": "2026-03-10T10:00:00Z"
}
```

---

### POST /referrals/apply

Apply a referral code during signup or on dashboard.

**Authentication**: Optional (Session preferred)

**Request Body:**
```json
{
  "code": "ABC123XYZ"
}
```

**Response:**
```json
{
  "success": true,
  "bonus": "$10 credit",
  "applied_at": "2026-03-11T14:30:00Z"
}
```

---

### GET /referrals/stats

Get referral statistics for the current user.

**Authentication**: Session required

**Response:**
```json
{
  "total_referrals": 12,
  "accepted_referrals": 8,
  "pending_referrals": 4,
  "total_bonus": 80.00,
  "currency": "USD"
}
```

---

## Affiliate Endpoints

### POST /affiliate/click

Record an affiliate link click (no auth required).

**Request Body:**
```json
{
  "affiliate_id": "aff-uuid",
  "source_url": "https://example.com"
}
```

**Response:**
```json
{
  "success": true,
  "tracking_id": "track-uuid"
}
```

---

### GET /affiliate/stats

Get affiliate click and conversion stats.

**Authentication**: Required (X-API-Key)

**Query Parameters:**
- `affiliate_id` (optional): Filter by affiliate UUID

**Response:**
```json
{
  "clicks": 1234,
  "conversions": 45,
  "conversion_rate": 3.65,
  "earned": 450.00
}
```

---

## Notifications Endpoints

### GET /notifications

Get all notifications for the current user.

**Authentication**: Session required

**Response:**
```json
{
  "notifications": [
    {
      "id": "notif-uuid",
      "type": "price_alert",
      "message": "Electricity price dropped below $0.22/kWh in CT",
      "read": false,
      "created_at": "2026-03-11T14:30:00Z"
    }
  ]
}
```

---

### GET /notifications/count

Get unread notification count.

**Authentication**: Session required

**Response:**
```json
{
  "unread_count": 5
}
```

---

### PUT /notifications/read-all

Mark all notifications as read.

**Authentication**: Session required

---

### PUT /notifications/{notification_id}/read

Mark a specific notification as read.

**Authentication**: Session required

**Path Parameters:**
- `notification_id` (required): Notification UUID

---

## Utility Accounts Endpoints

### GET /utility-accounts

List all utility accounts for the current user.

**Authentication**: Session required

**Response:**
```json
[
  {
    "id": "account-uuid",
    "user_id": "user-uuid",
    "utility_name": "Eversource Energy",
    "utility_type": "electricity",
    "account_number": "123456789",
    "meter_number": "987654321",
    "created_at": "2026-03-10T10:00:00Z"
  }
]
```

---

### POST /utility-accounts

Create a new utility account record.

**Authentication**: Session required

**Request Body:**
```json
{
  "utility_name": "Eversource Energy",
  "utility_type": "electricity",
  "account_number": "123456789",
  "meter_number": "987654321"
}
```

---

### GET /utility-accounts/types

Get list of available utility types.

**Authentication**: Not required

**Response:**
```json
{
  "types": [
    "electricity",
    "natural_gas",
    "water",
    "propane",
    "heating_oil"
  ]
}
```

---

### GET /utility-accounts/{account_id}

Get details of a specific utility account.

**Authentication**: Session required

**Path Parameters:**
- `account_id` (required): Account UUID

---

### PUT /utility-accounts/{account_id}

Update utility account details.

**Authentication**: Session required

**Path Parameters:**
- `account_id` (required): Account UUID

**Request Body:** (all fields optional)
```json
{
  "account_number": "new-number",
  "meter_number": "new-meter"
}
```

---

### DELETE /utility-accounts/{account_id}

Delete a utility account.

**Authentication**: Session required

**Path Parameters:**
- `account_id` (required): Account UUID

---

## Utility Discovery Endpoints

### GET /utility-discovery/discover

Get available utility types and completion progress for the current user.

**Authentication**: Session required

**Response:**
```json
{
  "available_utilities": [
    "electricity",
    "natural_gas",
    "water"
  ],
  "completed_utilities": ["electricity"],
  "completion_percentage": 33.3
}
```

---

### GET /utility-discovery/completion

Get utility setup completion percentage.

**Authentication**: Session required

**Response:**
```json
{
  "percentage": 33.3,
  "total_utilities": 3,
  "completed": 1
}
```

---

## Public Rates Endpoints

### GET /rates/states

List states with available rate data (ISR for SEO).

**Authentication**: Not required

**Response:**
```json
{
  "states": [
    {
      "code": "ct",
      "name": "Connecticut",
      "utility_types": ["electricity", "natural_gas", "water"]
    }
  ]
}
```

---

### GET /rates/{state}/{utility_type}

Public rate data for ISR (Incremental Static Regeneration) pages.

**Authentication**: Not required

**Path Parameters:**
- `state` (required): State code (e.g., `ct`, `ny`)
- `utility_type` (required): `electricity`, `gas`, `heating_oil`, `propane`, `water`

**Response:**
```json
{
  "state": "ct",
  "utility_type": "electricity",
  "rates": [
    {
      "supplier": "Eversource Energy",
      "current_price": 0.2845,
      "updated_at": "2026-03-11T14:30:00Z"
    }
  ]
}
```

---

## Reports Endpoint

### GET /reports

Cross-utility optimization report for the user.

**Authentication**: Session required (Pro+)

**Query Parameters:**
- `format` (optional): `json` or `pdf` (default `json`)

**Response:**
```json
{
  "report_id": "report-uuid",
  "generated_at": "2026-03-11T14:30:00Z",
  "summary": {
    "total_spending": 1200.50,
    "potential_savings": 245.00,
    "optimization_score": 82
  },
  "recommendations": [
    {
      "action": "Switch to NextEra Energy",
      "estimated_savings": 180.00
    }
  ]
}
```

---

## Export Endpoint

### GET /export

Export rate data in CSV or JSON format.

**Authentication**: Session required

**Query Parameters:**
- `format` (optional): `csv` or `json` (default `json`)
- `utility_type` (optional): Filter by utility type

**Response:** File download or JSON array

---

## Agent Endpoints

All require authentication. Rate limited per tier (free 3/day, pro 20/day, business unlimited).

### POST /agent/query

Send a prompt to RateShift AI and receive streaming response (SSE).

**Authentication**: Session required

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

Streaming ends with `[DONE]` message.

---

### POST /agent/task

Submit an async AI task for tool-heavy queries.

**Authentication**: Session required

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

**Authentication**: Session required

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

Status values: `processing`, `completed`, `failed`, `not_found`

---

### GET /agent/usage

Get daily query usage stats.

**Authentication**: Session required

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

### GET /agent/health

Get AI agent service health status.

**Authentication**: Session required

**Response:**
```json
{
  "status": "healthy",
  "model": "gemini-3-flash",
  "fallback_model": "groq-llama-3.3-70b",
  "tools_available": 15,
  "last_check": "2026-03-11T14:30:00Z"
}
```

---

## Neighborhood Endpoint

### GET /neighborhood/compare

Compare user's rates to neighborhood average.

**Authentication**: Session required

**Query Parameters:**
- `radius_miles` (optional): Comparison radius (default 10)

**Response:**
```json
{
  "user_rate": 0.2845,
  "neighborhood_average": 0.2750,
  "percentile": 75,
  "message": "You're paying slightly above average"
}
```

---

## Internal Endpoints

All require `X-API-Key` header authentication. Excluded from 30-second request timeout.

### POST /internal/check-alerts

Trigger alert checking job (deduped by cooldown window).

**Authentication**: Required (X-API-Key)

**Request**: Empty body

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

Fetch weather data for regions (parallelized with asyncio.gather + Semaphore(10)).

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

### POST /internal/fetch-gas-rates

Fetch natural gas rate data.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

---

### POST /internal/fetch-heating-oil

Fetch heating oil pricing data.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

---

### POST /internal/fetch-propane

Fetch propane pricing data.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

---

### POST /internal/detect-rate-changes

Detect rate changes across all utility types and trigger alerts.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

---

### POST /internal/geocode

Geocode an address using dual-provider (OWM primary, Nominatim fallback).

**Authentication**: Required (X-API-Key)

**Request Body:**
```json
{
  "address": "Hartford, CT"
}
```

---

### POST /internal/scan-emails

Batch scan email connections for bill attachments and rate extraction.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

**Response:**
```json
{
  "connections_scanned": 42,
  "rates_extracted": 18,
  "errors": 2,
  "timestamp": "2026-03-11T14:30:00Z"
}
```

---

### POST /internal/scrape-portals

Batch scrape portal connections (parallelized with Semaphore(2)).

**Authentication**: Required (X-API-Key)

**Request**: Empty body

**Response:**
```json
{
  "portals_scraped": 15,
  "rates_extracted": 23,
  "errors": 1,
  "timestamp": "2026-03-11T14:30:00Z"
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

### POST /internal/sync-users

Sync user data with external services.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

---

### POST /internal/dunning-cycle

Execute payment dunning cycle (overdue payment escalation with 7-day grace period).

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

### GET /internal/data-quality/freshness

Get data freshness metrics for all tables.

**Authentication**: Required (X-API-Key)

**Response:**
```json
{
  "tables": {
    "prices": {"freshness_hours": 0.5, "last_update": "2026-03-11T14:00:00Z"},
    "weather": {"freshness_hours": 2.0, "last_update": "2026-03-11T12:30:00Z"},
    "suppliers": {"freshness_hours": 24.0, "last_update": "2026-03-10T14:30:00Z"}
  }
}
```

---

### GET /internal/data-quality/anomalies

Get detected data anomalies and quality issues.

**Authentication**: Required (X-API-Key)

**Response:**
```json
{
  "anomalies": [
    {
      "table": "prices",
      "issue": "Missing prices for region us_ny",
      "severity": "high",
      "detected_at": "2026-03-11T14:30:00Z"
    }
  ]
}
```

---

### GET /internal/data-quality/sources

Get data source health and status.

**Authentication**: Required (X-API-Key)

**Response:**
```json
{
  "sources": {
    "eia": {"status": "healthy", "last_sync": "2026-03-11T14:30:00Z"},
    "nrel": {"status": "unhealthy", "last_sync": "2026-03-10T10:00:00Z", "error": "Rate limited"},
    "openweathermap": {"status": "healthy", "last_sync": "2026-03-11T14:15:00Z"}
  }
}
```

---

### POST /internal/observe-forecasts

Backfill actual prices into forecast observations for ML model training.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

---

### POST /internal/learn

Trigger nightly ML model learning/retraining.

**Authentication**: Required (X-API-Key)

**Request**: Empty body

---

### GET /internal/observation-stats

Get ML observation statistics.

**Authentication**: Required (X-API-Key)

---

### GET /internal/model-versions

Get available ML model versions.

**Authentication**: Required (X-API-Key)

---

### POST /internal/model-versions/compare

Compare two ML model versions for performance.

**Authentication**: Required (X-API-Key)

**Request Body:**
```json
{
  "model_v1": "v2.0.0",
  "model_v2": "v2.1.0"
}
```

---

### PUT /internal/flags/{name}

Set feature flags for A/B testing or gradual rollouts.

**Authentication**: Required (X-API-Key)

**Path Parameters:**
- `name` (required): Flag name

**Request Body:**
```json
{
  "value": true,
  "expires_at": "2026-03-25T00:00:00Z"
}
```

---

### GET /internal/flags

List all active feature flags.

**Authentication**: Required (X-API-Key)

---

### POST /internal/maintenance/cleanup

Run database cleanup and maintenance tasks.

**Authentication**: Required (X-API-Key)

**Request**: Empty body or cleanup options

**Response:**
```json
{
  "operations": [
    {"operation": "vacuum", "rows_affected": 5432, "duration_ms": 234},
    {"operation": "analyze", "tables_analyzed": 58, "duration_ms": 156}
  ],
  "total_duration_ms": 390
}
```

---

## Beta Endpoints

### POST /beta/signup

Submit beta signup (unauthenticated).

**Authentication**: Not required

**Request Body:**
```json
{
  "email": "user@example.com",
  "region": "us_ct",
  "utility_type": "electricity"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Signup recorded. Watch for early access email.",
  "id": "signup-uuid"
}
```

---

### GET /beta/signups/count

Get total beta signup count.

**Authentication**: Required (X-API-Key)

---

### GET /beta/signups/stats

Get beta signup statistics and demographics.

**Authentication**: Required (X-API-Key)

---

### POST /beta/verify-code

Verify beta access code.

**Authentication**: Optional

**Request Body:**
```json
{
  "code": "BETA2026"
}
```

---

## User Supplier Endpoint

### PUT /user/supplier

Link or update user's current supplier.

**Authentication**: Session required

**Request Body:**
```json
{
  "supplier_id": "supplier-uuid",
  "region": "us_ct"
}
```

---

### GET /user/supplier

Get user's current supplier information.

**Authentication**: Session required

---

### DELETE /user/supplier

Unlink user's supplier.

**Authentication**: Session required

---

### POST /user/supplier/link

Link a third-party account (via OAuth/API).

**Authentication**: Session required

**Request Body:**
```json
{
  "supplier_id": "supplier-uuid",
  "oauth_code": "auth-code-from-provider"
}
```

---

### GET /user/supplier/accounts

Get all linked supplier accounts.

**Authentication**: Session required

---

### DELETE /user/supplier/accounts/{supplier_id}

Unlink a specific supplier account.

**Authentication**: Session required

**Path Parameters:**
- `supplier_id` (required): Supplier UUID

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

8. **Connection Types**: Use `direct` for account numbers, `email` for OAuth (Gmail/Outlook), `portal` for web scraping.

9. **Tier Gating**: Always check subscription tier for gated endpoints (Pro, Business). Free tier has limited functionality.

10. **Webhook Security**: All Stripe webhook requests include `stripe-signature` header; verify signature before processing.

---

## SDK & Client Libraries

Currently no official SDKs. Use standard HTTP clients:
- **JavaScript/TypeScript**: Fetch API, axios, or openapi-fetch
- **Python**: requests, httpx, or httpcore
- **Go**: net/http, resty, or fasthttp

For OpenAPI/Swagger schema, contact support (Swagger disabled in production for security).
