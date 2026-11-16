# Audit Report: Payments & Billing

**Date:** 2026-03-19
**Scope:** Stripe integration, webhooks, tier gating, dunning, checkout flow
**Files Reviewed:**

- `backend/services/stripe_service.py`
- `backend/services/dunning_service.py`
- `backend/services/referral_service.py`
- `backend/services/maintenance_service.py`
- `backend/services/kpi_report_service.py`
- `backend/services/alert_service.py`
- `backend/api/v1/billing.py`
- `backend/api/v1/webhooks.py`
- `backend/api/v1/alerts.py`
- `backend/api/v1/agent.py`
- `backend/api/v1/internal/billing.py`
- `backend/api/v1/internal/operations.py`
- `backend/api/v1/user.py`
- `backend/api/v1/users.py`
- `backend/api/dependencies.py`
- `backend/config/settings.py`
- `backend/models/user.py`
- `backend/repositories/user_repository.py`
- `backend/migrations/init_neon.sql`
- `backend/migrations/004_performance_indexes.sql`
- `backend/migrations/024_payment_retry_history.sql`
- `backend/migrations/037_additional_performance_indexes.sql`
- `backend/migrations/054_stripe_processed_events.sql`
- `backend/.env.example`
- `backend/STRIPE_INTEGRATION.md`
- `backend/tests/test_api_billing.py`
- `backend/tests/test_stripe_service.py`
- `backend/tests/test_dunning_service.py`
- `backend/tests/test_tier_gating.py`
- `backend/tests/test_premium_tier_gating.py`
- `frontend/app/api/checkout/route.ts`
- `frontend/app/pricing/page.tsx`
- `frontend/e2e/billing-flow.spec.ts`

---

## Summary Table

| ID | Severity | Title | File(s) |
|----|----------|-------|---------|
| P0-1 | P0 Critical | Webhook Idempotency Race Condition — Committed Event May Not Be Processed | `backend/api/v1/billing.py:386-452` |
| P0-2 | P0 Critical | No UNIQUE Constraint on `stripe_customer_id` Column | `backend/migrations/init_neon.sql`, `004_performance_indexes.sql`, `037_additional_performance_indexes.sql` |
| P1-1 | P1 High | Missing Webhook Event Types — No Handler for `invoice.payment_succeeded` or `charge.dispute.created` | `backend/services/stripe_service.py:394-506` |
| P1-2 | P1 High | No Refund Handling Anywhere in the Codebase | Entire `backend/` directory |
| P1-3 | P1 High | Global `stripe.api_key` Assignment Is Not Thread-Safe | `backend/services/stripe_service.py:38` |
| P1-4 | P1 High | Dunning Escalation Not Reversible — No Recovery Path After Tier Downgrade | `backend/services/dunning_service.py:276-305` |
| P1-5 | P1 High | MRR Calculation Uses Hardcoded Prices — Will Desync If Prices Change | `backend/services/kpi_report_service.py:120` |
| P2-1 | P2 Medium | Frontend Checkout Route Proxies Backend Error Details to Client | `frontend/app/api/checkout/route.ts:53` |
| P2-2 | P2 Medium | Webhook Endpoint Always Returns 200 Even on Processing Failure | `backend/api/v1/billing.py:373-457` |
| P2-3 | P2 Medium | `payment_retry_history` Uses Counter-Based Escalation Instead of Invoice-Level Tracking | `backend/services/dunning_service.py:61-106` |
| P2-4 | P2 Medium | Redirect Domain Validation Allows Subdomain Bypass | `backend/api/v1/billing.py:38-48` |
| P2-5 | P2 Medium | `StripeService` Instantiated Per-Request Without Dependency Injection | `backend/api/v1/billing.py:128,203,263,342` |
| P2-6 | P2 Medium | Tier Cache 30-Second TTL Creates a Window for Post-Downgrade Feature Access | `backend/api/dependencies.py:96-97` |
| P2-7 | P2 Medium | Migration 054 GRANT Statement Not Wrapped in Exception Handler | `backend/migrations/054_stripe_processed_events.sql:70` |
| P3-1 | P3 Low | No Currency Validation on Checkout Flow | `backend/services/stripe_service.py:68-168` |
| P3-2 | P3 Low | `get_subscription_status` Uses `status="all"` With `limit=1` — May Return Stale Subscription | `backend/services/stripe_service.py:240-244` |
| P3-3 | P3 Low | Pricing Page CTA Says "Start Free Trial" But No Trial Is Configured | `frontend/app/pricing/page.tsx:45` |
| P3-4 | P3 Low | Referral Service Reward Redemption Is Not Implemented | `backend/services/referral_service.py:6` |
| P3-5 | P3 Low | `_calculate_mrr` Uses Float Arithmetic — Minor Precision Concern | `backend/services/kpi_report_service.py:120` |
| P3-6 | P3 Low | Dunning Service Creates New `EmailService()` Instance Per Call | `backend/services/dunning_service.py:58` |

