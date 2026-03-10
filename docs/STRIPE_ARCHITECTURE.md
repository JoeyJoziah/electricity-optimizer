# Stripe Monetization Architecture

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                          │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Pricing  │  │Dashboard │  │ Account  │  │  Billing │          │
│  │   Page   │  │   Page   │  │   Page   │  │  Portal  │          │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘          │
└───────┼─────────────┼─────────────┼─────────────┼─────────────────┘
        │             │             │             │
        │ (1) Subscribe             │             │ (5) Manage
        │             │ (3) Status  │             │
        ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Backend API (FastAPI)                            │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │            /api/v1/billing Router                           │  │
│  │                                                             │  │
│  │  POST /checkout    GET /subscription    POST /portal       │  │
│  │  POST /webhook                                             │  │
│  └───┬─────────────────────┬─────────────────────┬────────────┘  │
│      │                     │                     │                │
│      │                     ▼                     │                │
│      │          ┌──────────────────┐            │                │
│      │          │  StripeService   │            │                │
│      │          │                  │            │                │
│      │          │ • checkout       │            │                │
│      │          │ • portal         │            │                │
│      │          │ • status         │            │                │
│      │          │ • webhooks       │            │                │
│      │          └────────┬─────────┘            │                │
│      │                   │                      │                │
└──────┼───────────────────┼──────────────────────┼────────────────┘
       │                   │                      │
       │ (2) Create        │ (4) Fetch           │ (6) Create
       │ Session           │ Status              │ Portal
       │                   │                      │
       ▼                   ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Stripe API                                  │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │   Checkout   │  │Subscriptions │  │   Customer   │            │
│  │   Sessions   │  │              │  │    Portal    │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                     Webhooks                                 │ │
│  │  • checkout.session.completed                               │ │
│  │  • customer.subscription.updated                            │ │
│  │  • customer.subscription.deleted                            │ │
│  │  • invoice.payment_failed                                   │ │
│  └────────────────────────────┬─────────────────────────────────┘ │
└─────────────────────────────────┼───────────────────────────────────┘
                                  │
                                  │ (7) Webhook
                                  │ Events
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    POST /api/v1/billing/webhook                     │
│                                                                     │
│  1. Verify signature                                               │
│  2. Parse event                                                    │
│  3. Update user.subscription_tier                                  │
│  4. Update user.stripe_customer_id                                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Subscription Flow

### 1. User Subscribes to Pro/Business

```
User                Frontend             Backend              Stripe
 │                     │                    │                    │
 │  Click "Upgrade"    │                    │                    │
 │────────────────────>│                    │                    │
 │                     │                    │                    │
 │                     │ POST /checkout     │                    │
 │                     │ {tier: "pro"}      │                    │
 │                     │───────────────────>│                    │
 │                     │                    │                    │
 │                     │                    │ Create Session     │
 │                     │                    │───────────────────>│
 │                     │                    │                    │
 │                     │                    │<───────────────────│
 │                     │                    │ {url, session_id}  │
 │                     │<───────────────────│                    │
 │                     │ {checkout_url}     │                    │
 │<────────────────────│                    │                    │
 │                     │                    │                    │
 │  Redirect to Stripe checkout page       │                    │
 │──────────────────────────────────────────────────────────────>│
 │                     │                    │                    │
 │  Enter payment info │                    │                    │
 │  and complete       │                    │                    │
 │────────────────────>│                    │                    │
 │                     │                    │                    │
 │<────────────────────│                    │  Webhook:          │
 │  Redirect to        │                    │  checkout.session  │
 │  success_url        │                    │  .completed        │
 │                     │                    │<───────────────────│
 │                     │                    │                    │
 │                     │                    │ Update User:       │
 │                     │                    │ - tier = "pro"     │
 │                     │                    │ - customer_id      │
 │                     │                    │                    │
```

### 2. User Manages Subscription

```
User                Frontend             Backend              Stripe
 │                     │                    │                    │
 │  Click "Manage"     │                    │                    │
 │────────────────────>│                    │                    │
 │                     │                    │                    │
 │                     │ POST /portal       │                    │
 │                     │───────────────────>│                    │
 │                     │                    │                    │
 │                     │                    │ Create Portal      │
 │                     │                    │ Session            │
 │                     │                    │───────────────────>│
 │                     │                    │                    │
 │                     │                    │<───────────────────│
 │                     │                    │ {portal_url}       │
 │                     │<───────────────────│                    │
 │<────────────────────│                    │                    │
 │                     │                    │                    │
 │  Redirect to Stripe portal              │                    │
 │──────────────────────────────────────────────────────────────>│
 │                     │                    │                    │
 │  Update payment,    │                    │                    │
 │  cancel, etc.       │                    │                    │
 │────────────────────>│                    │                    │
 │                     │                    │                    │
 │                     │                    │  Webhook:          │
 │                     │                    │  subscription      │
 │                     │                    │  .updated          │
 │                     │                    │<───────────────────│
 │                     │                    │                    │
 │                     │                    │ Update User tier   │
 │                     │                    │                    │
```

