# T1: Frontend Test Gap Analysis

> Generated: 2026-03-03
> Analyst: test-writer agent (frontend-review-swarm)

---

## Summary

- **Total pages**: 19
- **Pages with tests**: 4 (architecture page, prices page, suppliers page — via `__tests__/pages/`, plus architecture page from `__tests__/app/dev/`)
- **Pages with NO tests**: 15
- **Layouts tested**: 1 of 3 (`(dev)/layout.tsx` has tests)
- **Layouts untested**: 2 (`app/layout.tsx`, `app/(app)/layout.tsx`)
- **Components untested**: 2 (`AccountLinkStep`, `QueryProvider`)

---

## 1. Untested Pages

### Marketing Pages (app root)

| Page | File Path | Notes |
|------|-----------|-------|
| Landing / Home | `frontend/app/page.tsx` | Pure static JSX; renders nav, hero, features grid, pricing preview, footer |
| Pricing | `frontend/app/pricing/page.tsx` | Pure static JSX; 3-tier pricing cards, FAQ, footer |
| Privacy Policy | `frontend/app/privacy/page.tsx` | Pure static content; nav + prose sections |
| Terms of Service | `frontend/app/terms/page.tsx` | Pure static content; nav + prose sections |

### App Pages `(app)/`

| Page | File Path | Notes |
|------|-----------|-------|
| Auth: Login | `frontend/app/(app)/auth/login/page.tsx` | Thin wrapper — renders `<LoginForm />` + heading |
| Auth: Signup | `frontend/app/(app)/auth/signup/page.tsx` | Thin wrapper — renders `<SignupForm />` + heading |
| Auth: Callback | `frontend/app/(app)/auth/callback/page.tsx` | useEffect redirects to `/dashboard`; shows spinner |
| Auth: Forgot Password | `frontend/app/(app)/auth/forgot-password/page.tsx` | Inline form with `authClient.requestPasswordReset`; submitted/error states |
| Auth: Reset Password | `frontend/app/(app)/auth/reset-password/page.tsx` | Suspense-wrapped; handles token/no-token/success states + password validation |
| Auth: Verify Email | `frontend/app/(app)/auth/verify-email/page.tsx` | Suspense-wrapped; token verification, resend flow |
| Beta Signup | `frontend/app/(app)/beta-signup/page.tsx` | Inline form, fetch to `/api/beta-signup`, success state |
| Connections | `frontend/app/(app)/connections/page.tsx` | Thin wrapper — renders `<ConnectionsOverview />` |
| Dashboard | `frontend/app/(app)/dashboard/page.tsx` | Thin wrapper — renders `<DashboardContent />` (integration tests exist but are partial — see §5) |
| Onboarding | `frontend/app/(app)/onboarding/page.tsx` | useProfile, redirect logic, renders `<OnboardingWizard />` |
| Optimize | `frontend/app/(app)/optimize/page.tsx` | Complex page with appliance CRUD, schedule optimization, inline state management |
| Settings | `frontend/app/(app)/settings/page.tsx` | Complex page with region, utility types, supplier, notifications, GDPR export/delete |

### Dev Pages `(dev)/`

| Page | File Path | Notes |
|------|-----------|-------|
| Architecture | `frontend/app/(dev)/architecture/page.tsx` | **HAS TESTS** — covered by `__tests__/app/dev/architecture.test.tsx` |

### Pages with existing tests (not in `__tests__/pages/`)

| Page | Test File |
|------|-----------|
| Prices | `frontend/__tests__/pages/prices.test.tsx` — imports `@/app/(app)/prices/page` |
| Suppliers | `frontend/__tests__/pages/suppliers.test.tsx` — imports `@/app/(app)/suppliers/page` |
| Architecture | `frontend/__tests__/app/dev/architecture.test.tsx` |

**Conclusion: 15 out of 19 pages are untested (79%).**

---

## 2. Untested Layouts

| Layout | File Path | Status | Notes |
|--------|-----------|--------|-------|
| Root layout | `frontend/app/layout.tsx` | **UNTESTED** | Wraps all pages; renders `QueryProvider`, `AuthProvider`, `ToastProvider`, Inter font, SEO metadata |
| App layout | `frontend/app/(app)/layout.tsx` | **UNTESTED** | Renders `SidebarProvider` + `<Sidebar />`; wraps all authenticated app pages |
| Dev layout | `frontend/app/(dev)/layout.tsx` | **HAS TESTS** | Covered by `__tests__/app/dev/layout.test.tsx` |

