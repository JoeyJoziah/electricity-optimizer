# 14 - Payments, Billing & Subscription Audit

> Auditor: Claude Opus 4.6 (fintech-engineer agent)
> Date: 2026-03-18
> Scope: All Stripe integration, billing endpoints, dunning cycle, tier enforcement, checkout flow, webhook handling, and payment-related data models
> Status: **READ-ONLY AUDIT -- no files modified**

---

## Files Reviewed

| File | Purpose |
|------|---------|
| `backend/services/stripe_service.py` | Core Stripe integration (checkout, portal, webhook handling, subscription management) |
| `backend/services/dunning_service.py` | Failed payment recovery, email escalation, 7-day grace period |
| `backend/api/v1/billing.py` | Billing API endpoints (checkout, portal, subscription status, webhook) |
| `backend/api/v1/internal/billing.py` | Internal dunning-cycle cron endpoint |
| `backend/api/v1/internal/__init__.py` | Internal router with X-API-Key dependency |
| `backend/api/dependencies.py` | `require_tier()` gating, tier cache (30s TTL), `invalidate_tier_cache()` |
| `backend/models/user.py` | User model with `subscription_tier` and `stripe_customer_id` fields |
| `backend/repositories/user_repository.py` | `get_by_stripe_customer_id()` lookup, `update()` with commit |
| `backend/config/settings.py` | Stripe configuration (secret key, webhook secret, price IDs) |
| `backend/migrations/024_payment_retry_history.sql` | `payment_retry_history` table schema |
| `backend/templates/emails/dunning_soft.html` | Soft dunning email template (amber, attempt N of 3) |
| `backend/templates/emails/dunning_final.html` | Final dunning email template (red, 7-day warning) |
| `frontend/app/api/checkout/route.ts` | Next.js checkout API route (server-side proxy) |
| `frontend/app/pricing/page.tsx` | Pricing page (3 tiers) |
| `backend/tests/test_stripe_service.py` | 22 tests covering StripeService and apply_webhook_action |
| `backend/tests/test_dunning_service.py` | 16 tests covering DunningService |
| `backend/tests/test_api_billing.py` | 24 tests covering billing API endpoints |
| `backend/tests/test_internal_billing.py` | 4 tests covering internal dunning-cycle endpoint |
| `backend/tests/test_tier_gating.py` | Tier gating tests including free-tier alert limit |
| `backend/tests/test_premium_tier_gating.py` | Premium tier gating for forecast, reports, export |
| `backend/services/alert_service.py` | Free-tier 1-alert limit enforcement (lines 655-717) |

---

## P0 -- Critical Findings (must fix before launch)

### P0-01: Tier cache not invalidated on subscription change

**File**: `backend/api/dependencies.py` (line 152) and `backend/services/stripe_service.py` (line 501)
**Impact**: After a user upgrades or downgrades via Stripe webhook, the `require_tier()` dependency continues to serve the OLD tier for up to 30 seconds from both Redis and in-memory caches.

The function `invalidate_tier_cache(user_id)` is defined at `backend/api/dependencies.py:152` but is **never called anywhere in the codebase**. It is not imported or invoked from `apply_webhook_action()`, the webhook endpoint, or any other module.

```python
# backend/api/dependencies.py:152-160 -- defined but NEVER called
async def invalidate_tier_cache(user_id: str) -> None:
    """Invalidate tier cache on subscription change (call from Stripe webhook)."""
    cache_key = f"tier:{user_id}"
    _tier_cache.pop(cache_key, None)
    redis = db_manager.redis_client
    if redis:
        try:
            await redis.delete(cache_key)
        except Exception:
            pass
```

**Consequence**: A user who upgrades from Free to Pro will be blocked by `require_tier("pro")` on endpoints like `/forecast` for up to 30 seconds after the webhook fires. Similarly, a downgraded user retains paid access for up to 30 seconds. For the downgrade case, this is a minor revenue-related timing issue; for the upgrade case, it is a poor user experience that may generate support tickets.

**Fix**: Import and call `invalidate_tier_cache(user_id)` from `apply_webhook_action()` immediately after updating the user's `subscription_tier` in the database, for all three actions (`activate_subscription`, `update_subscription`, `deactivate_subscription`).

---

### P0-02: No webhook event idempotency / deduplication