## Data Models

### User Model (Enhanced)

```python
class User(BaseModel):
    id: str
    email: EmailStr
    name: str

    # Subscription fields (NEW)
    subscription_tier: str = "free"  # free | pro | business
    stripe_customer_id: Optional[str] = None

    # ... other fields
```

### Subscription Tiers

| Tier     | Price    | Features                                                                          |
|----------|----------|-----------------------------------------------------------------------------------|
| Free     | $0       | Basic price view, 1 alert (hard limit), manual scheduling                        |
| Pro      | $4.99/mo | Unlimited alerts, ML forecasts (forecast/savings/recommendations), optimization   |
| Business | $14.99/mo| Pro + API access (prices/stream), multi-property, priority support                |

**Tier gating** (`backend/api/dependencies.py`): `require_tier(min_tier)` factory creates a FastAPI Depends that queries `subscription_tier` from the users table and compares against `_TIER_ORDER = {"free": 0, "pro": 1, "business": 2}`. Returns HTTP 403 if the user's tier is below `min_tier`.

**Gated endpoints (7 total):**
- `require_tier("pro")`: `/forecast`, `/savings/summary`, `/savings/history`, `/savings/goals`, `/recommendations/switching`, `/recommendations/usage`, `/recommendations/daily`
- `require_tier("business")`: `/prices/stream`

**Free tier alert limit**: `POST /api/v1/alerts` checks alert count for free users. If `COUNT(*) >= 1`, returns HTTP 403 "Free plan limited to 1 alert. Upgrade to Pro for unlimited."

## Webhook Events and Actions

| Event                            | Action                              | User Field Updates           |
|----------------------------------|-------------------------------------|------------------------------|
| `checkout.session.completed`     | Activate subscription               | `tier`, `stripe_customer_id` |
| `customer.subscription.updated`  | Update subscription                 | `tier` (based on status)     |
| `customer.subscription.deleted`  | Downgrade to free                   | `tier = "free"`              |
| `invoice.payment_failed`         | Resolve user via `stripe_customer_id`, trigger DunningService (record, cooldown check, send dunning email, escalate after 3 failures) | `tier = "free"` after 3 failures |

### Webhook Processing Details (2026-03-05)

**`payment_failed` handler fix:** The `invoice.payment_failed` webhook event does not include `client_reference_id`. The handler now resolves the `user_id` from `stripe_customer_id` via `UserRepository.get_by_stripe_customer_id()`.

**`apply_webhook_action()` two-stage guard:** All webhook handlers use a two-stage guard pattern:
1. Check if the event has already been handled (idempotency)
2. Resolve the customer identity from `stripe_customer_id` before processing

This prevents duplicate processing and ensures the user can always be identified even for events that lack a direct user reference.

### Dunning Service (Phase 3 — 2026-03-06)

**`invoice.payment_failed` → DunningService flow:**

1. `handle_webhook_event()` extracts `amount_due` (cents → dollars), `currency`, `invoice_id` from invoice data
2. `apply_webhook_action()` calls `DunningService.handle_payment_failure()` with resolved user
3. DunningService orchestrates:
   - `record_payment_failure()` — INSERT into `payment_retry_history` table
   - `should_send_dunning()` — 24h cooldown check (prevents email spam)
   - `send_dunning_email()` — soft template (< 3 attempts, amber) or final template (>= 3, red)
   - `escalate_if_needed()` — downgrade to free tier after 3 failures

**Daily dunning cycle** (`POST /internal/dunning-cycle`, GHA daily 7am UTC):
- Finds accounts with payment failing > 7 days and still on paid tier
- Sends final dunning email
- Downgrades to free tier

**Email templates:**
- `dunning_soft.html` — amber gradient header, empathetic tone, "Update Payment Method" CTA
- `dunning_final.html` — red gradient header, grace period warning, downgrade date notice

**Migration:** `024_payment_retry_history.sql` — UUID PK, retry tracking, email history, escalation audit

## Error Handling

### Graceful Degradation

