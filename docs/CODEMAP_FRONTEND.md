# Frontend Codemap

**Last Updated:** 2026-03-11 (AI Agent production, notification delivery tracking, A/B testing framework, Wave 4-5 completion)
**Framework:** Next.js 16.0.x (App Router) + React 19 + TypeScript
**Entry Point:** `frontend/app/layout.tsx`
**State Management:** Zustand (persisted to localStorage) + TanStack React Query v5
**Styling:** Tailwind CSS 3.4.1 + tailwind-merge + clsx
**Test Coverage:** Frontend 1,439+ tests (99 suites, 0 failures, 6 warnings pre-rebrand)

---

## Directory Structure

```
frontend/
  middleware.ts                   # Route protection (redirects unauthenticated users)
  app/                          # Next.js App Router (pages + API routes)
    layout.tsx                  # Root layout: Inter font, QueryProvider, AuthProvider
    page.tsx                    # Landing page (/) - marketing, hero, features, pricing preview
    error.tsx                   # Root error boundary
    global-error.tsx            # Global error boundary (catches layout-level errors)
    not-found.tsx               # 404 page
    manifest.ts                 # PWA manifest (standalone, blue theme)
    icon.tsx                    # Favicon 32x32 (next/og ImageResponse, blue bolt icon)
    apple-icon.tsx              # Apple touch icon 180x180 (gradient blue, rounded)
    robots.ts                   # robots.txt (disallows /api/, /dashboard/)
    sitemap.ts                  # Sitemap (/, /pricing, /dashboard, /privacy, /terms)
    globals.css                 # Global styles + design system CSS variables + animations
    pricing/page.tsx            # Pricing page (/pricing) - 3 tiers with FAQ
    privacy/page.tsx            # Privacy policy (/privacy)
    terms/page.tsx              # Terms of service (/terms)
    api/
      auth/[...all]/route.ts    # Better Auth API handler (sign-in, sign-up, sign-out, OAuth, etc.)
      checkout/route.ts         # POST /api/checkout - proxies to backend billing/checkout
      pwa-icon/route.tsx        # GET /api/pwa-icon?size=192|512 — dynamic PWA icon (ImageResponse)
    (app)/                      # Route group: authenticated app pages (sidebar layout)
      layout.tsx                # Sidebar layout + navigation
      dashboard/
        page.tsx                # Dashboard overview (user stats, recent recommendations)
        loading.tsx             # Stats + activity skeleton
      prices/
        page.tsx                # Electricity prices table + region selector
        loading.tsx             # Price table skeleton
      suppliers/
        page.tsx                # Supplier details + regional availability
        loading.tsx             # Grid skeleton for supplier cards
      optimize/
        page.tsx                # Appliance optimization tool + recommendations
        loading.tsx             # Stats + appliance/schedule skeleton
      settings/page.tsx         # User settings (region, notifications, profile)
      onboarding/page.tsx       # Initial setup flow (region selection, utility preferences)
      connections/
        page.tsx                # Connections overview (bills, utilities, direct sync)
        loading.tsx             # Connection cards + method picker skeleton
      alerts/
        page.tsx                # Alerts CRUD page (/alerts) — wrapper for AlertsContent
      assistant/
        page.tsx                # AI Assistant chat interface (/assistant) — RateShift AI agent (Gemini 3 Flash + Groq fallback, Composio tools)
      beta-signup/
        page.tsx                # Early access signup (public route, beta invitations, progress tracking)
      auth/                     # Authentication pages (route group within (app))
        layout.tsx              # Auth layout (centered cards, no sidebar)
        login/page.tsx          # Sign in form (email/password, OAuth, magic link)
        signup/page.tsx         # Register form (email/password, OAuth, terms)
        forgot-password/page.tsx # Password reset request
        reset-password/page.tsx  # Password reset form
        callback/page.tsx       # OAuth callback handler
        verify-email/page.tsx   # Email verification after signup
      (dev)/                    # Route group: development-only pages (gate with notFound)
        layout.tsx              # Dev layout (DevBanner, notFound if not development)
        architecture/page.tsx   # Excalidraw diagram editor (list + canvas)
  components/
    ui/
      input.tsx                 # Input + Checkbox: validation, success/error states, labelSuffix/labelRight
      button.tsx                # Button: primary/secondary/outline variants, loading state
      card.tsx                  # Card: CardHeader, CardTitle, CardContent, CardDescription
      badge.tsx                 # Badge: status indicators (primary/success/danger/warning)
      modal.tsx                 # Modal: controlled dialog with overlay
      toast.tsx                 # Toast: notifications (success/error/warning)
      dropdown.tsx              # Dropdown: menu with keyboard navigation
      tabs.tsx                  # Tabs: tab navigation (horizontal)
      tooltip.tsx               # Tooltip: hover text with delay
      avatar.tsx                # Avatar: user profile images with fallback
      skeleton.tsx              # Skeleton: shimmer loading placeholder
      spinner.tsx               # Spinner: animated loading indicator
    auth/
      LoginForm.tsx             # Login form (email blur validation, conditional OAuth, magic link toggle)
      SignupForm.tsx            # Signup form (password strength, conditional OAuth, email verification redirect)
    layout/
      Sidebar.tsx               # Main navigation sidebar (app pages only)
      Header.tsx                # Top header (logo, user menu, mobile toggle)
      NotificationBell.tsx      # In-app notification bell (sidebar, unread count badge, dropdown panel, mark read)
      DevBanner.tsx             # Development-only banner (top of page)
    dashboard/
      StatsCard.tsx             # Metric card (value, label, change %)
      RecentActivity.tsx        # Activity feed (timestamps, user actions)
      RecommendationCard.tsx    # Optimization recommendation display
    prices/
      PriceTable.tsx            # Prices data table (sortable, filterable)
      RegionSelector.tsx        # Dropdown to switch regions
      PriceChart.tsx            # Recharts visualization (line/area)
      PriceTrendsBadge.tsx      # Up/down indicator with color coding
    suppliers/
      SupplierList.tsx          # Supplier grid/table (region filtered)
      SupplierCard.tsx          # Supplier info card
      SupplierSelector.tsx      # Dropdown with search (bg-white text-gray-900)
    optimize/
      ApplianceForm.tsx         # Add/edit appliance
      ApplianceCard.tsx         # Display appliance with settings button
      RecommendationList.tsx    # List of optimization suggestions
    connections/                # Connection feature UI (9 components)
      Overview.tsx              # Dashboard of user connections
      MethodPicker.tsx          # Select connection type (direct, bill, email, etc.)
      Card.tsx                  # Connection status card
      DirectLogin.tsx           # UtilityAPI direct sync form (bg-white, text-gray-900)
      EmailFlow.tsx             # Gmail/Outlook OAuth flow
      BillUpload.tsx            # Bill upload form
      UploadFlow.tsx            # Multi-step upload wizard
      Rates.tsx                 # Imported rates table (sortable)
      Analytics.tsx             # Rate comparison + savings dashboard
    alerts/
      AlertsContent.tsx         # Main alerts component: My Alerts tab (CRUD) + History tab (paginated)
      AlertForm.tsx             # Create alert form: region select, price thresholds, optimal windows checkbox
    agent/
      AgentChat.tsx             # RateShift AI chat interface (streaming query, example prompts, message bubbles, model+tools display)
    feedback/
      FeedbackWidget.tsx        # In-app feedback collection widget (survey, rating, comment submission)
    settings/
      ProfileForm.tsx           # Edit user info
      RegionSelector.tsx        # Change region with 50 states + DC support
      NotificationPrefs.tsx     # Email notification toggles
      DangerZone.tsx            # Delete account button
  lib/
    hooks/
      useAuth.tsx               # Custom hook: auth state + sign in/up/out + magic link + email verification + OneSignal login/logout
      useAlerts.ts              # TanStack Query hooks: useAlerts, useAlertHistory, useCreateAlert, useUpdateAlert, useDeleteAlert (staleTime: 30s)
      useAgent.ts               # Agent query hook: useAgentQuery (streaming, messages, error, cancel, reset), useAgentStatus (usage limits)
      useConnections.ts         # TanStack Query hook: useConnections — migrated from useEffect+fetch (retry: false, staleTime: 30s, 403 gate preserved)
      useNotifications.ts       # TanStack Query hooks: useNotifications (staleTime 30s), useNotificationCount (refetch 30s), useMarkRead, useMarkAllRead
      useRealtime.ts            # Custom hook: SSE connection (openWhenHidden: false)
      useLocalStorage.ts        # Persist state to browser storage
      useDarkMode.ts            # Dark mode toggle (future)
      useMediaQuery.ts          # Responsive design breakpoint detection
      useClickOutside.ts        # Detect clicks outside an element
      useDebounce.ts            # Debounce values/callbacks
    utils/
      cn.ts                     # clsx + tailwind-merge for className composition
      format.ts                 # Currency formatting (Intl.NumberFormat, en-US)
      url.ts                    # isSafeRedirect() for same-origin validation
      api.ts                    # API client + error handling
      auth.ts                   # Auth utilities (JWT decode, token storage)
      error.ts                  # Error message extraction + logging
    api/
      client.ts                 # Fetch wrapper + 401 handler (3-layer callbackUrl guard)
      alerts.ts                 # Alerts API: getAlerts, createAlert, updateAlert, deleteAlert, getAlertHistory. Types: Alert, AlertHistoryItem, GetAlertsResponse, GetAlertHistoryResponse
      agent.ts                  # Agent API: queryAgent (SSE streaming, async generator), submitTask (async job), getAgentUsage (rate limits). Types: AgentMessage, AgentUsage, AgentTaskResponse, AgentJobResult
      notifications.ts          # Notifications API: getNotifications, getNotificationCount, markNotificationRead, markAllRead. Types: Notification, GetNotificationsResponse, GetNotificationCountResponse
      __tests__/
        client-401-redirect.test.ts  # 9 tests for 401 edge cases
    auth/
      server.ts                 # Better Auth server instance (emailVerification, magicLink plugin, password reset)
      client.ts                 # Better Auth client instance (magicLinkClient plugin)
    email/
      send.ts                   # Dual-provider email: Resend (primary) + nodemailer SMTP (fallback). getResend() returns null when key missing. sendViaSMTP() uses SMTP_HOST/PORT/USERNAME/PASSWORD
    notifications/
      onesignal.ts              # OneSignal push: loginOneSignal(userId), logoutOneSignal(). Uses v3+ API (login() replaces deprecated setExternalUserId())
    config/
      env.ts                    # Centralized NEXT_PUBLIC_* validation
  styles/
    (additional global styles imported in globals.css)
  public/
    (static assets: icons, logos, fonts)
  __tests__/
    __mocks__/
      better-auth-react.js      # ESM → CJS bridge for jest
    a11y/
      (51 accessibility tests using jest-axe)
    unit/
      (component unit tests with React Testing Library)
  e2e/
    (Playwright E2E tests, 634 passed, 5 skipped)
    helpers/
      auth.ts                   # mockBetterAuth(), setAuthenticatedState(), clearAuthState()
  playwright.config.ts          # E2E config (retries: 1, timeout fixes)
  jest.config.js                # Jest config
  tailwind.config.ts            # Tailwind CSS theme config
  tsconfig.json                 # TypeScript config
  next.config.js                # Next.js config (CSP, HSTS headers)
  package.json                  # Dependencies, scripts, dev tools (includes nodemailer + @types/nodemailer)
```