**Total Findings:** 20 (2 P0, 5 P1, 7 P2, 6 P3)

**Estimated Remediation Effort:**
- P0 fixes: 1-2 days (transaction restructuring + ALTER TABLE)
- P1 fixes: 3-5 days (new webhook handlers + reconciliation job + DI refactor)
- P2 fixes: 2-3 days (incremental improvements)
- P3 fixes: 1-2 days (housekeeping)

---

## P0 — Critical (Fix Immediately)

### P0-1: Webhook Idempotency Race Condition — Committed Event May Not Be Processed

**File:** `backend/api/v1/billing.py`, lines 386-452

The idempotency guard commits the `stripe_processed_events` insert at line 395 **before** the actual business logic runs at lines 418-433. If the processing (`handle_webhook_event` or `apply_webhook_action`) fails after the commit, the event is marked as "processed" in the idempotency table but the subscription change was never applied. On the next Stripe retry delivery, the idempotency guard at line 397 will detect `rowcount == 0` and silently skip the event as a "duplicate," permanently dropping it.

This creates a scenario where a user pays successfully but their subscription is never activated, or a cancellation is never applied. The current `except Exception` block at line 443 logs but does not rollback the idempotency record.

**Recommendation:** Either (a) wrap the idempotency insert and business logic in a single transaction so they commit together, or (b) delete the idempotency record from `stripe_processed_events` when processing fails, allowing Stripe to retry.

---

### P0-2: No UNIQUE Constraint on `stripe_customer_id` Column

**Files:**
- `backend/migrations/init_neon.sql` (users table definition)
- `backend/migrations/004_performance_indexes.sql`, lines 10-12
- `backend/migrations/037_additional_performance_indexes.sql`, lines 19-21

The `stripe_customer_id` column on the `users` table has a partial index (WHERE NOT NULL) but no UNIQUE constraint. This means two different user rows could have the same `stripe_customer_id` value. The `get_by_stripe_customer_id` method at `backend/repositories/user_repository.py` line 418 uses `result.mappings().first()`, which silently picks the first match. If a Stripe customer ID is erroneously associated with two users, `invoice.payment_failed` webhooks could downgrade the wrong user, or `checkout.session.completed` could activate the wrong subscription.

**Recommendation:** Add a UNIQUE constraint:

```sql
ALTER TABLE users ADD CONSTRAINT uq_users_stripe_customer_id UNIQUE (stripe_customer_id);
```

NULLs are excluded from unique checks in PostgreSQL, so free-tier users without a customer ID are unaffected.

---

## P1 — High (Fix This Sprint)

### P1-1: Missing Webhook Event Types — No Handler for `invoice.payment_succeeded` or `charge.dispute.created`

**File:** `backend/services/stripe_service.py`, lines 394-506

The webhook handler processes exactly four event types: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, and `invoice.payment_failed`. Critical events are not handled:

- **`invoice.payment_succeeded`**: After a dunning cycle recovers a failed payment, there is no handler to re-activate the subscription or clear the dunning state. If the user was downgraded to free after 3 failures (line 298 of `dunning_service.py`), a subsequent successful payment via Stripe's automatic retry will not restore their tier.
- **`charge.dispute.created` / `charge.dispute.closed`**: No dispute/chargeback handling. A disputed charge should immediately flag the account.
- **`customer.subscription.paused`**: If subscription pause is enabled in Stripe's billing portal, the system has no handler.

