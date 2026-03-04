# Frontend Codemap

**Last Updated:** 2026-03-03 (UI/UX overhaul: enhanced Input component, auth form refactoring, design system completion)
**Framework:** Next.js 14.2.35 (App Router) + React 18 + TypeScript
**Entry Point:** `frontend/app/layout.tsx`
**State Management:** Zustand (persisted to localStorage) + TanStack React Query v5
**Styling:** Tailwind CSS 3.4.1 + tailwind-merge + clsx

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
    robots.ts                   # robots.txt (disallows /api/, /dashboard/)
    sitemap.ts                  # Sitemap (/, /pricing, /dashboard, /privacy, /terms)
    globals.css                 # Global styles + design system CSS variables + animations
    pricing/page.tsx            # Pricing page (/pricing) - 3 tiers with FAQ
    privacy/page.tsx            # Privacy policy (/privacy)
    terms/page.tsx              # Terms of service (/terms)
    api/
      auth/[...all]/route.ts    # Better Auth API handler (sign-in, sign-up, sign-out, OAuth, etc.)
      checkout/route.ts         # POST /api/checkout - proxies to backend billing/checkout
    (app)/                      # Route group: authenticated app pages (sidebar layout)
      layout.tsx                # Sidebar layout + navigation
      dashboard/page.tsx        # Dashboard overview (user stats, recent recommendations)
      prices/page.tsx           # Electricity prices table + region selector
      suppliers/page.tsx        # Supplier details + regional availability
      optimize/page.tsx         # Appliance optimization tool + recommendations
      settings/page.tsx         # User settings (region, notifications, profile)
      onboarding/page.tsx       # Initial setup flow (region selection, utility preferences)
      auth/                     # Authentication pages (route group within (app))
        layout.tsx              # Auth layout (centered cards, no sidebar)
        login/page.tsx          # Sign in form (email/password, OAuth, magic link)
        signup/page.tsx         # Register form (email/password, OAuth, terms)
        forgot-password/page.tsx # Password reset request
        reset-password/page.tsx  # Password reset form
        callback/page.tsx       # OAuth callback handler
        verify-email/page.tsx   # Email verification after signup
      connections/page.tsx      # Connections overview (bills, utilities, direct sync)
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
      LoginForm.tsx             # Login form (email blur validation, OAuth, magic link toggle)
      SignupForm.tsx            # Signup form (password strength indicator, 5 req checks, confirm match)
      logout-button.tsx         # Sign out trigger + redirect
    layout/
      Sidebar.tsx               # Main navigation sidebar (app pages only)
      Header.tsx                # Top header (logo, user menu, mobile toggle)
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
    settings/
      ProfileForm.tsx           # Edit user info
      RegionSelector.tsx        # Change region with 50 states + DC support
      NotificationPrefs.tsx     # Email notification toggles
      DangerZone.tsx            # Delete account button
  lib/
    hooks/
      useAuth.ts                # Custom hook: auth state + sign in/up/out
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
      __tests__/
        client-401-redirect.test.ts  # 9 tests for 401 edge cases
    auth/
      server.ts                 # Better Auth server instance (edge runtime)
      client.ts                 # Better Auth client instance
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
  package.json                  # Dependencies, scripts, dev tools
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

**Sign in form with email/password, OAuth, and magic link support.**

**Features:**
- Email blur validation (`isValidEmail` regex check)
- OAuth buttons: Google + GitHub with SVG icons
- Magic link toggle: `Sign in with magic link` / `Use password instead`
- Password forgot link in labelRight
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
  ├─ OAuth buttons (Google + GitHub)
  ├─ Divider: "Or continue with"
  ├─ Form (space-y-4)
  │  ├─ Input: Email (required, blur validation)
  │  ├─ Input: Password (labelRight: Forgot link)
  │  └─ Button: Submit (loading spinner)
  ├─ Toggle: "Sign in with magic link"
  └─ Sign up link
