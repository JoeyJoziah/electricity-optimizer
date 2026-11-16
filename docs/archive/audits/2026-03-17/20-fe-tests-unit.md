# Audit Report: Frontend Unit Tests
## Date: 2026-03-17

---

### Executive Summary

**Scope**: 144 test files across `frontend/__tests__/` covering hooks, components, pages, contexts, stores, utils, API contracts, and one integration test.
**Sampled**: 20 files read in full; remainder scanned with targeted grep for structural patterns.
**Overall impression**: The test suite is well above average for a project of this size. Test isolation discipline is strong — mocks are declared before imports, `beforeEach` resets are consistent, and `userEvent` is used correctly over `fireEvent`. The auth hook (`useAuth.test.tsx`) and dashboard component (`DashboardContent.test.tsx`) suites are exemplary in breadth and specificity. Several systemic issues, however, warrant attention.

---

### Strengths

- **Auth coverage is thorough**: `useAuth.test.tsx` covers 30+ cases including redirect validation, open-redirect prevention (protocol-relative URLs), OneSignal integration, signOut error resilience, and the `useRequireAuth` guard — all behaviors that matter for security.
- **Contract tests exist and use real API clients**: `contracts/api-schemas.test.ts` calls real `lib/api/*` functions against mocked `fetch`, not just asserting on handwritten literals. This catches serialization and field-name mismatches.
- **Security headers are tested**: `config/next-config-csp.test.ts` verifies CSP directives, `frame-ancestors 'none'`, HSTS, and `X-Frame-Options`. Few projects do this.
- **Tier gating is tested at the component level**: `DashboardContent.test.tsx` and `AlertsContent.test.tsx` both assert that 403 errors from the API produce upgrade CTAs, not silent failures.
- **Store logic is comprehensively exercised**: `store/settings.test.ts` covers every action, state isolation, SSR guard, and `resetSettings`.
- **Email dual-provider fallback is tested**: `lib/email/send.test.ts` covers Resend success, Resend error, SMTP fallback, and combined failure — matching the production dual-provider architecture.
- **No snapshot tests**: Zero `toMatchSnapshot()` calls across all 144 files, eliminating an entire category of brittle, low-signal tests.
- **No skipped tests**: No `it.skip`, `xit`, or `xdescribe` calls anywhere in the suite.
- **RTL/userEvent best practices**: Tests consistently use `userEvent.setup()` + `await user.click()`, not the deprecated `userEvent.click()` or the weaker `fireEvent`.

---

### Findings

#### P0 — Critical

**P0-1: `useAgentQuery.sendQuery` is entirely untested — the core AI agent feature has no behavioral coverage.**

File: `frontend/__tests__/hooks/useAgent.test.ts` (lines 78–101)

`useAgentQuery` only tests initial state and `reset()`. The `sendQuery` method — which performs SSE streaming, appends messages, handles errors, respects the 2000-character limit, and manages `isStreaming` state — has zero tests. This is the primary user-facing action for the AI Agent feature (production live since 2026-03-11 with a complex Gemini+Groq dual-provider + rate-limit flow). A regression in `sendQuery` would go undetected.

```typescript
// Currently missing — example of what should be tested:
it('sendQuery appends user and assistant messages on success', async () => { ... })
it('sendQuery rejects input exceeding 2000 characters', async () => { ... })
it('sendQuery sets isStreaming true then false after completion', async () => { ... })
it('sendQuery sets error state on API failure', async () => { ... })
it('sendQuery handles rate limit (429) with correct error message', async () => { ... })
```

**Impact**: Any regression in the streaming or error-handling logic in the AI Agent's primary action goes undetected by unit tests.

---

**P0-2: The "prices dropping" banner is acknowledged to be dead code, but no failing test captures this.**

Files: `frontend/__tests__/components/dashboard/DashboardContent.test.tsx` (lines 735–763), `frontend/__tests__/integration/dashboard.test.tsx` (lines 404–432)

