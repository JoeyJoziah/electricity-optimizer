# Audit Report: Frontend Auth, Layout & UI Components
## Date: 2026-03-17
## Auditor: Claude Code (Sonnet 4.6)

---

### Executive Summary

This audit covers the frontend authentication layer, application layout shell, settings page, UI primitives, and supporting components (feedback, onboarding, dev tools, notifications). The codebase is in strong overall shape: the Better Auth integration is idiomatic, ARIA semantics are applied consistently, and the component API surface is well-typed.

**4 High-severity findings** were identified, all actionable without major refactoring:

1. Three protected routes (`/analytics`, `/gas-rates`, `/community-solar`) are absent from both the middleware `protectedPaths` list and its `matcher` config, leaving them fully accessible to unauthenticated users.
2. The Settings page enforces a minimum password length of 8 characters, which conflicts with the application-wide policy of 12 characters used in `SignupForm`, `ResetPasswordPage`, and the backend server config.
3. The `FeedbackWidget` modal has an incomplete focus trap: Escape closes the modal but focus is never restored to the trigger button after close, breaking keyboard navigation continuity.
4. The `OnboardingWizard` calls `updateProfile.mutateAsync` twice sequentially for `region`/`utility_types` then `onboarding_completed`, with no error handling on either call; a first-call failure silently leaves the user in an incomplete state.

No P0 (critical security) issues were found. No credentials are exposed client-side, `isSafeRedirect()` is consistently applied at the callbackUrl consumption point in `signIn()`, and the dev-only `/architecture` route has a triple guard (middleware rewrite, layout-level `notFound()`, `DevBanner` conditional).

---

### Findings

---

#### P1 — High

---

**P1-1: Three app routes missing from middleware protection and matcher — unauthenticated access possible**

Files:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/middleware.ts`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/analytics/page.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/gas-rates/page.tsx`
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/community-solar/page.tsx`

The routes `/analytics`, `/gas-rates`, and `/community-solar` are served under the `(app)` route group (with sidebar, auth context, and the full app shell) but are absent from both `protectedPaths` and the `matcher` array in `middleware.ts`. The matcher controls which routes Next.js even invokes middleware for, so an unauthenticated visitor can navigate directly to these URLs and render the full page content.

`/analytics` is labelled "Premium Analytics" in its page metadata and renders `AnalyticsDashboard`, which calls authenticated API endpoints. `/gas-rates` renders rate data. `/community-solar` renders solar content. All three pages will issue 401 API errors on load (caught by the API client's 401 handler which redirects to login), but the user sees a flash of the authenticated layout before the redirect fires.

The sidebar also includes no entry for `/gas-rates` or `/community-solar` (they are accessible via URL only), which may indicate they were intended as public pages. If they are truly public, they should be moved outside the `(app)` route group. If they are protected, add them to middleware.

Current `middleware.ts` `protectedPaths` (lines 12–29) and `matcher` (lines 70–91) must be updated.

Recommended fix for protected routes:

```typescript
// middleware.ts — add to protectedPaths array
'/analytics',
'/gas-rates',
'/community-solar',

// middleware.ts — add to matcher array
'/analytics/:path*',
'/gas-rates/:path*',
'/community-solar/:path*',
```

If these pages are intentionally public, move them to a route group outside `(app)` and remove the app-shell layout (sidebar + auth context) dependency from them.

---

**P1-2: Settings page enforces 8-character minimum password; application policy is 12 characters**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/settings/page.tsx` (line 168)

```typescript
// settings/page.tsx — current (incorrect)
if (newPassword.length < 8) {
  toastError('Password too short', 'Password must be at least 8 characters.')
  return
}
```

`SignupForm.tsx` (line 35) and `reset-password/page.tsx` (line 41, `MIN_PASSWORD_LENGTH = 12`) both enforce 12 characters, matching the backend's `minPasswordLength: 12` server config. The settings change-password form accepts any password of 8+ characters. This means a user who changes their password via Settings can set a weaker password than the one they created at signup.

Better Auth's `changePassword` call will pass the short password to the server, and the server's validation is the authoritative gate. However, the UI inconsistency is misleading and may result in user confusion if the backend rejects the request with a different error message.

Fix — align the constant and helper text:

```typescript
// settings/page.tsx
const MIN_PASSWORD_LENGTH = 12

// in handleChangePassword:
if (newPassword.length < MIN_PASSWORD_LENGTH) {
  toastError('Password too short', `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
  return
}