```

#### SignupForm (`components/auth/SignupForm.tsx`)

**Register form with password strength indicator and real-time validation.**

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
- OAuth buttons: Google + GitHub

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
  ├─ OAuth buttons (Google + GitHub)
  ├─ Divider: "Or create with email"
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

---

### Layout Components

#### Sidebar (`components/layout/Sidebar.tsx`)

**Main navigation for authenticated app pages.**

**Routes:**
- `/dashboard` → Dashboard icon + "Dashboard"
- `/prices` → Price chart icon + "Prices"
- `/suppliers` → Building icon + "Suppliers"
- `/optimize` → Zap icon + "Optimize"
- `/connections` → Plug icon + "Connections"
- `/settings` → Cog icon + "Settings"

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

### Settings Page Components

**All select dropdowns styled with `bg-white text-gray-900`:**
- RegionSelector (4 selects: state, utility type, price period, etc.)
- NotificationPrefs (3 notification email toggles with selects)

---

## Authentication Flow

### Better Auth Integration

**Frontend Auth Stack:**
- **Client Library:** `better-auth` package (React hooks + client)
- **Server:** `backend/auth/neon_auth.py` (FastAPI dependency)
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
4. Better Auth creates user + session
5. Email verification may be required (depends on config)
6. Redirect to dashboard or email verification page

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
2. `useAuth.sendMagicLink()` called (POST `/api/auth/send-magic-link`)
3. Better Auth sends email with clickable link
4. User clicks link in email
5. Link redirects to `/auth/callback?token=...&email=...`
6. Callback page exchanges token for session
7. Redirect to dashboard

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

### React Query Integration

**Used for server state (API calls):**
- Prices fetch with caching
- User profile data
- Recommendations list
- Connection status

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

**Base URL:** `process.env.NEXT_PUBLIC_API_URL` (from `lib/config/env.ts`)

**Error Handling:**
- Network errors → "Connection failed"
- 4xx errors → Extract message from response.data.detail
- 5xx errors → "Server error, try again"
- 401 → Trigger redirect guard
- Unknown → "Something went wrong"

---

## Testing

### Unit Tests

- **Framework:** Jest + React Testing Library
- **Coverage:** 1385 tests across 94 suites
- **Mock:** `frontend/__mocks__/better-auth-react.js` (ESM → CJS bridge)
- **Auth mocking:** `frontend/e2e/helpers/auth.ts` (mockBetterAuth, setAuthenticatedState, clearAuthState)

**Key test files:**
- `components/auth/__tests__/LoginForm.test.tsx`
- `components/auth/__tests__/SignupForm.test.tsx`
- `lib/hooks/__tests__/useAuth.test.tsx`
- `lib/api/__tests__/client-401-redirect.test.ts` (9 tests for 401 edge cases)
- `app/(app)/auth/__tests__/authentication.spec.ts`
- `__tests__/a11y/` (51 jest-axe tests)

### E2E Tests (Playwright)

- **Coverage:** 634 tests passed, 5 skipped
- **Config:** `playwright.config.ts` (retries: 1, baseURL: localhost:3000)
- **Auth helpers:** `e2e/helpers/auth.ts`
- **Data attributes for selectors:**
  - `data-testid="sign-out-button"` on Sidebar
  - `data-testid="appliance-card-settings"` on optimize page

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

### Code Splitting

- Next.js automatic code splitting per route
- Dynamic imports for dev-only pages (Excalidraw)
- React.lazy() for modal/dialog content

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

**Required `frontend/.env.local`:**
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_ENVIRONMENT=development
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

### Feature Components (Count: 20+)

- [x] Connection components (9)
- [x] Supplier components (3)
- [x] Settings components (4)
- [x] Dashboard components (3)
- [x] Prices components (4)
- [x] Optimize components (3)

---

## File Statistics

- **Total Pages:** 19 (root + (app) + (dev) + auth routes)
- **Total Layouts:** 3 (root, app, dev, auth)
- **Total Components:** 50+ (UI + feature-specific)
- **Total Tests:** 1385 across 94 suites
- **Accessibility Tests:** 51 (jest-axe)
- **E2E Tests:** 634 passed, 5 skipped
- **Total Test Coverage:** 3,370+ tests (frontend + backend + ML + E2E)

---

## Recent Updates (2026-03-03)

### UI/UX Overhaul (Commit b3cdf76)

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

**Last Reviewed:** 2026-03-03 by documentation engineer
**Status:** Current with all recent UI/UX changes
**Test Coverage:** 1385 tests (frontend), 3,370 total (all layers)
