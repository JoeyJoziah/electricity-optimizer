# Frontend Codemap

**Last Updated:** 2026-02-22
**Framework:** Next.js 14.1.0 (App Router) + React 18 + TypeScript
**Entry Point:** `frontend/app/layout.tsx`
**State Management:** Zustand (persisted to localStorage) + TanStack React Query v5
**Styling:** Tailwind CSS 3.4.1 + tailwind-merge + clsx

---

## Directory Structure

```
frontend/
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
      LoginForm.tsx             # Email/password + OAuth (Google, GitHub) + magic link
      SignupForm.tsx             # Registration form with OAuth options
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
      supabase.ts               # Supabase client + auth functions (signIn, signUp, OAuth, magic link, token storage)
    hooks/
      useAuth.tsx               # AuthProvider context + useAuth, useRequireAuth, useAccessToken hooks
      usePrices.ts              # useCurrentPrices, usePriceHistory, usePriceForecast, useOptimalPeriods, useRefreshPrices
      useSuppliers.ts           # useSuppliers, useSupplier, useSupplierRecommendation, useCompareSuppliers, useInitiateSwitch, useSwitchStatus
      useOptimization.ts        # useOptimalSchedule, useOptimizationResult, useAppliances, useSaveAppliances, usePotentialSavings
      useRealtime.ts            # useRealtimePrices (SSE), useRealtimeOptimization, useRealtimeSubscription, useRealtimeBroadcast
    store/
      settings.ts               # Zustand store: region, supplier, usage, appliances, notifications, display prefs
    utils/
      calculations.ts           # calculatePriceTrend, findOptimalPeriods, calculateAnnualSavings, calculatePaybackMonths, etc.
      cn.ts                     # cn() - Tailwind class merge utility (clsx + tailwind-merge)
      format.ts                 # formatCurrency, formatPricePerKwh, formatDateTime, formatTime, formatDuration, formatEnergy, etc.
    query/                      # Empty directory (unused)
  types/
    index.ts                    # All TypeScript interfaces (PriceDataPoint, Supplier, Appliance, etc.)
  hooks/                        # Empty directory (unused, hooks live in lib/hooks/)
  store/                        # Empty directory (unused, store lives in lib/store/)
  __tests__/
    components/                 # Unit tests: ComparisonTable, PriceLineChart, SavingsDonut, ScheduleTimeline, SupplierCard, SwitchWizard
    integration/                # Integration test: dashboard
  e2e/                          # Playwright E2E tests: authentication, dashboard, gdpr-compliance, load-optimization, onboarding, optimization, supplier-switching, switching
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
| `region` | string | `'us_ct'` | Pricing region (US_CT, US, UK, EU) |
| `currentSupplier` | Supplier \| null | `null` | User's current electricity supplier |
| `annualUsageKwh` | number | `10500` | Annual electricity consumption (US average) |
| `peakDemandKw` | number | `5` | Maximum power draw |
| `appliances` | Appliance[] | `[]` | Configured appliances for optimization |
| `notificationPreferences` | object | `{priceAlerts: true, optimalTimes: true, supplierUpdates: false}` | Notification toggles |
| `displayPreferences` | object | `{currency: 'USD', theme: 'system', timeFormat: '12h'}` | Display settings |

**Convenience selectors:** `useRegion`, `useCurrentSupplier`, `useAnnualUsage`, `useAppliances`, `useCurrency`, `useTheme`

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
| auth | `/auth/signup` | POST | SignupForm |
| auth | `/auth/signin` | POST | LoginForm |
| auth | `/auth/signin/oauth` | POST | OAuth flow |
| auth | `/auth/signin/magic-link` | POST | Magic link flow |
| auth | `/auth/signout` | POST | Sign out |
| auth | `/auth/refresh` | POST | Token refresh |
| auth | `/auth/me` | GET | Get current user |

---

## Authentication

### Architecture

- **Provider:** Supabase client (`lib/auth/supabase.ts`) configured with `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- **Context:** `AuthProvider` wraps the entire app in `app/layout.tsx`
- **Token Storage:** localStorage (`auth_access_token`, `auth_refresh_token`)
- **Auto-refresh:** On mount, attempts token validation then refresh if expired

### Auth Methods

| Method | Flow |
|--------|------|
| Email/Password | POST to `/auth/signin` or `/auth/signup`, store tokens, redirect to `/dashboard` |
| Google OAuth | POST to `/auth/signin/oauth`, redirect to provider, callback at `/auth/callback` |
| GitHub OAuth | Same as Google OAuth flow |
| Magic Link | POST to `/auth/signin/magic-link`, user clicks email link, lands at `/auth/callback` |

