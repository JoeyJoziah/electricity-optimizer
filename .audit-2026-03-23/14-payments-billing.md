# Audit Report: Payments & Billing
**Date:** 2026-03-23
**Scope:** Stripe integration, webhooks, dunning, tier management
**Files Reviewed:**
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/stripe_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/billing.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/dunning_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/v1/internal/billing.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/api/dependencies.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/settings.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/models/user.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/repositories/user_repository.py` (lines 410-430)
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/maintenance_service.py` (lines 135-161)
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/024_payment_retry_history.sql`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/054_stripe_processed_events.sql`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/056_stripe_customer_id_unique.sql`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_stripe_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_api_billing.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_dunning_service.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_webhook_payment_integrity.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_internal_billing.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_premium_tier_gating.py`
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_integration_paths.py` (lines 1-275)
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_webhooks.py`

---

## P0 -- Critical (Fix Immediately)

### 14-P0-1: `invoice.payment_succeeded` and `charge.refunded` / `charge.dispute.created` have no user_id resolution via `stripe_customer_id`

**File:** `backend/services/stripe_service.py`, lines 665-681
**Impact:** Silent data loss -- payment_succeeded, charge_refunded, and dispute_created webhook events will be silently dropped if the Stripe event metadata does not contain a `user_id`.

The `apply_webhook_action()` function has a special user_id resolution path for `payment_failed` events (line 669):

```python
if not user_id and action == "payment_failed" and result.get("customer_id"):
    resolved = await user_repo.get_by_stripe_customer_id(customer_id_for_lookup)
```

However, this resolution is **only** triggered when `action == "payment_failed"`. The following actions also originate from Stripe events that may not carry `user_id` in their metadata:

- `payment_succeeded` -- comes from `invoice.payment_succeeded`, and Stripe invoices do NOT carry subscription metadata `user_id` by default. The `handle_webhook_event` at line 530 extracts `user_id` from `data.object`, but invoices have no `metadata.user_id`. This means `result["user_id"]` will be `None`, the special resolution block is skipped (it only fires for `payment_failed`), and the handler silently returns `False` at line 681.
- `charge_refunded` -- comes from `charge.refunded`, and Stripe charges do NOT carry `user_id` metadata. Same silent drop.
- `dispute_created` -- comes from `charge.dispute.created`, same issue. The code at line 598 even acknowledges disputes "may not have direct customer" but does not resolve via customer_id at the apply stage.

**Why this is P0:** After a dunning cycle downgrades a user to free tier, a successful payment retry by Stripe fires `invoice.payment_succeeded`. If the user_id cannot be resolved (which it cannot, since invoices lack user metadata), the tier restoration at lines 741-787 never executes. The user remains on the free tier despite paying. This is a revenue-impacting bug that silently eats successful payments.

**Fix:** Extend the customer_id resolution block at lines 669-679 to also cover `payment_succeeded`, `charge_refunded`, and `dispute_created` actions. Replace the condition:

```python
if not user_id and action == "payment_failed" and result.get("customer_id"):
```

with:

```python
_RESOLVE_VIA_CUSTOMER = {"payment_failed", "payment_succeeded", "charge_refunded", "dispute_created"}
if not user_id and action in _RESOLVE_VIA_CUSTOMER and result.get("customer_id"):
```

### 14-P0-2: Dunning `handle_payment_failure` commits the DB session inside the orchestrator, conflicting with the webhook handler's own commit

**File:** `backend/services/dunning_service.py`, line 341 and line 390
**File:** `backend/api/v1/billing.py`, line 456
**Impact:** Potential data inconsistency or double-commit errors.

The dunning service's `handle_payment_failure()` calls `await self._db.commit()` twice internally (lines 341, 390). The webhook handler in `billing.py` also calls `await db.commit()` at line 456 after `apply_webhook_action()` completes. Since both the dunning service and the webhook handler share the same `db` session (passed through at line 452 -> stripe_service line 711), the following sequence occurs:

1. Webhook handler INSERTs idempotency row (line 402, not committed yet)
2. `apply_webhook_action()` calls `DunningService.handle_payment_failure()`
3. Dunning service commits at line 341 (this also commits the idempotency row)
4. Dunning service commits again at line 390
5. Webhook handler commits at line 456 (redundant, but harmless if no error)

The problem: If step 3 succeeds but the dunning flow fails between steps 3 and 4 (e.g., email send timeout), the idempotency row is already committed. The webhook handler's error recovery (lines 488-518) tries to rollback and DELETE the idempotency row, but the row was already committed in step 3 -- the rollback at line 469/501 has nothing to undo, and the DELETE may or may not succeed depending on the session state.

**Fix:** The dunning service should not manage transaction boundaries. Remove the `await self._db.commit()` calls at lines 341 and 390 of `dunning_service.py` and let the caller (the webhook handler) own the single commit. Alternatively, use SAVEPOINTs for nested transactions.

---

## P1 -- High (Fix This Sprint)

### 14-P1-1: `get_overdue_accounts` query returns accounts regardless of whether they have resolved their payment

**File:** `backend/services/dunning_service.py`, lines 394-425
**Impact:** Users who have successfully paid (resolved their invoice) may still be flagged as overdue and escalated, because the query only checks `created_at <= cutoff AND subscription_tier != 'free'` with no join against `stripe_processed_events` for a corresponding `invoice.payment_succeeded`.

The `DISTINCT ON (prh.user_id)` query at lines 403-424 finds users with any `payment_retry_history` row older than the grace period, but does not check whether a more recent `invoice.payment_succeeded` event has resolved the payment. A user who failed payment 8 days ago but successfully retried 2 days ago would still be returned by this query.

**Severity rationale:** The `escalate_if_needed()` check at line 295 does guard against downgrading users already on `free`, and the tier restoration via `payment_succeeded` webhook (if P0-1 is fixed) would have already restored their tier. However, the user would still receive an unnecessary final dunning email from the `dunning-cycle` cron, creating a bad user experience.

**Fix:** Add a condition to exclude users who have a more recent successful payment, or track resolution status on the `payment_retry_history` table (e.g., a `resolved_at` column).

### 14-P1-2: Tier cache invalidation is missing for the `payment_failed` action when dunning escalates to free

**File:** `backend/services/stripe_service.py`, lines 707-731
**File:** `backend/services/dunning_service.py`, lines 276-305

When a payment fails and dunning escalates (3+ failures), the `escalate_if_needed()` method at line 298 sets `user.subscription_tier = "free"` and calls `user_repo.update()`. However, `invalidate_tier_cache(user_id)` is **never called** in this code path. The payment_failed handler block (lines 707-731) does not call `invalidate_tier_cache`.

This means after a dunning escalation, the user's tier remains cached as "pro" or "business" for up to 30 seconds. During this window, they retain access to premium features despite being downgraded. This is confirmed by the test `test_apply_webhook_action_payment_failed_does_not_invalidate_cache` in `test_stripe_service.py` line 696, which explicitly asserts the cache is NOT invalidated -- this was written as a feature ("no tier change occurs") but it's wrong when dunning escalation does change the tier.

**Fix:** After `dunning.handle_payment_failure()` returns, check if `result["escalation_action"]` is set and call `invalidate_tier_cache(user_id)` if so.

### 14-P1-3: `checkout.session.completed` handler does not verify the checkout session mode

**File:** `backend/services/stripe_service.py`, lines 416-437
**Impact:** A `checkout.session.completed` event for a one-time payment (e.g., if the Stripe dashboard is used to create a non-subscription checkout) would be incorrectly processed as a subscription activation, setting a tier on the user.

The handler at line 416 unconditionally extracts `tier` from metadata and returns `action: "activate_subscription"` without verifying `session.mode == "subscription"`. While the `create_checkout_session()` method at line 146 always passes `mode="subscription"`, Stripe could send checkout completion events for sessions created outside RateShift's code (e.g., by a Stripe dashboard operator).

**Fix:** Add a guard to check `session.get("mode") == "subscription"` before processing.