// on the Input component:
helperText={`Must be at least ${MIN_PASSWORD_LENGTH} characters`}
```

---

**P1-3: FeedbackWidget modal does not restore focus to the trigger button on close**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/feedback/FeedbackWidget.tsx`

The `FeedbackModal` component opens on click of the floating action button. When the modal closes (via Escape key or backdrop click), focus is not returned to the FAB. This is a WCAG 2.1 AA violation (Success Criterion 2.4.3 — Focus Order). Keyboard and screen-reader users lose their place in the document after dismissing the modal.

The `useEffect` (line 54) registers Escape handling and calls `firstFocusRef.current?.focus()` to move focus into the modal on open, but there is no cleanup that restores focus to the previously focused element.

The `modal.tsx` primitive handles this correctly via `previouslyFocusedRef` (lines 32–38, 77–78). The `FeedbackModal` should follow the same pattern.

Fix:

```typescript
// FeedbackModal — add these two lines to the useEffect
const previouslyFocused = document.activeElement as HTMLElement | null

// In the effect cleanup:
return () => {
  document.removeEventListener('keydown', handleKeyDown)
  previouslyFocused?.focus()   // restore focus on close
}
```

---

**P1-4: OnboardingWizard has two sequential mutateAsync calls with no error recovery on the first**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/onboarding/OnboardingWizard.tsx` (lines 24–33)

```typescript
const handleRegionSelect = async (selectedRegion: string) => {
  await updateProfile.mutateAsync({
    region: selectedRegion,
    utility_types: ['electricity'],
  })
  settingsStore.getState().setRegion(selectedRegion)
  settingsStore.getState().setUtilityTypes(['electricity'])

  await updateProfile.mutateAsync({ onboarding_completed: true })  // second call
  onComplete()
}
```

Both `mutateAsync` calls are bare `await` expressions with no try/catch. React Query `mutateAsync` throws on error; an unhandled rejection here will propagate to the React rendering layer. Because `OnboardingWizard` is not wrapped in an `ErrorBoundary`, this rejection will surface as an unhandled promise rejection in the console and the user will see no feedback.

Additionally, if the first call succeeds but the second fails, `onboarding_completed` is never set to `true`. The user is stranded on the onboarding page with their region already saved, and refreshing will trigger the "has region but onboarding_completed is false" auto-fix path in `useAuth.tsx` (line 214), which silently re-fires the second call — meaning the two-step mutation is partly redundant. A more robust approach combines both updates into a single call.

Fix — combine into one call with error handling:

```typescript
const handleRegionSelect = async (selectedRegion: string) => {
  try {
    await updateProfile.mutateAsync({
      region: selectedRegion,
      utility_types: ['electricity'],
      onboarding_completed: true,
    })
    settingsStore.getState().setRegion(selectedRegion)
    settingsStore.getState().setUtilityTypes(['electricity'])
    onComplete()
  } catch {
    // updateProfile.isError + updateProfile.error are now available
    // for the parent or a local error display
  }
}
```

---

#### P2 — Medium

---

**P2-1: Error boundary "Try again" button resets state but does not re-trigger the failed operation**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/error-boundary.tsx` (lines 36–38)

```typescript
handleReset = (): void => {
  this.setState({ hasError: false, error: null })
}
```

`handleReset` clears the error state, which causes the children to re-render. However, if the child's failure was caused by an initial data fetch that will not automatically retry on re-render (e.g. a `useEffect` with an empty dependency array that has already run), the "Try again" button does nothing observable — the component re-mounts to the same broken state immediately. The built-in fallback UI gives no indication of this.

The `resetErrorBoundary` pattern from react-error-boundary provides a `resetKeys` mechanism for this purpose. As a lighter-weight fix, the default fallback should set a `key` on the children so React fully unmounts and remounts them, forcing any initialization effects to re-run.

No code change is strictly required here, but callers should be aware that custom `fallback` props with an `onReset` callback (as used in `AppLayout`) are the only reliable reset path.

