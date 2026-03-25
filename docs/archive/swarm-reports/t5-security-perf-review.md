> **DEPRECATED** — This document is archived for historical reference only. It may contain outdated information. See current documentation in the parent `docs/` directory.

---

# T5: Security & Performance Review

**Date**: 2026-03-03
**Agent**: security-perf
**Scope**: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/`

---

## Summary Statistics

| Category | P0 | P1 | P2 | P3 | Total |
|----------|----|----|----|----|-------|
| Security | 0  | 2  | 2  | 3  | 7     |
| Performance | 0 | 1 | 3  | 3  | 7     |
| **Total** | **0** | **3** | **5** | **6** | **14** |

**Overall posture**: Good baseline with no P0 (critical) issues. Two P1 (high) security issues require attention before the next release. Performance is solid with a few meaningful gaps in the hot paths.

---

## Security Findings

### P1 — High

#### SEC-01: Unvalidated `redirect_url` from backend — Open Redirect
**Files**:
- `frontend/components/connections/DirectLoginForm.tsx:139`
- `frontend/components/connections/EmailConnectionFlow.tsx:89`

**Issue**: Both files perform a direct `window.location.href = data.redirect_url` assignment using a URL received from the backend API response, with zero client-side validation.

**Impact**: If an attacker can influence the backend response, users can be redirected to an arbitrary external origin. This is a classic open redirect / phishing vector.

**Fix Recommendation**: Apply origin validation before redirect:
```ts
function isSafeRedirect(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin)
    return parsed.origin === window.location.origin
  } catch {
    return false
  }
}

if (data.redirect_url && isSafeRedirect(data.redirect_url)) {
  window.location.href = data.redirect_url
}
```

---

#### SEC-02: `requireEmailVerification: false` in Better Auth config
**File**: `frontend/lib/auth/server.ts:36`

**Issue**: Email verification is disabled. Users can register with any email address and immediately access the application. This enables account enumeration, fraudulent accounts, and bypassing org-based access controls.

**Fix Recommendation**: Enable email verification:
```ts
requireEmailVerification: true,
```

---

### P2 — Medium

#### SEC-03: `'unsafe-inline'` in `script-src` CSP directive
**File**: `frontend/next.config.js:46`

**Issue**: `'unsafe-inline'` in `script-src` effectively negates XSS protection from the CSP, allowing any inline `<script>` tag to execute.

**Fix Recommendation**: Use nonce-based CSP with Next.js middleware or replace `'unsafe-inline'` with specific nonce values.

---

## Performance Findings

### P1 — High

#### PERF-01: `useRealtimeSubscription` — `onUpdate` callback not stabilized
**File**: `frontend/lib/hooks/useRealtime.ts:160-181`

**Issue**: `onUpdate` is in the `useEffect` dependency array. If callers pass an inline arrow function (which is recreated every render), this will cancel and restart the 30-second polling interval on every parent re-render.

**Impact**: Real-time subscriptions may silently restart their timers on every parent render, potentially causing missed updates and excessive network connections.

**Fix Recommendation**: Use `useRef` to hold the latest `onUpdate` without including it in the dependency array.

---

### P2 — Medium

#### PERF-02: Dashboard `topSuppliers` memo has unnecessary `currentSupplier` dependency
**File**: `frontend/components/dashboard/DashboardContent.tsx:137`

**Issue**: `currentSupplier` is included as a `useMemo` dependency but is not accessed inside the memo callback.

**Fix Recommendation**: Remove `currentSupplier` from the `useMemo` dependency array.

---

#### PERF-03: React Query `retry: 3` default is excessive for auth-gated endpoints
**File**: `frontend/components/providers/QueryProvider.tsx:15`

**Issue**: With `retry: 3` and exponential backoff, a 401 or 403 response causes 3 retry attempts with delays of 1s, 2s, 4s before giving up.

**Fix Recommendation**: Configure `retry` to skip retries on 4xx errors.

---

#### PERF-04: `ConnectionsOverview` uses raw `fetch` without React Query caching
**File**: `frontend/components/connections/ConnectionsOverview.tsx:44-64`

**Issue**: The connections list is fetched with a raw `fetch` + `useState` pattern, bypassing React Query entirely.

**Fix Recommendation**: Migrate to a `useConnections` React Query hook.

---

## Recommended Fix Priority

| ID | Priority | Effort | Description |
|----|----------|--------|-------------|
| SEC-01 | P1 | Low | Add origin validation before `window.location.href = data.redirect_url` |
| SEC-02 | P1 | Low | Enable `requireEmailVerification: true` in Better Auth config |
| PERF-01 | P1 | Low | Fix `onUpdate` dep in `useRealtimeSubscription` using `useRef` pattern |
| SEC-03 | P2 | Medium | Replace `'unsafe-inline'` in `script-src` with nonce-based CSP |
| PERF-03 | P2 | Low | Configure React Query `retry` to skip 4xx errors |
| PERF-04 | P2 | Medium | Migrate `ConnectionsOverview` fetch to React Query |

---

*This report is an archived analysis of security and performance findings from March 2026 audits.*