---

## 3. Untested Components

All 9 connection components have tests. All dashboard, supplier, onboarding, auth, chart, layout, gamification, and UI components have tests. Two components lack test coverage:

| Component | File Path | Notes |
|-----------|-----------|-------|
| `AccountLinkStep` | `frontend/components/onboarding/AccountLinkStep.tsx` | Renders `<SupplierAccountForm>`, calls `useLinkAccount`, has skip button. Used in `OnboardingWizard` |
| `QueryProvider` | `frontend/components/providers/QueryProvider.tsx` | Wraps `QueryClientProvider`; trivial wrapper but referenced in root layout |

---

## 4. Integration Test Candidates

### A. Connection Flow (9 components, `components/connections/`)

All 9 components have individual unit tests. Missing: an **end-to-end integration test** for the full flow:

**Scope:**
- User sees `ConnectionsOverview` (no connections)
- Clicks "Add Connection" → `ConnectionMethodPicker` renders
- Selects "Upload Bill" → `ConnectionUploadFlow` + `BillUploadForm`
- Selects "Email" → `EmailConnectionFlow`
- Selects "Direct Login" → `DirectLoginForm`
- After connection created: `ConnectionCard` renders, `ConnectionRates` loads, `ConnectionAnalytics` shows

**Recommended file:** `frontend/__tests__/integration/connections.test.tsx`

### B. Onboarding Flow

**Scope:**
- `OnboardingPage` loads; shows spinner during profile fetch
- Profile has no region → `OnboardingWizard` renders
- Step 1: `RegionSelector` — user selects state
- Step 2: `UtilityTypeSelector` — user selects utility types
- Step 3: `SupplierPicker` — user selects supplier
- Step 4 (optional): `AccountLinkStep` — link account or skip
- `onComplete` fires → redirects to `/dashboard`
- Profile already onboarded → redirect immediately

**Recommended file:** `frontend/__tests__/integration/onboarding.test.tsx`

### C. Auth Flow

**Scope:**
- Login: render `LoginPage` → `LoginForm` → submit → success redirect
- Signup: render `SignupPage` → `SignupForm` → submit → redirect to verify-email
- Forgot password: `ForgotPasswordPage` → submit email → success state
- Reset password: `ResetPasswordPage` with valid token → submit → success; without token → error state
- Verify email: `VerifyEmailPage` with valid token → success; with invalid token → error; without token → resend flow
- Auth callback: `AuthCallbackPage` → useEffect triggers router.replace('/dashboard')

**Recommended file:** `frontend/__tests__/integration/auth.test.tsx`

### D. Settings Page (complex inline page)

**Scope:**
- `SettingsPage` renders all 5 cards (Account, Energy Usage, Notifications, Display, Privacy)
- Region selector change updates store
- Utility type toggles work
- Supplier picker flow
- Notification checkboxes toggle
- Currency/theme/time-format selects
- Save button calls `useUpdateProfile`
- Export data button calls GDPR endpoint
- Delete account button shows confirm dialog

**Recommended file:** `frontend/__tests__/pages/settings.test.tsx`

### E. Optimize Page (complex inline page)

**Scope:**
- Empty state: "No appliances added yet"
- Quick-add presets work
- Custom add form
- Appliance edit/delete in edit mode
- "Optimize Now" button calls `useOptimalSchedule`
- Loading skeleton shows
- Schedule results display with `ScheduleTimeline`
- Savings summary cards update

**Recommended file:** `frontend/__tests__/pages/optimize.test.tsx`

---

## 5. Dashboard Timing Failures — Root Cause Analysis

File: `frontend/__tests__/integration/dashboard.test.tsx`

The MEMORY.md notes mention 7 pre-existing dashboard timing failures (now reportedly fixed as of deep audit). However, the current test file still contains tests that are structurally prone to timing issues. Analysis of each:

### Test 1: `'renders dashboard with all main widgets'` (line 125)
**Pattern:** `waitFor` with multiple assertions.
**Risk:** The `waitFor` callback must pass all assertions simultaneously. If some widgets render before others, intermediate render states can cause flakiness. Multiple assertions in a single `waitFor` cause retry overhead.
**Fix:** Split into per-widget `waitFor` or use `findBy*` queries.

### Test 2: `'displays current price and price trend'` (line 143)
**Pattern:** `getAllByTestId('price-trend')` inside `waitFor`.
**Risk:** `price-trend` testid count varies by render state. If the component renders before data resolves (skeleton phase), `getAllByTestId` might return 0 elements.
**Fix:** Use `findAllByTestId('price-trend')` which includes built-in waiting.