**File**: `backend/api/v1/billing.py` (lines 334-422) and `backend/services/stripe_service.py` (lines 357-497)
**Impact**: Stripe may deliver the same webhook event multiple times (network retry, manual replay from the Stripe dashboard). There is no deduplication mechanism.

The webhook endpoint logs the `event_id` at line 382 but never checks whether that event has already been processed. The `apply_webhook_action()` function directly modifies user subscription state without any idempotency guard.

For the `checkout.session.completed` event, re-processing is benign (idempotent SET). However, for `invoice.payment_failed`, re-delivery causes:
1. A new row inserted into `payment_retry_history` each time (inflating `retry_count`)
2. The inflated retry count may prematurely trigger escalation (downgrade to free at count >= 3)
3. Multiple dunning emails may be sent (the 24h cooldown helps but does not cover all replay windows)

**Fix**: Track processed event IDs. Either:
- (Recommended) Store `event_id` in a `stripe_processed_events` table with a UNIQUE constraint and INSERT ... ON CONFLICT DO NOTHING before processing
- Or use Redis `SETNX` with a 72-hour TTL on the event ID as a lightweight dedup guard

---

### P0-03: Floating-point arithmetic for currency amounts

**File**: `backend/services/stripe_service.py` (line 474)
**Impact**: The cents-to-dollars conversion uses floating-point division, which can introduce rounding errors for financial amounts.

```python
# Line 474
amount_due = amount_due / 100.0  # float division
```

This value flows into `dunning_service.py` where `amount_owed` is typed as `Optional[float]` (lines 65, 309), and eventually into the `payment_retry_history` table's `NUMERIC(10,2)` column and email templates.

For the specific amounts in this system ($4.99 = 499 cents, $14.99 = 1499 cents), `499 / 100.0 = 4.99` and `1499 / 100.0 = 14.99` are exactly representable as IEEE 754 floats, so this is not currently producing incorrect values. However, it violates financial best practice and will break for amounts like $0.10 (10 cents) where `10 / 100.0` yields `0.1` which has an infinite binary representation.

**Fix**: Use `Decimal` for all currency amounts:
```python
from decimal import Decimal
amount_due = Decimal(amount_due) / Decimal("100")
```
Update `dunning_service.py` type hints to `Optional[Decimal]`.

---

## P1 -- High Severity Findings

### P1-01: No duplicate subscription guard on checkout

**File**: `backend/api/v1/billing.py` (lines 122-182)
**Impact**: A user who is already on a Pro subscription can create a new checkout session for Pro (or Business), potentially resulting in multiple active Stripe subscriptions for the same customer.

The checkout endpoint (`POST /billing/checkout`) does not verify whether the user already has an active subscription before creating a new Stripe Checkout session. While Stripe itself allows multiple subscriptions on a single customer, this application only models one `subscription_tier` per user, so only the last webhook to fire would "win" and the user might be billed for two subscriptions with only one tier reflected in the app.

```python
# Lines 141-154 -- no check for existing subscription
session_data = await stripe_service.create_checkout_session(
    user_id=current_user.user_id,
    email=user_email,
    tier=request.tier,
    ...
)
```

**Fix**: Before creating the checkout session, check if the user already has `subscription_tier != "free"` or query Stripe for active subscriptions. Return a 409 Conflict or redirect to the customer portal if the user is already subscribed.

---

### P1-02: Internal dunning-cycle endpoint leaks exception details

**File**: `backend/api/v1/internal/billing.py` (line 101)
**Impact**: The dunning-cycle endpoint includes the raw exception string in the HTTP 500 response.

```python
raise HTTPException(status_code=500, detail=f"Dunning cycle failed: {str(exc)}")
```

While this endpoint is protected by `X-API-Key` (internal use only), the exception string may contain database connection strings, SQL statements, or internal service names. Previous audit remediations specifically addressed error sanitization for internal endpoints (patterns doc notes: "test for generic message ('See server logs'), not raw exception text").

**Fix**: Return a generic error message:
```python
raise HTTPException(status_code=500, detail="Dunning cycle failed. See server logs for details.")
```

---

### P1-03: Race condition in dunning payment failure recording

**File**: `backend/services/dunning_service.py` (lines 60-105, 304-389)
**Impact**: `record_payment_failure()` first reads the retry count (line 69) and then inserts a new row with `new_count = retry_count + 1` (line 71). This is a classic read-then-write race condition.