### 14-P1-4: No webhook endpoint rate limiting

**File:** `backend/api/v1/billing.py`, lines 329-523
**Impact:** The `/billing/webhook` endpoint has no rate limiting applied. While Stripe webhook signatures prevent unauthorized payloads from being processed, an attacker who can replay valid signed payloads (before the 72-hour idempotency window) could cause resource exhaustion (DB queries, Stripe API calls for subscription lookups in the payment_succeeded path).

The endpoint is also excluded from `RequestTimeoutMiddleware` as an internal endpoint. The idempotency guard mitigates repeated processing, but the signature verification and DB INSERT still run for each request.

**Fix:** Apply rate limiting to the webhook endpoint (e.g., 100 requests/minute per IP) or move the signature verification before any DB interaction.

### 14-P1-5: `apply_webhook_action` performs redundant `get_by_id` call after `get_by_stripe_customer_id` resolution

**File:** `backend/services/stripe_service.py`, lines 671-686
**Impact:** Performance -- two sequential DB queries for the same user.

When user_id is resolved via `get_by_stripe_customer_id` (line 671), the resolved user object is already available. But then at line 686, `user_repo.get_by_id(user_id)` is called again with the same user's ID, making a redundant database query for every `payment_failed` event. For the `payment_failed` path specifically, the user is fetched a third time at line 712 inside the dunning flow.

**Fix:** Store the already-resolved user object and pass it through to avoid redundant lookups.

---

## P2 -- Medium (Fix Soon)

### 14-P2-1: `amount_due=0` skips Decimal conversion due to falsy guard

**File:** `backend/services/stripe_service.py`, lines 502-504
**Impact:** Inconsistent type -- when Stripe sends `amount_due=0` (e.g., for trial invoices or $0 invoices), the amount remains as raw `int(0)` instead of `Decimal("0.00")`. This could cause type errors downstream if code expects Decimal.

The guard `if amount_due and isinstance(amount_due, (int, float))` at line 503 short-circuits on `0` because `0` is falsy in Python. The same pattern exists for `amount_refunded` at line 572 and `dispute_amount` at line 608.

This is confirmed by the test at `test_stripe_service.py` line 794 which comments "amount_due=0 is falsy; conversion is skipped, raw int 0 returned" -- the test documents the behavior but the behavior is still a bug.

**Fix:** Change the guard to `if amount_due is not None and isinstance(amount_due, (int, float))` (or similar non-falsy check).

### 14-P2-2: `get_subscription_status` fetches only `limit=1` subscription with `status="all"`

**File:** `backend/services/stripe_service.py`, lines 262-267
**Impact:** If a customer has multiple subscriptions (e.g., after a failed cancellation and re-subscribe), this always returns the first one by Stripe's default sort order (newest first). This is usually correct but may not be if the customer has a canceled subscription that sorts before an active one.

The code does not filter to `status="active"` or sort by status. Stripe's default ordering for `Subscription.list` is by `created` descending, so a newer canceled subscription would shadow an older active one.

**Fix:** Consider filtering by `status="active"` first, falling back to `status="all"` only if no active subscription is found.

### 14-P2-3: Stripe API key prefix logged at INFO level

**File:** `backend/services/stripe_service.py`, line 37
**Impact:** Low security concern -- the first 7 characters of the Stripe secret key (which includes the `sk_live_` or `sk_test_` prefix) are logged at INFO level on every process startup. While this does not expose the full key, it reveals whether production or test keys are in use.

```python
logger.info("stripe_api_key_set", key_prefix=settings.stripe_secret_key[:7])
```

**Fix:** Log only whether the key is set (boolean), not its prefix. Or log at DEBUG level only.

### 14-P2-4: `dunning_service.py` does not validate `user_email` format before sending

**File:** `backend/services/dunning_service.py`, lines 148-274
**Impact:** If the user record has a corrupted or empty email, the dunning email send will fail silently (caught by the broad `except Exception` at line 272) and the user will not be notified of their payment failure.