**P2-2: `useRequireAuth` hook redirects to `/auth/login` without a `callbackUrl` parameter**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/lib/hooks/useAuth.tsx` (lines 451–462)

```typescript
export function useRequireAuth(): AuthContextType {
  const auth = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      router.push('/auth/login')   // no callbackUrl
    }
  }, [auth.isLoading, auth.isAuthenticated, router])

  return auth
}
```

The middleware redirect (line 57–59 of `middleware.ts`) correctly appends `?callbackUrl=<pathname>` so that after login the user is returned to where they were. But `useRequireAuth` — intended as a client-side guard for use in page components — omits the `callbackUrl`. Any component using this hook for a secondary auth check will send the user to `/auth/login` with no return path, so after login they will land on `/dashboard` instead of the page they were on.

Since the middleware already handles the primary protection for all protected routes, `useRequireAuth` is not currently called from any page component (confirmed by grep — it is only referenced in its own test file and definition). It is safe to fix preemptively.

Fix:

```typescript
useEffect(() => {
  if (!auth.isLoading && !auth.isAuthenticated) {
    const callbackUrl = window.location.pathname + window.location.search
    router.push(`/auth/login?callbackUrl=${encodeURIComponent(callbackUrl)}`)
  }
}, [auth.isLoading, auth.isAuthenticated, router])
```

**P2-3: NotificationBell panel is not keyboard-dismissible via Escape**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/NotificationBell.tsx`

The notification panel renders as `role="dialog"` (line 113) but lacks an Escape key handler. The `modal.tsx` primitive and `FeedbackModal` both implement Escape-to-close; the NotificationBell panel is inconsistent. Per ARIA authoring practices, dialog/panel widgets should close on Escape.

Fix — add a `useEffect` that mirrors the click-outside handler:

```typescript
useEffect(() => {
  if (!open) return
  const handleKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') setOpen(false)
  }
  document.addEventListener('keydown', handleKey)
  return () => document.removeEventListener('keydown', handleKey)
}, [open])
```

**P2-4: Login page h1/h2 hierarchy — page-level title conflicts with form heading**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/login/page.tsx` (line 16) and `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/auth/LoginForm.tsx` (line 122)

The login page renders an `<h1>` ("RateShift") above the `LoginForm`. The `LoginForm` then renders an `<h2>` ("Sign in to your account"). This is the correct hierarchy. However, the signup page (`app/(app)/auth/signup/page.tsx`) is equivalent — it too has an `<h1>` from the page shell and the `SignupForm` renders its own `<h2>`. This is fine.

The sub-issue is that the page-level `<h1>` ("RateShift") on the login page is essentially a logo/brand label, not a landmark heading that describes the page content. Screen readers will announce "RateShift" as the page title, which is less descriptive than "Sign in to RateShift". This is minor but worth addressing for accessibility completeness.

**P2-5: Settings page "Reset Settings" is irreversible with no confirmation dialog**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/settings/page.tsx` (lines 644–652)

The "Reset" button calls `resetSettings()` (a Zustand store action) immediately on click. `handleDeleteAccount` (line 213) correctly gates on `window.confirm()`. The reset action is less severe than account deletion (it only clears localStorage-persisted preferences, not server data), but the omission of any confirmation for a "danger" variant button is still a UX gap.

The account deletion `window.confirm()` pattern is itself not ideal (native browser dialogs are not accessible to AT). A single confirmation modal using the existing `modal.tsx` primitive (`variant="danger"`) would be preferred for both actions.

**P2-6: `RegionSelector` search input is missing an accessible label**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/onboarding/RegionSelector.tsx` (lines 53–61)

```tsx
<input
  type="text"
  placeholder="Search states..."
  value={search}
  onChange={(e) => setSearch(e.target.value)}
  className="..."
/>
```

The search input has a `placeholder` but no `<label>` element and no `aria-label` attribute. Screen readers will announce only the placeholder text, which may not be meaningful once the user starts typing. The shared `Input` component (which automatically wires `htmlFor` + `id`) should be used here, or an `aria-label="Search states"` attribute added directly.

**P2-7: `AuthCallbackPage` unconditionally redirects to `/dashboard`, ignoring OAuth `callbackURL`**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/auth/callback/page.tsx` (lines 20–25)

`signInWithGoogle` and `signInWithGitHub` in `useAuth.tsx` set `callbackURL: '/onboarding'` (lines 358, 376). Better Auth handles the callback server-side via `/api/auth/callback/*`, so a new OAuth user should be redirected to `/onboarding`. However, if a user somehow lands on the `/auth/callback` client page (e.g. a browser that interrupted the server-side redirect), this page unconditionally calls `router.replace('/dashboard')`. A new user who hasn't completed onboarding would be sent to `/dashboard`, and the `initAuth` effect in `AuthProvider` would redirect them back to `/onboarding`, creating a redirect cycle visible as a brief flash.

This is low-probability in practice (the server-side handler will complete first for normal OAuth flows), but the fallback link on line 44 should use `/onboarding` instead of hardcoding `/dashboard` to match the intended OAuth post-signup destination, or use the `callbackUrl` query param if present.