If two `invoice.payment_failed` webhooks for the same invoice arrive concurrently (e.g., Stripe retry overlap), both calls read `retry_count = 0`, both set `new_count = 1`, and both insert rows with `retry_count = 1`. This means the escalation threshold of 3 may be reached at a different actual count than intended.

Additionally, there are no row-level locks or advisory locks used in the dunning flow, unlike the alert creation flow which correctly uses `SELECT ... FOR UPDATE`.

**Fix**: Use an atomic approach:
```sql
INSERT INTO payment_retry_history (...)
VALUES (...)
RETURNING (SELECT COUNT(*) FROM payment_retry_history WHERE stripe_invoice_id = :invoice_id) as actual_count
```
Or use `SELECT ... FOR UPDATE` on the user row before counting, similar to the pattern in `alert_service.py`.

---

### P1-04: `get_overdue_accounts` query logic may miss accounts or double-process

**File**: `backend/services/dunning_service.py` (lines 391-422)
**Impact**: The `DISTINCT ON (prh.user_id)` with `ORDER BY prh.user_id, prh.created_at DESC` selects the **most recent** payment failure for each user, but the `WHERE prh.created_at <= :cutoff` filter means it only considers failures older than 7 days.

This creates a subtlety: if a user has a failure from 10 days ago (older than cutoff) AND a more recent failure from 2 days ago (newer than cutoff), the `DISTINCT ON` combined with the WHERE clause will return the most recent failure among those that are older than the cutoff (10-day-old one), not the most recent overall. This is actually correct for the intended behavior (finding accounts where the first failure was > 7 days ago).

However, there is no check for whether the user was already processed by a previous dunning cycle run. If the cron runs daily at 7am UTC, the same overdue accounts will be found and escalated every day. The `escalate_if_needed()` method at line 292 does check `if user.subscription_tier == "free": return None`, which prevents double-downgrade but does NOT prevent repeated final dunning emails being sent on each cron cycle (the 24h cooldown in `should_send_dunning` only protects per-invoice, and the dunning cycle endpoint hardcodes `retry_count=3` bypassing that check by calling `send_dunning_email` directly rather than `handle_payment_failure`).

**Fix**: Add an `escalation_action IS NULL` condition to the `get_overdue_accounts` query to exclude accounts that have already been escalated, or add a `processed_at` column.

---

### P1-05: Webhook processing exception caught but DB transaction left uncommitted

**File**: `backend/api/v1/billing.py` (lines 383-417) and `backend/services/stripe_service.py` (line 501)
**Impact**: When `apply_webhook_action()` is called for `activate_subscription`, `update_subscription`, or `deactivate_subscription`, it modifies the user object and calls `user_repo.update()` which commits the transaction. However, if `user_repo.update()` raises an exception (caught by the broad `except Exception` at billing.py line 408), the response is still 200. The user's subscription tier in the database will NOT have been updated, but Stripe believes the event was processed.

The next time Stripe sends an event for this subscription (e.g., a renewal), the stale tier may cause incorrect behavior. There is no retry mechanism on the application side.

For the `payment_failed` action specifically, the DunningService commits the failure record at line 338 (`await self._db.commit()`), but if the email or escalation phase fails and the second commit at line 387 is skipped, the email_sent and escalation_action fields remain NULL, which is a partial failure state.

**Fix**: Consider implementing an event outbox pattern or at minimum re-queuing failed events for retry. At a bare minimum, log the event_id along with the error so it can be manually replayed.

---

## P2 -- Medium Severity Findings

### P2-01: No downgrade prevention for subscription updates with `incomplete` status

**File**: `backend/services/stripe_service.py` (lines 421-425)
**Impact**: The subscription update handler correctly preserves the paid tier for `trialing`, `past_due`, and `incomplete` statuses (only downgrading for `canceled` and `unpaid`). However, there is no explicit handling for `incomplete_expired` status, which Stripe can emit.

```python
_downgrade_statuses = {"canceled", "unpaid"}
effective_tier = "free" if status in _downgrade_statuses else (tier or "free")
```

If a `customer.subscription.updated` webhook fires with `status = "incomplete_expired"`, the user retains their paid tier despite having a dead subscription. This is a potential revenue leak (user gets free access) and creates a state mismatch between Stripe and the application.