### Hooks

| Hook | Purpose |
|------|---------|
| `useAuth()` | Access user, isAuthenticated, signIn/signUp/signOut methods |
| `useRequireAuth()` | Same as useAuth but redirects to `/auth/login` if not authenticated |
| `useAccessToken()` | Get current access token from localStorage |

---

## Real-Time Data

### SSE Price Stream (`useRealtimePrices`)

- Connects to `/prices/stream?region={region}&interval={interval}` via `EventSource`
- On message: parses `PriceUpdate`, invalidates `['prices', 'current']` and `['prices', 'history']` queries
- Auto-reconnects on error (native EventSource behavior)
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
| `LoginForm` | `components/auth/LoginForm.tsx` | Email/password form + Google/GitHub OAuth buttons + magic link option |
| `SignupForm` | `components/auth/SignupForm.tsx` | Registration form with name, email, password + OAuth |

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
| next | 14.1.0 | Framework (App Router) |
| react | ^18.2.0 | UI library |
| @tanstack/react-query | ^5.17.15 | Server state management |
| zustand | ^4.4.7 | Client state management |
| recharts | ^2.10.3 | Charts and data visualization |
| @supabase/supabase-js | ^2.39.0 | Authentication client |
| lucide-react | ^0.309.0 | Icon library |
| tailwindcss | ^3.4.1 | Utility-first CSS |
| tailwind-merge | ^2.2.0 | Tailwind class deduplication |
| clsx | ^2.1.0 | Conditional class names |
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

### Unit Tests (`__tests__/`)

6 component tests + 1 integration test:

| Test File | Covers |
|-----------|--------|
| ComparisonTable.test.tsx | Supplier comparison table rendering and sorting |
| PriceLineChart.test.tsx | Chart rendering with different data/configs |
| SavingsDonut.test.tsx | Donut chart with savings breakdown |
| ScheduleTimeline.test.tsx | Timeline with schedules and price zones |
| SupplierCard.test.tsx | Card rendering, savings badge, selection |
| SwitchWizard.test.tsx | Multi-step wizard flow (note: flaky) |
| dashboard.test.tsx | Dashboard integration: data loading, display, interactions |

### E2E Tests (`e2e/`)

8 Playwright spec files: authentication, dashboard, gdpr-compliance, load-optimization, onboarding, optimization, supplier-switching, switching.

### Commands

```bash
npm run test          # Jest watch mode
npm run test:ci       # Jest with coverage
npm run test:e2e      # Playwright E2E
npm run type-check    # tsc --noEmit
npm run lint          # next lint
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | Backend API base URL (default: `http://localhost:8000/api/v1`) |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Supabase anonymous key |
| `NEXT_PUBLIC_SITE_URL` | No | Site URL for SEO (default: `https://electricity-optimizer.vercel.app`) |

---

## Recent Changes (as of 2026-02-22)

1. **Region default changed from 'uk' to 'us_ct'** -- All API functions (`prices.ts`, `suppliers.ts`, `optimization.ts`) and hooks (`usePrices.ts`, `useSuppliers.ts`, `useOptimization.ts`, `useRealtime.ts`) now default to `'us_ct'`
2. **Settings store defaults updated** -- region: `'us_ct'`, currency: `'USD'`, annualUsageKwh: `10500` (US average), timeFormat: `'12h'`
3. **Landing page added at `/`** -- Previously redirected to `/dashboard`; now shows full marketing page with hero, features, pricing preview, and footer
4. **Route restructuring** -- Marketing pages (/, /pricing, /privacy, /terms) at root layout without sidebar; app pages under `(app)` route group with sidebar
5. **Stripe monetization** -- Checkout API route proxy at `/api/checkout`; tiers: Free, Pro ($4.99/mo), Business ($14.99/mo)
6. **SEO metadata** -- Root layout includes OG tags, Twitter card, keywords; dedicated robots.ts and sitemap.ts
7. **Error boundaries** -- Global error boundary + per-route boundaries for dashboard, prices, suppliers

---

## Related Codemaps

- [Backend Codemap](./CODEMAP_BACKEND.md) - FastAPI backend, API endpoints, database schema
- [Stripe Architecture](./STRIPE_ARCHITECTURE.md) - Payment integration details
- [Deployment](./DEPLOYMENT.md) - Deployment configuration and environment setup