---

## Design System

### Colors (Tailwind CSS Extended)

```typescript
// Primary blue (brand color)
primary: {
  50: '#eff6ff',    100: '#dbeafe',   200: '#bfdbfe',   300: '#93c5fd',
  400: '#60a5fa',   500: '#3b82f6',   600: '#2563eb',   700: '#1d4ed8',
  800: '#1e40af',   900: '#1e3a8a',
}

// Semantic colors
success:  { 50-900: green palette }     // Energy savings, validation
warning:  { 50-900: amber palette }     // Caution, pending states
danger:   { 50-900: red palette }       // Errors, alerts, destructive
electricity: {
  cheap: '#22c55e',       // Green: low prices
  moderate: '#f59e0b',    // Amber: medium prices
  expensive: '#ef4444',   // Red: high prices
}
```

### CSS Custom Properties (`globals.css`)

```css
/* Surface colors */
--color-background: 249 250 251;        /* Light gray (bg-gray-50) */
--color-foreground: 17 24 39;           /* Dark gray (text-gray-900) */
--color-surface: 255 255 255;           /* White (cards, inputs) */
--color-surface-secondary: 249 250 251; /* Light gray (secondary surfaces) */

/* Brand */
--color-primary: 59 130 246;            /* Blue primary */
--color-primary-foreground: 255 255 255; /* White text on primary */

/* Energy theme accent */
--color-energy-green: 34 197 94;        /* Green (savings) */
--color-energy-amber: 245 158 11;       /* Amber (moderate) */
--color-energy-red: 239 68 68;          /* Red (expensive) */

/* Semantic */
--color-success: 16 185 129;            /* Teal success */
--color-warning: 245 158 11;            /* Amber warning */
--color-danger: 239 68 68;              /* Red danger */

/* Form inputs */
--color-input-bg: 255 255 255;          /* White background */
--color-input-text: 17 24 39;           /* Gray-900 text */
--color-input-border: 209 213 219;      /* Gray-300 border */
--color-input-placeholder: 156 163 175; /* Gray-400 placeholder */
--color-input-focus-ring: 59 130 246;   /* Blue focus ring */

/* Borders */
--color-border: 229 231 235;            /* Gray-200 */
--color-border-hover: 209 213 219;      /* Gray-300 on hover */

/* Shadows */
--shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
--shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
--shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
--shadow-card: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
```

### Typography

- **Font Family:** Inter (sans-serif), JetBrains Mono (monospace)
- **Base Size:** 16px (html), 14px body fallback
- **Headings:** font-bold (600-700 weight)
- **Body:** font-normal (400 weight)
- **Small Text:** text-sm (0.875rem)

### Box Shadows (Tailwind Extended)

```typescript
boxShadow: {
  'card': '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
  'card-hover': '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
  'input-focus': '0 0 0 3px rgb(59 130 246 / 0.15)',
}
```

### Animations (Tailwind Extended)

```typescript
animation: {
  'slide-down': 'slideDown 0.2s ease-out',       // Alert slide in from top
  'slide-up': 'slideUp 0.2s ease-out',           // Modal/tooltip slide in from bottom
  'fade-in': 'fadeIn 0.2s ease-out',             // General fade in
  'scale-in': 'scaleIn 0.15s ease-out',          // Card/modal scale in
  'shimmer': 'shimmer 1.5s ease-in-out infinite', // Skeleton loading
  'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
  'flash-green': 'flashGreen 0.5s ease-out',     // Success flash
  'flash-red': 'flashRed 0.5s ease-out',         // Error flash
}

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
```

### Global Styles

- **Color scheme:** `color-scheme: light` (forces light mode until dark mode implemented)
- **Scrollbar:** Custom webkit scrollbar with gray colors
- **Focus visible:** 2px primary-colored outline with 2px offset
- **Input colors:** All inputs force `bg-white` + `text-gray-900` in base layer (ensures visibility in dark mode prefers-color-scheme)
- **Skeleton loading:** Shimmer gradient animation on placeholder elements

---

## Component Reference

### UI Component Library

#### Input Component (`components/ui/input.tsx`)

**Enhanced form input with validation, success states, and flexible labeling.**

```typescript
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string              // Input label above field
  labelSuffix?: React.ReactNode // "(optional)" or other suffix text
  labelRight?: React.ReactNode  // Right-aligned content (e.g., "Forgot password?" link)
  error?: string              // Error message (displays with icon + danger-600 color)
  helperText?: string         // Helper text below input (gray-500)
  success?: boolean           // True if value is valid
  successText?: string        // Success message (displays with icon + success-600 color)
}

// Usage: Email input with blur validation
<Input
  id="email"
  label="Email address"
  type="email"
  value={email}
  onChange={(e) => handleEmailChange(e.target.value)}
  onBlur={handleEmailBlur}
  error={emailError || undefined}
  placeholder="you@example.com"
  required
/>

// Usage: Password input with forgot link
<Input
  id="password"
  label="Password"
  labelRight={<Link href="/forgot-password">Forgot?</Link>}
  type="password"
  value={password}
  onChange={(e) => setPassword(e.target.value)}
/>

// Usage: Name field with optional suffix
<Input
  id="name"
  label="Name"
  labelSuffix="(optional)"
  type="text"
  value={name}
  onChange={(e) => setName(e.target.value)}
/>

// Usage: Confirm password with success feedback
<Input
  id="confirmPassword"
  label="Confirm password"
  type="password"
  value={confirmPassword}
  onChange={(e) => setConfirmPassword(e.target.value)}
  error={confirmPasswordHasError ? 'Passwords do not match' : undefined}
  success={confirmPasswordMatch}
  successText={confirmPasswordMatch ? 'Passwords match' : undefined}
/>
```

**Styling:**
- Border: `rounded-lg border bg-white px-4 py-2.5`
- Default state: `border-gray-300 focus:border-primary-500 focus:ring-primary-500`
- Error state: `border-danger-300 focus:border-danger-500 focus:ring-danger-500`
- Success state: `border-success-400 focus:border-success-500 focus:ring-success-500`
- Hover: `hover:border-gray-400` with `transition-all duration-200`
- Disabled: `disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-500`
- Focus ring: `focus:ring-2 focus:ring-offset-0`
- Aria: `aria-invalid` for errors, `aria-describedby` for helper/error/success text

#### Checkbox Component (`components/ui/input.tsx`)

**Checkbox with integrated label.**

```typescript
interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string
}

// Usage
<Checkbox
  id="terms"
  label="I agree to the Terms of Service"
  checked={acceptTerms}
  onChange={(e) => setAcceptTerms(e.target.checked)}
/>
```

**Styling:**
- Checkbox: `h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500`
- Label: `text-sm text-gray-700 cursor-pointer`

---

### Authentication Components

#### LoginForm (`components/auth/LoginForm.tsx`)

**Sign in form with email/password, conditional OAuth, and magic link support.**

**Features:**
- Email blur validation (`isValidEmail` regex check)
- OAuth buttons: Google + GitHub (conditionally rendered via `NEXT_PUBLIC_OAUTH_*_ENABLED` env vars)
- Magic link toggle: `Sign in with magic link` / `Use password instead`
- Password forgot link in labelRight
- Error handling: "Email not verified" error includes "Resend verification email" link to `/auth/verify-email?email=...`
- Error alert with animate-slideDown
- Success state: "Check your email" card with checkmark icon
- Loading spinner on submit button

**State:**
- `email`: Email input value
- `password`: Password input value
- `emailError`: Email validation error
- `showMagicLink`: Toggle between password/magic link mode
- `magicLinkSent`: Success state (shows email confirmation screen)
- `isLoading`: Loading state from useAuth hook
- `error`: Auth error from useAuth context

**Handlers:**
- `handleEmailChange()`: Update email + clear emailError
- `handleEmailBlur()`: Validate email format
- `handleSubmit()`: Validate + call signIn() or sendMagicLink()
- `handleGoogleSignIn()`: OAuth sign-in
- `handleGitHubSignIn()`: OAuth sign-in

**UI Structure:**
```
Card (bg-white, shadow-card, rounded-xl, p-8)
  ├─ Heading: "Sign in to your account"
  ├─ Error alert (if error || localError)
  ├─ OAuth buttons (conditional: NEXT_PUBLIC_OAUTH_*_ENABLED)
  ├─ Divider: "Or continue with" (conditional: only if OAuth enabled)
  ├─ Form (space-y-4)
  │  ├─ Input: Email (required, blur validation)
  │  ├─ Input: Password (labelRight: Forgot link)
  │  └─ Button: Submit (loading spinner)
  ├─ Toggle: "Sign in with magic link"
  └─ Sign up link
```

