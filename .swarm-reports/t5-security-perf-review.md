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

```ts
// DirectLoginForm.tsx:138-139
if (data.redirect_url) {
  window.location.href = data.redirect_url   // no origin check
```

```ts
// EmailConnectionFlow.tsx:87-89
if (data.redirect_url) {
  window.location.href = data.redirect_url   // no origin check
```

**Impact**: If an attacker can influence the backend response (e.g., via a compromised API, MITM on a non-TLS connection, or a backend SSRF that leaks a crafted response), users can be redirected to an arbitrary external origin. This is a classic open redirect / phishing vector.

**Contrast**: The `useAuth.tsx:151-163` hook correctly validates the `callbackUrl` parameter:
```ts
const parsed = new URL(callback, window.location.origin)
if (parsed.origin === window.location.origin && parsed.pathname.startsWith('/')) {
  destination = parsed.pathname + ...
}
```
The same pattern must be applied here.

**Fix Recommendation**:
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
} else if (data.redirect_url) {
  // External OAuth redirect: only allow known OAuth provider domains
  // or log a warning and redirect to /dashboard
  window.location.href = '/connections'
}
```
Note: For legitimate external OAuth redirects (UtilityAPI, Gmail, Outlook), the backend should provide a pre-approved list of OAuth origins that the frontend can whitelist explicitly rather than blindly trusting any URL.

---

#### SEC-02: `requireEmailVerification: false` in Better Auth config
**File**: `frontend/lib/auth/server.ts:36`

```ts
emailAndPassword: {
  enabled: true,
  minPasswordLength: 12,
  requireEmailVerification: false,   // P1
}
```

**Issue**: Email verification is disabled. Users can register with any email address (including fake ones or emails belonging to others) and immediately access the application. This enables:
1. Account enumeration (sign up with victim@example.com to confirm the email is not yet registered)
2. Fraudulent accounts using others' email addresses
3. Bypassing org-based access controls if any are added later

**Impact**: Medium-to-high: enables fake account creation and spam/abuse. Less severe in the current context because OAuth is the primary flow, but still a P1 gap.

**Fix Recommendation**: Enable email verification:
```ts
requireEmailVerification: true,
```
Ensure a transactional email service (SendGrid/Resend) is configured and the verification email template is in place.

---

### P2 — Medium

#### SEC-03: `'unsafe-inline'` in `script-src` CSP directive
**File**: `frontend/next.config.js:46`

```js
`script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ''}`,
```

**Issue**: `'unsafe-inline'` in `script-src` effectively negates XSS protection from the CSP, allowing any inline `<script>` tag to execute. This is applied in production (the `isDev` check only adds `'unsafe-eval'`, not `'unsafe-inline'`).

**Impact**: A real XSS injection (should one be discovered via a future code path or dependency) would not be stopped by the CSP header, removing a key defense-in-depth layer.

**Fix Recommendation**: Use nonce-based CSP with Next.js middleware:
```ts
// middleware.ts - generate nonce per request
const nonce = Buffer.from(crypto.randomUUID()).toString('base64')
const cspHeader = `script-src 'self' 'nonce-${nonce}'`
// Pass nonce to response headers and <Script> components
```
Next.js 14 has built-in nonce support via `next/script`. This is the recommended approach.

---

#### SEC-04: `last_sync_error` rendered directly from backend without escaping
**File**: `frontend/components/connections/ConnectionCard.tsx:386`

```tsx
<p className="text-xs text-warning-700 truncate">
  {connection.last_sync_error}   // backend string rendered directly
