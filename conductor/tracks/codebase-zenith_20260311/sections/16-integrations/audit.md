# Section 16: External Integrations — Clarity Gate Audit

**Date:** 2026-03-12
**Auditor:** Claude Code (Direct)
**Score:** 78/90 (PASS)

---

## Aggregate Scores

| # | Dimension | Score |
|---|-----------|-------|
| 1 | Correctness | 8/10 |
| 2 | Coverage | 9/10 |
| 3 | Security | 9/10 |
| 4 | Performance | 8/10 |
| 5 | Maintainability | 9/10 |
| 6 | Documentation | 9/10 |
| 7 | Error Handling | 9/10 |
| 8 | Consistency | 9/10 |
| 9 | Modernity | 8/10 |
| | **TOTAL** | **78/90** |

---

## Files Analyzed (~2,500 lines across 15+ integration files)

**Pricing APIs**: `integrations/pricing_apis/service.py`, `integrations/pricing_apis/eia.py`, `integrations/pricing_apis/nrel.py`, `integrations/pricing_apis/flatpeak.py`, `integrations/pricing_apis/iea.py`, `integrations/pricing_apis/base.py`, `integrations/pricing_apis/cache.py`, `integrations/pricing_apis/rate_limiter.py`
**Utilities**: `integrations/utilityapi.py`, `integrations/weather_service.py`
**Auth**: `auth/neon_auth.py` (Neon Auth / Better Auth integration)
**Payments**: `services/stripe_service.py` (Stripe integration)
**Email**: `lib/email/send.ts` (Resend + Gmail SMTP)
**Notifications**: `lib/notifications/onesignal.ts` (OneSignal push)
**AI Agent**: `services/agent_service.py` (Gemini + Groq + Composio)

---

## Architecture Assessment

Rich integration ecosystem connecting 10+ external services through well-defined abstraction layers. The PricingService provides a unified interface over 4 pricing APIs (EIA, NREL, Flatpeak, IEA) with automatic region-based routing and fallback chains. Each integration follows a consistent pattern: typed client class, async context manager, structured error handling, and optional caching. The AI agent uses a primary/fallback pattern (Gemini Flash -> Groq Llama 3.3 70B) with per-tier rate limits.

## HIGH Findings (2)

**H-01: PricingService client type annotations use `object` instead of base class**
- File: `integrations/pricing_apis/service.py:92`
- `self._clients: dict[str, Optional[object]]` — loses type safety for client methods
- `client.supports_region()`, `client.get_current_price()` calls rely on duck typing
- Fix: Use `BasePricingClient` as the type annotation (the base class already exists)

**H-02: No circuit breaker on external API calls**
- Pricing APIs, weather service, and UtilityAPI integrations have retry logic but no circuit breaker
- A consistently failing API will continue receiving requests until timeout
- Frontend has a circuit breaker for the CF Worker gateway, but backend integrations lack one
- Fix: Add a lightweight circuit breaker (similar to frontend's) for pricing and weather API clients

## MEDIUM Findings (3)

**M-01: Weather service doesn't batch API calls efficiently**
- File: `integrations/weather_service.py`
- Weather data for 51 regions fetched with `asyncio.gather` + `Semaphore(10)`
- Each region makes a separate HTTP request — no batch endpoint used
- Fix: Investigate OpenWeatherMap/NWS batch endpoints; cache aggressively (weather changes slowly)

**M-02: AI agent fallback doesn't track failure reasons**
- File: `services/agent_service.py`
- When Gemini fails with 429, switches to Groq, but doesn't log which model served the response
- Makes it hard to audit model usage for cost tracking
- Fix: Include `model_used` in the response metadata

**M-03: UtilityAPI sync interval (2h) may miss real-time meter data**
- File: `sync-connections.yml` runs every 2 hours
- UtilityAPI can provide near-real-time meter readings for some utilities
- 2-hour gap means optimization recommendations lag behind actual consumption
- Fix: For Pro/Business users, consider webhook-based sync or shorter intervals

## Strengths

- **Unified PricingService**: Single interface over 4 APIs with region-based routing and automatic fallback
- **4 pricing API clients**: EIA (US federal), NREL (US solar/utility), Flatpeak (UK/EU), IEA (global)
- **Async context manager pattern**: All clients implement `__aenter__`/`__aexit__` for proper cleanup
- **Shared caching layer**: `PricingCache` used across all pricing clients for consistent cache behavior
- **Per-API rate limiting**: Each API client respects its quota via shared `RateLimiter`
- **Dual-provider email**: Resend (primary, DKIM/SPF/DMARC verified) + Gmail SMTP fallback
- **AI agent resilience**: Gemini 3 Flash (primary, free tier) -> Groq Llama 3.3 70B (fallback on 429)
- **Stripe webhook security**: HMAC signature verification, idempotent event processing
- **OneSignal user binding**: Push subscription linked on login, unbound on logout
- **AES-256-GCM portal credentials**: Utility portal passwords encrypted at rest in database
- **Health check endpoint**: `PricingService.health_check()` monitors all API client health
- **16 Composio connections**: Extensive automation (Gmail, GitHub, Sentry, Vercel, Slack, Notion, etc.)

**Verdict:** PASS (78/90). Comprehensive integration layer with good abstraction patterns, fallback chains, and security practices. Main issues are weak typing in PricingService and missing backend circuit breakers for external API resilience.