The `send_dunning_email()` method accepts `user_email: str` with no validation. The caller in `apply_webhook_action()` at line 713 sets `user_email = user.email if user else ""`, which could pass an empty string.

**Fix:** Add email validation at the entry point; return False early if email is empty or invalid.

### 14-P2-5: `get_overdue_accounts` query has no LIMIT clause

**File:** `backend/services/dunning_service.py`, lines 403-424
**Impact:** In a scenario with many overdue accounts (e.g., if a payment processor outage causes mass failures), the query would return an unbounded result set. The dunning cycle endpoint at `internal/billing.py` line 66 iterates over all results sequentially, which could cause request timeouts.

**Fix:** Add a `LIMIT 1000` (or similar) and process in batches.

### 14-P2-6: No webhook event logging to a persistent audit trail beyond `stripe_processed_events`

**File:** `backend/api/v1/billing.py`, lines 399-523
**Impact:** The `stripe_processed_events` table only stores `event_id`, `event_type`, and `processed_at`. The actual webhook payload, processing result, and any errors are only logged via structlog (ephemeral). For PCI compliance and dispute resolution, having a persistent audit trail of webhook payloads and outcomes is important.

**Fix:** Consider storing the webhook processing result (action taken, user_id affected, any errors) in the `stripe_processed_events` table or a separate audit table.

---

## P3 -- Low / Housekeeping

### 14-P3-1: `plan` parameter alias on `create_checkout_session` is undocumented in the API schema

**File:** `backend/services/stripe_service.py`, lines 98-120
**Impact:** The `plan` parameter at line 98 is an alias for `tier` accepted by the service method, but the billing API endpoint at `billing.py` line 31 only exposes `tier` in the Pydantic model. The alias exists only for "newer callers" but no caller uses it. Dead code.

### 14-P3-2: `billing_address_collection="auto"` may not be optimal for SaaS

**File:** `backend/services/stripe_service.py`, line 167
**Impact:** The `billing_address_collection="auto"` setting lets Stripe decide whether to collect billing address. For a SaaS subscription product, `"required"` may be preferred for tax compliance and fraud prevention, especially if operating internationally.

### 14-P3-3: Unused `Decimal` import in `billing.py`

**File:** `backend/api/v1/billing.py`
**Impact:** The file does not use `Decimal` directly (it is imported in `stripe_service.py`). No `Decimal` import exists but `sqlalchemy.text` is imported and used. This is a non-issue on inspection -- no unused imports found.

### 14-P3-4: `CheckoutSessionRequest` uses `HttpUrl` which may reject valid localhost URLs in development

**File:** `backend/api/v1/billing.py`, lines 35-36
**Impact:** Pydantic's `HttpUrl` type enforces strict URL parsing. The `validate_redirect_domain` validator at line 38 correctly allows `localhost`, but HttpUrl may reject certain localhost URL formats (e.g., `http://localhost:3000/` with trailing slash handling differences across Pydantic versions).

### 14-P3-5: Test file `test_webhooks.py` only covers GitHub webhooks, not Stripe webhooks

**File:** `backend/tests/test_webhooks.py`
**Impact:** Naming confusion. The Stripe webhook tests are split across `test_api_billing.py`, `test_stripe_service.py`, and `test_webhook_payment_integrity.py`, but `test_webhooks.py` only tests GitHub webhook signature verification. Consider renaming to `test_github_webhooks.py` for clarity.

### 14-P3-6: Magic number `3` for dunning escalation threshold is hardcoded in multiple places

**File:** `backend/services/dunning_service.py`, lines 72, 183, 287
**File:** `backend/api/v1/internal/billing.py`, lines 74, 83
**Impact:** The escalation threshold of 3 failures is scattered across multiple files as a magic number. Changing the threshold requires modifications in multiple places.

**Fix:** Extract to a module-level constant (e.g., `DUNNING_ESCALATION_THRESHOLD = 3`).

### 14-P3-7: `allow_promotion_codes=True` in checkout session creation

