# Section 5: API Routers — Clarity Gate Audit

**Date:** 2026-03-12
**Auditor:** Claude Code (Direct)
**Score:** 74/90 (PASS)

---

## Aggregate Scores

| # | Dimension | Score |
|---|-----------|-------|
| 1 | Correctness | 8/10 |
| 2 | Coverage | 8/10 |
| 3 | Security | 8/10 |
| 4 | Performance | 8/10 |
| 5 | Maintainability | 8/10 |
| 6 | Documentation | 9/10 |
| 7 | Error Handling | 8/10 |
| 8 | Consistency | 8/10 |
| 9 | Modernity | 9/10 |
| | **TOTAL** | **74/90** |

---

## Files Analyzed (20+ router files, ~4,600 lines)

`api/v1/users.py`, `api/v1/auth.py`, `api/v1/prices.py`, `api/v1/alerts.py`, `api/v1/agent.py`, `api/v1/billing.py`, `api/v1/recommendations.py`, `api/v1/savings.py`, `api/v1/webhooks.py`, `api/v1/suppliers.py`, `api/v1/compliance.py`, `api/v1/user_supplier.py`, `api/v1/prices_analytics.py`, `api/v1/prices_sse.py`, `api/v1/beta.py`, `api/v1/health.py`, `api/v1/feedback.py`, `api/v1/notifications.py`, `api/v1/regulations.py`, `api/dependencies.py`, `api/v1/internal/*.py`

---

## HIGH Findings (5)

**H-01: users.py duplicates VALID_REGIONS instead of using Region enum**
- File: `api/v1/users.py:42-52`
- Hardcoded `VALID_REGIONS` set duplicates `models/region.py` Region enum
- Drift risk: adding a region to enum won't update the API validation
- Fix: Import Region enum and use `set(r.value for r in Region)`

**H-02: users.py `update_profile` builds dynamic SQL SET clause from user input keys**
- File: `api/v1/users.py:196`
- `set_clause = ", ".join(f"{k} = :{k}" for k in updates)` — while `updates` keys come from a Pydantic model (safe), this pattern is fragile
- The field names are safe because Pydantic validates them, but no explicit allowlist exists
- Fix: Add an explicit `_UPDATABLE_COLUMNS` allowlist (like `user_repository.py:177`)

**H-03: prices.py falls back to mock data in non-production**
- File: `api/v1/prices.py:155-179`
- On any service exception in dev/staging, returns mock data instead of an error
- This masks real bugs during development and staging testing
- Fix: Return 503 in staging, only mock in `development` environment

**H-04: recommendations.py swallows all exceptions**
- File: `api/v1/recommendations.py:30-31`
- `except Exception: logger.exception(...)` then returns `None` for every error
- All 3 endpoints silently degrade — no way to know if the service is broken
- Fix: Re-raise specific expected exceptions, only catch for graceful degradation

**H-05: agent.py `_get_user_context` returns "Unknown" instead of raising**
- File: `api/v1/agent.py:83-89`
- If user not found in DB, returns `{"region": "Unknown", "tier": "free"}` rather than 404
- AI agent will generate incorrect region-specific advice
- Fix: Raise HTTPException 404 if user row not found

## MEDIUM Findings (4)

**M-01: Duplicate user.py and users.py routers**
- `api/v1/user.py` (98 lines) and `api/v1/users.py` (212 lines) both exist
- Unclear which is canonical for user profile endpoints
- Fix: Consolidate into single router

**M-02: alerts.py `_get_alert_service()` creates new instance per request**
- File: `api/v1/alerts.py:84-85`
- `AlertService()` constructed on every call without DI
- Fix: Use FastAPI `Depends()` pattern for consistency with other services

**M-03: billing.py uses deprecated `stripe.error.StripeError`**
- File: `api/v1/billing.py:172`
- Modern Stripe SDK uses `stripe.StripeError` (not `stripe.error.StripeError`)
- Fix: Update to `stripe.StripeError`

**M-04: No response_model on several endpoints**
- `recommendations.py`, `savings.py`, `agent.py` return `Dict[str, Any]` without response models
- Reduces type safety and OpenAPI documentation quality
- Fix: Add Pydantic response models for all public endpoints

## Strengths

- **Tier gating**: `require_tier("pro"/"business")` properly gates 7 premium endpoints
- **Redirect domain validation**: `billing.py` validates `success_url`/`cancel_url` against allowlist
- **Webhook signature verification**: Both Stripe and GitHub webhooks use proper HMAC verification
- **Constant-time API key compare**: `dependencies.py:86` uses `hmac.compare_digest`
- **Rate limiting**: Per-endpoint rate limiter on `password/check-strength` (5/min)
- **Pagination**: Price history with proper `page`/`page_size`/`total`/`pages` response
- **Internal endpoints**: `/internal/*` requires `X-API-Key`, excluded from timeout middleware
- **Good documentation**: All endpoints have summary, description, and response codes

**Verdict:** PASS (74/90). Well-structured API layer with proper auth, tier gating, and webhook verification. Main issues are duplicated validation sets, swallowed exceptions, and mock data leakage in non-prod.
