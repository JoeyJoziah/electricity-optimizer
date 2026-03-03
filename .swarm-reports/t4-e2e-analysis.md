# T4: E2E Test Analysis Report

> Generated: 2026-03-03 | Agent: e2e-fixer

---

## 1. Playwright Configuration Notes

**File**: `frontend/playwright.config.ts`

- **Base URL**: `http://localhost:3000`
- **Test dir**: `./e2e`
- **Fully parallel**: yes
- **CI retries**: 2
- **Browsers**: Chromium, Firefox, WebKit, Mobile Chrome (Pixel 5), Mobile Safari (iPhone 12)
- **Timeout**: default (30s per action, not explicitly set)
- **No global setup/teardown** configured
- **Web server**: `npm run dev` — reuses existing server in non-CI mode
- **Trace**: on-first-retry only; screenshot on failure only

**Gaps**:
- No explicit `timeout` configured at test level (could cause flakiness)
- No global auth setup (each test manually mocks or sets cookies)
- No `globalSetup` / `globalTeardown` for shared state

---

## 2. Auth Helper Analysis (`frontend/e2e/helpers/auth.ts`)

### Existing Functions

| Function | What It Does |
|---|---|
| `mockBetterAuth(page, options?)` | Intercepts `/api/auth/sign-in/email`, `/api/auth/get-session`, `/api/auth/sign-out`, `/api/auth/sign-up/email`, `/api/auth/callback/**`, `/api/auth/sign-in/social` |
| `setAuthenticatedState(page)` | Injects `better-auth.session_token` cookie directly |
| `clearAuthState(page)` | Clears `better-auth.session_token` cookie |

### Auth Scenarios NOT Covered

1. **`__Secure-better-auth.session_token`** cookie — MEMORY.md notes that on HTTPS, Better Auth auto-prefixes with `__Secure-`. The auth helper only sets/clears the non-secure variant. In production-like E2E environments this could fail middleware checks.

2. **Logout via sidebar** — The sidebar has a "Sign out" button but there is NO `data-testid="user-menu"` anywhere in source. The skipped logout tests reference `[data-testid="user-menu"]` but the Sidebar component (`components/layout/Sidebar.tsx:98-104`) renders a plain `<button>` with text "Sign out" — no testid. Tests that rely on the user-menu testid will need the sidebar's sign-out button to get `data-testid="sign-out-button"` added.

3. **Session expiry UI flow** — The `sessionExpired` option is mocked but there is no test for what the UI shows when a mid-session token expires (e.g., forced redirect on API 401).

4. **Password reset / forgot password** — No mock for password reset endpoints.

5. **Email verification** — No mock for the verification flow after signup.

6. **Multi-tab scenarios** — SSE `openWhenHidden: false` is set but no E2E tests for tab visibility changes.

---

## 3. Complete Skipped Test Inventory

### `authentication.spec.ts` — 5 skipped tests

| # | Test Name | Line | Reason | Difficulty |
|---|---|---|---|---|
| 1 | `validates email format` | 72 | HTML5 native browser tooltip — not a visible DOM element | Easy — remove skip; assert `input:invalid` or use a custom error display approach |
| 2 | `user can login with magic link` | 107 | Magic link not supported by useAuth — returns error message | Medium — feature not implemented; keep skipped until feature ships |
| 3 | `user can logout` | 120 | User menu UI not yet finalized — testid `user-menu` missing | Easy — add `data-testid="sign-out-button"` to Sidebar button; update test selector |
| 4 | `shows forgot password link` | 141 | Forgot password UI not implemented | Medium — feature not implemented; keep skipped |
| 5 | `clears sensitive data on logout` | 219 | User menu UI not yet finalized — testid `user-menu` missing | Easy — same fix as #3; add testid to Sidebar |

### `dashboard.spec.ts` — 1 conditional skip

| # | Test Name | Line | Reason | Difficulty |
|---|---|---|---|---|
| 6 | `shows realtime indicator` (mobile) | 141 | `test.skip(isMobile === true, ...)` — indicator is `hidden sm:flex` | Already correct — skip is appropriate, not a bug |

### `full-journey.spec.ts` — 2 skipped tests