Both test files contain the comment: *"Component hardcodes trend='stable', so the decreasing banner does not appear."* The test at line 740 is titled `'shows price dropping banner when trend is decreasing'` but asserts `queryByText(/prices dropping/i)` is **not** in the document — the test name directly contradicts what it asserts. This is a documentation mismatch that masks a dead code path in the component. If the component is ever fixed to derive trend from `price_change_24h`, these tests will pass incorrectly (they already pass today for the wrong reason).

**Recommendation**: Either (a) fix the component so `trend` is derived from `price_change_24h` and update the test expectations to assert the banner IS shown, or (b) rename the test to `'does not show price dropping banner (trend always stable — known limitation)'` and file a tracking issue.

---

#### P1 — High

**P1-1: `useRealtimeOptimization` and `useRealtimeSubscription` are tested only as polling stubs, never with real SSE behavior.**

File: `frontend/__tests__/hooks/useRealtime.test.ts` (lines 402–545)

`useRealtimeOptimization` tests verify it "returns `isConnected: true` immediately" and "invalidates optimization queries every 60 seconds." `useRealtimeSubscription` tests verify "returns `isConnected: true`" and "calls onUpdate callback every 30 seconds." Both hooks are confirmed to be polling timers disguised as realtime hooks, and the tests confirm this. There is no test for what happens if the interval misfires, or for the cleanup path of `useRealtimeOptimization` when the interval should be cleared. The `clearInterval` call on unmount is tested, but `invalidateQueries` content is not verified — the test only checks the spy was called, not which query keys were invalidated.

**Recommendation**: Add assertions on the exact query keys passed to `invalidateQueries`, and test the scenario where the component re-renders with a new region before the interval fires.

---

**P1-2: `AgentChat` cancel button test is guarded by an `if (cancelBtn)` conditional — the test silently passes when the button is not found.**

File: `frontend/__tests__/components/agent/AgentChat.test.tsx` (lines 169–185)

```typescript
it('calls cancel when stop button is clicked', async () => {
  // ...
  const cancelBtn = buttons.find(btn => btn.getAttribute('type') === 'button')
  if (cancelBtn) {
    await user.click(cancelBtn)
    expect(mockCancel).toHaveBeenCalled()
  }
})
```

If `cancelBtn` is `undefined` (e.g., the button is removed from the component or changes its `type` attribute), the `if` block is skipped and the test passes vacuously. `mockCancel` is never called, but the test reports green. This is a P0-style false positive wrapped in an `if`.

**Fix**: Use RTL's `getByRole` with an appropriate accessible name, or assert after the find:

```typescript
const cancelBtn = buttons.find(btn => btn.getAttribute('type') === 'button')
expect(cancelBtn).toBeDefined() // fail fast if missing
await user.click(cancelBtn!)
expect(mockCancel).toHaveBeenCalled()
```

---

**P1-3: Settings page has no test for `changePassword` flow.**

File: `frontend/__tests__/pages/settings.test.tsx`

The settings page mock (`authClient.changePassword`) is set up (line 104) but there is no test that exercises the "Change Password" form interaction, submitting the form, success feedback, or the error path when `changePassword` returns `{ data: null, error: ... }`. Per project memory, profile name update and change-password were added in the Pre-Launch UX Polish sprint (2026-03-16). The mock exists but no test uses it.

---

**P1-4: Integration test (`dashboard.test.tsx`) uses `require()` inside test bodies to access mocked modules — fragile and anti-pattern.**

File: `frontend/__tests__/integration/dashboard.test.tsx` (lines 289, 341, 361, 409, 453)

```typescript
it('handles API errors gracefully', async () => {
  const { getCurrentPrices } = require('@/lib/api/prices')
  getCurrentPrices.mockRejectedValueOnce(new Error('API Error'))
  // ...
})
```

Using `require()` inside test bodies to retrieve jest mocks works but is fragile. The module reference obtained this way is the same as the top-level `jest.mock` factory, but if module paths change or the mock factory changes to use named re-exports, these inline `require()` calls can silently return the real module. The standard pattern is to capture the mock function reference at the top of the file via `jest.mocked()` or by declaring module-level mock variables, as done correctly in every other test file in this suite.

---

**P1-5: `useRealtime.test.ts` — SSE `EventSource` mock uses a custom class that simulates events but does not accurately model browser `EventSource` behavior (buffered initial response, reconnect timing).**