**File:** `backend/services/stripe_service.py`, line 166
**Impact:** This enables Stripe promotion codes on all checkout sessions. If no promotion codes are configured in the Stripe dashboard, this is a no-op. However, if someone creates promotion codes in Stripe, they will automatically work on all RateShift checkouts without any backend validation. This is an intentional feature but worth noting from a revenue assurance perspective.

---

## Files With No Issues Found

- `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/024_payment_retry_history.sql` -- Well-structured migration with proper FK constraints, indexes, and neondb_owner grants. `IF NOT EXISTS` guards present.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/054_stripe_processed_events.sql` -- Clean idempotency table design with cleanup index and documentation. 72-hour retention strategy is sound.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/migrations/056_stripe_customer_id_unique.sql` -- UNIQUE constraint with proper `DO NOTHING` idempotency guard, diagnostic query documented, NULL exclusion behavior correctly understood.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_premium_tier_gating.py` -- Thorough coverage of all tier-gated endpoints, including edge case of `None` tier.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_dunning_service.py` -- Good coverage including dispatcher integration, dedup, cooldown, escalation, and fallback paths. 19 test cases.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/tests/test_internal_billing.py` -- Covers happy path, error path, and auth requirement for dunning cycle endpoint.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/config/settings.py` (Stripe-related fields) -- Proper production validation for `STRIPE_SECRET_KEY` (must start with `sk_`), webhook secret config, MRR prices externalized.
- `/Users/devinmcgrath/projects/electricity-optimizer/backend/services/maintenance_service.py` (Stripe cleanup) -- 72-hour retention cleanup properly implemented with parameterized cutoff.

---

## Summary

### PCI Compliance Assessment

**PASS -- No card data stored.** The implementation correctly uses Stripe Checkout (hosted payment page) and Stripe Customer Portal for all payment data collection. No card numbers, CVVs, or PANs are stored, processed, or logged anywhere in the codebase. The `stripe_customer_id` and `subscription_id` are the only Stripe identifiers stored, which is PCI-compliant. Tokenization is handled entirely by Stripe. The Stripe secret key has proper production validation (line 358-368 of settings.py).

### Architecture Strengths

1. **Webhook signature verification** is correctly implemented using `stripe.Webhook.construct_event()` (line 371 of stripe_service.py) -- this is the Stripe-recommended approach.
2. **Idempotency handling** is well-designed with the race-condition fix documented in the code comments (billing.py lines 386-398). The INSERT-before-commit, DELETE-on-failure pattern is sound.
3. **Dunning flow** is well-structured with proper cooldown windows (24 hours), escalation thresholds (3 failures), and email template selection (soft vs. final).
4. **Tier gating** via `require_tier()` dependency with 2-layer cache (Redis + in-memory, 30s TTL) and explicit cache invalidation on subscription changes.
5. **Subscription state machine** correctly handles terminal states (`canceled`, `unpaid`) for tier downgrade while preserving access during `trialing`, `past_due`, and `incomplete` states.
6. **Stripe API key** is correctly set at module level (not per-request) to avoid concurrency issues.
7. **Redirect URL domain validation** prevents open redirect attacks on checkout and portal endpoints.
8. **Test coverage** is strong: ~100 tests across 6 test files covering service logic, API endpoints, idempotency, new webhook handlers, tier gating, and integration paths.

### Risk Summary

| Priority | Count | Key Risks |
|----------|-------|-----------|
| P0 | 2 | Silent payment event drops for `payment_succeeded`/`refunded`/`dispute`; dunning commit conflicts with webhook handler |
| P1 | 5 | Overdue account false positives; missing tier cache invalidation on escalation; no checkout mode verification; no webhook rate limiting; redundant DB queries |
| P2 | 6 | Falsy amount conversion; subscription list ordering; key prefix logging; no email validation; unbounded query; no persistent audit trail |
| P3 | 7 | Dead code, magic numbers, naming inconsistencies |

**Highest priority:** P0-1 (user_id resolution for `payment_succeeded`) must be fixed immediately -- it directly causes paid users to remain stuck on the free tier after successful Stripe payment retries following a dunning cycle. P0-2 (double-commit) should be addressed concurrently as it affects the same code path.
