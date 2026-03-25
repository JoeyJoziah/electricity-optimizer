> **DEPRECATED** — This document is archived for historical reference only. It may contain outdated information. See current documentation in the parent `docs/` directory.

---

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

---

## 2. Auth Helper Analysis (`frontend/e2e/helpers/auth.ts`)

### Existing Functions

| Function | What It Does |
|---|---|
| `mockBetterAuth(page, options?)` | Intercepts `/api/auth/sign-in/email`, `/api/auth/get-session`, `/api/auth/sign-out`, `/api/auth/sign-up/email`, `/api/auth/callback/**`, `/api/auth/sign-in/social` |
| `setAuthenticatedState(page)` | Injects `better-auth.session_token` cookie directly |
| `clearAuthState(page)` | Clears `better-auth.session_token` cookie |

---

## 3. Complete Skipped Test Inventory

### `authentication.spec.ts` — 5 skipped tests

| # | Test Name | Line | Reason | Difficulty |
|---|---|---|---|---|
| 1 | `validates email format` | 72 | HTML5 native browser tooltip — not a visible DOM element | Easy |
| 2 | `user can login with magic link` | 107 | Magic link not supported by useAuth | Medium |
| 3 | `user can logout` | 120 | User menu UI not yet finalized — testid `user-menu` missing | Easy |
| 4 | `shows forgot password link` | 141 | Forgot password UI not implemented | Medium |
| 5 | `clears sensitive data on logout` | 219 | User menu UI not yet finalized | Easy |

---

## 4. Missing Test ID Map

| `data-testid` Used in Tests | Exists in Source? | Action Required |
|---|---|---|
| `user-menu` | NO | Add `data-testid="sign-out-button"` to sign-out button in Sidebar |
| `supplier-card-settings` | NO | Add `data-testid="appliance-card-settings"` to appliance card |
| `schedule-block-1` | YES (dynamic) | May just need to unskip |
| `price-zone-cheap` / `price-zone-expensive` | YES (dynamic) | Verify zone types match test expectations |

---

## 5. E2E Coverage Gaps (No Tests at All)

| Flow | Coverage Status | Notes |
|---|---|---|
| Connection management | NO E2E tests | All 5 phases complete — zero E2E coverage. High priority. |
| Billing subscription management | Partial | Covers pricing page + checkout initiation. Missing: portal redirect, post-checkout success |
| Settings save confirmation | Minimal | Has 5 tests but no test for persistence after reload |
| Onboarding wizard | Good | Has 7 tests. Good coverage. |
| Profile/account management | None | No test for profile updates |
| Password change | None | No test for password change flow |
| Notification system | None | No test for notification bell |
| GDPR suite | Skipped (entire suite) | 4 planned tests, all skipped |

---

## Summary Statistics

| Category | Count |
|---|---|
| Total E2E spec files | 15 |
| Individual `test.skip` calls | 16 |
| Entire suites skipped | 2 |
| Total tests affected by skips | ~23 |
| Easy wins (can unskip with minimal change) | 7 tests |
| Testids missing from source but needed | 2 |

---

*This report is an archived analysis of E2E test coverage from March 2026 audits.*