**Recommendation:** Add handlers for `invoice.payment_succeeded` (re-activate tier + clear dunning state), `charge.dispute.created` (flag account), and `customer.subscription.paused` (preserve tier but restrict access).

---

### P1-2: No Refund Handling Anywhere in the Codebase

**Files:** Entire `backend/` directory (grep for `refund`, `charge_back`, `chargeback`, `dispute` returns zero results in application code)

There is no refund processing logic. If a subscription is refunded through the Stripe dashboard, the system will not be notified (no `charge.refunded` webhook handler). The user could retain their paid tier indefinitely after a full refund.

**Recommendation:** Add a handler for `charge.refunded` webhook events that checks if the refund amount covers the subscription price and, if so, downgrades the user or flags the account for manual review.

---

### P1-3: Global `stripe.api_key` Assignment Is Not Thread-Safe

**File:** `backend/services/stripe_service.py`, line 38

```python
stripe.api_key = settings.stripe_secret_key
```

The Stripe SDK uses a module-level global `stripe.api_key`. Every `StripeService()` instantiation (which happens per-request at `backend/api/v1/billing.py` lines 128, 203, 263, 342) overwrites this global. Under gunicorn with multiple workers and `asyncio.to_thread` (lines 122, 192, 240, 296, 302), concurrent requests could race on this global state. While the key is always the same value from settings, this pattern is fragile: if the key were ever rotated during a rolling deployment, in-flight requests could use the wrong key.

**Recommendation:** Use the per-request `stripe_client` object introduced in Stripe SDK v7+ instead of the global `stripe.api_key`, or set the key exactly once at application startup rather than per-request.

---

### P1-4: Dunning Escalation Not Reversible — No Recovery Path After Tier Downgrade

**File:** `backend/services/dunning_service.py`, lines 276-305

When `escalate_if_needed` fires at 3+ failures, it sets `user.subscription_tier = "free"` at line 298 and persists it. However, if Stripe successfully retries the payment later (Stripe retries for up to 7 days), there is no code path to re-promote the user. The Stripe subscription remains active on Stripe's side, but the user is on the free tier in the application. This creates an inconsistency where the user is paying but not receiving paid features.

**Recommendation:** Tie the escalation to `customer.subscription.updated` with status `unpaid` or `canceled` from Stripe rather than using a local retry counter. Alternatively, add an `invoice.payment_succeeded` handler that restores the tier (see P1-1).

---

### P1-5: MRR Calculation Uses Hardcoded Prices — Will Desync If Prices Change

**File:** `backend/services/kpi_report_service.py`, line 120

```python
return round(pro_count * 4.99 + business_count * 14.99, 2)
```

Prices $4.99 and $14.99 are hardcoded rather than fetched from Stripe or from a central configuration. If pricing changes in Stripe, the KPI report will silently produce incorrect MRR figures.

**Recommendation:** Fetch active price amounts from Stripe's Price API or store canonical prices in a shared constant/config that is also used by the pricing page and KPI calculator.

---

## P2 — Medium (Fix Soon)

### P2-1: Frontend Checkout Route Proxies Backend Error Details to Client

**File:** `frontend/app/api/checkout/route.ts`, line 53

```typescript
const safeError = typeof data?.detail === 'string' ? data.detail : 'Checkout failed'
```

While this does type-check for string, it forwards the raw `detail` field from the backend response to the client. Backend errors like `"Price ID for tier 'pro' not configured. Set STRIPE_PRICE_PRO environment variable."` could leak environment variable names. The backend sanitizes at `backend/api/v1/billing.py` line 165 to a generic message, but if the backend error sanitization is ever relaxed, the frontend proxy would pass through internal details.

**Recommendation:** Maintain an allowlist of safe error strings on the frontend side rather than forwarding arbitrary backend detail strings.

---

### P2-2: Webhook Endpoint Always Returns 200 Even on Processing Failure

**File:** `backend/api/v1/billing.py`, lines 373-457

