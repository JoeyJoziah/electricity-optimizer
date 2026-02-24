# Frontend Codemap

**Last Updated:** 2026-02-24 (SSE auth upgrade: fetch-event-source, route splitting, 45-item refactoring complete)
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
    globals.css                 # Global styles
    pricing/page.tsx            # Pricing page (/pricing) - 3 tiers with FAQ
    privacy/page.tsx            # Privacy policy (/privacy)
    terms/page.tsx              # Terms of service (/terms)
    api/
      auth/[...all]/route.ts    # Better Auth API handler (sign-in, sign-up, sign-out, OAuth, etc.)
      checkout/route.ts         # POST /api/checkout - proxies to backend billing/checkout
    (app)/                      # Route group: authenticated app pages (sidebar layout)
      layout.tsx                # App layout: Sidebar + flex main content
      auth/
        login/page.tsx          # Login page (/auth/login) - renders LoginForm
        signup/page.tsx         # Signup page (/auth/signup) - renders SignupForm
        callback/page.tsx       # OAuth/magic-link callback (/auth/callback)
      beta-signup/page.tsx      # Beta signup form (/beta-signup) - CT suppliers
      dashboard/
        page.tsx                # Dashboard (/dashboard) - stats, charts, gamification
        error.tsx               # Dashboard error boundary
      prices/
        page.tsx                # Prices (/prices) - history, forecast, optimal periods
        error.tsx               # Prices error boundary
      suppliers/
        page.tsx                # Suppliers (/suppliers) - grid/table, compare, switch wizard
        error.tsx               # Suppliers error boundary
      optimize/page.tsx         # Optimization (/optimize) - appliances, schedule, savings
      settings/page.tsx         # Settings (/settings) - region, usage, notifications, display
    optimization/               # Empty directory (unused)
  components/
    auth/
      LoginForm.tsx             # Email/password + OAuth (Google, GitHub) + magic link (legacy UI)
      SignupForm.tsx             # Registration form with OAuth options (legacy UI)
    charts/
      ForecastChart.tsx         # ML forecast visualization (Recharts)
      PriceLineChart.tsx        # Price history line chart with time range selector
      SavingsDonut.tsx          # Donut chart for savings breakdown
      ScheduleTimeline.tsx      # 24-hour timeline with price zones + scheduled tasks
    gamification/
      SavingsTracker.tsx        # Streak tracking, savings summary, optimization score
    layout/
      Header.tsx                # Sticky header: title, live indicator, refresh, notifications
      Sidebar.tsx               # Fixed sidebar: logo + 5 nav links (Dashboard through Settings)
    providers/
      QueryProvider.tsx         # TanStack React Query client (1min stale, 5min GC, 3 retries)
    suppliers/
      ComparisonTable.tsx       # Tabular supplier comparison with filters
      SupplierCard.tsx          # Supplier card with pricing, rating, green badge
      SwitchWizard.tsx          # Multi-step supplier switching flow with GDPR consent
    ui/                         # Primitive UI components (badge, button, card, input, skeleton)
      badge.tsx                 # Badge with variants: default, success, warning, danger, info
      button.tsx                # Button with variants: primary, ghost, outline, danger + sizes
      card.tsx                  # Card, CardHeader, CardTitle, CardContent, CardFooter, CardDescription
      input.tsx                 # Input with label/helperText + Checkbox component
      skeleton.tsx              # Skeleton + ChartSkeleton loading placeholders
    optimize/                   # Empty directory (unused)
  lib/
    api/
      client.ts                 # Base API client (GET/POST/PUT/DELETE) -> NEXT_PUBLIC_API_URL
      prices.ts                 # Price API: getCurrentPrices, getPriceHistory, getPriceForecast, getOptimalPeriods
      suppliers.ts              # Supplier API: getSuppliers, getRecommendation, compareSuppliers, initiateSwitch, getSwitchStatus
      optimization.ts           # Optimization API: getOptimalSchedule, saveAppliances, calculatePotentialSavings
    auth/
      client.ts                 # Better Auth client (createAuthClient) — browser-side auth
      server.ts                 # Better Auth server-side helpers
    hooks/
      useAuth.tsx               # AuthProvider context + useAuth, useRequireAuth, useAccessToken hooks
      usePrices.ts              # useCurrentPrices, usePriceHistory, usePriceForecast, useOptimalPeriods, useRefreshPrices
      useSuppliers.ts           # useSuppliers, useSupplier, useSupplierRecommendation, useCompareSuppliers, useInitiateSwitch, useSwitchStatus
      useOptimization.ts        # useOptimalSchedule, useOptimizationResult, useAppliances, useSaveAppliances, usePotentialSavings
      useRealtime.ts            # useRealtimePrices (SSE via fetch-event-source), useRealtimeOptimization, useRealtimeSubscription, useRealtimeBroadcast
    store/
      settings.ts               # Zustand store: region, supplier, usage, appliances, notifications, display prefs
    utils/
      calculations.ts           # calculatePriceTrend, findOptimalPeriods, calculateAnnualSavings, calculatePaybackMonths, etc.
      cn.ts                     # cn() - Tailwind class merge utility (clsx + tailwind-merge)
      format.ts                 # formatCurrency, formatPricePerKwh, formatDateTime, formatTime, formatDuration, formatEnergy, etc.
  types/
    index.ts                    # All TypeScript interfaces (PriceDataPoint, Supplier, Appliance, etc.)
  __tests__/
    components/                 # Component unit tests (14 suites)
      auth/                     #   LoginForm, SignupForm
      charts/                   #   ForecastChart
      gamification/             #   SavingsTracker
      layout/                   #   Header, Sidebar
      ui/                       #   Badge, Button, Card, Input, Skeleton
      ComparisonTable, PriceLineChart, SavingsDonut, ScheduleTimeline, SupplierCard, SwitchWizard
    integration/                # Integration test: dashboard
  lib/
    api/__tests__/
      client.test.ts            # API client unit tests (30 tests)
    utils/__tests__/
      format.test.ts            # Format utility tests (46 tests)
      calculations.test.ts      # Calculation utility tests (46 tests)
  e2e/                          # Playwright E2E tests (11 specs, 5 browser projects, 805 total)
    helpers/
      auth.ts                   # Better Auth mocking: mockBetterAuth, setAuthenticatedState, clearAuthState
  public/                       # Static assets (icons, etc.)
