# RateShift Stripe Monetization Integration

## Overview

Complete Stripe integration for subscription-based monetization with three tiers:
- **Free**: $0 (basic price view, 1 alert, manual scheduling)
- **Pro**: $4.99/mo (unlimited alerts, ML forecasts, optimization, weather)
- **Business**: $14.99/mo (API access, multi-property, priority support)

## Files Created

### 1. `backend/services/stripe_service.py`
Core service handling all Stripe operations:
- `create_checkout_session()` - Create Stripe checkout for subscriptions
- `create_customer_portal_session()` - Generate customer portal URL
- `get_subscription_status()` - Retrieve current subscription info
- `cancel_subscription()` - Cancel or schedule cancellation
- `verify_webhook_signature()` - Validate webhook authenticity
- `handle_webhook_event()` - Process webhook events

### 2. `backend/api/v1/billing.py`
FastAPI router with endpoints:
- `POST /api/v1/billing/checkout` - Create checkout session (requires auth)
- `POST /api/v1/billing/portal` - Create portal session (requires auth)
- `GET /api/v1/billing/subscription` - Get subscription status (requires auth)
- `POST /api/v1/billing/webhook` - Handle Stripe webhooks (signature verification)

### 3. `backend/tests/test_stripe_service.py`
Comprehensive test suite with 20+ tests:
- Checkout session creation
- Customer portal generation
- Subscription status retrieval
- Webhook event handling (checkout.session.completed, customer.subscription.updated, etc.)
- Error handling and edge cases
- Webhook signature verification

## Files Modified

### 1. `backend/models/user.py`
Added subscription fields:
```python
subscription_tier: str = Field(default="free", pattern=r"^(free|pro|business)$")
stripe_customer_id: Optional[str] = None
```

### 2. `backend/config/settings.py`
Added Stripe configuration:
```python
stripe_secret_key: Optional[str] = Field(default=None, validation_alias="STRIPE_SECRET_KEY")
stripe_webhook_secret: Optional[str] = Field(default=None, validation_alias="STRIPE_WEBHOOK_SECRET")
stripe_price_pro: Optional[str] = Field(default=None, validation_alias="STRIPE_PRICE_PRO")
stripe_price_business: Optional[str] = Field(default=None, validation_alias="STRIPE_PRICE_BUSINESS")
```

### 3. `backend/main.py`
Added billing router:
```python
from api.v1 import billing as billing_v1

app.include_router(
    billing_v1.router,
    prefix=f"{settings.api_prefix}/billing",
    tags=["Billing"]
)
```

## Environment Variables

Required for production (already documented in `.env.example`):
```bash
# Stripe Keys (from Stripe Dashboard)
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# Stripe Price IDs (created in Stripe Dashboard)
STRIPE_PRICE_PRO=price_xxx
STRIPE_PRICE_BUSINESS=price_xxx
```

## Setup Instructions

### 1. Install Dependencies
```bash
# Stripe is already in requirements.txt
pip install stripe>=7.0,<8.0
```

### 2. Configure Stripe

1. **Create Stripe Account**: https://dashboard.stripe.com/register
2. **Create Products**:
   - Go to Products → Add Product
   - Create "Pro" ($4.99/month recurring)
   - Create "Business" ($14.99/month recurring)
   - Copy Price IDs (e.g., `price_1ABC...`)

3. **Get API Keys**:
   - Go to Developers → API keys
   - Copy Secret Key (`sk_test_...` for test, `sk_live_...` for production)

4. **Configure Webhook**:
   - Go to Developers → Webhooks
   - Add endpoint: `https://your-domain.com/api/v1/billing/webhook`
   - Select events:
     - `checkout.session.completed`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
     - `invoice.payment_failed`
   - Copy Webhook Signing Secret (`whsec_...`)

5. **Set Environment Variables**:
   ```bash
   export STRIPE_SECRET_KEY=sk_test_xxx
   export STRIPE_WEBHOOK_SECRET=whsec_xxx
   export STRIPE_PRICE_PRO=price_xxx
   export STRIPE_PRICE_BUSINESS=price_xxx
   ```

### 3. Test Locally with Stripe CLI

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login to Stripe
stripe login

# Forward webhooks to local server
stripe listen --forward-to localhost:8000/api/v1/billing/webhook