### Test 3: `'shows 24-hour forecast section'` (line 152)
**Pattern:** `waitFor` with `getAllByText(/24-hour forecast/i)`.
**Root cause:** Dashboard uses React Query; forecast data may arrive after initial render. The `waitFor` default timeout (1000ms) may be too short for complex component trees with multiple query dependencies.
**Fix:** Increase `waitFor` timeout to 3000ms or use `findByText`.

### Test 4: `'displays optimal scheduling recommendations'` (line 160)
**Pattern:** `waitFor` looking for `/optimal times/i`.
**Risk:** This text only appears in the schedule widget after the optimization API resolves. The mock resolves immediately but React state updates are async.
**Fix:** `await screen.findByText(/optimal times/i)` with appropriate timeout.

### Test 5: `'shows content after loading completes'` (line 179)
**Pattern:** `waitFor` for `getByTestId('dashboard-container')`.
**Root cause:** `dashboard-container` testid must be in `DashboardContent`. If the component doesn't add this testid, the test always fails regardless of timing.
**Fix:** Verify `DashboardContent` has `data-testid="dashboard-container"`. If not, add it. This is likely the main source of failures.

### Test 6: `'is responsive on mobile devices'` (line 255)
**Pattern:** `waitFor` checking for `flex-col` class on `dashboard-container`.
**Root cause:** CSS classes are static Tailwind; they don't change based on `window.innerWidth` unless media queries or JS-driven responsive logic is used. If `DashboardContent` doesn't conditionally apply `flex-col`, this always fails.
**Fix:** Either verify `DashboardContent` uses a JS-driven responsive class, or replace with a more accurate assertion about the container structure.

### Test 7: `'shows real-time update indicator'` (line 268)
**Pattern:** `waitFor` for `getByTestId('realtime-indicator')`.
**Root cause:** `realtime-indicator` testid must exist in the rendered component. `useRealtimePrices` is mocked to return `isConnected: false`. The component may only render the indicator when connected.
**Fix:** Either mock `isConnected: true`, or update the assertion to match the disconnected state indicator.

### Test 8: `'displays notification banner for price alerts'` (line 276)
**Pattern:** `waitFor` for `/prices dropping/i` text.
**Root cause:** The `getCurrentPrices` mock returns `trend: 'decreasing'` only for one call. If `DashboardContent` doesn't render a "prices dropping" banner based on `trend` data, this always fails. This is a **test-code mismatch** — the mock assumes behavior that may not be implemented.
**Fix:** Verify `DashboardContent` renders a trend-based banner, or remove/update this test to match actual component behavior.

### Test 9: `'recovers from widget errors without crashing entire dashboard'` (line 312)
**Pattern:** `waitFor` checking for "forecast unavailable" text.
**Root cause:** Error boundaries must be implemented in `DashboardContent` for individual widgets. If error boundaries don't exist, a rejected `getPriceForecast` mock crashes the whole tree.
**Fix:** Verify error boundary implementation in `DashboardContent`, or mock the error at a level that the component actually catches.

**Primary root causes across all failures:**
1. Missing `data-testid` attributes in `DashboardContent` (dashboard-container, realtime-indicator, price-trend)
2. Tests assert UI behavior (trend banners, responsive classes) that may not be implemented
3. `waitFor` timeouts too short for multi-query component trees
4. Single `waitFor` with multiple assertions — any one failure retries the full block

---

## 6. Recommended Test Files

### Priority 1 — Page Unit Tests (needed for coverage threshold)