The design decision to always return 200 to Stripe (documented in the comment at line 373-376) means Stripe will never retry a failed event. Combined with P0-1 (idempotency record already committed), a transient DB failure during `apply_webhook_action` at line 433 will permanently lose the event. The comments acknowledge this risk but rely on "internal monitoring / alerting" at line 446 — however, there is no evidence of a dead-letter queue, compensating scheduled job, or reconciliation process that would catch and replay dropped events.

**Recommendation:** Implement a reconciliation job that periodically compares Stripe subscription states with local `subscription_tier` values and corrects any drift. Alternatively, return 500 for processing errors so Stripe retries, but remove the idempotency commit from before the processing step (fixing P0-1).

---

### P2-3: `payment_retry_history` Uses Counter-Based Escalation Instead of Invoice-Level Tracking

**File:** `backend/services/dunning_service.py`, lines 61-106

`get_retry_count` at line 108 counts ALL rows for a given `stripe_invoice_id`. Each call to `record_payment_failure` inserts a new row and increments the count. However, Stripe sends `invoice.payment_failed` events per-attempt on the same invoice, AND can create new invoices for subsequent billing cycles. If a user fails payment on invoice A (3 attempts, escalated), then pays successfully, then fails on invoice B, the first failure on invoice B starts at count 1 (correct). But if the same invoice A is retried by Stripe 4 times before the code sees it, the counter could jump past the escalation threshold on the first processing.

More critically, the `should_send_dunning` check at line 119 uses both `user_id` AND `stripe_invoice_id`, but `get_retry_count` only uses `stripe_invoice_id`. This means the cooldown applies per-invoice but escalation applies per-invoice — which is correct but could confuse operators reviewing the data.

**Recommendation:** Add a column like `escalation_applied` to the `payment_retry_history` table to explicitly track whether escalation was performed for a given invoice, preventing re-escalation on duplicate webhook deliveries that get past the idempotency guard.

---

### P2-4: Redirect Domain Validation Allows Subdomain Bypass

**File:** `backend/api/v1/billing.py`, lines 38-48

```python
if not any(hostname == d or hostname.endswith(f".{d}") for d in allowed):
```

The default allowed domains include `"localhost"` (from `backend/config/settings.py` line 154). The `endswith` check means any hostname ending in `.localhost` (e.g., `evil.localhost`) would pass validation. While `.localhost` is not a routable TLD in practice, the pattern is fragile. More concerning: if someone adds a short domain like `"app"` to the allowlist, any `*.app` domain would match.

**Recommendation:** Use exact domain matching or a proper URL validation library. Remove `localhost` from the production allowlist entirely (the frontend checkout route at `frontend/app/api/checkout/route.ts` line 33 constructs URLs server-side, so backend redirect validation is a defense-in-depth layer).

---

### P2-5: `StripeService` Instantiated Per-Request Without Dependency Injection

**File:** `backend/api/v1/billing.py`, lines 128, 203, 263, 342

`StripeService()` is instantiated inline in every endpoint handler with no DI or singleton pattern. This makes testing harder (tests must patch the class), creates unnecessary overhead (logging "stripe_service_initialized" on every request), and makes it impossible to inject different configurations for different contexts.

**Recommendation:** Create a FastAPI dependency `get_stripe_service()` that returns a singleton or scoped instance, consistent with how `get_price_service()` and other services are managed in `backend/api/dependencies.py`.

---

### P2-6: Tier Cache 30-Second TTL Creates a Window for Post-Downgrade Feature Access

**File:** `backend/api/dependencies.py`, lines 96-97

```python
_TIER_CACHE_TTL = 30  # seconds
```

While the cache is invalidated on webhook actions (line 145-154), there is a 30-second window where a user whose subscription was just canceled via the Stripe portal could still access paid features. The invalidation fires only after `apply_webhook_action` completes. If the webhook is delayed (Stripe does not guarantee delivery latency), the window could be minutes.

This is noted as a known design tradeoff in the codebase (CLAUDE.md: "Tier cache: 30s TTL... cache self-heals within 30s"), but for business-critical tier gating on API endpoints that stream data (`/prices/stream`), this could be abused.

**Recommendation:** For business-tier endpoints, consider a real-time check as a fallback for requests that would incur significant cost (e.g., SSE streaming).