---

#### P3 — Low

---

**P3-1: `LoginForm` and `SignupForm` duplicate the `isValidEmail` regex and OAuth env-var logic**

Files:
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/auth/LoginForm.tsx` (lines 19–23)
- `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/auth/SignupForm.tsx` (lines 26–30)

Both files define identical `isValidEmail` regex, `GOOGLE_ENABLED`, `GITHUB_ENABLED`, and `OAUTH_ENABLED` module-level constants. These should be extracted to a shared `lib/auth/constants.ts` or `lib/utils/validation.ts` to avoid divergence if either is changed.

**P3-2: OAuth social sign-in buttons are duplicated verbatim between LoginForm and SignupForm**

Files: `LoginForm.tsx` (lines 153–193), `SignupForm.tsx` (lines 171–213)

The Google and GitHub button JSX, including the inline SVG paths, is duplicated character-for-character. An `OAuthButtons` sub-component would eliminate ~80 lines of duplication and make future provider additions a single-site change.

**P3-3: `Header` component uses `setTimeout` for fake refresh delay**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Header.tsx` (lines 26–31)

```typescript
const handleRefresh = async () => {
  setIsRefreshing(true)
  refreshPrices()
  setTimeout(() => setIsRefreshing(false), 1000)  // artificial 1s delay
}
```

`refreshPrices()` is called but its promise is not awaited. The spinner disappears after a hard-coded 1 second rather than when the data fetch completes. If `useRefreshPrices` returns a Promise or is a React Query refetch function, it should be awaited so the spinner reflects actual request state.

**P3-4: `StatusBadge` always renders a green pulse, regardless of actual system status**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/StatusBadge.tsx`

The badge unconditionally renders a `bg-success-500 animate-pulse` dot. There is no fetching of the actual status page health; the green indicator is cosmetic only. This could mislead users during an actual outage. If `StatusBadge` is intended to be functional, it should fetch the status page API and conditionally color the dot.

**P3-5: `ArchitecturePage` creates a new `QueryClient` instance at module scope**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(dev)/architecture/page.tsx` (line 9)

```typescript
const queryClient = new QueryClient()
```

`QueryClient` is created at module level, meaning it is shared across hot-module reloads and concurrent tests. For a dev-only tool this is acceptable, but creating it inside the component (or via `useState`) is the idiomatic React Query pattern to avoid stale state. This is purely a dev-tool and has no production impact.

**P3-6: `OnboardingWizard` accesses the Zustand store directly via `.getState()` instead of the hook**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/onboarding/OnboardingWizard.tsx` (lines 21, 29–30)

```typescript
const settingsStore = useSettingsStore   // store, not a hook call
// later:
settingsStore.getState().setRegion(selectedRegion)
```

Calling `.getState()` bypasses Zustand's subscription mechanism and the React render cycle. If any component that subscribes to `region` needs to re-render after onboarding completes, it may not receive the update immediately. The canonical pattern is `useSettingsStore(s => s.setRegion)` inside the component to obtain the bound setter.

**P3-7: Hardcoded version string `v1.0.0` in Sidebar footer**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Sidebar.tsx` (line 154)

```tsx
<p className="px-3 py-1 text-[10px] text-gray-300">v1.0.0</p>
```

The version string is hardcoded. It will drift out of sync with actual releases. It should be sourced from `process.env.NEXT_PUBLIC_APP_VERSION` (injected at build time from `package.json`) or removed.

**P3-8: `handleDeleteAccount` uses `window.confirm()` — not accessible**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/app/(app)/settings/page.tsx` (lines 214–217)

`window.confirm()` dialogs are not consistently accessible across screen readers and cannot be styled. The existing `Modal` component with `variant="danger"` should be used for this destructive confirmation (same recommendation as P2-5 above).

**P3-9: `Sidebar` navigation has no `aria-label` on the `<nav>` element**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/layout/Sidebar.tsx` (line 74)

```tsx
<nav className="flex-1 space-y-1 px-3 py-4">
```

When there are multiple navigation landmarks on a page (e.g. pagination or breadcrumbs inside `<main>`), screen readers require `aria-label` to distinguish them. Adding `aria-label="Main navigation"` to this `<nav>` element satisfies WCAG 2.4.1 (Bypass Blocks) and aids AT users.

**P3-10: `Input` component: auto-generated `id` from `label` text is not collision-safe**