```

---

## Route Map

### Marketing Pages (root layout - no sidebar)

| Route | File | Description |
|-------|------|-------------|
| `/` | `app/page.tsx` | Landing page: hero, 6 features, pricing preview, footer |
| `/pricing` | `app/pricing/page.tsx` | Detailed pricing page: 3 tiers (Free/$4.99 Pro/$14.99 Business) + FAQ |
| `/privacy` | `app/privacy/page.tsx` | Privacy policy (GDPR, data retention, third-party services) |
| `/terms` | `app/terms/page.tsx` | Terms of service (subscriptions, API usage, liability) |

### App Pages ((app) route group - sidebar layout)

| Route | File | Description |
|-------|------|-------------|
| `/dashboard` | `app/(app)/dashboard/page.tsx` | Main dashboard: current price, savings, charts, forecast, schedule |
| `/prices` | `app/(app)/prices/page.tsx` | Price detail: history chart, stats, 48h forecast, optimal periods, alerts |
| `/suppliers` | `app/(app)/suppliers/page.tsx` | Supplier comparison: grid/table views, recommendation banner, switch wizard |
| `/optimize` | `app/(app)/optimize/page.tsx` | Load optimization: appliance config, schedule optimizer, savings calc |
| `/settings` | `app/(app)/settings/page.tsx` | Settings: region, supplier, usage, notifications, display, privacy |
| `/auth/login` | `app/(app)/auth/login/page.tsx` | Login form (force-dynamic) |
| `/auth/signup` | `app/(app)/auth/signup/page.tsx` | Signup form (force-dynamic) |
| `/auth/callback` | `app/(app)/auth/callback/page.tsx` | OAuth/magic-link callback handler (force-dynamic) |
| `/beta-signup` | `app/(app)/beta-signup/page.tsx` | Beta program signup form |

### API Routes

| Route | Method | File | Description |
|-------|--------|------|-------------|
| `/api/auth/*` | GET/POST | `app/api/auth/[...all]/route.ts` | Better Auth handler (sign-in, sign-up, sign-out, OAuth, session, etc.) |
| `/api/checkout` | POST | `app/api/checkout/route.ts` | Proxy to backend Stripe checkout (requires auth header) |

### SEO / Meta

| File | Description |
|------|-------------|
| `app/manifest.ts` | PWA manifest: "Electricity Optimizer", standalone, blue theme |
| `app/robots.ts` | Disallows /api/ and /dashboard/ from crawlers |
| `app/sitemap.ts` | 5 URLs: /, /pricing, /dashboard, /privacy, /terms |
| `app/layout.tsx` | Root metadata: title template, OG tags, Twitter card, keywords |

---

## State Management

### Zustand Settings Store (`lib/store/settings.ts`)

Persisted to localStorage under key `electricity-optimizer-settings`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `region` | string | `'us_ct'` | Pricing region (all US states + international) |
| `utilityTypes` | UtilityType[] | `['electricity']` | Selected utility types for comparison |
| `currentSupplier` | Supplier \| null | `null` | User's current energy supplier |
| `annualUsageKwh` | number | `10500` | Annual electricity consumption (US average) |
| `peakDemandKw` | number | `5` | Maximum power draw |
| `appliances` | Appliance[] | `[]` | Configured appliances for optimization |
| `notificationPreferences` | object | `{priceAlerts: true, optimalTimes: true, supplierUpdates: false}` | Notification toggles |
| `displayPreferences` | object | `{currency: 'USD', theme: 'system', timeFormat: '12h'}` | Display settings |

**UtilityType:** `'electricity' | 'natural_gas' | 'heating_oil' | 'propane' | 'community_solar'`

**Convenience selectors:** `useRegion`, `useUtilityTypes`, `useCurrentSupplier`, `useAnnualUsage`, `useAppliances`, `useCurrency`, `useTheme`

### React Query (TanStack Query v5)

Configured in `QueryProvider` with defaults: 1min stale time, 5min garbage collection, 3 retries with exponential backoff, refetch on window focus.

| Query Key Pattern | Hook | Refetch Interval | Stale Time |
|-------------------|------|-------------------|------------|
| `['prices', 'current', region]` | `useCurrentPrices` | 60s | 55s |
| `['prices', 'history', region, hours]` | `usePriceHistory` | -- | 60s |
| `['prices', 'forecast', region, hours]` | `usePriceForecast` | 300s | 180s |
| `['prices', 'optimal', region, hours]` | `useOptimalPeriods` | 300s | 180s |
| `['suppliers', region, annualUsage]` | `useSuppliers` | -- | 300s |
| `['supplier', id]` | `useSupplier` | -- | 300s |
| `['recommendation', ...]` | `useSupplierRecommendation` | -- | 300s |
| `['optimization', 'schedule', ...]` | `useOptimalSchedule` | -- | 180s |
| `['potential-savings', ...]` | `usePotentialSavings` | -- | 300s |
| `['appliances']` | `useAppliances` | -- | 300s |

---

## API Layer (`lib/api/`)

### Base Client (`client.ts`)

- Base URL: `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000/api/v1`)
- Methods: `get<T>`, `post<T>`, `put<T>`, `delete<T>`
- All 4 fetch methods include `credentials: 'include'` for cross-origin cookie support (Neon Auth sessions)
- Error handling: throws `ApiClientError` with status, message, details
- All requests include `Content-Type: application/json`

### Region Default

All API functions and hooks default to `region = 'us_ct'` (Connecticut). This was changed from `'uk'` to reflect the CT focus.

### Endpoints Called

| API Module | Endpoint | Method | Used By |
|------------|----------|--------|---------|
| prices | `/prices/current` | GET | Dashboard, Prices |
| prices | `/prices/history` | GET | Dashboard, Prices |
| prices | `/prices/forecast` | GET | Dashboard, Prices |
| prices | `/prices/optimal-periods` | GET | Prices |
| prices | `/prices/stream` | SSE | Dashboard (useRealtimePrices) |
| suppliers | `/suppliers` | GET | Dashboard, Suppliers |
| suppliers | `/suppliers/{id}` | GET | Supplier detail |
| suppliers | `/suppliers/recommend` | POST | Suppliers |
| suppliers | `/suppliers/compare` | POST | Suppliers |
| suppliers | `/suppliers/switch` | POST | Suppliers (SwitchWizard) |
| suppliers | `/suppliers/switch/{ref}` | GET | Switch status polling |
| optimization | `/optimization/schedule` | POST | Optimize |
| optimization | `/optimization/result` | GET | Optimization results |
| optimization | `/optimization/appliances` | GET/POST | Appliance management |
| optimization | `/optimization/potential-savings` | POST | Optimize |
| billing | `/billing/checkout` | POST | Checkout API route proxy |
| auth | `/api/auth/*` | GET/POST | Better Auth handles all auth flows (sign-in, sign-up, sign-out, OAuth, session) |
| auth | `/auth/me` | GET | Get current user (backend) |

---

## Authentication

### Architecture

- **Provider:** Neon Auth (Better Auth) — managed auth via `@better-auth` SDK
- **API Route:** `app/api/auth/[...all]/route.ts` handles all auth endpoints (sign-in, sign-up, sign-out, OAuth, session, etc.)
- **Client:** `lib/auth/client.ts` — `createAuthClient()` from `better-auth/react`
- **Server:** `lib/auth/server.ts` — server-side auth helpers
- **Session Storage:** httpOnly cookies (`better-auth.session_token`) — no localStorage tokens
- **Route Protection:** `middleware.ts` checks session cookie, redirects unauthenticated users to `/auth/login`
- **Context:** `AuthProvider` wraps the entire app in `app/layout.tsx`, provides `useAuth()` hook

### Auth Methods

| Method | Flow |
|--------|------|
| Email/Password | Better Auth handles via `/api/auth/sign-in/email` and `/api/auth/sign-up/email` |
| Google OAuth | `authClient.signIn.social({ provider: "google" })` → callback → session cookie |
| GitHub OAuth | `authClient.signIn.social({ provider: "github" })` → callback → session cookie |
| Magic Link | Better Auth magic link flow via `/api/auth/magic-link` |

### Hooks

| Hook | Purpose |
|------|---------|
| `useAuth()` | Access user, isAuthenticated, signIn/signUp/signOut/signInWithGoogle/signInWithGitHub methods |
| `useRequireAuth()` | Same as useAuth but redirects to `/auth/login` if not authenticated |

---

## Real-Time Data

### SSE Price Stream (`useRealtimePrices`)

- Connects to `/prices/stream?region={region}&interval={interval}` via `@microsoft/fetch-event-source`
- Uses `credentials: 'include'` to send Better Auth session cookies (native `EventSource` cannot)
- Auth failure detection: 401/403 in `onopen` throws to stop retrying
- `onerror` returns retry delay (ms) or throws for auth failures; exponential backoff (1s -> 2s -> 4s, max 30s)
- `openWhenHidden: true` keeps streaming in background tabs
- Cleanup via `AbortController.abort()` (not `EventSource.close()`)
- On message: parses `PriceUpdate` (with optional `source` field: `"live"` or `"fallback"`), invalidates `['prices', 'current']` and `['prices', 'history']` queries
- Returns: `{ isConnected, lastPrice, disconnect }`

### Polling Fallbacks

- `useRealtimeOptimization`: Polls optimization queries every 60s
- `useRealtimeSubscription`: Generic polling every 30s
- `useRealtimeBroadcast`: Placeholder for future WebSocket support

---

## Key Components

### Layout

| Component | File | Props | Description |
|-----------|------|-------|-------------|
| `Sidebar` | `components/layout/Sidebar.tsx` | -- | Fixed left sidebar (hidden on mobile). 5 nav items: Dashboard, Prices, Suppliers, Optimize, Settings |
| `Header` | `components/layout/Header.tsx` | `title, onMenuClick?` | Sticky header with page title, live indicator (green dot), refresh button, notification bell |

### Charts (Recharts)

| Component | File | Description |
|-----------|------|-------------|
| `PriceLineChart` | `components/charts/PriceLineChart.tsx` | Line chart with time range selector (6h/12h/24h/48h/7d), optional forecast overlay, optimal period highlighting |
| `ForecastChart` | `components/charts/ForecastChart.tsx` | ML forecast visualization with confidence intervals |
| `SavingsDonut` | `components/charts/SavingsDonut.tsx` | Donut chart breaking down savings by category |
| `ScheduleTimeline` | `components/charts/ScheduleTimeline.tsx` | 24-hour horizontal timeline showing price zones (cheap/expensive) and scheduled appliance runs |

### Suppliers

| Component | File | Description |
|-----------|------|-------------|
| `SupplierCard` | `components/suppliers/SupplierCard.tsx` | Card showing supplier name, price, rating, green badge, savings vs current |
| `ComparisonTable` | `components/suppliers/ComparisonTable.tsx` | Full table with sortable columns and filters |
| `SwitchWizard` | `components/suppliers/SwitchWizard.tsx` | Multi-step modal: review -> GDPR consent -> confirm -> complete |

### Gamification

| Component | File | Description |
|-----------|------|-------------|
| `SavingsTracker` | `components/gamification/SavingsTracker.tsx` | Daily/weekly/monthly savings, streak counter (bronze/silver/gold/legendary), optimization score, progress bar toward $50/mo goal |

### Auth

| Component | File | Description |
|-----------|------|-------------|
| `LoginForm` | `components/auth/LoginForm.tsx` | Email/password form + Google/GitHub OAuth buttons + magic link option (legacy, uses useAuth hook) |
| `SignupForm` | `components/auth/SignupForm.tsx` | Registration form with name, email, password + OAuth (legacy, uses useAuth hook) |

---

## Utility Functions

### `lib/utils/format.ts`

| Function | Signature | Description |
|----------|-----------|-------------|
| `formatCurrency` | `(amount, currency='USD')` | Intl.NumberFormat with `en-US` locale, supports USD/GBP/EUR |
| `formatPricePerKwh` | `(price, currency)` | Formatted price + "/kWh" suffix |
| `formatPercentage` | `(value, decimals=2)` | Number with % suffix |
| `formatDateTime` | `(dateString, formatStr)` | date-fns format, default `dd MMM yyyy HH:mm` |
| `formatTime` | `(dateString, is24Hour)` | Time-only format (HH:mm or h:mm a) |
| `formatDuration` | `(hours)` | e.g., "2h 30m" |
| `formatEnergy` | `(kWh)` | Auto-scales to MWh if >= 1000 |
| `formatRelativeTime` | `(dateString)` | e.g., "2 hours ago" |
| `formatCompactNumber` | `(num)` | e.g., "1.2K", "3.5M" |

### `lib/utils/calculations.ts`

| Function | Description |
|----------|-------------|
| `calculatePriceTrend` | Compares recent price halves to determine increasing/decreasing/stable |
| `findOptimalPeriods` | Finds contiguous low-price periods below a percentile threshold |
| `calculateAnnualSavings` | Difference between two suppliers' annual costs |
| `calculatePaybackMonths` | Months to recoup exit fee from monthly savings |
| `calculateTotalScheduleSavings` | Sum of savings across optimization schedules |
| `calculateRecommendationConfidence` | Weighted score from savings, volatility, data quality |
| `getPriceCategory` | cheap/moderate/expensive based on ratio to average |
| `calculateChangePercent` | Percentage change between two values |

---

## Type System (`types/index.ts`)

### Core Types

| Type | Key Fields |
|------|------------|
| `PriceDataPoint` | time, price, forecast, isOptimal, confidenceLow/High |
| `CurrentPrice` | region, price, timestamp, trend, changePercent |
| `PriceForecast` | hour, price, confidence [low, high], timestamp |
| `Supplier` | id, name, avgPricePerKwh, standingCharge, greenEnergy, rating, estimatedAnnualCost, tariffType |
| `SupplierRecommendation` | supplier, currentSupplier, estimatedSavings, paybackMonths, confidence |
| `Appliance` | id, name, powerKw, typicalDurationHours, isFlexible, priority |
| `OptimizationSchedule` | applianceId, applianceName, scheduledStart/End, estimatedCost, savings, reason |
| `UserSettings` | region, currentSupplier, annualUsageKwh, peakDemandKw, appliances, notification/display prefs |
| `TimeRange` | `'6h' \| '12h' \| '24h' \| '48h' \| '7d'` |

---

## Data Flow

```
User Action
    |
    v
Page Component (app/(app)/*)
    |
    +--> Zustand Store (settings, appliances, preferences)
    |        persisted to localStorage
    |
    +--> React Query Hook (lib/hooks/*)
              |
              v
         API Function (lib/api/*)
              |
              v
         apiClient.get/post -> fetch()
              |
              v
         Backend (FastAPI @ NEXT_PUBLIC_API_URL)
              |
              v
         Response -> React Query Cache -> Component Re-render
              |
         SSE Stream (prices) -> query invalidation -> auto-refetch
```

---

## Error Handling

- **Root level:** `app/error.tsx` catches page-level errors, `app/global-error.tsx` catches layout-level errors
- **Per-route:** Dashboard, Prices, and Suppliers each have dedicated `error.tsx` boundaries with retry buttons
- **API layer:** `ApiClientError` class with status code, message, and details
- **Auth:** `AuthError` class with optional error code
- **404:** Custom `app/not-found.tsx` with link back to dashboard

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| next | 14.2.35 | Framework (App Router, fixes CVE-2025-29927/CVE-2024-46982/CVE-2024-34351) |
| react | ^18.2.0 | UI library |
| better-auth | latest | Authentication (Neon Auth / Better Auth) |
| @tanstack/react-query | ^5.17.15 | Server state management |
| zustand | ^4.4.7 | Client state management |
| recharts | ^2.10.3 | Charts and data visualization |
| lucide-react | ^0.309.0 | Icon library |
| tailwindcss | ^3.4.1 | Utility-first CSS |
| tailwind-merge | ^2.2.0 | Tailwind class deduplication |
| clsx | ^2.1.0 | Conditional class names |
| @microsoft/fetch-event-source | ^2.0.1 | SSE with auth (replaces native EventSource) |
| date-fns | ^3.2.0 | Date formatting |

### Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| @playwright/test | ^1.40.1 | E2E testing |
| jest | ^29.7.0 | Unit testing |
| @testing-library/react | ^14.1.2 | Component testing |
| typescript | ^5.3.3 | Type checking |

---

## Testing

### Unit Tests

17 test suites, 346 tests total:

**Component tests** (`__tests__/`):

| Test File | Covers |
|-----------|--------|
| ComparisonTable.test.tsx | Supplier comparison table rendering and sorting |
| PriceLineChart.test.tsx | Chart rendering with different data/configs |
| SavingsDonut.test.tsx | Donut chart with savings breakdown |
| ScheduleTimeline.test.tsx | Timeline with schedules and price zones |
| SupplierCard.test.tsx | Card rendering, savings badge, selection |
| SwitchWizard.test.tsx | Multi-step wizard flow (note: flaky) |
| auth/LoginForm.test.tsx | Login form: email/password, OAuth, magic link, error states |
| auth/SignupForm.test.tsx | Signup form: registration, password validation, OAuth |
| charts/ForecastChart.test.tsx | Forecast chart: data rendering, empty state, confidence |
| gamification/SavingsTracker.test.tsx | Streak tiers, progress bar, formatCurrency |
| layout/Header.test.tsx | Header: title, nav, active state |
| layout/Sidebar.test.tsx | Sidebar: nav links, responsive |
| ui/*.test.tsx | UI primitives: Badge, Button, Card, Input, Skeleton |
| integration/dashboard.test.tsx | Dashboard integration: data loading, display, interactions |

**Library tests** (`lib/`):

| Test File | Tests | Covers |
|-----------|-------|--------|
| lib/utils/\_\_tests\_\_/format.test.ts | 46 | All 9 format functions (currency, date, time, energy, etc.) |
| lib/utils/\_\_tests\_\_/calculations.test.ts | 46 | All 8 calculation functions (trend, optimal periods, savings, etc.) |
| lib/api/\_\_tests\_\_/client.test.ts | 30 | API client (GET/POST/PUT/DELETE), ApiClientError class |

### E2E Tests (`e2e/`)

11 Playwright spec files x 5 browser projects = 805 total tests.
**Last run:** 431 passed, 374 skipped, 0 failed (2026-02-23).

| Spec File | Tests | Description |
|-----------|-------|-------------|
| authentication.spec.ts | 15 | Login, OAuth, session persistence, rate limiting (10 active, 5 skipped) |
| billing-flow.spec.ts | 9 | Stripe pricing, checkout flow |
| dashboard.spec.ts | 11 | Widgets, navigation, error handling |
| full-journey.spec.ts | 25 | Full user journey (landing -> optimize) |
| gdpr-compliance.spec.ts | 14 | Cookie consent, data export/deletion |
| load-optimization.spec.ts | 18 | Appliance scheduling, savings |
| onboarding.spec.ts | 11 | Signup navigation, dashboard access |
| optimization.spec.ts | 12 | Quick add, custom appliance, flexibility |
| sse-streaming.spec.ts | 11 | SSE connection, error recovery |
| supplier-switching.spec.ts | 18 | Supplier comparison, switch wizard |
| switching.spec.ts | 17 | Switching wizard GDPR consent |

**Browser projects:** Chromium, Firefox, WebKit, Mobile Chrome (Pixel 5), Mobile Safari (iPhone 12)

### Commands

```bash
npm run test          # Jest watch mode
npm run test:ci       # Jest with coverage
npm run test:e2e      # Playwright E2E (all 5 browsers)
npm run type-check    # tsc --noEmit
npm run lint          # next lint
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Backend API base URL (default: `http://localhost:8000/api/v1`) |
| `NEXT_PUBLIC_SITE_URL` | No | Site URL for SEO (default: `https://electricity-optimizer.vercel.app`) |
| `BETTER_AUTH_SECRET` | Yes | Secret for Better Auth session encryption |
| `BETTER_AUTH_URL` | Yes | App URL for auth callbacks (e.g., `http://localhost:3000`) |

---

## Recent Changes (as of 2026-02-24)

1. **Multi-utility support** -- Settings store includes `utilityTypes` field (array of UtilityType). Settings page has utility type checkboxes
2. **Multi-state region selector** -- Settings page offers expanded region dropdown covering all 50 US states + international regions
3. **Region default changed from 'uk' to 'us_ct'** -- All API functions and hooks default to `'us_ct'`
4. **Settings store defaults updated** -- region: `'us_ct'`, utilityTypes: `['electricity']`, currency: `'USD'`, annualUsageKwh: `10500`, timeFormat: `'12h'`
5. **Landing page added at `/`** -- Full marketing page with hero, features, pricing preview, and footer
6. **Route restructuring** -- Marketing pages at root layout without sidebar; app pages under `(app)` route group with sidebar
7. **Stripe monetization** -- Checkout API route proxy at `/api/checkout`; tiers: Free, Pro ($4.99/mo), Business ($14.99/mo)
8. **SEO metadata** -- Root layout includes OG tags, Twitter card, keywords; dedicated robots.ts and sitemap.ts
9. **Error boundaries** -- Global error boundary + per-route boundaries for dashboard, prices, suppliers
10. **Neon Auth migration** -- Supabase SDK removed; auth now via Better Auth (`better-auth` package) with Neon Auth backend. Session cookies replace localStorage JWT tokens. Route protection via `middleware.ts`
11. **CSP + HSTS headers** -- Content-Security-Policy and Strict-Transport-Security added to `next.config.js`
12. **Frontend test expansion** -- 346 Jest tests across 17 suites covering components, lib/utils, lib/api
13. **Cross-browser E2E** -- 11 Playwright specs across 5 browser projects (Chromium, Firefox, WebKit, Mobile Chrome, Mobile Safari). 431 passing, 0 failures
14. **SSE auth upgrade** -- Replaced native `EventSource` with `@microsoft/fetch-event-source` for cookie-based session auth. Enables `credentials: 'include'`, auth failure detection, and exponential backoff retry
15. **Backend route splitting** -- `prices.py` split into `prices.py` (CRUD), `prices_analytics.py` (statistics), `prices_sse.py` (streaming with real DB data via PriceService)

---

## Related Codemaps

- [Backend Codemap](./CODEMAP_BACKEND.md) - FastAPI backend, API endpoints, database schema
- [Stripe Architecture](./STRIPE_ARCHITECTURE.md) - Payment integration details
- [Deployment](./DEPLOYMENT.md) - Deployment configuration and environment setup
