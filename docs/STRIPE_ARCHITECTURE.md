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

| Tier     | Price    | Features                                            |
|----------|----------|-----------------------------------------------------|
| Free     | $0       | Basic price view, 1 alert, manual scheduling       |
| Pro      | $4.99/mo | Unlimited alerts, ML forecasts, optimization       |
| Business | $14.99/mo| Pro + API access, multi-property, priority support |

## Webhook Events and Actions

| Event                            | Action                              | User Field Updates           |
|----------------------------------|-------------------------------------|------------------------------|
| `checkout.session.completed`     | Activate subscription               | `tier`, `stripe_customer_id` |
| `customer.subscription.updated`  | Update subscription                 | `tier` (based on status)     |
| `customer.subscription.deleted`  | Downgrade to free                   | `tier = "free"`              |
| `invoice.payment_failed`         | Log warning, notify user (TODO)     | None (keep tier for grace)   |

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
ALLOWED_REDIRECT_DOMAINS=["electricity-optimizer.vercel.app","electricity-optimizer-frontend.onrender.com","localhost"]
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
ALLOWED_REDIRECT_DOMAINS=["https://electricity-optimizer-frontend.onrender.com","https://electricity-optimizer.vercel.app"]
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

**Last Updated**: 2026-03-02

**Key Changes**:
- Environment variable `ALLOWED_REDIRECT_DOMAINS` now controls billing redirect domains (previously hardcoded)
- Supports both JSON array and comma-separated formats for flexibility
- Reduces security risk by allowing environment-specific configuration without code changes
