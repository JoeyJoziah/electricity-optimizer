# Section 9: Frontend Core Infrastructure — Clarity Gate Audit

**Date:** 2026-03-12
**Auditor:** Claude Code (Direct)
**Score:** 81/90 (PASS)

---

## Aggregate Scores

| # | Dimension | Score |
|---|-----------|-------|
| 1 | Correctness | 9/10 |
| 2 | Coverage | 9/10 |
| 3 | Security | 9/10 |
| 4 | Performance | 9/10 |
| 5 | Maintainability | 9/10 |
| 6 | Documentation | 9/10 |
| 7 | Error Handling | 9/10 |
| 8 | Consistency | 9/10 |
| 9 | Modernity | 9/10 |
| | **TOTAL** | **81/90** |

---

## Files Analyzed (~1,500 lines across 15 core files)

`lib/api/client.ts`, `lib/api/circuit-breaker.ts`, `lib/auth/client.ts`, `lib/auth/server.ts`, `lib/config/env.ts`, `lib/email/send.ts`, `lib/notifications/onesignal.ts`, `lib/utils/cn.ts`, `lib/utils/calculations.ts`, `lib/utils/format.ts`, `lib/utils/url.ts`, `lib/utils/devGate.ts`, `lib/constants/regions.ts`

---

## Architecture Assessment

Robust frontend core with several production-hardened patterns: circuit breaker for CF Worker gateway resilience, 401 redirect loop prevention with never-resolving promise, Better Auth client with httpOnly cookies, and comprehensive API client with retry logic. Clean separation between auth (Better Auth), API (custom fetch wrapper), and state management (Zustand + React Query).

## HIGH Findings (2)

**H-01: client.ts never-resolving promise could cause memory leaks in long-lived tabs**
- File: `lib/api/client.ts`
- On 401, returns `new Promise(() => {})` — a promise that never resolves
- In long-lived browser tabs, accumulated never-resolving promises may prevent garbage collection
- While this pattern correctly stops React Query retries, it should clean up after redirect
- Fix: Reject with a sentinel error after a timeout, or use AbortController

**H-02: circuit-breaker.ts has no persistence across page reloads**
- File: `lib/api/circuit-breaker.ts`
- Circuit breaker state is in-memory only — resets on every page navigation
- User could keep hitting a broken gateway after each page load
- Fix: Persist circuit state to sessionStorage with TTL

## MEDIUM Findings (2)

**M-01: auth/client.ts uses window.location.origin which may differ from API origin**
- File: `lib/auth/client.ts:13`
- `baseURL: typeof window !== "undefined" ? window.location.origin : APP_URL`
- In preview deployments (Vercel), window.location.origin may not match backend URL
- Fix: Always use APP_URL; the fallback should be primary, not secondary

**M-02: No request deduplication in API client**
- File: `lib/api/client.ts`
- Multiple components mounting simultaneously can fire identical API calls
- React Query handles this at the hook level, but raw `apiFetch()` calls don't deduplicate
- Fix: Add request deduplication map in `apiFetch()` for GET requests

## Strengths

- **Circuit breaker**: 3-state (CLOSED/OPEN/HALF_OPEN) with automatic gateway error detection (502/503/1027)
- **401 loop prevention**: `MAX_401_REDIRECTS=2` within `REDIRECT_WINDOW_MS=10000`, `redirectInFlight` flag
- **Exponential backoff retry**: `fetchWithRetry` with 500ms base, max 2 retries, only on 5xx
- **Safe redirect validation**: `isSafeRedirect()` checks same-origin before redirect
- **Better Auth integration**: httpOnly session cookies, no localStorage token management
- **Magic link support**: Better Auth magic link client plugin configured
- **Type-safe env config**: `lib/config/env.ts` centralizes environment variable access
- **5 dedicated test files**: circuit-breaker, client, client-401-redirect, client-circuit-breaker, prices

**Verdict:** PASS (81/90). Production-hardened frontend core with circuit breaker, 401 loop prevention, and comprehensive retry logic. Minor issues around memory cleanup for never-resolving promises and circuit breaker persistence.