#### SignupForm (`components/auth/SignupForm.tsx`)

**Register form with password strength indicator, real-time validation, and email verification redirect.**

**Features:**
- Email blur validation
- Name field with "(optional)" suffix via labelSuffix
- Password strength indicator: 6-segment bar + label (Weak/Medium/Strong/Very Strong)
- Password requirements checklist: 5 items with checkmarks
  - At least 12 characters
  - One uppercase letter
  - One lowercase letter
  - One number
  - One special character
- Confirm password with success feedback (green checkmark + "Passwords match")
- Terms acceptance checkbox
- Submit button disabled until: password valid + passwords match + terms accepted
- OAuth buttons: Google + GitHub (conditionally rendered via `NEXT_PUBLIC_OAUTH_*_ENABLED` env vars)
- Signup redirects to `/auth/verify-email?email=...` (email verification required before sign-in)

**Password Strength Scoring:**
```typescript
// Score 0-6 (each category adds 1)
if (password.length >= 12) score += 1
if (password.length >= 16) score += 1
if (/[A-Z]/.test(password)) score += 1
if (/[a-z]/.test(password)) score += 1
if (/[0-9]/.test(password)) score += 1
if (/[^A-Za-z0-9]/.test(password)) score += 1

// Labels by score
score <= 2: "Weak" (danger-500)
score <= 4: "Medium" (warning-500)
score <= 5: "Strong" (success-500)
score > 5: "Very Strong" (success-600)
```

**Handlers:**
- `handleEmailChange()`: Update + clear error
- `handleEmailBlur()`: Validate email
- `handleSubmit()`: Validate all fields + call signUp()
- `handleGoogleSignIn()` / `handleGitHubSignIn()`: OAuth

**UI Structure:**
```
Card (bg-white, shadow-card, rounded-xl, p-8)
  ├─ Heading: "Create your account"
  ├─ Error alert (if error || localError)
  ├─ OAuth buttons (conditional: NEXT_PUBLIC_OAUTH_*_ENABLED)
  ├─ Divider: "Or create with email" (conditional: only if OAuth enabled)
  ├─ Form (space-y-4)
  │  ├─ Input: Name (labelSuffix: "(optional)")
  │  ├─ Input: Email (blur validation)
  │  ├─ Input: Password
  │  │  ├─ Strength bar (6 segments)
  │  │  └─ Requirements checklist (5 items)
  │  ├─ Input: Confirm password (success feedback)
  │  ├─ Checkbox: Terms acceptance
  │  └─ Button: Submit (disabled state logic)
  └─ Sign in link
```

#### ForgotPasswordForm (`app/(app)/auth/forgot-password/page.tsx`)

**Password reset request form.**

**Features:**
- Email blur validation
- Submit button shows "Sending..." while loading
- Success screen: Shows submitted email + "Back to sign in" link
- Error handling with danger alert
- Card + Button components for consistent styling

**Flow:**
1. User enters email + submits
2. `authClient.requestPasswordReset()` called
3. On success: Show "Check your email" confirmation screen
4. Error: Display error alert

#### ResetPasswordForm (`app/(app)/auth/reset-password/page.tsx`)

**Set new password after email reset link.**

**Features:**
- New password input (minLength: 12)
- Confirm password input
- Token extraction from query param (`?token=...`)
- Invalid token state: Shows error + link to request new reset
- Success state: Shows confirmation + "Sign in" link
- Minimum password length enforced: 12 characters

**States:**
- No token: "Invalid reset link" error screen
- Form: "Set new password" form
- Success: "Password reset successful" confirmation

#### VerifyEmailPage (`app/(app)/auth/verify-email/page.tsx`)

**Email verification after signup and resend verification email flow.**

**Two Modes:**
1. **With token** (`?token=...`): Auto-verifies email via Better Auth, shows result (verifying → verified/failed)
2. **Without token**: Shows "Check your email" prompt with resend option

**Features:**
- Automatic token verification on mount (single execution with `useRef` guard)
- Better Auth error handling: checks `result?.error` (returns `{data, error}` instead of throwing)
- Resend verification email: uses shared `Input` component (if no email param) + submit button
- Error handling: `result?.error` from Better Auth + try/catch for exceptions
- Success feedback: Success-token confirmation banner "Verification email sent!"
- Pre-filled email: `?email=...` query param auto-fills resend form
- States: `verifying`, `verified`, `verifyError`, `resending`, `resent`, `resendError`
- **Design tokens**: All colors use design token system (`primary-*`, `danger-*`, `success-*`) — no raw Tailwind colors

**Token Verification Flow:**
1. Page mounts with `?token=...` query param
2. Immediately calls `authClient.verifyEmail({ query: { token } })`
3. Returns `{ data, error }` — check `result?.error` for failures
4. On success: Redirect to `/auth/login` (user auto-signed in)
5. On error: Show error message + offer new verification link

**Resend Flow:**
1. User lands on `/auth/verify-email?email=user@example.com`
2. Email address pre-filled (from signup form)
3. Clicks "Resend verification email" button
4. Calls `authClient.sendVerificationEmail({ email: resendEmail })`
5. Returns `{ data, error }` — check `result?.error` for failures
6. On success: Show green banner "Verification email sent!"
7. On error: Show red banner with error message

**UI States:**
```
With token:
  ├─ Verifying: Spinner + "Verifying your email..."
  ├─ Verified: Green checkmark + "Email verified" + "Go to sign in" link
  └─ Failed: Red X + "Verification failed" + error message + "Request a new verification email" link

Without token (default):
  ├─ Check email: Email icon + message + resend button
  ├─ Email input: Only shown if no email param
  ├─ Error state: Red banner with error (both result?.error and exceptions)
  └─ Success state: Green banner "Verification email sent!"
```

**Logging:**
- `[VerifyEmail] verifyEmail error: ...` when `result?.error` returned
- `[VerifyEmail] verifyEmail exception: ...` when exception caught
- `[VerifyEmail] sendVerificationEmail error: ...` when `result?.error` returned
- `[VerifyEmail] sendVerificationEmail exception: ...` when exception caught

**Tests:** 19 tests covering token verification (success/error/exception), resend flow (success/error/exception), error displays, re-render guard

---

### Layout Components

#### Sidebar (`components/layout/Sidebar.tsx`)

**Main navigation for authenticated app pages.**

**Routes (7 items):**
- `/dashboard` → LayoutDashboard icon + "Dashboard"
- `/prices` → TrendingUp icon + "Prices"
- `/suppliers` → Building2 icon + "Suppliers"
- `/connections` → Link2 icon + "Connections"
- `/optimize` → Calendar icon + "Optimize"
- `/alerts` → Bell icon + "Alerts"
- `/settings` → Settings icon + "Settings"

**Features:**
- Hover highlight on current route
- Collapse/expand toggle on mobile
- User profile section (avatar + name + sign out button)
- `data-testid="sign-out-button"` for E2E tests

#### Header (`components/layout/Header.tsx`)

**Top navigation bar (logo, user menu, mobile toggle).**

---

### Dashboard Components

#### StatsCard (`components/dashboard/StatsCard.tsx`)

**Metric display card with change indicator.**

```
┌─────────────────────┐
│ Label: "Monthly Bill"│
│ Value: "$125.34"    │
│ Change: +5.2% ▲     │ (green or red)
└─────────────────────┘
```

#### RecommendationCard (`components/dashboard/RecommendationCard.tsx`)

**Optimization suggestion with action button.**

---

### Supplier Components

#### SupplierSelector (`components/suppliers/SupplierSelector.tsx`)

**Dropdown with search, styled with `bg-white text-gray-900`.**

**Usage:**
```typescript
<SupplierSelector
  value={selectedSupplier}
  onChange={setSelectedSupplier}
  utilities={['electricity', 'natural_gas']}
  region="CT"
/>
```

---

### Connection Components (9 files)

#### Overview (`components/connections/Overview.tsx`)

**Dashboard of user connections (bills, utilities, sync status).**

#### MethodPicker (`components/connections/MethodPicker.tsx`)

**Select connection type: Direct, Bill Upload, Email OAuth, or UtilityAPI.**

#### DirectLogin (`components/connections/DirectLogin.tsx`)

**UtilityAPI login form, styled with `bg-white text-gray-900`.**

#### EmailFlow (`components/connections/EmailFlow.tsx`)

**Gmail/Outlook OAuth flow with HMAC-SHA256 state validation.**

#### BillUpload (`components/connections/BillUpload.tsx`)

**Bill PDF/image upload with OCR parsing.**

#### UploadFlow (`components/connections/UploadFlow.tsx`)

**Multi-step upload wizard.**

#### Rates (`components/connections/Rates.tsx`)

**Imported rates table (sortable, filterable).**

#### Analytics (`components/connections/Analytics.tsx`)

**Rate comparison + savings calculator (kWh input styled with `bg-white text-gray-900`).**

---

### Alerts Components (2 files)

#### AlertsContent (`components/alerts/AlertsContent.tsx`)

**Main alerts page content with two tabs.**

**Tabs:**
- **My Alerts**: CRUD list of configured alert rules. Each card shows region, active/paused badge, price thresholds, and optimal-window flag. Toggle-active (ToggleLeft/ToggleRight icons) and delete (Trash2 icon) per card. "Add Alert" button shows inline AlertForm. Free-tier note: "Free plan: 1 alert. Upgrade for unlimited" visible when alerts.length >= 1.
- **History**: Paginated table of triggered alerts — Type badge (price_drop/price_spike/optimal_window), Region, Price, Threshold, Triggered timestamp. Previous/Next pagination with page count.

**State:**
- `activeTab`: 'alerts' | 'history'
- Uses `useAlerts`, `useAlertHistory(page)`, `useDeleteAlert`, `useUpdateAlert` hooks

**UI Structure:**
```
Header ("Alerts")
  └─ Tab nav: My Alerts | History
     ├─ My Alerts:
     │   ├─ Free-tier note + Add Alert button
     │   ├─ AlertForm (inline, shown when showForm=true)
     │   └─ Alert cards (region, status badge, thresholds, toggle, delete)
     └─ History:
         ├─ Table (Type | Region | Price | Threshold | Triggered)
         └─ Pagination (Previous / Next)
```