File: `frontend/__tests__/hooks/useRealtime.test.ts` (lines 1–66, mock class definition)

The mock EventSource dispatches events synchronously by calling stored handlers directly. Real browser EventSource dispatches asynchronously and re-connections after error involve a minimum 1-3 second browser delay. Tests at lines 199–233 ("exponential backoff" and "stops retrying on auth failure") simulate the retry logic but test the hook's internal state machine, not its interaction with real timing. If the backoff logic were accidentally removed, these tests would still pass because they invoke the error/close handlers directly without waiting for real timers. Consider using `jest.useFakeTimers()` and advancing time explicitly for backoff tests.

---

**P1-6: `LoginPage` test delegates entirely to mocked `LoginForm` — page-level layout and auth guard are not tested.**

File: `frontend/__tests__/pages/auth-login.test.tsx`

```typescript
jest.mock('@/components/auth/LoginForm', () => ({
  LoginForm: () => <div data-testid="login-form">LoginForm</div>,
}))
```

The four tests only verify heading text, subtitle text, the mock div being present, and a CSS class. The comment says "LoginForm has its own comprehensive test suite" — correct — but the page wrapper has additional responsibilities: checking if the user is already authenticated and redirecting to `/dashboard`, passing a `callbackUrl` query param to `LoginForm`, and the mobile/desktop centering layout. None of these behaviors are tested.

---

#### P2 — Medium

**P2-1: `jest.spyOn(require(...))` pattern used in 11 test locations — fragile mid-test mocking.**

Files: `DashboardTabs.test.tsx` (5 occurrences), `CompletionProgress.test.tsx` (3 occurrences), `gas-rates.test.tsx`, `community-solar.test.tsx`, `UtilityDiscoveryCard.test.tsx`

```typescript
// Example from DashboardTabs.test.tsx:261
jest.spyOn(require('@/lib/hooks/useCombinedSavings'), 'useCombinedSavings').mockReturnValueOnce({...})
```

This pattern works today but is fragile for two reasons: (1) it depends on Jest module cache ordering — if the spy is called after the module is already initialized in a different way, the spy may not intercept calls; (2) `mockReturnValueOnce` on a spy tied to `require()` can leave the spy in an inconsistent state if the test fails before cleanup. The standard pattern used elsewhere in this codebase (declaring a top-level `jest.mock()` with a configurable variable) is more robust. These 11 occurrences should be migrated.

---

**P2-2: `DashboardContent.test.tsx` — the `next/dynamic` mock inspects `loader.toString()` to determine which component to return.**

File: `frontend/__tests__/components/dashboard/DashboardContent.test.tsx` (lines 13–30)

```typescript
jest.mock('next/dynamic', () => {
  return (loader: () => Promise<unknown>) => {
    const src = loader.toString()
    if (src.includes('PriceLineChart')) return PriceLineChartMock
    if (src.includes('ForecastChart')) return ForecastChartMock
    // ...
  }
})
```

This is a creative but fragile approach. The test depends on the string representation of an arrow function containing the import path. If Next.js or the bundler minifies the loader function, or if the dynamic import is refactored to use a variable, `src.includes('PriceLineChart')` silently returns false and the fallback stub is used instead, hiding the chart. This is also duplicated between `DashboardContent.test.tsx` and `integration/dashboard.test.tsx`.

**Recommendation**: Extract to a shared test utility (`__tests__/utils/mock-next-dynamic.ts`) with a registry approach, and add a guard assertion that at least one known chart renders.

---

**P2-3: `Community.test.tsx` — mock override inside test body mutates `jest.requireMock` directly.**

File: `frontend/__tests__/components/community/Community.test.tsx` (lines 202–215)

```typescript
it('shows empty state when no posts', () => {
  const origMock = jest.requireMock('@/lib/hooks/useCommunity')
  const origFn = origMock.useCommunityPosts
  origMock.useCommunityPosts = () => ({...})
  render(<PostList utilityType="electricity" />)
  expect(screen.getByTestId('post-list-empty')).toBeInTheDocument()
  origMock.useCommunityPosts = origFn  // manual restore
})
```

