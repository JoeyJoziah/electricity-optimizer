# Stripe Monetization Integration

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
- `invoice.payment_failed` → Log warning, notify user (TODO)

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

## TODO for Production

1. **Database Integration**:
   - Update webhook handler to modify user records in database
   - Implement user repository methods for subscription updates

2. **Email Notifications**:
   - Send confirmation on subscription activation
   - Alert on payment failure
   - Reminder before trial ends

3. **Feature Gating**:
   - Create middleware/dependency to check subscription tier
   - Restrict endpoints based on tier (e.g., /api/v1/forecast requires Pro+)

4. **Billing History**:
   - Add endpoint to fetch invoices from Stripe
   - Display in user dashboard

5. **Usage Tracking**:
   - Track API calls for Business tier
   - Implement rate limits per tier

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