**Test IDs:** `free-tier-note`, `empty-alerts`, `alert-card`, `toggle-alert`, `delete-alert`, `empty-history`, `history-row`

#### AlertForm (`components/alerts/AlertForm.tsx`)

**Create new alert configuration form.**

**Fields:**
- Region: `<select>` with US_REGIONS grouped by state (optgroup)
- Price Below: `<Input>` type=number step=0.0001, labelSuffix="($/kWh)"
- Price Above: `<Input>` type=number step=0.0001, labelSuffix="($/kWh)"
- Notify optimal windows: `<Checkbox>` (default: checked)

**Validation:**
- Region required
- At least one condition must be set (price_below, price_above, or optimal windows)
- price_below/price_above must be positive numbers if provided

**Error Handling:**
- Validation errors: shown as `role="alert"` paragraph
- 403 (tier limit): Amber upgrade prompt with link to `/pricing` — "Free plan is limited to 1 alert. Upgrade to Pro for unlimited alerts."
- Other mutation errors: danger text

**Test IDs:** `alert-form`, `region-select`, `form-error`, `tier-limit-error`, `submit-alert`

---

### Agent Components (1 file)

#### AgentChat (`components/agent/AgentChat.tsx`)

**RateShift AI assistant chat interface with streaming query support.**

**Features:**
- SSE streaming responses from `POST /agent/query` endpoint
- Example prompts carousel (4 predefined queries for new users)
- Message bubbles: User (primary-600 text on bg), Assistant (gray-100 bg), Error (red-50 with border)
- Real-time model display: "via Gemini 3 Flash" / "via Groq Llama 3.3 70B" with duration (1.2s)
- Tools display: Composio tools used as blue badge pills in message
- Controls: Send button, Cancel button (during streaming), Reset conversation button
- Input field: Large text area with send on Ctrl+Enter or button click
- Rate limiting: Display quota (Free: 3/day, Pro: 20/day, Business: unlimited)
- Error recovery: Fallback to Groq on Gemini 429 (automatic retry)
- Mobile responsive: Full viewport height with scrollable message area

**State:**
- `messages`: Array of AgentMessage objects (role: 'user' | 'assistant' | 'error' | 'tool')
- `isStreaming`: Boolean indicating active SSE connection
- `error`: Error message if query fails
- `input`: Current text input value

**Hooks:**
- `useAgentQuery()`: Streaming query management (sendQuery, cancel, reset)
- `useAgentStatus()`: Usage limit tracking

**UI Structure:**
```
Container (flex flex-col h-full)
  ├─ Header: "AI Assistant" title + description
  ├─ Messages area (scrollable, flex-1)
  │  ├─ Example prompts (initial state)
  │  └─ Message bubbles (user/assistant/error)
  │     ├─ Avatar (Bot icon for assistant)
  │     ├─ Bubble with content
  │     └─ Model + Duration + Tools badges
  ├─ Input area
  │  ├─ Textarea with placeholder
  │  ├─ Controls: Send, Cancel, Reset
  │  └─ Usage indicator
  └─ Error alert (if error state)
```

**Tests:** 13 tests covering streaming query, message display, example prompts, error handling, token usage, model fallback

---

### Feedback Components (1 file)

#### FeedbackWidget (`components/feedback/FeedbackWidget.tsx`)

**In-app feedback collection widget for user surveys and bug reports.**

**Features:**
- Floating button (bottom-right, Slack/Zendesk style)
- Modal form: feedback type selector (bug/feature_request/general), rating (1-5 stars), text comment
- Validation: Type required, comment min 10 chars
- Success state: "Thank you for your feedback"
- Integration: Submits to `POST /api/v1/feedback` endpoint
- Analytics: Track feedback submission counts by type

**State:**
- `isOpen`: Modal visibility
- `feedback_type`: Selected type
- `rating`: Star rating (1-5)
- `comment`: Textarea value
- `isSubmitting`: Loading state

**UI Structure:**
```
Floating button (bottom-right, primary-600)
  └─ Modal (overlay)
     ├─ Title: "Send us feedback"
     ├─ Type select (bug/feature_request/general)
     ├─ Star rating (1-5)
     ├─ Comment textarea (min 10 chars)
     ├─ Submit button
     └─ Success confirmation
```

---

### Layout Components

#### NotificationBell (`components/layout/NotificationBell.tsx`)

**In-app notification bell for alerts and system messages (sidebar header).**

**Features:**
- Bell icon with unread count badge (red pill, 0+ count)
- Dropdown panel on click (right-aligned, max-width 400px)
- Polling: Unread count refetches every 30s (via `useNotificationCount()`)
- Notifications list: Only fetch when dropdown open (enabled: open)
- Each notification: Title + body + timestamp + mark-as-read button
- "Mark all as read" action (batch operation)
- Empty state: "No notifications"
- Types: price_alert, optimal_window, payment, system
- Color coding by type (primary/success/danger badges)

**State:**
- `open`: Dropdown visibility
- `notifications`: List of Notification objects
- `unreadCount`: Badge count

**Hooks:**
- `useNotificationCount()`: Polling unread count
- `useNotifications()`: Full notification list (staleTime: 30s)
- `useMarkRead()`: Mark single notification as read
- `useMarkAllRead()`: Batch mark all as read

**UI Structure:**
```
Bell icon + badge (unread count)
  └─ Dropdown panel (when open=true)
     ├─ Header: "Notifications"
     ├─ Mark all read button
     ├─ Notification items
     │  ├─ Type badge
     │  ├─ Title
     │  ├─ Body (gray-500)
     │  ├─ Timestamp (gray-400, relative)
     │  └─ Mark read button
     └─ Empty state or scroll area
```

**Tests:** 15 tests covering polling, dropdown interactions, mark read, batch operations, empty state

---

### Settings Page Components

**All select dropdowns styled with `bg-white text-gray-900`:**
- RegionSelector (4 selects: state, utility type, price period, etc.)
- NotificationPrefs (3 notification email toggles with selects)

---

## Authentication Flow

### Better Auth Integration

**Frontend Auth Stack:**
- **Client Library:** `better-auth` package (React hooks + client) with `magicLinkClient` plugin
- **Server:** `frontend/lib/auth/server.ts` (Better Auth server with emailVerification, magicLink plugin, password reset)
- **Email:** `frontend/lib/email/send.ts` (Resend primary + nodemailer SMTP fallback for verification, magic link, password reset emails)
- **Backend:** `backend/auth/neon_auth.py` (FastAPI session validation dependency)
- **API Route:** `app/api/auth/[...all]/route.ts` (NextAuth-style catch-all)
- **Session Management:** HTTP-only cookies (`better-auth.session_token` + `__Secure-` variant on HTTPS)

**Sign In Flow:**
1. User enters email + password in LoginForm
2. `useAuth.signIn()` calls `authClient.signIn()` (POST `/api/auth/sign-in`)
3. Better Auth validates credentials
4. Session cookie set automatically
5. Frontend auth state updated
6. Redirect to `/dashboard` (via `onSuccess` callback)

**Sign Up Flow:**
1. User fills SignupForm (name, email, password, confirm, terms)
2. Password strength validated client-side
3. `useAuth.signUp()` calls `authClient.signUp()` (POST `/api/auth/sign-up`)
4. Better Auth creates user (no session — email verification required)
5. Verification email sent automatically via Resend (`sendOnSignUp: true`)
6. Redirect to `/auth/verify-email?email=...`
7. User clicks verification link in email → auto-sign-in → redirect to dashboard

**OAuth Flow:**
1. User clicks "Continue with Google/GitHub"
2. `useAuth.signInWithGoogle()` / `signInWithGitHub()` called
3. Browser redirects to OAuth provider
4. User approves + browser redirects to callback URL
5. Better Auth exchanges code for token
6. Session created + cookie set
7. Redirect to dashboard

**Magic Link Flow:**
1. User enters email + clicks "Sign in with magic link"
2. `useAuth.sendMagicLink()` calls `authClient.signIn.magicLink({ email, callbackURL: '/dashboard' })`
3. Better Auth magic link plugin sends email via Resend (5-minute expiry)
4. User clicks link in email
5. Link redirects to `/auth/callback?token=...&email=...`
6. Callback page exchanges token for session
7. Redirect to dashboard
8. On error: throws (prevents misleading "Check your email" success screen)

**Password Reset Flow:**
1. User enters email in forgot-password form
2. `authClient.requestPasswordReset()` (POST `/api/auth/request-password-reset`)
3. Email sent with reset link
4. User clicks link: `/auth/reset-password?token=...`
5. User enters new password + confirms
6. `authClient.resetPassword()` called (POST `/api/auth/reset-password`)
7. Password updated in database
8. User redirected to login

**401 Redirect Guard (3-layer defense):**

Context: Stale session cookies → 401 on auth pages → nested callbackUrl → HTTP 414 (URI_TOO_LONG)

1. **Auth page guard in `useAuth.tsx`:**
   - Detect `/auth/*` pages
   - Skip expensive queries (`getUserSupplier()`, `getUserProfile()`)
   - Reduces redirect spam

2. **CallbackUrl extraction in `client.ts`:**
   - Extract callbackUrl from response (fallback: `localStorage`)
   - Validate with `isSafeRedirect()` (same-origin only)
   - Prevents open redirect + nested URL explosion

3. **SessionStorage safety valve:**
   - Track redirect nesting level in sessionStorage
   - Max 3 redirects before giving up
   - Prevents infinite loops

**Implementation in `frontend/lib/api/client.ts`:**
```typescript
// On 401 response:
if (response.status === 401) {
  const callbackUrl = extractCallbackUrl(data)
  if (callbackUrl && isSafeRedirect(callbackUrl)) {
    window.location.href = callbackUrl
  }
}
```

---

## State Management

### Auth Hook (`lib/hooks/useAuth.ts`)