| # | Test Name | Line | Reason | Difficulty |
|---|---|---|---|---|
| 7 | `Step 2: Navigate to signup and fill the form` | 226 | SignupForm uses Better Auth client directly — needs proper route interception | Medium — `mockBetterAuth` already intercepts `/api/auth/sign-up/email`; likely fixable by removing skip |
| 8 | `Step 3: Signup API responds correctly and user is redirected` | 254 | Same as above | Medium — same fix; the skip comment says "needs mockBetterAuth route interception" but auth.ts already does this |

### `gdpr-compliance.spec.ts` — 1 entire suite skipped (4 tests)

| # | Test Name | Line | Reason | Difficulty |
|---|---|---|---|---|
| 9 | Entire `GDPR Compliance Flow` describe | 18 | `test.skip()` at describe level — GDPR consent management UI not yet implemented | Hard — needs new UI: data export, `/settings/privacy`, deletion confirmation, cookie banner |

**Individual tests in skipped suite**:
- `navigates to privacy settings` — settings page already has Privacy & Data section; could be unskipped partially
- `user can export all data` — Export button not implemented
- `user can view consent settings` — `/settings/privacy` route does not exist
- `user can delete all data with confirmation` — Delete button not implemented

### `load-optimization.spec.ts` — 1 entire suite skipped (3 tests)

| # | Test Name | Line | Reason | Difficulty |
|---|---|---|---|---|
| 10 | Entire `Load Optimization Flow` describe | 19 | `test.skip()` at describe level — optimization wizard UI not yet implemented | Hard — 3 vague tests that duplicate `optimization.spec.ts` tests |

**Note**: The active `optimization.spec.ts` file already covers the optimization page. `load-optimization.spec.ts` appears to be a legacy/duplicate file.

### `optimization.spec.ts` — 4 skipped tests

| # | Test Name | Line | Reason | Difficulty |
|---|---|---|---|---|
| 11 | `can remove appliance in edit mode` | 94 | TODO: `supplier-card-settings` testid not implemented in SupplierCard | Medium — add `data-testid="appliance-card-settings"` to appliance card; rename selector in test |
| 12 | `runs optimization and shows results` | 103 | TODO: `schedule-block-{id}` testids on ScheduleTimeline | Easy — testids EXIST in `ScheduleTimeline.tsx:203` as `data-testid={`schedule-block-${schedule.applianceId}`}`; test uses static id "1" but mock data uses `applianceId: '1'` — should work if optimization results are shown |
| 13 | `displays schedule details` | 113 | TODO: schedule details after optimization | Medium — depends on whether ScheduleTimeline renders after optimization API call |
| 14 | `timeline shows price zones` | 157 | TODO: `price-zone-{type}` testids on ScheduleTimeline | Easy — testids EXIST in `ScheduleTimeline.tsx:180` as `data-testid={`price-zone-${zone.type}`}`; need to verify price-zone data is populated |

### `sse-streaming.spec.ts` — 1 conditional skip

| # | Test Name | Line | Reason | Difficulty |
|---|---|---|---|---|
| 15 | `dashboard shows realtime indicator` (mobile) | 99 | Same as dashboard.spec.ts — correct skip | Already correct |

### `switching.spec.ts` — 1 skipped test

| # | Test Name | Line | Reason | Difficulty |
|---|---|---|---|---|
| 16 | `can switch view between grid and table` | 127 | TODO: implement table view toggle on suppliers page | Easy — table view IS implemented in `SuppliersContent.tsx` (`viewMode` state, ComparisonTable component); the test is looking for the wrong selector. The buttons are aria-pressed toggles |

---

## 4. Missing Test ID Map

| `data-testid` Used in Tests | Exists in Source? | Component File | Action Required |
|---|---|---|---|
| `user-menu` | NO | `components/layout/Sidebar.tsx` | Add `data-testid="sign-out-button"` to sign-out `<button>` (line 98-104); update test selectors |
| `supplier-card-settings` | NO | Likely an appliance card component | Add `data-testid="appliance-card-settings"` to appliance card edit button in optimize page |
| `schedule-block-1` | YES (dynamic) | `components/charts/ScheduleTimeline.tsx:203` | Uses `schedule.applianceId` — mock data applianceId `'1'` should match `schedule-block-1`; may just need to unskip |
| `price-zone-cheap` / `price-zone-expensive` | YES (dynamic) | `components/charts/ScheduleTimeline.tsx:180` | Uses `zone.type` — need to verify zone types are `cheap`/`expensive` or adjust test |
| `supplier-card-1` / `supplier-card-2` | YES (dynamic) | `components/suppliers/SupplierCard.tsx:49` | Uses `supplier.id` — works when supplier IDs are `'1'` and `'2'` as in test mocks |
| `realtime-indicator` | YES | `components/layout/Header.tsx:53` | Already correct |
| `current-price` | YES | `components/dashboard/DashboardContent.tsx:218` / `PriceLineChart.tsx:177` | Already correct |
| `price-trend` | YES | `components/dashboard/DashboardContent.tsx:228` / `PriceLineChart.tsx:186` | Already correct |
| `price-chart-container` | YES | `components/charts/PriceLineChart.tsx:125,142,170` | Already correct |