</p>
```

**Issue**: While React's JSX rendering prevents HTML injection (React escapes text content by default), `last_sync_error` strings from the backend could contain content that misleads users (e.g., "Your session expired. Please re-enter credentials at evil.com"). This is more a social engineering/phishing-via-error-message concern than a direct XSS vector.

**Impact**: Low XSS risk (React escapes), but moderate social engineering risk. Rating P2 due to the context (connection management, trusted UI).

**Fix Recommendation**: Either truncate/sanitize backend error strings to a maximum length and known safe format, or use predefined error codes mapped to safe UI messages rather than rendering raw backend strings.

---

### P3 — Informational

#### SEC-05: `callbackUrl` query param only checked at sign-in, not used in API client redirect
**File**: `frontend/lib/api/client.ts:40`

```ts
window.location.href = `/auth/login?callbackUrl=${encodeURIComponent(currentPath)}`
```

**Issue**: The `callbackUrl` is properly `encodeURIComponent`-encoded before being appended to the redirect URL. However, the `currentPath` is taken from `window.location.pathname + window.location.search` which could include attacker-controlled query parameters from the URL. The `useAuth.tsx` hook validates the callback on consumption, so the chain is safe, but it is a defense-in-depth concern.

**Impact**: No exploitable path found given the validation in `useAuth.tsx:156-163`. Informational.

---

#### SEC-06: No CSRF protection on state-mutating `fetch` calls in Connection components
**File**: `frontend/components/connections/ConnectionCard.tsx`, `DirectLoginForm.tsx`, `EmailConnectionFlow.tsx`

**Issue**: Direct `fetch` calls (DELETE, POST, PATCH) rely solely on session cookies (via `credentials: 'include'`). Better Auth should handle CSRF protection at the session level, but the frontend does not send a CSRF token header. Whether this matters depends on Better Auth's CSRF configuration.

**Impact**: If Better Auth's CSRF protection is enabled (default for cookie-based auth), this is informational only. If it is not configured or was disabled, cross-site form submissions could be forged. Recommend confirming Better Auth CSRF settings in `server.ts`.

---

#### SEC-07: `console.error` and `console.warn` leaking DB/auth error details
**Files**:
- `frontend/lib/auth/server.ts:19` — logs `DATABASE_URL is empty`
- `frontend/lib/api/client.ts:37` — logs `Session expired or unauthorized`

**Issue**: In production, `console.*` output is accessible via server logs and client DevTools. The DB URL message in particular could reveal configuration details. The warning in `client.ts` is acceptable for debugging but should be guarded.

**Impact**: Low. Informational. Fix by removing production `console.error` calls or replacing with structured logging behind a `IS_PRODUCTION` guard.

---

## Performance Findings

### P1 — High

#### PERF-01: `useRealtimeSubscription` and `useRealtimeOptimization` — `onUpdate` callback not stabilized
**File**: `frontend/lib/hooks/useRealtime.ts:160-181`

```ts
export function useRealtimeSubscription(
  config: RealtimeConfig,
  onUpdate?: (payload: unknown) => void   // not wrapped in useCallback at call sites
) {
  useEffect(() => {
    const timer = setInterval(() => {
      ...
      onUpdate?.({ table: config.table, event: config.event })
    }, 30_000)
    ...
  }, [config.table, config.event, config.filter, onUpdate, queryClient])
```

**Issue**: `onUpdate` is in the `useEffect` dependency array. If callers pass an inline arrow function (which is recreated every render), this will cancel and restart the 30-second polling interval on every parent re-render. Even with a single parent render this causes unexpected interval resets.

**Impact**: Real-time subscriptions that use `onUpdate` will silently restart their timers on every parent render, potentially causing: missed updates, excessive network connections, and confusing timing behavior.

**Fix Recommendation**: Callers must wrap `onUpdate` in `useCallback`. Alternatively, the hook itself should use a `useRef` to hold the latest `onUpdate` without including it in the dependency array:
```ts
const onUpdateRef = useRef(onUpdate)
onUpdateRef.current = onUpdate

useEffect(() => {
  const timer = setInterval(() => {
    onUpdateRef.current?.({ ... })
  }, 30_000)
  return () => clearInterval(timer)
}, [config.table, config.event, config.filter])  // onUpdate removed from deps
```

---

### P2 — Medium

#### PERF-02: Dashboard `topSuppliers` memo has unnecessary `currentSupplier` dependency
**File**: `frontend/components/dashboard/DashboardContent.tsx:137`

```ts
const topSuppliers = React.useMemo(() => (suppliersData?.suppliers?.slice(0, 2) || []).map(
  (s: RawSupplierRecord) => ({...})
), [suppliersData, currentSupplier])  // currentSupplier not used in map
```

**Issue**: `currentSupplier` is included as a `useMemo` dependency but is not accessed inside the memo callback. It only appears in JSX where `supplier.id === currentSupplier?.id`. Adding it as a dependency causes unnecessary recomputation of the suppliers slice whenever the current supplier changes.

**Impact**: Minor — recomputes a `slice(0, 2).map()` on supplier changes. Low cost for a small list, but indicates a pattern error that could be replicated in larger computations.

**Fix Recommendation**: Remove `currentSupplier` from the `useMemo` dependency array.

---

#### PERF-03: React Query `retry: 3` default is excessive for auth-gated endpoints
**File**: `frontend/components/providers/QueryProvider.tsx:15`

```ts
defaultOptions: {
  queries: {
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  }
}
```

**Issue**: With `retry: 3` and exponential backoff, a 401 or 403 response causes 3 retry attempts with delays of 1s, 2s, 4s before giving up. The `apiClient` itself also has `MAX_RETRIES = 2`. For authenticated endpoints, 401/403 should not be retried at all. With both layers of retry, a single auth failure triggers 3×3 = 9 fetch calls over ~7 seconds.

**Impact**: Wastes network bandwidth and delays the 401 redirect to login by up to 7 seconds for expired sessions.

**Fix Recommendation**: Configure `retry` to skip retries on 4xx errors:
```ts
retry: (failureCount, error) => {
  if (error instanceof ApiClientError && error.status < 500) return false
  return failureCount < 2
},
```

---

#### PERF-04: `ConnectionsOverview` uses raw `fetch` without React Query caching
**File**: `frontend/components/connections/ConnectionsOverview.tsx:44-64`

```ts
const fetchConnections = useCallback(async () => {
  const res = await fetch(`${API_ORIGIN}/api/v1/connections`, { credentials: 'include' })
  ...
}, [])
```

**Issue**: The connections list is fetched with a raw `fetch` + `useState` pattern, bypassing React Query entirely. This means:
1. No automatic cache invalidation when mutations succeed
2. No background refetch
3. No deduplication if the component mounts multiple times
4. Every view-switch re-triggers a network call (`fetchConnections()` is called in `handleBackToOverview`)

The rest of the app (prices, suppliers, savings) correctly uses React Query hooks.

**Impact**: Inconsistent caching behavior; unnecessary network requests on tab/view switches; stale data possible if external mutation occurs.

**Fix Recommendation**: Migrate to a `useConnections` React Query hook:
```ts
const { data, isLoading, error, refetch } = useQuery({
  queryKey: ['connections'],
  queryFn: () => fetch(`${API_ORIGIN}/api/v1/connections`, { credentials: 'include' }).then(r => r.json()),
})
```

---

### P3 — Informational

#### PERF-05: Chart components are `React.memo`-wrapped but called with object literals
**Files**: `DashboardContent.tsx:335`, `PricesContent.tsx:262`

```tsx
<PriceLineChart
  data={chartData}        // ✓ memoized via useMemo
  loading={historyLoading}
  timeRange={timeRange}
  onTimeRangeChange={setTimeRange}  // ✓ stable setter from useState
  showCurrentPrice
  showTrend
  highlightOptimal
  height={300}
/>
```

**Issue**: `PriceLineChart` is wrapped in `React.memo`, which is good. However, `showCurrentPrice`, `showTrend`, `highlightOptimal` are JSX boolean shorthand props — these are equivalent to `{true}` literals. These are primitives and stable across renders so they do not break memoization. This is a non-issue confirmed by inspection.

**Impact**: None. Informational — the `React.memo` usage is correct.

---

#### PERF-06: `refetchOnWindowFocus: true` in QueryProvider may cause excessive refetches on dashboard
**File**: `frontend/components/providers/QueryProvider.tsx:13`

```ts
refetchOnWindowFocus: true,
```

**Issue**: With `refetchOnWindowFocus: true` (the React Query default), every time the browser window regains focus (e.g., switching back from another tab), all active queries will refetch. On the dashboard, this means up to 5 simultaneous requests (prices, history, forecast, suppliers, savings) on every focus event.

**Impact**: Medium — adds load on the backend on every tab switch. Combined with `staleTime: 60 * 1000`, data must be older than 1 minute before refetch is skipped on focus, which is reasonable. The SSE connection (`openWhenHidden: false`) already pauses when hidden. This is a trade-off rather than a clear bug.

**Fix Recommendation**: Consider `refetchOnWindowFocus: 'always'` replaced with `false` for the dashboard-specific queries that use SSE for live data. Alternatively, keep the default but accept the behavior.

---

#### PERF-07: `SupplierCard` not memoized despite being rendered in large lists
**File**: `frontend/components/suppliers/SupplierCard.tsx`

**Issue**: `SupplierCard` is a `React.FC` without `React.memo`. It is rendered in lists of up to 34+ suppliers (nationwide expansion noted in MEMORY.md). When the parent `SuppliersContent` state changes (e.g., `viewMode`, `showWizard`, `showSetDialog`), all supplier cards will re-render even though their `supplier` prop has not changed.

**Impact**: In a list of 34 suppliers, every parent state update (modal open/close, view toggle) triggers 34 re-renders. Each `SupplierCard` contains `formatCurrency` calls and `Image` components. Not catastrophic but measurable.

**Fix Recommendation**:
```ts
export const SupplierCard = React.memo<SupplierCardProps>(({ ... }) => {
  ...
})
```

---

## CSP Analysis

**File**: `frontend/next.config.js:44-54`

| Directive | Value | Assessment |
|-----------|-------|------------|
| `default-src` | `'self'` | Good |
| `script-src` | `'self' 'unsafe-inline'` | **P2 — see SEC-03** |
| `style-src` | `'self' 'unsafe-inline'` | Acceptable for Tailwind/CSS-in-JS |
| `img-src` | `'self' data: blob: https://*.electricity-optimizer.com` | Good |
| `font-src` | `'self'` | Good |
| `connect-src` | `'self' + allowed domains` | Good — SSE and API domains included |
| `frame-ancestors` | `'none'` | Good — aligns with `X-Frame-Options: DENY` |
| `base-uri` | `'self'` | Good |
| `form-action` | `'self'` | Good |

Missing: `object-src 'none'` (low priority; prevents Flash/plugin attacks, which are obsolete but still best practice to add).

---

## Auth Cookie Analysis

**File**: `frontend/middleware.ts:27-29`

Both cookie name variants are correctly checked:
```ts
const sessionToken =
  request.cookies.get('better-auth.session_token')?.value ||
  request.cookies.get('__Secure-better-auth.session_token')?.value
```

Cookie security flags (`httpOnly`, `secure`, `sameSite`) are managed by Better Auth's server-side implementation, not explicitly set in frontend code. This is the correct pattern — Better Auth sets these based on the environment automatically.

No auth tokens are exposed in client-side bundles. The `authClient` only exposes methods, not credentials. Session is purely cookie-based (httpOnly). **Auth cookie handling: PASS**.

---

## Environment Variable Analysis

All client-side code uses only `NEXT_PUBLIC_*` vars via the centralized `frontend/lib/config/env.ts`. Server-only vars (`DATABASE_URL`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_SECRET`) are accessed only in `frontend/lib/auth/server.ts` which is a server-side module.

No hardcoded secrets found in any frontend file. **Env var handling: PASS**.

---

## XSS Vector Analysis

- `dangerouslySetInnerHTML`: **Zero usages found** across all `.ts`/`.tsx` files.
- URL parameter injection: `callbackUrl` is validated in `useAuth.tsx:156-163`. **PASS**.
- Backend string rendering: Only identified in `ConnectionCard.tsx:386` (see SEC-04).
- React's default JSX text escaping provides strong baseline protection.

**XSS posture: Good**.

---

## SSE / Memory Leak Analysis

**File**: `frontend/lib/hooks/useRealtime.ts`

`useRealtimePrices`:
- Uses `AbortController` + `mountedRef.current` guard pattern. **Correct**.
- `openWhenHidden: false` is set. **PASS** (memory/MEMORY.md notes this as required).
- Exponential backoff on errors (1s → 30s cap). **Good**.
- Cleanup on unmount: `ctrl.abort()` + `mountedRef.current = false`. **PASS**.
- No memory leaks detected.

`useRealtimeOptimization` and `useRealtimeSubscription`:
- Use `setInterval` with proper `clearInterval` in cleanup. **PASS**.
- `onUpdate` dependency issue noted in PERF-01.

---

## Bundle Optimization Analysis

**Code splitting**: `PriceLineChart` and `ForecastChart` are dynamically imported with `next/dynamic + ssr: false` in both `DashboardContent.tsx` and `PricesContent.tsx`. **Good**.

**Image optimization**: `SupplierCard.tsx` uses `next/image` (with `width`, `height`, `alt`). **PASS**.

**Package optimization**: `next.config.js:8` includes `optimizePackageImports` for `date-fns`, `lucide-react`, `recharts`, `better-auth`. **Good** — these are the largest dependencies.

**Large barrel imports**: `lucide-react` is tree-shaken via `optimizePackageImports`. Individual icons are imported by name in all components reviewed. **PASS**.

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
| SEC-04 | P2 | Low | Sanitize/truncate `last_sync_error` before rendering |
| PERF-02 | P2 | Trivial | Remove stale `currentSupplier` dep from `topSuppliers` useMemo |
| PERF-07 | P3 | Trivial | Wrap `SupplierCard` in `React.memo` |
| SEC-05 | P3 | None | Informational — existing validation is sufficient |
| SEC-06 | P3 | Low | Confirm Better Auth CSRF protection is enabled |
| SEC-07 | P3 | Low | Remove/guard `console.error` in production in `server.ts` |
| PERF-05 | P3 | None | Informational — memo usage is correct |
| PERF-06 | P3 | Low | Consider per-query `refetchOnWindowFocus: false` for SSE-backed data |