**Fix**: Add `"incomplete_expired"` to `_downgrade_statuses`.

---

### P2-02: `subscription_tier` not validated on webhook update

**File**: `backend/services/stripe_service.py` (lines 414-441)
**Impact**: The `tier` value comes from `subscription.get("metadata", {}).get("tier")` which is a freeform string. If Stripe metadata is manually edited or corrupted, an invalid tier value (e.g., `"premium"`, `"enterprise"`, or empty string) could be written to the `users.subscription_tier` column.

The `User` Pydantic model at `backend/models/user.py:76` has a pattern validator `^(free|pro|business)$`, but `apply_webhook_action()` at line 547 directly sets `user.subscription_tier = tier or "pro"` on an already-instantiated User object, which bypasses Pydantic validation in `from_attributes` mode.

**Fix**: Validate the tier value before writing:
```python
if tier not in ("free", "pro", "business"):
    logger.error("webhook_invalid_tier", tier=tier, user_id=user_id)
    return False
```

---

### P2-03: Frontend checkout constructs server-side URLs without CSRF protection

**File**: `frontend/app/api/checkout/route.ts` (lines 32-34)
**Impact**: The frontend checkout route constructs success/cancel URLs server-side using `request.nextUrl.origin` (line 33), which is good (prevents client-supplied URL injection). However, there is no CSRF token validation on this POST endpoint. The authorization header check (Bearer token) provides reasonable protection, but in cookie-based auth scenarios, CSRF could be a concern.

```typescript
const origin = request.nextUrl.origin
const successUrl = `${origin}/dashboard?checkout=success`
const cancelUrl = `${origin}/pricing?checkout=cancelled`
```

The current implementation passes the `Authorization` header as a Bearer token (lines 8-13), which is inherently CSRF-proof since cookies are not used. This is a defensive note, not an active vulnerability.

**Recommendation**: Document that Bearer token auth is intentionally used as CSRF mitigation for this endpoint.

---

### P2-04: Amount displayed in email template lacks currency symbol localization

**File**: `backend/templates/emails/dunning_soft.html` (line 77) and `backend/templates/emails/dunning_final.html` (line 84)
**Impact**: The template hardcodes a dollar sign: `${{ amount }} {{ currency }}`. If the currency is not USD (e.g., a future international expansion), the display would be incorrect (e.g., "$14.99 EUR").

```html
<div class="amount-value">${{ amount }} {{ currency }}</div>
```

This is currently correct since all Stripe prices are in USD, but it creates a maintenance trap.

**Fix**: Use a conditional currency symbol or remove the hardcoded `$` and use the currency code with proper formatting.

---

### P2-05: `apply_webhook_action` double-fetches user for `payment_failed`

**File**: `backend/services/stripe_service.py` (lines 524-573)
**Impact**: For the `payment_failed` action, the function first fetches the user via `get_by_stripe_customer_id` (line 526) to resolve the user_id, then fetches the user AGAIN via `get_by_id` (line 541). Inside `handle_payment_failure`, the user is fetched a THIRD time by `escalate_if_needed` (line 287). This is 3 database queries for the same user in a single webhook processing path.

While not a correctness bug, this is unnecessary overhead for a webhook that may fire under load during a payment retry storm.

**Fix**: Pass the already-fetched user object through the call chain instead of re-querying.

---

### P2-06: Missing `db.commit()` in webhook handler for non-dunning actions

**File**: `backend/services/stripe_service.py` (lines 546-555) and `backend/repositories/user_repository.py` (line 226)
**Impact**: For `activate_subscription`, `update_subscription`, and `deactivate_subscription`, the `apply_webhook_action` function calls `user_repo.update()`, which internally commits the transaction at `user_repository.py:226`. This means each action is committed in its own implicit transaction.

However, since the `user_repo.update()` method creates its own commit boundary, if there were additional operations after the update call (there currently are not), they would be in a new implicit transaction. The pattern is not transactionally unsafe today but is fragile.

**Note**: The DunningService path has explicit double-commit (lines 338 and 387), which is intentional to ensure the failure record is persisted before attempting email delivery.

---

### P2-07: Subscription status endpoint queries Stripe API on every call