### Testids to ADD to Source Components

1. **`components/layout/Sidebar.tsx` line ~98**: Add `data-testid="sign-out-button"` to `<button onClick={() => signOut()}>` — unlocks 3 tests (auth #3, auth #5)
2. **Appliance card component** (optimize page): Add `data-testid="appliance-card-settings"` to the edit/settings toggle — unlocks 1 test (optimization #11)

---

## 5. E2E Coverage Gaps (No Tests at All)

| Flow | Coverage Status | Notes |
|---|---|---|
| Connection management | NO E2E tests | All 5 phases of connections feature are complete — zero E2E coverage. Connection page exists at `/connections`. Components have rich testids: `connection-card-{id}`, `connection-analytics`, `rate-comparison-card`, `rate-history-table`, etc. High priority to add. |
| Billing subscription management | Partial | `billing-flow.spec.ts` covers pricing page + checkout initiation. Missing: actual portal redirect, post-checkout success page, webhook-triggered tier upgrade UI |
| Settings save confirmation | Minimal | `settings.spec.ts` has 5 tests but no test for region/preference change + reload persistence |
| Onboarding wizard | Good | `onboarding-flow.spec.ts` has 7 tests. Good coverage of 3-step wizard |
| Profile/account management | None | No test for profile name update, email change, avatar |
| Password change | None | No test for password change flow in settings |
| Notification system | None | No test for notification bell or notification preferences saving |
| Mobile navigation | Partial | Mobile viewport tested in dashboard + sse-streaming but no test for mobile sidebar open/close |
| GDPR suite | Skipped (entire suite) | 4 planned tests, all skipped. Partial match — Privacy & Data section in Settings is visible |
| Connection analytics | None | Rich testids available but no E2E test |
| Bill upload flow | None | FileUpload component used in connections — no E2E |
| Email OAuth flow | None | Email OAuth UI components exist — no E2E |

---

## 6. Priority-Ordered Fix Plan

### Priority 1 — Easy Wins (1 testid addition each, high ROI)

**Fix 1: Add `data-testid="sign-out-button"` to Sidebar** (30 min)
- File: `frontend/components/layout/Sidebar.tsx`, line 98
- Add `data-testid="sign-out-button"` to the sign-out button
- Then update `authentication.spec.ts` test #3 (`user can logout`) and #5 (`clears sensitive data on logout`) to use `[data-testid="sign-out-button"]` instead of `[data-testid="user-menu"]`
- Remove skip from both tests
- **Unlocks**: 2 tests

**Fix 2: Unskip `can switch view between grid and table` in switching.spec.ts** (1 hour)
- The table view toggle exists in `SuppliersContent.tsx` using `aria-pressed` buttons
- Update selector from `getByRole('button').filter({has:svg}).nth(1)` to `page.getByRole('button', { name: /table view/i })` or use aria-pressed attribute query
- Remove skip
- **Unlocks**: 1 test

**Fix 3: Unskip optimization schedule-block tests** (1 hour)
- `schedule-block-{applianceId}` testids exist in `ScheduleTimeline.tsx:203`
- `price-zone-{type}` testids exist in `ScheduleTimeline.tsx:180`
- Need to verify the Optimize page renders ScheduleTimeline after optimization and that zone types match expected values (`cheap`/`expensive`)
- Read ScheduleTimeline to confirm zone type values, then unskip tests 12 and 14
- **Unlocks**: 2 tests

**Fix 4: Unskip full-journey signup steps 2 and 3** (45 min)
- `mockBetterAuth` already mocks `/api/auth/sign-up/email`
- Remove `test.skip` from `Step 2` and `Step 3` tests in `full-journey.spec.ts`
- Test expects `check your email|dashboard|onboarding` — confirm which redirect path the signup form uses
- **Unlocks**: 2 tests

### Priority 2 — Medium Effort (implementation required)

**Fix 5: Add appliance card settings testid** (2 hours)
- Locate the appliance card component in the optimize page
- Add `data-testid="appliance-card-settings"` to the edit/settings control
- Update `optimization.spec.ts` test #11 selector and remove skip
- **Unlocks**: 1 test

**Fix 6: Unskip `validates email format`** (1 hour)
- Current test expects visible text `/valid email/i` — native browser tooltips are not visible text nodes
- Options: (a) add custom validation error text to the login form, OR (b) change assertion to `input:invalid` via `page.locator('#email:invalid')`
- If the login form already shows custom errors, the test may need just a selector fix
- **Unlocks**: 1 test

### Priority 3 — New Test Suites (feature-complete areas with zero E2E)

**Fix 7: Add connections E2E test file** (4-6 hours)
- Create `frontend/e2e/connections.spec.ts`
- Cover: display connections overview, add connection via method picker, view connection card, trigger sync, view analytics
- Rich testids already available in connection components
- High business value — this is a major feature with zero E2E coverage

**Fix 8: Unskip GDPR privacy navigation test** (1 hour)
- In `gdpr-compliance.spec.ts`, test `navigates to privacy settings` — Settings page DOES have a "Privacy & Data" section
- Extract this single test from the skipped suite and move it to `settings.spec.ts`
- The full suite should remain skipped until export/delete/consent-page features are built

### Priority 4 — Feature-Gated (skip until features ship)

| Test | Status | Reason |
|---|---|---|
| `user can login with magic link` | Keep skipped | Feature not implemented |
| `shows forgot password link` | Keep skipped | Feature not implemented |
| `user can export all data` (GDPR) | Keep skipped | Export endpoint not implemented |
| `user can view consent settings` (GDPR) | Keep skipped | `/settings/privacy` route doesn't exist |
| `user can delete all data` (GDPR) | Keep skipped | Delete confirmation UI not implemented |
| Entire `load-optimization.spec.ts` | Consider deleting | Duplicates `optimization.spec.ts`; 3 vague tests |

---

## 7. Auth Mocking Gap Analysis Summary

| Auth Scenario | Covered? | Gap |
|---|---|---|
| Email/password sign-in (success) | Yes | — |
| Email/password sign-in (failure) | Yes | — |
| Email/password sign-in (rate limited) | Yes | — |
| Session validation (active) | Yes | — |
| Session validation (expired) | Yes | — |
| Sign-out | Yes | — |
| Sign-up | Yes | — |
| OAuth callback | Yes | — |
| Social sign-in initiation | Yes | — |
| `__Secure-` cookie variant (HTTPS) | NO | `setAuthenticatedState` only sets plain `better-auth.session_token`; may fail in HTTPS test environments |
| Mid-session token expiry redirect | No | `sessionExpired` option exists but no test verifies the redirect path |
| Password reset flow | No | No route mock; feature not yet implemented |
| Email verification flow | No | No route mock; feature not yet implemented |
| Sign-out via sidebar button | No | Skipped tests reference non-existent `user-menu` testid |

---

## 8. Estimated Testid Additions by Component

| Component | Testids to Add | Count |
|---|---|---|
| `components/layout/Sidebar.tsx` | `sign-out-button` | 1 |
| Appliance card in optimize page | `appliance-card-settings` | 1 |
| **Total** | | **2** |

No other component requires new testids to fix the existing skipped tests.

---

## Summary Statistics

| Category | Count |
|---|---|
| Total E2E spec files | 15 |
| Individual `test.skip` calls | 16 |
| Entire suites skipped (`test.skip()` at describe) | 2 (`gdpr-compliance`, `load-optimization`) |
| Total tests affected by skips | ~23 |
| Easy wins (can unskip with minimal change) | 7 tests |
| Medium effort (need testid addition or selector fix) | 4 tests |
| Feature-gated (must stay skipped) | 8 tests |
| Flows with ZERO E2E coverage | 6 (connections, billing portal, profile, password change, notifications, connection analytics) |
| Testids missing from source but needed | 2 (`sign-out-button`, `appliance-card-settings`) |
| Testids referenced that already exist | 6 (`realtime-indicator`, `current-price`, `price-trend`, `supplier-card-{id}`, `schedule-block-{id}`, `price-zone-{type}`) |