| Test File | Page | Complexity | Key Mocks |
|-----------|------|------------|-----------|
| `__tests__/pages/landing.test.tsx` | `app/page.tsx` | Low | None (static) |
| `__tests__/pages/pricing.test.tsx` | `app/pricing/page.tsx` | Low | None (static) |
| `__tests__/pages/privacy.test.tsx` | `app/privacy/page.tsx` | Low | None (static) |
| `__tests__/pages/terms.test.tsx` | `app/terms/page.tsx` | Low | None (static) |
| `__tests__/pages/auth-login.test.tsx` | `auth/login/page.tsx` | Low | `@/components/auth/LoginForm` |
| `__tests__/pages/auth-signup.test.tsx` | `auth/signup/page.tsx` | Low | `@/components/auth/SignupForm` |
| `__tests__/pages/auth-callback.test.tsx` | `auth/callback/page.tsx` | Low | `next/navigation` (useRouter) |
| `__tests__/pages/auth-forgot-password.test.tsx` | `auth/forgot-password/page.tsx` | Medium | `@/lib/auth/client` (authClient) |
| `__tests__/pages/auth-reset-password.test.tsx` | `auth/reset-password/page.tsx` | Medium | `@/lib/auth/client`, `next/navigation` (useSearchParams) |
| `__tests__/pages/auth-verify-email.test.tsx` | `auth/verify-email/page.tsx` | Medium | `@/lib/auth/client`, `next/navigation` (useSearchParams) |
| `__tests__/pages/beta-signup.test.tsx` | `beta-signup/page.tsx` | Medium | `global.fetch` |
| `__tests__/pages/connections.test.tsx` | `connections/page.tsx` | Low | `@/components/connections/ConnectionsOverview` |
| `__tests__/pages/onboarding.test.tsx` | `onboarding/page.tsx` | Medium | `@/lib/hooks/useProfile`, `@/components/onboarding/OnboardingWizard`, `next/navigation` |
| `__tests__/pages/optimize.test.tsx` | `optimize/page.tsx` | High | `@/lib/hooks/useOptimization`, `@/lib/store/settings`, `@/lib/utils/format` |
| `__tests__/pages/settings.test.tsx` | `settings/page.tsx` | High | `@/lib/store/settings`, `@/lib/hooks/useSuppliers`, `@/lib/hooks/useProfile`, `global.fetch` |

### Priority 2 — Layout Tests

| Test File | Layout | Key Tests |
|-----------|--------|-----------|
| `__tests__/app/root-layout.test.tsx` | `app/layout.tsx` | Renders providers (QueryProvider, AuthProvider, ToastProvider), metadata exports, font class |
| `__tests__/app/app-layout.test.tsx` | `app/(app)/layout.tsx` | Renders Sidebar + SidebarProvider, children in `<main>` |

### Priority 3 — Component Tests

| Test File | Component | Key Tests |
|-----------|-----------|-----------|
| `__tests__/components/onboarding/AccountLinkStep.test.tsx` | `AccountLinkStep.tsx` | Renders with supplier, submit calls `useLinkAccount`, skip button calls `onSkip` |
| `__tests__/components/providers/QueryProvider.test.tsx` | `QueryProvider.tsx` | Renders children, provides QueryClient context |

### Priority 4 — Integration Tests

| Test File | Flow | Key Scenarios |
|-----------|------|---------------|
| `__tests__/integration/connections.test.tsx` | Connection flow | Add connection, method picker, upload, email, direct login, view rates/analytics |
| `__tests__/integration/onboarding.test.tsx` | Onboarding wizard | Full 4-step flow, redirect if completed, skip account link |
| `__tests__/integration/auth.test.tsx` | Auth flows | Login, signup, forgot/reset password, verify email, callback redirect |

---

## Key Testing Patterns Observed

- **Mock pattern for stores**: `jest.mock('@/lib/store/settings', () => ({ useSettingsStore: (selector) => selector({...}) }))`
- **Mock pattern for API**: `jest.mock('@/lib/api/prices', () => ({ getCurrentPrices: jest.fn() }))`
- **Auth mock**: `jest.mock('@/lib/auth/client', () => ({ authClient: { requestPasswordReset: jest.fn(), resetPassword: jest.fn(), verifyEmail: jest.fn(), sendVerificationEmail: jest.fn() } }))`
- **Router mock**: `jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn(), push: jest.fn() }), useSearchParams: () => new URLSearchParams() }))`
- **QueryClient wrapper**: All data-fetching pages need `QueryClientProvider` wrapper with `retry: false, gcTime: 0`
- **Better Auth mock**: Already configured in `__mocks__/better-auth-react.js`; `authClient` from `@/lib/auth/client` needs separate mocking

---

## Coverage Gap Estimate

Based on `jest.config.js` coverage threshold of 70% across branches/functions/lines/statements:

- `app/**/*.{ts,tsx}` is included in coverage collection
- 15 untested pages + 2 untested layouts represent a significant gap in `app/` coverage
- Current passing count: 1,126 frontend tests across 64 suites
- Estimated tests needed to close gaps: ~120-180 new tests across 17 new test files

The `optimize/page.tsx` and `settings/page.tsx` pages are the highest-complexity untested files and should be prioritized for integration-style page tests given their extensive inline logic (appliance CRUD, GDPR operations, supplier selection flows).