File: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/components/ui/input.tsx` (line 19)

```typescript
const inputId = id || label?.toLowerCase().replace(/\s+/g, '-')
```

If two `Input` components on the same page share the same label text (e.g. two "Password" fields in the same form, or a form rendered twice), they will generate duplicate `id` attributes. Duplicate IDs break the `<label htmlFor>` association for screen readers and cause HTML validation errors. An explicit `id` prop should always be passed, or the fallback should use `React.useId()` to guarantee uniqueness.

---

### Statistics

| Severity | Count | IDs |
|----------|-------|-----|
| P0 Critical | 0 | — |
| P1 High | 4 | P1-1 through P1-4 |
| P2 Medium | 7 | P2-1 through P2-7 |
| P3 Low | 10 | P3-1 through P3-10 |
| **Total** | **21** | |

### Files Audited

| File | Lines | Notes |
|------|-------|-------|
| `frontend/middleware.ts` | 91 | Auth route guard |
| `frontend/lib/hooks/useAuth.tsx` | 463 | Auth context + hooks |
| `frontend/components/auth/LoginForm.tsx` | 268 | Login UI |
| `frontend/components/auth/SignupForm.tsx` | 364 | Signup UI |
| `frontend/components/layout/Sidebar.tsx` | 215 | App navigation |
| `frontend/components/layout/Header.tsx` | 84 | Page header |
| `frontend/components/layout/NotificationBell.tsx` | 159 | Notification dropdown |
| `frontend/components/layout/StatusBadge.tsx` | 16 | Status indicator |
| `frontend/components/error-boundary.tsx` | 86 | React error boundary |
| `frontend/components/page-error-fallback.tsx` | 53 | Page-level error UI |
| `frontend/components/feedback/FeedbackWidget.tsx` | 285 | Feedback FAB + modal |
| `frontend/components/onboarding/OnboardingWizard.tsx` | 45 | Onboarding flow |
| `frontend/components/onboarding/RegionSelector.tsx` | 122 | State picker |
| `frontend/components/onboarding/AccountLinkStep.tsx` | 73 | Account linking |
| `frontend/components/dev/DevBanner.tsx` | 13 | Dev mode indicator |
| `frontend/components/dev/DiagramList.tsx` | 62 | Diagram sidebar |
| `frontend/components/dev/DiagramEditor.tsx` | 114 | Excalidraw editor wrapper |
| `frontend/components/dev/ExcalidrawWrapper.tsx` | 60 | Excalidraw dynamic import |
| `frontend/components/ui/button.tsx` | 75 | Button primitive |
| `frontend/components/ui/input.tsx` | 136 | Input + Checkbox primitives |
| `frontend/components/ui/modal.tsx` | 134 | Modal dialog |
| `frontend/components/ui/toast.tsx` | 71 | Toast notification |
| `frontend/app/(app)/layout.tsx` | 31 | App route group layout |
| `frontend/app/(dev)/layout.tsx` | 15 | Dev route group layout |
| `frontend/app/(app)/settings/page.tsx` | 700 | Settings page |
| `frontend/app/(app)/auth/login/page.tsx` | 26 | Login page |
| `frontend/app/(app)/auth/callback/page.tsx` | 51 | OAuth callback page |
| `frontend/app/(app)/auth/reset-password/page.tsx` | 204 | Password reset page |
| `frontend/app/(app)/analytics/page.tsx` | 24 | Analytics page |
| `frontend/app/(app)/onboarding/page.tsx` | 61 | Onboarding page |
| `frontend/app/(dev)/architecture/page.tsx` | 66 | Architecture diagram tool |
| `frontend/lib/utils/url.ts` | 46 | `isSafeRedirect` utility |
| `frontend/lib/api/client.ts` | ~60 (head) | API client 401 handler |

### Priority Fix Order

1. **P1-1** — Add `/analytics`, `/gas-rates`, `/community-solar` to middleware `protectedPaths` and `matcher` (or decide they are public and move them out of the `(app)` group).
2. **P1-2** — Align Settings change-password minimum to 12 characters.
3. **P1-3** — Restore focus to FAB on FeedbackModal close.
4. **P1-4** — Consolidate `OnboardingWizard` into a single `mutateAsync` call with try/catch.
5. **P2-3** — Add Escape handler to `NotificationBell` panel.
6. **P2-6** — Add `aria-label` or `<label>` to `RegionSelector` search input.
7. **P3-9** — Add `aria-label="Main navigation"` to `<nav>` in Sidebar.
8. **P3-7** — Source sidebar version from env var.
9. Remaining P3 items as bandwidth allows.