```typescript
const {
  user,                    // Current user object (null if not signed in)
  isLoading,              // Loading state during auth operations
  error,                  // Error message from auth
  signIn,                 // async (email, password) => Promise<void>
  signUp,                 // async (email, password, name?) => Promise<void>
  signOut,                // async () => Promise<void>
  signInWithGoogle,       // async () => Promise<void>
  signInWithGitHub,       // async () => Promise<void>
  sendMagicLink,          // async (email) => Promise<void>
  clearError,             // () => void
} = useAuth()
```

**Features:**
- Persists auth state to localStorage (Zustand store)
- Syncs with Better Auth session
- Handles 401 errors with 3-layer redirect guard
- Wires OneSignal push: `loginOneSignal(userId)` on session init + signIn, `logoutOneSignal()` on signOut

### Alerts Hooks (`lib/hooks/useAlerts.ts`)

**TanStack Query hooks for alert CRUD and history. All queries use staleTime: 30s.**

```typescript
// Fetch all alert configurations for current user
useAlerts()           // queryKey: ['alerts']

// Fetch paginated alert trigger history
useAlertHistory(page, pageSize)  // queryKey: ['alerts', 'history', page]

// Create a new alert configuration
useCreateAlert()      // mutationFn: createAlert(body), invalidates ['alerts']

// Update an alert (toggle is_active, change thresholds, etc.)
useUpdateAlert()      // mutationFn: updateAlert({ id, body }), invalidates ['alerts']

// Delete an alert configuration
useDeleteAlert()      // mutationFn: deleteAlert(id), invalidates ['alerts']
```

### Connections Hook (`lib/hooks/useConnections.ts`)

**Migrated from manual useEffect+fetch to TanStack Query.**

```typescript
const { data, isLoading, error } = useConnections()
// queryKey: ['connections'], staleTime: 30s, retry: false
// 403 preserved: throws error with { status: 403 } for tier-gate display
```

### Agent Hooks (`lib/hooks/useAgent.ts`)

**Hooks for RateShift AI agent queries and usage tracking.**

```typescript
// Hook for streaming agent queries
const { messages, isStreaming, error, sendQuery, cancel, reset } = useAgentQuery()
// messages: AgentMessage[] (role: 'user' | 'assistant' | 'error' | 'tool')
// sendQuery(prompt: string) → async generator streaming SSE events
// cancel() → abort active request
// reset() → clear messages and error state

// Hook for agent usage limits
const { data: usage, isLoading } = useAgentStatus()
// Returns: { used: number, limit: number, remaining: number, tier: string }
// Tier-based limits: Free=3/day, Pro=20/day, Business=unlimited
```

**Features:**
- SSE streaming with async generator pattern
- Error fallback: Automatic retry to Groq on Gemini 429 (transparent to UI)
- Model metadata: Displays "via Gemini 3 Flash" or "via Groq Llama 3.3 70B"
- Tool tracking: Composio tools used listed as badges
- Token usage: tracked and displayed with response
- Message types: 'user' (blue), 'assistant' (gray), 'error' (red), 'tool' (info)

### Notifications Hooks (`lib/hooks/useNotifications.ts`)

**TanStack Query hooks for notification CRUD and polling. All use staleTime: 30s.**

```typescript
// Poll unread count every 30 seconds (for badge)
const { data: countData } = useNotificationCount()
// Returns: { unread: number }
// refetchInterval: 30_000 (badge stays current)

// Fetch full notification list (only when panel open)
const { data: notifData } = useNotifications()
// Returns: { notifications: Notification[], total: number }
// enabled: open (only fetch when dropdown open)

// Mark single notification as read
const markRead = useMarkRead()
// mutationFn: markNotificationRead(id), invalidates ['notifications', 'count']

// Mark all notifications as read (batch)
const markAllRead = useMarkAllRead()
// mutationFn: markAllRead(), invalidates ['notifications', 'count']
```

**Performance Optimization:**
- Count polling: Every 30s for badge (cheap)
- Full list: Only fetch when panel open (expensive, stale after 30s)
- Batch invalidation: Both queries refetch on mutation success
- Example notification types: price_alert, optimal_window, payment_failed, system

### React Query Integration

**Used for server state (API calls):**
- Prices fetch with caching
- User profile data
- Recommendations list
- Connection status
- Alert configurations and history

**Query hooks pattern:**
```typescript
const { data, isLoading, error } = useQuery({
  queryKey: ['prices', region],
  queryFn: () => api.getPrices(region),
  staleTime: 5 * 60 * 1000, // 5 minutes
})
```

---

## API Integration

### Frontend API Client (`lib/api/client.ts`)

**Fetch wrapper with:**
- Authorization header (Bearer token from auth)
- Error handling + logging
- 401 response handling (3-layer guard)
- Request/response transformation
- Timeout management

**Base URL:** `process.env.NEXT_PUBLIC_API_URL` (from `lib/config/env.ts`, default: `/api/v1` — relative, proxied through Next.js)

**Same-Origin Proxy (2026-03-04):**
- Production: Client requests go to `/api/v1/*` (same-origin, proxied by Next.js)
- `next.config.js` rewrites `/api/v1/:path*` to `${BACKEND_URL}/api/v1/:path*` (server-side)
- `BACKEND_URL` (server env var) = `https://api.rateshift.app` in production
- Eliminates cross-origin cookie issues; sessions work transparently

**Error Handling:**
- Network errors → "Connection failed"
- 4xx errors → Extract message from response.data.detail
- 5xx errors → "Server error, try again"
- 401 → Trigger redirect guard
- Unknown → "Something went wrong"

### Alerts API Client (`lib/api/alerts.ts`)

**CRUD functions for price alert configurations and trigger history.**

**Types exported:**
```typescript
interface Alert {
  id: string; user_id: string; region: string; currency: string;
  price_below: number | null; price_above: number | null;
  notify_optimal_windows: boolean; is_active: boolean;
  created_at: string | null; updated_at: string | null;
}

interface AlertHistoryItem {
  id: string; user_id: string; alert_config_id: string | null;
  alert_type: string; current_price: number; threshold: number | null;
  region: string; supplier: string | null; currency: string;
  optimal_window_start: string | null; optimal_window_end: string | null;
  estimated_savings: number | null; triggered_at: string | null;
  email_sent: boolean;
}
```

**Functions:**
```typescript
getAlerts()                              // GET /alerts
createAlert(body: CreateAlertRequest)    // POST /alerts
updateAlert(id, body: UpdateAlertRequest) // PUT /alerts/{id}
deleteAlert(id)                          // DELETE /alerts/{id}
getAlertHistory(page, pageSize)          // GET /alerts/history?page=&page_size=
```

### Agent API Client (`lib/api/agent.ts`)

**Functions for RateShift AI agent queries, async tasks, and usage tracking.**

**Types exported:**
```typescript
interface AgentMessage {
  role: 'user' | 'assistant' | 'error' | 'tool'
  content: string
  model_used?: string           // 'Gemini 3 Flash' or 'Groq Llama 3.3 70B'
  tools_used?: string[]         // Composio tool names used
  tokens_used?: number          // Prompt + completion tokens
  duration_ms?: number          // Response time in milliseconds
}

interface AgentUsage {
  used: number                  // Queries used today
  limit: number                 // Daily limit for tier
  remaining: number             // limit - used
  tier: string                  // 'free' | 'pro' | 'business'
}

interface AgentTaskResponse {
  job_id: string               // UUID for async task
}

interface AgentJobResult {
  status: 'processing' | 'completed' | 'failed' | 'not_found'
  result?: string              // Async task result
  model_used?: string
  error?: string               // Error message if failed
}
```

**Functions:**
```typescript
// Stream agent query with SSE
async function* queryAgent(prompt: string, context?: Record<string, unknown>)
// Returns async generator yielding AgentMessage objects
// POST /agent/query with { prompt, context }
// SSE streaming: each event is JSON AgentMessage

// Submit async task (long-running queries)
submitTask(prompt: string)     // POST /agent/task → returns { job_id }

// Check async task status
checkTask(jobId: string)       // GET /agent/task/{jobId} → returns AgentJobResult

// Get usage limits and usage count
getAgentUsage()                // GET /agent/usage → returns AgentUsage
```

**Features:**
- **SSE streaming:** Real-time message display as model generates
- **Model fallback:** On Gemini 429 error, automatically retry with Groq (transparent to caller)
- **Composio integration:** Tools available (1K actions/month free tier)
- **Rate limiting:** Enforced at backend per tier (Free: 3/day, Pro: 20/day, Business: unlimited)
- **Timeout handling:** Frontend timeout 15s, internal timeout excluded from RequestTimeoutMiddleware

### Notifications API Client (`lib/api/notifications.ts`)

**Functions for in-app notification CRUD and batch operations.**

**Types exported:**
```typescript
interface Notification {
  id: string
  type: string                 // 'price_alert' | 'optimal_window' | 'payment' | 'system'
  title: string
  body: string | null
  created_at: string           // ISO timestamp
  is_read?: boolean
}

interface GetNotificationsResponse {
  notifications: Notification[]
  total: number
}

interface GetNotificationCountResponse {
  unread: number
}

interface MarkReadResponse {
  success: boolean
}
```

**Functions:**
```typescript
getNotifications()                    // GET /notifications → returns GetNotificationsResponse
getNotificationCount()                // GET /notifications/count → returns GetNotificationCountResponse
markNotificationRead(id: string)      // PUT /notifications/{id}/read → returns MarkReadResponse
markAllRead()                         // POST /notifications/read-all → marks all as read (batch)
```

**Features:**
- **Polling support:** Count endpoint optimized for 30s polling
- **Batch operations:** Mark all as read in single API call
- **Type-based filtering:** Supports filtering by notification type (future feature)
- **Timestamp format:** ISO string, frontend formats relative (e.g., "2m ago")

---

## Testing

### Unit Tests