---

### P2-7: Migration 054 GRANT Statement Not Wrapped in Exception Handler

**File:** `backend/migrations/054_stripe_processed_events.sql`, line 70

```sql
GRANT ALL ON stripe_processed_events TO neondb_owner;
```

Unlike migration 024 (lines 53-58) which wraps the GRANT in a `DO $$ BEGIN ... EXCEPTION WHEN undefined_object THEN ... END $$;` block, migration 054 uses a bare GRANT. If the `neondb_owner` role does not exist in the target environment, the migration will fail.

**Recommendation:** Wrap the GRANT in a PL/pgSQL exception handler consistent with other migrations.

---

## P3 — Low / Housekeeping

### P3-1: No Currency Validation on Checkout Flow

**File:** `backend/services/stripe_service.py`, lines 68-168

The checkout session creation relies entirely on the Stripe Price ID (which has a fixed currency). There is no explicit currency handling or validation in the RateShift codebase. This is fine as long as all prices are USD, but the system accepts and stores currency codes in `payment_retry_history` (migration 024, line 28: `currency VARCHAR(10) NOT NULL DEFAULT 'USD'`). If Stripe is configured with a non-USD price, the dunning emails at `dunning_service.py` line 194 would display `{amount:.2f}` without proper currency formatting (e.g., "4.99 EUR" formatted as "4.99" with no symbol).

**Recommendation:** Add currency-aware formatting in dunning email templates. Consider validating that the configured Stripe Price IDs use USD.

---

### P3-2: `get_subscription_status` Uses `status="all"` With `limit=1` — May Return Stale Subscription

**File:** `backend/services/stripe_service.py`, lines 240-244

```python
subscriptions = await asyncio.to_thread(
    stripe.Subscription.list,
    customer=customer_id,
    status="all",
    limit=1,
)
```

This fetches the most recent subscription regardless of status. If a customer canceled one subscription and created a new one, `limit=1` returns the newest, which is correct. However, `status="all"` means a canceled subscription could be returned if it is the most recent entry. The code then exposes this canceled status through the API, which is appropriate for display purposes but could confuse frontend logic.

**Recommendation:** Consider filtering by `status="active"` first, falling back to `status="all"` only if no active subscription is found, to present the most relevant subscription.

---

### P3-3: Pricing Page CTA Says "Start Free Trial" But No Trial Is Configured

**File:** `frontend/app/pricing/page.tsx`, line 45

```typescript
cta: 'Start Free Trial',
```

The Pro tier CTA reads "Start Free Trial" but the checkout session creation at `backend/services/stripe_service.py` line 122-146 does not include `subscription_data.trial_period_days` or `subscription_data.trial_settings`. Users clicking this CTA will be immediately charged $4.99.

**Recommendation:** Either implement a free trial period in the checkout session or change the CTA text to "Subscribe to Pro" / "Get Pro" to accurately reflect the billing behavior.

---

### P3-4: Referral Service Reward Redemption Is Not Implemented

**File:** `backend/services/referral_service.py`, line 6

```python
"""Reward redemption deferred to Wave 3 (Stripe integration)."""
```

The `complete_referral` method (line 126) sets `reward_applied = TRUE` and `status = 'completed'` but does not actually apply any reward (e.g., extending a trial, applying a Stripe coupon, or crediting the account). This is documented as deferred work.

**Recommendation:** Track this as a product backlog item. Consider whether the `reward_applied = TRUE` flag is misleading in its current state.

---

### P3-5: `_calculate_mrr` Uses Float Arithmetic — Minor Precision Concern

**File:** `backend/services/kpi_report_service.py`, line 120

```python
return round(pro_count * 4.99 + business_count * 14.99, 2)
```

Float multiplication of monetary values can introduce rounding errors at scale (e.g., `100000 * 4.99 = 499000.00000000006`). The `round()` call mitigates this for typical counts, but using `Decimal` would be more precise.

**Recommendation:** Use `Decimal("4.99")` and `Decimal("14.99")` for MRR calculation, consistent with how `amount_due` is handled in `stripe_service.py` lines 480-482.

---