# Trigger test webhook
stripe trigger checkout.session.completed
```

## Usage Flow

### Subscription Purchase
1. Frontend calls `POST /api/v1/billing/checkout` with tier and URLs
2. Backend creates Stripe checkout session
3. User redirected to Stripe checkout page
4. After payment, Stripe redirects to success_url
5. Stripe sends `checkout.session.completed` webhook
6. Webhook handler updates user's `subscription_tier` and `stripe_customer_id`

### Subscription Management
1. Frontend calls `POST /api/v1/billing/portal` with return_url
2. Backend creates portal session
3. User redirected to Stripe customer portal
4. User can update payment method, cancel subscription, etc.
5. Changes trigger webhooks that update user record

### Status Check
1. Frontend calls `GET /api/v1/billing/subscription`
2. Backend fetches status from Stripe
3. Returns tier, status, billing period

## Webhook Events Handled

- `checkout.session.completed` → Activate subscription, save customer_id
- `customer.subscription.updated` → Update tier/status
- `customer.subscription.deleted` → Downgrade to free tier
- `invoice.payment_failed` → Trigger dunning cycle (see Dunning Service below)

## Dunning Service — Payment Failure Recovery

When a payment fails (invoice.payment_failed webhook), the system automatically initiates the dunning cycle to recover failed payments while maintaining a positive user experience.

### Overdue Payment Escalation

The dunning service manages failed payments with a 7-day grace period:

1. **Soft dunning** (retries 1-2): Amber-colored email requesting payment method update
2. **Final notice** (retry 3+): Red-colored email warning of subscription downgrade after grace period
3. **Escalation**: User automatically downgraded to free tier after 3 consecutive failures

### Key Implementation Details

**Service**: `backend/services/dunning_service.py`
**Database**: `payment_retry_history` table (migration 024)
**Notification routing**: Integrated with NotificationDispatcher (EMAIL + PUSH channels)

### Cooldown Window (24 hours)

The service enforces a 24-hour dedup window to prevent duplicate dunning emails. This is the same pattern used for price alerts:

```python
DUNNING_COOLDOWN_HOURS = 24