- **Framework:** Jest + React Testing Library
- **Coverage:** 1,439 tests across 98 suites (3 pre-existing failures in send.test.ts)
- **Mock:** `frontend/__mocks__/better-auth-react.js` (ESM → CJS bridge)
- **Auth mocking:** `frontend/e2e/helpers/auth.ts` (mockBetterAuth, setAuthenticatedState, clearAuthState)

**Key test files:**
- `__tests__/components/auth/LoginForm.test.tsx` (magic link failure, conditional OAuth)
- `__tests__/components/auth/SignupForm.test.tsx` (conditional OAuth)
- `__tests__/hooks/useAuth.test.tsx` (email verification redirect, real magic link, clearError)
- `__tests__/lib/email/send.test.ts` (Resend SDK: send, error handling, missing API key — 3 pre-existing failures)
- `lib/api/__tests__/client-401-redirect.test.ts` (9 tests for 401 edge cases)
- `__tests__/a11y/` (51 jest-axe tests)
- `__tests__/components/alerts/` (+27 new tests for AlertsContent, AlertForm)

### E2E Tests (Playwright)

- **Coverage:** 634 tests passed, 5 skipped
- **Config:** `playwright.config.ts` (retries: 1, baseURL: localhost:3000)
- **Auth helpers:** `e2e/helpers/auth.ts`
- **Data attributes for selectors:**
  - `data-testid="sign-out-button"` on Sidebar
  - `data-testid="appliance-card-settings"` on optimize page
  - `data-testid="alert-form"`, `data-testid="alert-card"` on alerts page

**Skipped tests (legitimate):**
- Email validation smoke tests
- Magic link flow (requires real email)
- GDPR data export suite
- 2 mobile viewport conditionals

---

## Performance Optimizations

### Page Optimizations