**File**: `backend/api/v1/billing.py` (lines 259-321) and `backend/services/stripe_service.py` (lines 212-269)
**Impact**: `GET /billing/subscription` makes a live Stripe API call (`stripe.Subscription.list`) on every request. This is both slow (200-500ms latency to Stripe) and can hit Stripe rate limits under load.

The subscription status is also available in the local `users.subscription_tier` column, but the endpoint does not use it. The local column is updated by webhooks, so it should be authoritative for the tier. The Stripe API call provides additional data (period end date, cancel_at_period_end) not stored locally.

**Fix**: Consider caching the subscription details in Redis with a 5-minute TTL, or at minimum returning the local `subscription_tier` immediately and enriching with Stripe data asynchronously.

---

## P3 -- Low Severity / Informational Findings

### P3-01: StripeService instantiated per-request in billing endpoints

**File**: `backend/api/v1/billing.py` (lines 133, 208, 268, 347)
**Impact**: Each endpoint creates a new `StripeService()` instance, which sets `stripe.api_key` globally every time (line 36 of `stripe_service.py`). This is functionally fine since the key is always the same, but it is unnecessary overhead and the global state mutation is a code smell.

**Recommendation**: Use a singleton or dependency injection pattern for `StripeService`.

---

### P3-02: `plan` parameter alias on `create_checkout_session` not validated

**File**: `backend/services/stripe_service.py` (lines 95-97)
**Impact**: The `plan` parameter is accepted as an alias for `tier`, but if both are provided, `tier` takes precedence silently. This is documented behavior (`if plan is not None and tier is None: tier = plan`) and currently only the billing API uses `tier`, so this is a minor inconsistency.

---

### P3-03: No monitoring/alerting on repeated webhook processing failures

**File**: `backend/api/v1/billing.py` (lines 400-417)
**Impact**: When webhook processing fails (caught by the broad `except` blocks), `logger.exception()` is called but no metric is incremented and no alert is fired. The application relies entirely on log monitoring to detect webhook processing failures.

For a payment system, webhook processing failures should increment a counter metric and trigger an alert if the failure rate exceeds a threshold.

**Recommendation**: Add a Prometheus counter or Sentry breadcrumb for webhook processing failures.

---

### P3-04: Pricing page CTA labels inconsistent with actual tier behavior

**File**: `frontend/app/pricing/page.tsx` (lines 10-67)
**Impact**: The Pro tier CTA says "Start Free Trial" (line 45) but there is no trial period configured in the Stripe integration. The Business tier CTA says "Contact Sales" (line 64) but the href links to the signup page with `?plan=business` (line 65), which suggests self-service.

These are UX/marketing issues, not technical bugs.

---

### P3-05: `payment_retry_history` table has no index on `(user_id, email_sent, email_sent_at)`

**File**: `backend/migrations/024_payment_retry_history.sql` (lines 39-46)
**Impact**: The `should_send_dunning()` query at `dunning_service.py:128-145` queries by `user_id`, `stripe_invoice_id`, `email_sent`, and `email_sent_at`. The existing index `idx_payment_retry_user_invoice` covers `(user_id, stripe_invoice_id)`, which should be sufficient for the query planner to use, but the additional predicates on `email_sent` and `email_sent_at` are not indexed.

At the current scale (low volume payment failures), this is not a performance concern. It would only matter with tens of thousands of payment failure records per user, which is unrealistic.

---

### P3-06: `allow_promotion_codes=True` on checkout session

**File**: `backend/services/stripe_service.py` (line 142)
**Impact**: Promotion codes are enabled on the checkout session. This is a business decision, not a security issue, but it means any valid Stripe coupon code will be accepted. Ensure the Stripe dashboard has appropriate coupon restrictions configured.

---

### P3-07: Test coverage gap: `customer.subscription.updated` with terminal states

**File**: `backend/tests/test_stripe_service.py` (lines 363-388)
**Impact**: The only test for `customer.subscription.updated` uses `status: "active"`. There are no tests for the `_downgrade_statuses` logic with `status: "canceled"` or `status: "unpaid"`. The logic at `stripe_service.py:424-425` is critical for preventing unintended tier downgrades during `past_due` or `trialing` states.

**Recommendation**: Add test cases for all subscription states (`canceled`, `unpaid`, `past_due`, `trialing`, `incomplete`, `incomplete_expired`).