async def should_send_dunning(user_id, stripe_invoice_id) -> bool:
    """Return True if no dunning email sent within 24-hour window"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        text("""
            SELECT email_sent_at FROM payment_retry_history
            WHERE user_id = :user_id AND stripe_invoice_id = :invoice_id
              AND email_sent = TRUE AND email_sent_at >= :cutoff
            ORDER BY email_sent_at DESC LIMIT 1
        """),
        {"user_id": user_id, "invoice_id": stripe_invoice_id, "cutoff": cutoff},
    )
    return result.first() is None  # No recent email found
```

### Email Templates

- `dunning_soft.html`: Subject "Action Required: Update your payment method" (amber styling)
- `dunning_final.html`: Subject "Final Notice: Your subscription will be downgraded" (red styling)

Both templates include:
- User name and amount owed
- Direct link to billing settings (`/settings?tab=billing`)
- Clear action items and consequences

### Webhook Integration

The dunning service is wired into `apply_webhook_action()` for real-time processing of `invoice.payment_failed` events:

```python
# In stripe_service.py
if event.type == "invoice.payment_failed":
    invoice = event.data.object
    user = await user_repo.get_by_stripe_customer_id(invoice.customer)
    if user:
        result = await dunning_service.handle_payment_failure(
            user_id=user.id,
            stripe_invoice_id=invoice.id,
            stripe_customer_id=invoice.customer,
            amount_owed=invoice.amount_due / 100,  # Convert from cents
            currency=invoice.currency.upper(),
            user_email=user.email,
            user_name=user.name,
            user_repo=user_repo,
        )
```

Important: `invoice.amount_due` is in cents — always divide by 100 for dollar amounts.

### GHA Cron Workflow

**File**: `.github/workflows/dunning-cycle.yml`
**Schedule**: Daily 7am UTC
**Purpose**: Proactive sweep for overdue accounts beyond grace period

```bash
POST /api/v1/internal/dunning-cycle
X-API-Key: [INTERNAL_API_KEY]
```

The endpoint calls `get_overdue_accounts(grace_period_days=7)` to identify users whose most recent payment failure is older than 7 days and still on a paid tier. For each overdue account, it sends a final dunning email and escalates to free tier if needed.

### Webhook Resolution

**Important**: Invoice webhook events from Stripe do NOT include user metadata (no user_id, no customer metadata). Resolution is done via **stripe_customer_id column lookup**:

```python
# From user_repository
async def get_by_stripe_customer_id(stripe_customer_id: str) -> Optional[User]:
    result = await db.execute(
        text("SELECT * FROM public.users WHERE stripe_customer_id = :cid"),
        {"cid": stripe_customer_id},
    )
    return result.scalars().first()
```

This lookup is called in `apply_webhook_action()` every time a payment-related webhook arrives.

## Security Features

- Webhook signature verification prevents fake events
- API key authentication on checkout/portal endpoints
- Graceful degradation when Stripe not configured
- No sensitive data in logs

## Testing

```bash
# Run all Stripe tests
pytest backend/tests/test_stripe_service.py -v

# Run specific test
pytest backend/tests/test_stripe_service.py::test_create_checkout_session_success -v

# With coverage
pytest backend/tests/test_stripe_service.py --cov=services.stripe_service --cov-report=term-missing
```

## Tier Gating — Feature Access by Subscription

RateShift implements fine-grained tier gating on 7 endpoints using the `require_tier()` dependency factory.

### Tier Order

```python
_TIER_ORDER = {
    "free": 0,    # Lowest access
    "pro": 1,     # Mid-tier
    "business": 2 # Highest access
}
```

### Dependency Factory

File: `backend/api/dependencies.py`

```python
def require_tier(min_tier: str):
    """
    Factory for tier-gating dependencies.

    Args:
        min_tier: Minimum subscription tier required ('free', 'pro', or 'business')

    Returns:
        Dependency function that checks the user's subscription tier.
        Returns 403 if the user's tier is below min_tier.

    Examples:
        require_tier("pro")      — allows pro + business
        require_tier("business") — allows business only
    """
    async def check_tier(
        current_user: SessionData = Depends(get_current_user),
        db=Depends(get_db_session),
    ) -> SessionData:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT subscription_tier FROM public.users WHERE id = :id"),
            {"id": current_user.user_id},
        )
        user_tier = result.scalar_one_or_none() or "free"
        user_level = _TIER_ORDER.get(user_tier, 0)
        required_level = _TIER_ORDER.get(min_tier, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires a {min_tier.title()} or higher subscription",
            )
        return current_user

    return check_tier
```

### Gated Endpoints

**Pro Tier** (`require_tier("pro")`):
- `POST /api/v1/forecast` — ML price predictions
- `POST /api/v1/savings` — Savings calculations
- `POST /api/v1/recommendations` — Optimization recommendations

**Business Tier** (`require_tier("business")`):
- `GET /api/v1/prices/stream` — Real-time price streaming

### Free Tier Alert Limit

The free plan is limited to **1 active alert config**. Pro and Business tiers have unlimited alerts.

Implementation in `POST /api/v1/alerts` (create_alert endpoint):

```python
# Free-tier alert limit: 1 alert max
tier_result = await db.execute(
    text("SELECT subscription_tier FROM public.users WHERE id = :id"),
    {"id": current_user.user_id},
)
user_tier = tier_result.scalar_one_or_none() or "free"
if user_tier not in ("pro", "business"):
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM user_alert_configs WHERE user_id = :id"),
        {"id": current_user.user_id},
    )
    alert_count = count_result.scalar() or 0
    if alert_count >= 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Free plan limited to 1 alert. Upgrade to Pro for unlimited.",
        )
```

This check is performed inline (not via require_tier) because the limit is a soft business rule, not an endpoint restriction.

## Troubleshooting

### Webhooks Not Received
- Check webhook endpoint URL in Stripe dashboard
- Verify webhook signing secret matches environment variable
- Check server logs for signature verification errors

### Checkout Session Errors
- Verify price IDs match Stripe dashboard
- Ensure secret key is for correct mode (test vs live)
- Check that price is set to recurring billing

### Payment Failed
- Check Stripe dashboard for specific error
- Verify payment method is valid
- Check if customer has sufficient funds

## Reference

- [Stripe Checkout Docs](https://stripe.com/docs/payments/checkout)
- [Stripe Webhooks Guide](https://stripe.com/docs/webhooks)
- [Stripe Customer Portal](https://stripe.com/docs/billing/subscriptions/integrating-customer-portal)
- [Stripe Python SDK](https://stripe.com/docs/api/python)