1. **Stripe Not Configured**: Returns 503 with helpful message
2. **Invalid Tier**: Returns 400 with validation error
3. **Stripe API Error**: Returns 500, logs details for debugging
4. **Webhook Signature Invalid**: Returns 400, prevents processing

### Security Measures

1. **Webhook Verification**: All webhooks verified via signature
2. **Authentication**: Checkout/portal require valid session (Neon Auth)
3. **No PII in Logs**: Only IDs and tier names logged
4. **Constant-Time Comparison**: Prevents timing attacks on secrets

## Environment Configuration

### Billing Redirect Domains (2026-03-02)

Stripe redirect domains (for checkout success/cancel and portal return URLs) are now configurable via the `ALLOWED_REDIRECT_DOMAINS` environment variable. This enables flexible deployment across different environments without code changes.

**Environment Variable:**
```
ALLOWED_REDIRECT_DOMAINS=["rateshift.app","localhost"]
```

Accepts either:
- JSON array format: `["domain1", "domain2", ...]`
- Comma-separated format: `domain1,domain2,...`

**Usage in Code:**
- The `stripe_service.py` validates redirect URLs against this allowlist before creating checkout/portal sessions
- Prevents Open Redirect vulnerabilities
- Defaults in `.env.example` cover Vercel and Render deployments plus localhost

### Development (Test Mode)

```bash
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_PRO=price_test_xxx
STRIPE_PRICE_BUSINESS=price_test_xxx
ALLOWED_REDIRECT_DOMAINS=["http://localhost:3000"]
```

### Production (Live Mode)

```bash
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_PRO=price_live_xxx
STRIPE_PRICE_BUSINESS=price_live_xxx
ALLOWED_REDIRECT_DOMAINS=["https://rateshift.app","https://www.rateshift.app"]
```

## API Endpoints

### POST /api/v1/billing/checkout
Create Stripe checkout session.

**Auth**: Required (session)

**Request**:
```json
{
  "tier": "pro",
  "success_url": "https://app.example.com/success",
  "cancel_url": "https://app.example.com/pricing"
}
```

**Response**:
```json
{
  "session_id": "cs_test_123",
  "checkout_url": "https://checkout.stripe.com/pay/cs_test_123"
}
```

### GET /api/v1/billing/subscription
Get current subscription status.

**Auth**: Required (session)

**Response**:
```json
{
  "tier": "pro",
  "status": "active",
  "has_active_subscription": true,
  "current_period_end": "2026-03-12T00:00:00Z",
  "cancel_at_period_end": false
}
```

### POST /api/v1/billing/portal
Create customer portal session.

**Auth**: Required (session)

**Request**:
```json
{
  "return_url": "https://app.example.com/account"
}
```

**Response**:
```json
{
  "portal_url": "https://billing.stripe.com/p/session/xxx"
}
```

### POST /api/v1/billing/webhook
Handle Stripe webhook events.

**Auth**: Webhook signature (no JWT)

**Headers**: `stripe-signature`

**Body**: Raw webhook event from Stripe

**Response**:
```json
{
  "received": true,
  "event_id": "evt_123"
}
```

## Testing Strategy

### Unit Tests (test_stripe_service.py)
- Mock all Stripe API calls
- Test success and error paths
- Verify webhook signature validation
- Test event parsing and handling

### Integration Tests (Manual/Stripe CLI)
```bash
# Forward webhooks to local server
stripe listen --forward-to localhost:8000/api/v1/billing/webhook

# Trigger test events
stripe trigger checkout.session.completed
stripe trigger customer.subscription.updated
stripe trigger invoice.payment_failed
```

### End-to-End Tests (Staging)
- Use Stripe test mode
- Create real checkout session
- Complete test payment
- Verify webhook received
- Check user tier updated

## Performance Considerations

1. **Webhook Processing**: All webhook handlers are async
2. **Caching**: Subscription status could be cached (TODO)
3. **Batch Updates**: Multiple tier checks batched if needed
4. **Database Queries**: User updates use prepared statements

## Monitoring

Log events to track:
- `checkout_session_created`
- `subscription_activated`
- `subscription_canceled`
- `payment_failed`
- `webhook_signature_invalid`

Metrics to monitor:
- Conversion rate (free → pro/business)
- Churn rate (cancellations)
- Failed payment rate
- Webhook processing time

---

**Last Updated**: 2026-03-09

**Key Changes**:
- Environment variable `ALLOWED_REDIRECT_DOMAINS` now controls billing redirect domains (previously hardcoded)
- Supports both JSON array and comma-separated formats for flexibility
- Reduces security risk by allowing environment-specific configuration without code changes