### P3-6: Dunning Service Creates New `EmailService()` Instance Per Call

**File:** `backend/services/dunning_service.py`, line 58

```python
self._email_service = email_service or EmailService()
```

When called from `apply_webhook_action` at `backend/services/stripe_service.py` line 582, `DunningService(db)` is instantiated without an `email_service`, creating a new `EmailService()` per webhook. This is functional but wasteful.

**Recommendation:** Pass the `EmailService` via dependency injection or use a singleton pattern.

---

## Files With No Issues Found

- `backend/api/v1/webhooks.py` — GitHub webhook handler uses proper HMAC-SHA256 with constant-time comparison. Not related to Stripe payments.
- `backend/models/user.py` — User model properly validates `subscription_tier` with regex pattern `^(free|pro|business)$` at line 78. GDPR consent fields are correctly required at registration.
- `backend/api/v1/user.py` — User preferences endpoint does not expose `stripe_customer_id` or `subscription_tier` in responses.
- `backend/api/v1/users.py` — Profile endpoint does not expose any billing-related fields.
- `backend/tests/test_tier_gating.py` — Comprehensive tier-gating tests cover free/pro/business for all 8 gated endpoints including edge cases (None tier treated as free).
- `backend/tests/test_premium_tier_gating.py` — Additional tier-gating tests for forecast, reports, and export endpoints.
- `backend/tests/test_dunning_service.py` — Thorough tests including dispatcher integration, cooldown enforcement, and escalation logic.
- `backend/tests/test_stripe_service.py` — Good coverage of all webhook event types, Decimal currency conversion, tier cache invalidation, and edge cases.
- `backend/migrations/024_payment_retry_history.sql` — Clean migration with proper FK constraints, indexes, and GRANT wrapping.
- `frontend/e2e/billing-flow.spec.ts` — E2E tests cover pricing page display, CTA links, upgrade flow, subscribed user access, and Stripe-unconfigured graceful degradation.
- `backend/api/dependencies.py` — `require_tier()` correctly uses `_TIER_ORDER` dict for comparison, supports `get_current_user` chain, uses Redis+in-memory dual cache with proper TTL.
- `backend/config/settings.py` — Stripe key validation enforces `sk_` prefix in production (line 354), validates JWT_SECRET strength, and ensures internal API key differs from JWT secret.
- `backend/services/alert_service.py` — Free-tier alert limit uses `SELECT ... FOR UPDATE` at line 705 for atomic race-condition-safe enforcement.

---

## Critical Architecture Strengths

- Webhook signature verification is correctly implemented using Stripe's SDK (`stripe.Webhook.construct_event`).
- Redirect URL domain validation prevents open-redirect attacks on checkout/portal flows.
- Frontend checkout route constructs redirect URLs server-side (line 33-34 of `route.ts`), never trusting client-supplied URLs.
- Tier gating uses a database query with Redis caching and proper invalidation on subscription changes.
- Free-tier alert limit uses `SELECT ... FOR UPDATE` for atomic enforcement, preventing TOCTOU race conditions.
- Subscription status changes for `trialing`, `past_due`, and `incomplete` correctly preserve the user's paid tier rather than prematurely downgrading.
- Idempotency table exists with proper cleanup (72-hour retention via maintenance job).
- Error messages in billing API responses are sanitized — no internal details leak to clients.
- `UserResponse` schema (line 201 of `models/user.py`) correctly excludes `stripe_customer_id` and `subscription_tier`.
- Constant-time comparison (`hmac.compare_digest`) is used for API key verification.

---

## Key Risk Areas

1. **Event loss risk (P0-1):** The idempotency-commit-before-process pattern creates a permanent event loss window. This is the highest priority fix.
2. **Data integrity (P0-2):** Missing UNIQUE constraint on `stripe_customer_id` could cause cross-user subscription corruption.
3. **Incomplete lifecycle (P1-1, P1-2, P1-4):** Missing handlers for payment recovery, refunds, and disputes leave gaps in the subscription lifecycle that could result in users paying without access or retaining access after refund.
4. **Pricing page misrepresentation (P3-3):** "Start Free Trial" CTA with no trial configured is a minor legal/trust concern.