**SSE Configuration:**
- `openWhenHidden: false` (don't waste bandwidth on background tabs)

**Auth Waterfall Fix:**
- Use `Promise.allSettled()` instead of sequential promises
- Parallel auth checks: user + supplier + profile

**Page Load Strategy:**
- Root pages: Static generation where possible
- App pages: Server-side auth check + data fetch
- Auth pages: Force dynamic (don't cache 401 responses)

**Component Loading:**
- Skeleton loaders on async components
- Lazy load heavy components (e.g., Excalidraw on `/architecture`)

### React Query Optimizations (2026-03-09)

- **Hoisted inline props:** Frequently-rendered components no longer create new object/function references on every render
- **Memoized callbacks:** `useCallback` applied to handlers in high-frequency render paths
- **Memoized context values:** `useMemo` applied to context value objects to prevent unnecessary re-renders
- **ConnectionsOverview migrated to useQuery:** Removed manual `useEffect + fetch + useState` pattern; now uses `useConnections()` hook with TanStack Query caching (staleTime: 30s, retry: false)

### Code Splitting

- Next.js automatic code splitting per route
- Dynamic imports for dev-only pages (Excalidraw)
- React.lazy() for modal/dialog content

---

## Type Safety

### TypeScript Coverage

- **Page Components:** 100% type-safe (zero `any` types)
- **Content Components:** 100% type-safe (zero `any` types)
- **UI Components:** Fully typed props and event handlers
- **Hooks:** Explicit return types on all custom hooks
- **API Client:** Typed request/response handlers

### Exception (Necessary)

- **ExcalidrawWrapper.tsx:** Uses `any` type for third-party library cast (dev tool only, justified by external API constraints)

---

## Accessibility

### WCAG AA Compliance

- **51 jest-axe tests** in `__tests__/a11y/`
- All form inputs have associated labels
- Error messages linked via `aria-describedby`
- Invalid inputs marked with `aria-invalid="true"`
- Alert boxes use `role="alert"` + `aria-live="polite"`
- Keyboard navigation on dropdowns + modals
- Color contrast checked (primary-600 on white, etc.)

### Semantic HTML

- `<form>` for forms (prevents nested forms)
- `<label htmlFor>` for all inputs
- `<button type="submit">` for form submissions
- `<main>` for main content
- `<nav>` for navigation

### Focus Management

- Focus visible outline: 2px primary-colored
- Focus order matches visual order
- Modal/dialog traps focus

---

## Known Issues & Workarounds

### Color Scheme Light Forcing

**Issue:** Browser dark mode + hardcoded Tailwind colors create contrast issues (white text on white in inputs).

**Workaround:** Set `color-scheme: light` in `globals.css` to force light mode until dark mode is fully implemented.

**Future:** Switch to `darkMode: 'class'` in `tailwind.config.ts` and use `dark:` prefixes on all color-bearing classes.

### Input Color Forcing

**Issue:** System Python + form autofill override input colors.

**Workaround:** Force all select inputs to `bg-white text-gray-900` in code:
- Settings page (4 selects)
- Beta signup page (3 selects)
- SupplierSelector (search input)
- ConnectionCard (label input)
- ConnectionAnalytics (kWh input)

**Pattern:**
```tsx
<select className="bg-white text-gray-900 border-gray-300 ...">
```

### URI_TOO_LONG Redirect Loop (FIXED)

**Issue:** Stale session cookies → 401 on auth pages → nested callbackUrl → HTTP 414

**Fix (3-layer defense):**
1. Detect `/auth/*` pages in `useAuth.tsx` → skip expensive queries
2. Validate callbackUrl with `isSafeRedirect()` in `client.ts`
3. Track nesting in sessionStorage (max 3 redirects)

**Files changed:**
- `frontend/lib/api/client.ts` (add guard)
- `frontend/lib/hooks/useAuth.tsx` (+2 tests)
- `frontend/lib/api/__tests__/client-401-redirect.test.ts` (9 new tests)
- `frontend/app/(app)/auth/callback/page.tsx` (a11y)
- `frontend/playwright.config.ts` (retries: 1)

### send.test.ts Pre-Existing Failures

**Issue:** 3 tests in `__tests__/lib/email/send.test.ts` fail consistently. These are pre-existing failures related to Resend SDK mocking and do not reflect production email behavior.

**Status:** Known + tracked. Not blocking CI. Production email verified working via Gmail SMTP fallback.

---

## Development Workflow

### Running Frontend Locally

```bash
# Install dependencies
npm install

# Start dev server
npm run dev
# Runs on http://localhost:3000

# Run unit tests
npm run test

# Run E2E tests
npm run test:e2e

# Run specific test suite
npm run test -- LoginForm

# Build for production
npm run build

# Start production server
npm start

# Linting
npm run lint

# Type checking
npm run type-check
```

### Environment Variables

**Required `frontend/.env.local` (Development):**
```
NEXT_PUBLIC_API_URL=/api/v1              # Default: relative path (proxied through Next.js)
NEXT_PUBLIC_ENVIRONMENT=development
BACKEND_URL=http://localhost:8000        # Server-side: backend for rewrites + server calls
RESEND_API_KEY=re_xxxxxxxxxxxx           # For email verification, magic link, password reset
# NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED=true  # Show Google OAuth button
# NEXT_PUBLIC_OAUTH_GITHUB_ENABLED=true  # Show GitHub OAuth button
```

**Production (Vercel):**
```
NEXT_PUBLIC_API_URL=/api/v1              # Relative, proxied by Next.js
BACKEND_URL=https://api.rateshift.app  # For server-side rewrites
RESEND_API_KEY=re_xxxxxxxxxxxx           # (Server-only, loaded at runtime)
BETTER_AUTH_SECRET=...                   # (Server-only)
BETTER_AUTH_URL=...                      # (Server-only)
```

**Centralized in `lib/config/env.ts`:**
- Validates NEXT_PUBLIC_* variables
- Type-safe access
- Fallbacks for development

### Hot Reload

- Next.js dev server watches files + hot reloads
- Auth state persists in localStorage during reload
- Query cache persists during reload (React Query)

---

## Component Checklist

### Core Components (Count: 19)

- [x] Input (enhanced with labelSuffix, labelRight, success, successText)
- [x] Checkbox (integrated in input.tsx)
- [x] Button (primary/secondary/outline + loading state)
- [x] Card (CardHeader, CardTitle, CardContent, CardDescription)
- [x] Badge (status indicators)
- [x] Modal (controlled dialog)
- [x] Toast (notifications)
- [x] Dropdown (menu)
- [x] Tabs (tab navigation)
- [x] Tooltip (hover text)
- [x] Avatar (user profile images)
- [x] Skeleton (loading placeholder)
- [x] Spinner (loading indicator)
- [x] LoginForm
- [x] SignupForm
- [x] Sidebar
- [x] Header
- [x] DevBanner
- [x] StatsCard

### Feature Components (Count: 22+)

- [x] Connection components (9)
- [x] Supplier components (3)
- [x] Settings components (4)
- [x] Dashboard components (3)
- [x] Prices components (4)
- [x] Optimize components (3)
- [x] Alerts components (AlertsContent, AlertForm)

---

## File Statistics

- **Total Pages:** 20 (root + (app) including /alerts + (dev) + auth routes)
- **Total Layouts:** 3 (root, app, dev, auth)
- **Total Components:** 52+ (UI + feature-specific)
- **Loading Skeletons:** 5 (dashboard, prices, suppliers, optimize, connections)
- **Total Tests:** 1,439 across 98 suites (3 pre-existing failures in send.test.ts)
- **Accessibility Tests:** 51 (jest-axe)
- **E2E Tests:** 634 passed, 5 skipped
- **Total Test Coverage:** ~4,170 tests (frontend + backend + ML + E2E)

---

## Recent Updates (2026-03-09)

### Alerts UI (2026-03-09)

1. **New Page: `/alerts`** (`app/(app)/alerts/page.tsx`)
   - Wrapper page with metadata: `title: 'Alerts | RateShift'`
   - Renders `<AlertsContent />` — no layout logic in page itself

2. **AlertsContent** (`components/alerts/AlertsContent.tsx`)
   - Tab navigation: "My Alerts" | "History"
   - My Alerts tab: alert card list with toggle-active (ToggleRight/ToggleLeft) + delete (Trash2), inline AlertForm, empty state with Bell icon, free-tier note when >= 1 alert
   - History tab: paginated table — Type badge, Region, Price, Threshold, Triggered At — with Previous/Next pagination
   - Skeleton loading states for both tabs

3. **AlertForm** (`components/alerts/AlertForm.tsx`)
   - Region `<select>` with US_REGIONS grouped by optgroup
   - Price Below / Price Above: `<Input>` with labelSuffix="($/kWh)"
   - Notify optimal windows: `<Checkbox>` (default checked)
   - 403 tier-limit error: amber upgrade prompt linking to `/pricing`
   - Uses `useCreateAlert()` mutation with cache invalidation

4. **Alerts API Client** (`lib/api/alerts.ts`)
   - Exports: `getAlerts`, `createAlert`, `updateAlert`, `deleteAlert`, `getAlertHistory`
   - Types: `Alert`, `AlertHistoryItem`, `GetAlertsResponse`, `GetAlertHistoryResponse`, `CreateAlertRequest`, `UpdateAlertRequest`

5. **useAlerts hooks** (`lib/hooks/useAlerts.ts`)
   - `useAlerts()` — staleTime: 30s
   - `useAlertHistory(page, pageSize)` — staleTime: 30s
   - `useCreateAlert()` — invalidates ['alerts'] on success
   - `useUpdateAlert()` — invalidates ['alerts'] on success
   - `useDeleteAlert()` — invalidates ['alerts'] on success

6. **Sidebar Bell icon**
   - Alerts added as 6th nav item (Bell icon from lucide-react)
   - Navigation array now has 7 items: Dashboard, Prices, Suppliers, Connections, Optimize, Alerts, Settings

### Tier Gating Upgrade CTAs (2026-03-09)

- `DashboardForecast.tsx`: Detects 403 response → shows "Unlock forecasts with Pro" upgrade card instead of error
- `AlertForm.tsx`: 403 on createAlert → amber banner "Free plan is limited to 1 alert. Upgrade to Pro for unlimited alerts."
- `AlertsContent.tsx`: Shows "Free plan: 1 alert. Upgrade for unlimited" note when user already has 1 alert configured

### Favicon Files (2026-03-09)

1. **`app/icon.tsx`** — 32x32 PNG favicon via `next/og` ImageResponse
   - Blue (#2563eb) rounded square background
   - White lightning bolt SVG (path: M13 2L3 14h9l-1 10 10-12h-9l1-10z)

2. **`app/apple-icon.tsx`** — 180x180 Apple touch icon
   - Gradient blue (#2563eb → #1d4ed8), 36px border radius
   - White lightning bolt SVG at 120x120

3. **`app/api/pwa-icon/route.tsx`** — Dynamic PWA icon endpoint
   - Accepts `?size=192` or `?size=512` (validated set — 400 on other values)
   - Returns ImageResponse with proportional lightning bolt
   - Used by `manifest.ts` for PWA icon entries

### useConnections Hook Migration (2026-03-09)

- **Before:** ConnectionsOverview used `useEffect + fetch + useState` pattern
- **After:** Uses `useConnections()` hook from `lib/hooks/useConnections.ts`
- **Benefits:** TanStack Query caching (staleTime: 30s), automatic deduplication, no manual cleanup
- **403 preserved:** `fetchConnections()` throws `{ status: 403 }` error object for tier-gate display in parent

### Performance Optimizations (2026-03-09)

- Hoisted inline object/function props from frequently-rendered components
- Applied `useCallback` to event handlers in render-heavy paths
- Applied `useMemo` to context value objects
- ConnectionsOverview manual data-fetching replaced with `useConnections()` hook

### Auth System Fix (2026-03-04)

1. **Email Verification via Resend + SMTP Fallback**
   - Created `lib/email/send.ts`: Dual-provider — Resend SDK (primary, lazy singleton) + nodemailer SMTP fallback (`sendViaSMTP()` using SMTP_HOST/PORT/USERNAME/PASSWORD). `getResend()` returns null (not throw) when RESEND_API_KEY missing
   - Added `emailVerification` config to `lib/auth/server.ts`: `sendOnSignUp: true`, `autoSignInAfterVerification: true`
   - Branded HTML email template for verification emails

2. **Magic Link Plugin (Real Implementation)**
   - Server: `better-auth/plugins/magic-link` in `lib/auth/server.ts` (5-minute expiry)
   - Client: `magicLinkClient()` in `lib/auth/client.ts`
   - Hook: `useAuth.sendMagicLink()` now calls `authClient.signIn.magicLink()` (was stub)
   - Error handling: throws on failure (prevents misleading success screen in LoginForm)

3. **Password Reset Emails**
   - Added `sendResetPassword` callback in `lib/auth/server.ts`
   - Uses same Resend email utility with branded HTML template

4. **Signup Flow Fix**
   - `useAuth.signUp()` redirects to `/auth/verify-email?email=...` (was `/onboarding`)
   - Removed premature `setUser()` call (no session exists until email verified)

5. **Conditional OAuth Buttons**
   - LoginForm + SignupForm: OAuth buttons only rendered when `NEXT_PUBLIC_OAUTH_*_ENABLED=true`
   - Divider ("Or continue with") also hidden when no OAuth providers enabled

6. **New Environment Variables**
   - `RESEND_API_KEY`: Resend email service API key
   - `EMAIL_FROM_ADDRESS`: Configurable FROM address (default: `onboarding@resend.dev`)
   - `NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED`: Show Google OAuth button
   - `NEXT_PUBLIC_OAUTH_GITHUB_ENABLED`: Show GitHub OAuth button

7. **Tests Updated**
   - 133 auth+email tests passing across 12 suites
   - New: `__tests__/lib/email/send.test.ts` (3 tests)
   - Updated: `useAuth.test.tsx` (signup redirect, real magic link, clearError flow)
   - Updated: `LoginForm.test.tsx` (conditional OAuth, magic link failure)
   - Updated: `SignupForm.test.tsx` (conditional OAuth)

### Email Verification Fix (Commit fd13207, 2026-03-04)

**Problem:** VerifyEmailPage and LoginForm assumed Better Auth methods throw on error, but they return `{data, error}` instead.

**Solutions:**

1. **VerifyEmailPage (`app/(app)/auth/verify-email/page.tsx`)**
   - Fixed token verification: now checks `result?.error` from `authClient.verifyEmail()`
   - Fixed resend flow: now checks `result?.error` from `authClient.sendVerificationEmail()`
   - Added separate `verifyError` and `resendError` states for distinct error messages
   - Added red error banner for resend failures (matches send success green banner)
   - Added logging: `[VerifyEmail] verifyEmail error/exception`, `[VerifyEmail] sendVerificationEmail error/exception`
   - Exception handling: try/catch as fallback (logs and shows user message)
   - Tests: 19 tests covering 3 token scenarios (success, error return, exception throw) + 3 resend scenarios

2. **LoginForm (`components/auth/LoginForm.tsx`)**
   - Added "Resend verification email" link in error message for "Email not verified" errors
   - Link points to `/auth/verify-email?email=...` (pre-fills email in resend form)
   - Enables faster re-verification without manual email entry

3. **Email Service Logging (`frontend/lib/email/send.ts`)**
   - Added structured logging before send: `[Email] Sending to=... subject=... from=...`
   - Added logging after successful send: `[Email] Sent successfully id=...`
   - SMTP fallback logs: `[Email] Resend unavailable, falling back to SMTP`
   - Helps diagnose email delivery failures

4. **Auth Server Logging (`frontend/lib/auth/server.ts`)**
   - Added logging in `sendVerificationEmail` callback: `[Auth] sendVerificationEmail called for user=... url=...`
   - Tracks when verification emails are triggered (signup, resend, etc.)

**Tests Added:**
   - `__tests__/pages/auth-verify-email.test.tsx`: 19 tests
     - Token verification: success, error return, exception throw (3 tests)
     - Resend flow: success, error return, exception throw (3 tests)
     - Error display: verification failed, resend failed (2 tests)
     - UI states: check email screen, resent confirmation (2 tests)
     - Form behavior: pre-filled email, empty email disables button (2 tests)
     - Re-render guard: useRef prevents double-verify in StrictMode (1 test)

### UI/UX Overhaul (Commit b3cdf76, 2026-03-03)

1. **Input Component Enhanced**
   - Added `labelSuffix` prop: "(optional)" text in gray-400
   - Added `labelRight` prop: Right-aligned content (e.g., "Forgot password?" link)
   - Added `success` + `successText` props: Green feedback with checkmark icon
   - Updated padding: `px-4 py-2.5` (taller for touch targets)
   - Updated border transitions: `hover:border-gray-400` with `transition-all duration-200`
   - Added error/success icons in feedback text (SVG checkmark + error circle)

2. **Auth Forms Refactored**
   - LoginForm: Now uses shared Input component instead of custom inputs
   - LoginForm: Added email blur validation with `isValidEmail()` helper
   - LoginForm: Uses Input's `labelRight` for "Forgot password?" link
   - SignupForm: Now uses shared Input component
   - SignupForm: Added email blur validation
   - SignupForm: Uses Input's `labelSuffix` for "(optional)" on name field
   - SignupForm: Uses Input's `success` + `successText` for confirm password match feedback
   - SignupForm: Password strength indicator: 6-segment bar + 5 requirement checks

3. **Forgot/Reset Password Pages**
   - Refactored to use Input component
   - Added email blur validation on forgot-password page
   - Standardized colors: primary-*/danger-*/success-* (was blue-*/red-*/green-*)

4. **Global Styles Rewrite (`globals.css`)**
   - Complete rewrite with 20+ CSS custom properties (colors, shadows, spacing, transitions)
   - Force light color scheme (`color-scheme: light`)
   - Base layer input color rules (`bg-white text-gray-900`)
   - New animations: `slideUp`, `scaleIn`, `shimmer`
   - New utility classes: `.skeleton` (shimmer loading)
   - Custom scrollbar styling (webkit)

5. **Tailwind Config Extended (`tailwind.config.ts`)**
   - New box shadows: `card`, `card-hover`, `input-focus`
   - New animations: `slide-down`, `slide-up`, `fade-in`, `scale-in`, `shimmer`
   - Spring easing function: `cubic-bezier(0.4, 0, 0.2, 1)`
   - Custom keyframes for flashGreen, flashRed, slideDown, slideUp, fadeIn, scaleIn, shimmer

6. **Input Color Fixes**
   - Settings page: 4 select dropdowns → `bg-white text-gray-900`
   - Beta signup page: 3 select dropdowns → `bg-white text-gray-900`
   - SupplierSelector: Search input → `bg-white text-gray-900`
   - ConnectionCard: Label input → `bg-white text-gray-900`
   - ConnectionAnalytics: kWh input → `bg-white text-gray-900`

### Wave 4-5: AI Agent + Notifications (2026-03-11)

**1. RateShift AI Assistant (`/assistant` page)**
   - New page: `app/(app)/assistant/page.tsx` with full-viewport chat UI
   - Component: `components/agent/AgentChat.tsx` — SSE streaming from backend
   - Hooks: `useAgentQuery()` (streaming) + `useAgentStatus()` (usage tracking)
   - API: `lib/api/agent.ts` — `queryAgent()` async generator, `submitTask()`, `getAgentUsage()`
   - Features: Example prompts, message bubbles with model/tools display, error recovery (Groq fallback on 429), rate-limit badge
   - Rate limits: Free=3/day, Pro=20/day, Business=unlimited
   - Models: Gemini 3 Flash (primary) + Groq Llama 3.3 70B (fallback)
   - Tools: Composio integration (1K actions/month)
   - Test coverage: 13 tests (streaming, examples, error handling, token usage)

**2. Notification Bell (`NotificationBell.tsx` in sidebar)**
   - In-app notification center: Bell icon with unread badge (top-right sidebar)
   - Dropdown panel: Notification list, mark-as-read actions, batch clear
   - Hooks: `useNotificationCount()` (poll 30s), `useNotifications()` (staleTime 30s), `useMarkRead()`, `useMarkAllRead()`
   - API: `lib/api/notifications.ts` — CRUD operations + polling endpoints
   - Notification types: price_alert, optimal_window, payment, system
   - Performance: Count polls every 30s (cheap), full list only fetches when dropdown open
   - Test coverage: 15 tests (polling, interactions, batch ops, empty state)

**3. Feedback Widget (`components/feedback/FeedbackWidget.tsx`)**
   - Floating button (bottom-right) → modal form
   - Feedback types: bug, feature_request, general
   - Rating: 1-5 star picker
   - Comment: Textarea with min 10 chars validation
   - Submission: POST to `/api/v1/feedback`

**4. Sidebar Update**
   - Added "Assistant" nav item (Bot icon) → `/assistant`
   - Navigation routes: Dashboard, Prices, Suppliers, Connections, Optimize, Alerts, Settings, + Assistant (8 items)
   - NotificationBell positioned in sidebar header (right side, above nav)

**5. Beta Signup Page** (`app/(app)/beta-signup/page.tsx`)
   - Early access signup with validation
   - Batch invite system + invite-stats tracking
   - Conversion tracking: Invited → Converted → Active
   - Backward-compat routes: `/beta/*` routes redirect to `/beta-signup` for public access

**6. Testing Updates**
   - Frontend tests: 1,439 total (Wave 4: +125 notification tracking, +49 A/B testing, +9 model-versions)
   - New test files: `useAgent.test.ts` (+13), `NotificationBell.test.tsx` (+15), agent API tests
   - E2E tests: 634 passed, 5 skipped (no changes)
   - Total test suites: 99 (0 failures, 6 pre-existing warnings)

**7. Framework Updates**
   - Next.js: 14.2.35 → 16.0.x (React 19 compatible)
   - React: 18 → 19 (new hook APIs, automatic batching)
   - TypeScript: Stricter type checking
   - Dependencies: @testing-library/react ^16, @types/react-dom 19, .npmrc legacy-peer-deps=true

**8. Design System Refinements**
   - Component library: +3 new components (AgentChat, NotificationBell, FeedbackWidget)
   - Color standardization: All components use primary-*/success-*/danger-* tokens
   - Icon library: lucide-react (45+ icons used across UI)
   - Shadows: card + card-hover for elevation

**9. API Client Enhancements**
   - Agent API: SSE streaming with async generator pattern
   - Notifications API: Polling-optimized (count endpoint + full list endpoint)
   - Error handling: Transparent fallback (Gemini 429 → Groq retry)
   - Rate limiting: Enforced at backend per tier, displayed in UI

**10. Performance & A11y**
   - Notification polling: 30s intervals (avoids excessive network)
   - Message streaming: Lazy render as events arrive (no buffering)
   - A11y: ARIA labels on NotificationBell, keyboard navigation on dropdown, color contrast verified

**Files Created/Modified (26 files):**
   - New: AgentChat.tsx, NotificationBell.tsx, FeedbackWidget.tsx, assistant/page.tsx, beta-signup/page.tsx
   - New: useAgent.ts, useNotifications.ts, agent.ts, notifications.ts
   - Modified: Sidebar.tsx (added Assistant route + NotificationBell), layout.tsx (Bot icon nav)
   - Tests: +60 new tests across agent, notifications, beta-signup

### Earlier Updates (2026-03-02)

- **URI_TOO_LONG Fix:** 3-layer 401 redirect guard, +13 tests, docs updated (Commit 555d48f)
- **Frontend Review Swarm:** +248 tests, a11y tooling, security & perf fixes (Commit c29e1d6)
- **E2E Healing:** 624 E2E passed, 0 lint errors (Commit 9585625)
- **Env Var Audit:** 27 1Password mappings, validation added (Commit b7436e6)

---

## Quick Reference: New Props & Patterns

### Input Component API

```typescript
<Input
  // Standard HTML input props
  id="email"
  type="email"
  name="email"
  value={email}
  onChange={(e) => setEmail(e.target.value)}
  onBlur={handleEmailBlur}
  placeholder="you@example.com"
  required
  autoComplete="email"
  disabled={false}

  // New props
  label="Email address"                    // Top label
  labelSuffix="(optional)"                 // Gray-400 suffix on label
  labelRight={<Link>Forgot?</Link>}        // Right-aligned content on label line
  error="Invalid email"                    // Error message (danger-600 + icon)
  helperText="We'll never share..."        // Helper text (gray-500)
  success={true}                           // Show success state
  successText="Email verified"             // Success message (success-600 + icon)

  // Style merging (clsx + tailwind-merge)
  className="custom-class"                 // Merges with default Tailwind
/>
```

### Blur Validation Pattern

```typescript
const isValidEmail = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)

const [email, setEmail] = useState('')
const [emailError, setEmailError] = useState<string | null>(null)

const handleEmailChange = (value: string) => {
  setEmail(value)
  if (emailError) setEmailError(null)  // Clear error on change
}

const handleEmailBlur = () => {
  if (email && !isValidEmail(email)) {
    setEmailError('Please enter a valid email address')
  }
}

// In JSX:
<Input
  value={email}
  onChange={(e) => handleEmailChange(e.target.value)}
  onBlur={handleEmailBlur}
  error={emailError || undefined}
/>
```

### Success Feedback Pattern

```typescript
const confirmPasswordHasError = Boolean(confirmPassword && password !== confirmPassword)
const confirmPasswordMatch = Boolean(confirmPassword && password === confirmPassword)

// In JSX:
<Input
  id="confirmPassword"
  label="Confirm password"
  type="password"
  value={confirmPassword}
  onChange={(e) => setConfirmPassword(e.target.value)}
  error={confirmPasswordHasError ? 'Passwords do not match' : undefined}
  success={confirmPasswordMatch}
  successText={confirmPasswordMatch ? 'Passwords match' : undefined}
/>
```

### TanStack Query Alerts Pattern

```typescript
// In component:
const { data, isLoading, isError } = useAlerts()
const createMutation = useCreateAlert()
const deleteMutation = useDeleteAlert()
const updateMutation = useUpdateAlert()

// Create:
createMutation.mutate({ region, price_below, price_above, notify_optimal_windows })

// Delete:
deleteMutation.mutate(alertId)

// Toggle active:
updateMutation.mutate({ id: alert.id, body: { is_active: !alert.is_active } })
```

---

## Style Guide

### Color Usage

- **Primary (Blue):** Buttons, links, focus rings, active states
- **Success (Teal/Green):** Confirmations, valid inputs, passing checks
- **Warning (Amber):** Medium priority, caution messages, moderate values
- **Danger (Red):** Errors, invalid inputs, destructive actions
- **Gray:** Text, backgrounds, disabled states, borders

### Typography Usage

- **Headings:** font-bold, text-lg/xl/2xl, text-gray-900
- **Body:** font-normal, text-sm/base, text-gray-700
- **Labels:** font-medium, text-sm, text-gray-700
- **Placeholder:** text-gray-400, italic

### Spacing

- **Gaps between form inputs:** `space-y-4` (1rem)
- **Card padding:** `p-8` (2rem)
- **Button padding:** `px-4 py-2.5`
- **Label margin:** `mb-1.5` (0.375rem)

### Animations

- **Entry animations:** `animate-fadeIn` (200ms) or `animate-slideDown` (alerts)
- **Success messages:** `animate-slideDown` (200ms)
- **Modals:** `animate-scaleIn` (150ms)
- **Loading:** `animate-spin` (SVG spinner) or `.skeleton` (shimmer)

---

**Last Reviewed:** 2026-03-11 by documentation engineer
**Status:** Current with AI Agent, notification delivery, A/B testing framework, Waves 4-5 complete
**Test Coverage:** 1,439 tests (frontend), ~4,170 total (all layers)
**Framework:** Next.js 16 + React 19 + TypeScript
**Components:** 55+ (19 UI + 36 feature-specific)
**Pages:** 21 (root + (app) with sidebar + (dev) + auth)
**Hooks:** 12+ (auth, alerts, agent, notifications, connections, prices, suppliers, etc.)
**API Clients:** 8+ (alerts, agent, notifications, prices, suppliers, profile, optimization, connections)