Mutating the mock registry object directly and manually restoring it is error-prone. If the test throws before restoration, subsequent tests in the suite will use the wrong mock. This pattern is used instead of the established `let mockReturn = ...; jest.mock(..., () => ({ useCommunityPosts: () => mockReturn }))` pattern used in every other test file.

---

**P2-4: `AlertsContent.test.tsx` — uses CSS class selector `.animate-pulse` to detect loading state.**

File: `frontend/__tests__/components/alerts/AlertsContent.test.tsx` (lines 194–200)

```typescript
it('renders loading skeletons while alerts are fetching', () => {
  const skeletons = document.querySelectorAll('.animate-pulse')
  expect(skeletons.length).toBeGreaterThan(0)
})
```

Asserting on Tailwind CSS class names in tests couples tests to styling implementation. If the loading skeleton is refactored to use a different animation class (e.g., `animate-shimmer` from a UI library upgrade), this test fails for a styling-only change. The rest of the suite uses `getByTestId` or `getByRole` — this file should use `data-testid="alert-loading-skeleton"` on the skeleton wrapper.

---

**P2-5: Settings page region selection test uses `document.querySelector` with a CSS attribute selector — brittle DOM traversal.**

File: `frontend/__tests__/pages/settings.test.tsx` (lines 149–154)

```typescript
const regionSelect = document.querySelector('select optgroup[label="Northeast"]')?.closest('select')
expect(regionSelect).not.toBeNull()
await user.selectOptions(regionSelect as HTMLSelectElement, 'us_ny')
```

This traverses the DOM by HTML structure rather than accessible semantics. If the region selector is refactored to a custom combobox or the `optgroup` groupings change, this silently returns `null` and the test fails at `selectOptions` with an unhelpful error. The select should have an `aria-label` or be associated with a `<label>` so it can be queried with `getByRole('combobox', { name: /region/i })`.

---

**P2-6: `useAgent.test.ts` only has 5 tests for `useAgentQuery` and `useAgentStatus` combined — the agent hook is critically under-tested given its production status.**

File: `frontend/__tests__/hooks/useAgent.test.ts`

Beyond P0-1 (missing `sendQuery` tests), the overall test count is 5 for a hook that manages streaming state, dual-provider fallback, rate limiting, error normalization, and SSE message parsing. Compare to `useAuth.test.tsx` with 30+ tests for a hook of comparable complexity. The 3 tests in `useAgentStatus` cover only the happy path, the query key, and a single error — no 429, no 403, no refetch-on-window-focus behavior.

---

**P2-7: `contracts/api-schemas.test.ts` uses `toHaveProperty` presence checks without value validation for critical numeric fields.**

File: `frontend/__tests__/contracts/api-schemas.test.ts` (throughout)

```typescript
expect(result).toHaveProperty('total')
expect(typeof result.total).toBe('number')
```

While checking the property exists and is a number is better than nothing, the contract tests do not validate value ranges, Decimal-string format (`"0.2500"` vs `0.25`), or enum constraints. For example:

- `current_price` is a string (Decimal), but the test only checks `typeof price.current_price === 'string'`. It does not verify it matches `/^\d+\.\d{4}$/` (4 decimal places from Python's `Decimal`).
- `connection_type` accepts only 4 valid enum values (`direct_login`, `email_import`, `bill_upload`, `utility_api`) but the test only checks `typeof conn.connection_type === 'string'`.
- `alert.is_active` is boolean — tested.
- `alert.price_below` is `float | null` — tested as `toHaveProperty` only; if the backend ever sends a Decimal string here, the test would not catch the mismatch.

---

**P2-8: `useAuth.test.tsx` — `window.location` is rewritten using `Object.defineProperty` with `writable: true` but the spread-copy approach may preserve stale JSDOM internals.**

File: `frontend/__tests__/hooks/useAuth.test.tsx` (lines 96–106)

```typescript
Object.defineProperty(window, 'location', {
  writable: true,
  value: {
    ...originalLocation,
    href: 'http://localhost:3000/auth/login',
    search: '',
    pathname: '/auth/login',
    origin: 'http://localhost:3000',
  },
})
```

This is a known pattern, but spreading `originalLocation` (a JSDOM `Location` object) may not copy all prototype-chained getters correctly across jsdom 26. If jsdom upgrades its `Location` implementation, spread-copying may include non-serializable references. The more robust approach for testing redirect logic is injecting the router as a dependency or using Next.js's `useRouter` mock. The existing approach works in jsdom 26 but is worth noting for future jsdom upgrades.

---

**P2-9: `integration/dashboard.test.tsx` — mock data uses `region: 'US_CT'` (uppercase) while the component store mock uses `region: 'us_ct'` (lowercase).**

File: `frontend/__tests__/integration/dashboard.test.tsx` (lines 12, 53)

```typescript
// Helper returns uppercase:
region: 'US_CT',

// Store mock returns lowercase:
region: 'us_ct',
```

The backend uses snake_case lowercase region codes (`us_ct`). The `mockPriceResponse` and `mockApiPrice` helpers in the integration test use `'US_CT'`. This inconsistency with the component-level test (which uses `'us_ct'` throughout) could mask a real case-sensitivity bug in the API contract. If the backend ever validates region values strictly, the integration test would be using an invalid region code.

---

#### P3 — Low

**P3-1: `pricing.test.tsx` renders in `beforeEach` — all 15 tests share a single render and cannot test page in different states.**

File: `frontend/__tests__/pages/pricing.test.tsx` (lines 13–15)

```typescript
describe('PricingPage', () => {
  beforeEach(() => {
    render(<PricingPage />)
  })
```

Rendering in `beforeEach` is fine for a static page, but if any test ever needs to test the page with a different prop or context (e.g., user already logged in), the shared render structure must be refactored. Currently there are no auth-aware states being tested on the pricing page (e.g., "Get started" vs "Go to dashboard" CTA for authenticated users).

---

**P3-2: `pages/auth-login.test.tsx` also renders in `beforeEach`, testing only 4 structural properties of the page wrapper.**

File: `frontend/__tests__/pages/auth-login.test.tsx`

4 tests for a page that is the entry point for all authentication. As noted in P1-6, the redirect behavior for already-authenticated users, and query param forwarding, are untested. The page should have at least 8-10 tests.

---

**P3-3: `AgentChat.test.tsx` uses `fireEvent.change` for the over-limit character count test while the rest of the file uses `userEvent`.**

File: `frontend/__tests__/components/agent/AgentChat.test.tsx` (lines 273–276)

```typescript
it('shows over-limit character count styling', () => {
  render(<AgentChat />)
  const textarea = screen.getByPlaceholderText('Ask RateShift AI...')
  fireEvent.change(textarea, { target: { value: 'a'.repeat(2001) } })
  expect(screen.getByText('2001/2000')).toBeInTheDocument()
})
```

`fireEvent.change` bypasses React's synthetic event system and does not simulate real user input (no `beforeinput`, no `input` event sequence). Since the character count likely uses a controlled `onChange` handler, this works in practice, but the inconsistency with the rest of the file using `userEvent` is a maintenance smell. Use `await user.type(textarea, 'a'.repeat(2001))` or, for performance, `fireEvent.input(textarea, ...)` with a note explaining why `userEvent` is not used for large strings.

---

**P3-4: `DashboardContent.test.tsx` — mock for `lucide-react` lists 6 icons; Sidebar test lists 17 icons. New icons added in future will silently not render in DashboardContent tests.**

File: `frontend/__tests__/components/dashboard/DashboardContent.test.tsx` (lines 146–153)

Each component that uses `lucide-react` must maintain its own mock list. Per project memory: "New lucide-react icon imports: update ALL test file mocks (Sidebar.test.tsx, sidebar.a11y.test.tsx) or tests break." This is a known issue. The fragility is inherent to the mock-per-file approach. A shared `__mocks__/lucide-react.tsx` auto-mock or a Proxy-based mock would eliminate this class of issue:

```typescript
// __mocks__/lucide-react.tsx
import React from 'react'
export default new Proxy({}, {
  get: (_, name: string) =>
    (props: React.SVGAttributes<SVGElement>) => <svg data-testid={`icon-${name}`} {...props} />
})
```

---

**P3-5: `store/settings.test.ts` — SSR localStorage guard test deletes `globalThis.window` but does not restore it inside the `isolateModules` callback if `require()` throws.**

File: `frontend/__tests__/store/settings.test.ts` (lines 391–409)

```typescript
delete (globalThis as any).window
jest.isolateModules(() => {
  require('@/lib/store/settings')  // if this throws, window is not restored
  importedSuccessfully = true
})
globalThis.window = origWindow  // restore is OUTSIDE the isolateModules block
```

If `require('@/lib/store/settings')` throws, `globalThis.window` is never restored, and subsequent tests in the suite run without a `window` object. This is a test isolation hazard. The restore should be in a `finally` block.

---

**P3-6: 439 uses of `getByTestId`/`queryByTestId` — heavy reliance on `data-testid` attributes.**

Cross-file

`data-testid` queries are fast and stable when the attribute is in the component source. However, with 439 uses across 144 files, there is a significant surface area for testids to become stale. When a component is refactored to use a different testid (e.g., `alert-card` renamed to `alert-item`), multiple test files fail for non-behavioral reasons. Where RTL accessible queries exist (`getByRole`, `getByLabelText`, `getByText`), they should be preferred. The heavy testid usage is not wrong, but should be flagged as maintenance overhead.

---

### Statistics

| Metric | Value |
|--------|-------|
| Total test files | 144 |
| Files fully read for this audit | 20 |
| Files scanned via grep patterns | 124 |
| Estimated total test cases | ~2,024 (per project count) |
| Skipped tests (`it.skip`, `xit`) | 0 |
| Snapshot tests | 0 |
| Files with `jest.spyOn(require())` anti-pattern | 5 files, 11 occurrences |
| Files using `fireEvent` (vs userEvent) | ~3 (mixed usage in AgentChat, AlertsContent) |
| Vacuously-passing tests confirmed | 1 (AgentChat cancel button `if` guard) |
| Known-dead code tests (documented in comments) | 2 (prices-dropping banner) |
| Test files missing auth-state variants | ~8 page-level files |
| Critical feature untested (sendQuery) | 1 (useAgentQuery) |

---

### Recommendations

**Immediate (before next sprint)**

1. **Fix the vacuously-passing test** in `AgentChat.test.tsx` (P1-2). Replace the `if (cancelBtn)` guard with a hard assertion. This is a 2-line fix.

2. **Add `sendQuery` tests to `useAgent.test.ts`** (P0-1). The AI Agent is in production with rate limits. The minimum required: happy path (message appended), 429 rate-limit error, 2000-char truncation, and `isStreaming` state transitions. Target: 8–10 new tests.

3. **Rename the misleadingly-titled "prices dropping" test** (P0-2) to reflect actual behavior, or fix the component. A test titled "shows X" that asserts "X is not present" is a documentation liability.

**Short-term (within 1–2 sprints)**

4. **Add `changePassword` tests to `settings.test.tsx`** (P1-3). The mock is already wired; just add the test cases.

5. **Replace `jest.spyOn(require())` with module-level mocks** in the 5 affected files (P2-1). Migrate to the configurable-variable pattern used in the rest of the suite.

6. **Fix the `window` restore in `store/settings.test.ts` SSR test** to use a `try/finally` (P3-5). 3-line fix.

7. **Extract the `next/dynamic` mock** to a shared utility (P2-2). The string-inspection approach is duplicated and fragile.

**Medium-term**

8. **Introduce a Proxy-based `lucide-react` auto-mock** at `frontend/__mocks__/lucide-react.tsx` (P3-4). This eliminates the per-file icon list maintenance burden entirely.

9. **Strengthen contract tests** with format/enum validation, not just `typeof` checks (P2-7). Add regex assertions on Decimal string fields and enumeration checks on `connection_type`, `status`, `alert_type`.

10. **Add integration-test coverage for the authenticated LoginPage** redirect behavior and `callbackUrl` forwarding (P1-6).