---

### P3-08: `BILLING_URL` hardcoded in dunning service

**File**: `backend/services/dunning_service.py` (line 32)
**Impact**: The billing URL in dunning emails is hardcoded to `https://rateshift.app/settings?tab=billing`. This should come from a configuration setting to support staging/preview environments.

---

### P3-09: No refund handling implemented

**File**: All billing files reviewed
**Impact**: There is no endpoint, webhook handler, or service method for processing refunds. The Stripe events `charge.refunded` and `charge.refund.updated` are not handled. If a refund is issued through the Stripe dashboard, the user's tier will not change automatically.

This may be intentional (manual refund handling via Stripe dashboard), but should be documented.

---

### P3-10: No `checkout.session.expired` webhook handler

**File**: `backend/services/stripe_service.py` (lines 357-497)
**Impact**: If a user starts checkout but abandons it, Stripe fires `checkout.session.expired` after 24 hours. This event is not handled. While no action is strictly required (no state was changed in the database when the session was created), tracking abandoned checkouts is valuable for conversion analytics.

---

## Summary

| Severity | Count | Key Theme |
|----------|-------|-----------|
| **P0** | 3 | Tier cache never invalidated, no webhook idempotency, floating-point currency |
| **P1** | 5 | No duplicate subscription guard, error detail leakage, dunning race conditions, stale overdue query, uncommitted transactions |
| **P2** | 7 | Missing `incomplete_expired` handling, unvalidated tier metadata, double user fetch, per-request Stripe queries |
| **P3** | 10 | Singleton pattern, test gaps, hardcoded URLs, no refund handling, informational |

### What Is Done Well

1. **Webhook signature verification** (P0 pass): Properly uses `stripe.Webhook.construct_event()` with the webhook signing secret. Invalid signatures return 400, preventing processing of tampered payloads.

2. **Webhook error resilience**: Post-signature-verification errors return 200 to Stripe (preventing infinite retries) while logging the error via `logger.exception()` for monitoring. This is explicitly tested in 3 test cases.

3. **Redirect URL domain allowlist**: Both `success_url` and `cancel_url` are validated against an allowlist (`rateshift.app`, `localhost`) using Pydantic field validators. Frontend checkout route constructs URLs server-side, never trusting client input.

4. **Free-tier alert limit enforcement**: Uses `SELECT ... FOR UPDATE` on the user row to prevent race conditions when checking the 1-alert limit for free-tier users. This is an atomic, correct implementation.

5. **Subscription state machine logic**: The `_downgrade_statuses` set correctly preserves paid access during `trialing`, `past_due`, and `incomplete` states (Stripe's grace periods), only forcing free for terminal states.

6. **PCI compliance**: No credit card data is stored or processed by the application. All payment processing is delegated to Stripe Checkout (hosted), and the customer portal is used for payment method updates.

7. **Internal endpoint protection**: The dunning-cycle endpoint is protected by `verify_api_key` dependency at the router level, and internal endpoints are excluded from the `RequestTimeoutMiddleware`.

8. **Dunning email cooldown**: 24-hour cooldown window prevents duplicate dunning emails for the same invoice, with both DB-level and dispatcher-level deduplication.

9. **Payment failed user resolution**: The `payment_failed` webhook correctly resolves the user via `stripe_customer_id` since invoices don't carry `user_id` metadata.

10. **Comprehensive test coverage**: 66 total tests across 4 test files covering all major billing flows, error cases, authentication requirements, and edge cases.

### Recommended Priority Order

1. **P0-01** (tier cache invalidation) -- Quick fix, one function call addition
2. **P0-02** (webhook idempotency) -- Requires a new table or Redis key, but straightforward
3. **P1-01** (duplicate subscription guard) -- Important for revenue protection
4. **P2-01** (`incomplete_expired` handling) -- One-line fix
5. **P2-02** (tier validation on webhook) -- Three-line guard
6. **P0-03** (Decimal for currency) -- Broader refactor, lower immediate risk
7. **P1-02** (error detail leakage) -- One-line fix
8. **P1-03** (dunning race condition) -- Requires SQL refactor
9. **P1-04** (overdue accounts re-processing) -- Query change
10. **P3-07** (test coverage gaps) -- Testing improvement
