# Frontend UI & State Specification

> SPARC Phase: Specification | Layer: Frontend (Next.js 14 App Router + TypeScript)
> Last updated: 2026-02-22
>
> **Note (2026-02-24):** This spec predates the refactoring roadmap (2026-02-23). Key changes since: Supabase auth fully replaced by Neon Auth (Better Auth), SSE upgraded to `@microsoft/fetch-event-source` for cookie-based auth, Next.js upgraded to 14.2.35. See [REFACTORING_ROADMAP.md](../REFACTORING_ROADMAP.md).

---

## 1. Route Map

Two layout groups: **root** (marketing, no sidebar) and **(app)** (authenticated, sidebar).

### Root Layout (`app/layout.tsx`)

Wraps every page. Provides `QueryProvider` (TanStack Query) and `AuthProvider`
(Supabase auth context). Uses Inter font. SEO metadata targets "Electricity Optimizer"
with Open Graph, Twitter cards, and robots directives.

```
RootLayout -> html[lang="en"] -> body[Inter]
  QueryProvider  (staleTime:60s, gcTime:5min, retry:3, exponential backoff max 30s)
    AuthProvider (user, isLoading, isAuthenticated, error + auth methods)
      {children}
```

### Marketing Pages (root, no sidebar, static RSC)

| Route | File | Description |
|-------|------|-------------|
| `/` | `app/page.tsx` | Landing: hero, 6 features, 3 pricing tiers, footer |
| `/pricing` | `app/pricing/page.tsx` | Detailed pricing with FAQ and limitations |
| `/privacy` | `app/privacy/page.tsx` | Privacy policy |
| `/terms` | `app/terms/page.tsx` | Terms of service |

### App Layout (`app/(app)/layout.tsx`)

Fixed-left `Sidebar` (hidden <lg, 16rem wide) + `main.flex-1.lg:pl-64`.

### App Pages (all `'use client'`)

| Route | File | Data Sources |
|-------|------|--------------|
| `/dashboard` | `(app)/dashboard/page.tsx` | currentPrices, priceHistory, priceForecast, suppliers, realtimeSSE |
| `/prices` | `(app)/prices/page.tsx` | currentPrices, priceHistory, priceForecast, optimalPeriods |
| `/suppliers` | `(app)/suppliers/page.tsx` | suppliers, supplierRecommendation, initiateSwitch mutation |
| `/optimize` | `(app)/optimize/page.tsx` | optimalSchedule, appliances (Zustand), potentialSavings |
| `/settings` | `(app)/settings/page.tsx` | Zustand store only (no API calls) |
| `/auth/login` | `(app)/auth/login/page.tsx` | force-dynamic, useAuth |
| `/auth/signup` | `(app)/auth/signup/page.tsx` | force-dynamic, useAuth |
| `/auth/callback` | `(app)/auth/callback/page.tsx` | force-dynamic, URL hash tokens |

### Sidebar Navigation

```
Dashboard  /dashboard  LayoutDashboard | Prices  /prices  TrendingUp
Suppliers  /suppliers  Building2       | Optimize /optimize Calendar
Settings   /settings   Settings
```

---

## 2. Component Architecture

### Dashboard Page

```
DashboardPage
  Header[title="Dashboard"]
  PriceAlertBanner                -- shown when trend == "decreasing"
  StatsGrid (4 cards): CurrentPrice, TotalSaved+streak, OptimalTimes(02:00-06:00), Suppliers
  Row1: PriceLineChart (2col, timeRange selector) + SavingsTracker (1col)
  Row2: ForecastChart 24hr (2col) + TopSuppliers top-2 SupplierCards (1col)
  ScheduleTimeline                -- mock schedules with priceZones
```

### SavingsTracker (`components/gamification/SavingsTracker.tsx`)

```
Props: { dailySavings, weeklySavings, monthlySavings, streakDays, bestStreak, optimizationScore }
Streak levels: bronze(<7d), silver(<14d), gold(<30d), legendary(30d+)
Progress bar: monthlySavings / $50 goal * 100%, capped at 100%
```

### Suppliers Page

```
SuppliersPage
  RecommendationBanner            -- when recommendation + currentSupplier exist
  StatsRow: Cheapest (min annual cost), Greenest (greenEnergy==true), Current (Zustand)
  ViewToggle: grid (SupplierCard[]) | table (ComparisonTable)
  SwitchWizard modal              -- on supplier select, shows savings estimate + GDPR consent
```

### Optimize Page

```
OptimizePage
  StatsRow: appliance count, daily/monthly/annual savings
  Left col: AppliancesList (Zustand) + QuickAdd presets + CustomAdd form
  Right col: OptimizeButton -> ScheduleTimeline + ScheduleDetails
  Empty states: no appliances vs no schedule yet
```

---

## 3. State Management -- Zustand Store

File: `lib/store/settings.ts`. Single store, localStorage persistence.

```pseudocode
STORE "electricity-optimizer-settings"

DEFAULT_STATE:
  region            = "us_ct"
  currentSupplier   = null
  annualUsageKwh    = 10500
  peakDemandKw      = 5
  appliances        = []
  notificationPreferences: { priceAlerts: true, optimalTimes: true, supplierUpdates: false }
  displayPreferences:      { currency: "USD", theme: "system", timeFormat: "12h" }

ACTIONS:
  setRegion(region)                           -> replace region
  setCurrentSupplier(supplier|null)           -> replace currentSupplier
  setAnnualUsage(usage)                       -> replace annualUsageKwh
  setPeakDemand(demand)                       -> replace peakDemandKw
  addAppliance(appliance)                     -> append to appliances
  updateAppliance(id, partial)                -> map + merge matching id
  removeAppliance(id)                         -> filter out by id
  setNotificationPreferences(partial)         -> shallow merge
  setDisplayPreferences(partial)              -> shallow merge
  resetSettings()                             -> restore DEFAULT_STATE

PERSISTENCE: key="electricity-optimizer-settings", localStorage, partialize all data fields
SELECTORS: useRegion, useCurrentSupplier, useAnnualUsage, useAppliances, useCurrency, useTheme
```

---

## 4. API Layer

### Base Client (`lib/api/client.ts`)

```pseudocode
BASE_URL = env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

handleResponse<T>(response):
  IF NOT response.ok: parse JSON for {detail,message}, THROW ApiClientError{message,status,details}
  RETURN response.json()

apiClient: GET(endpoint, params?), POST(endpoint, data?), PUT(endpoint, data?), DELETE(endpoint)
  -- all use JSON Content-Type, construct URL with BASE_URL
```

### Prices API (`lib/api/prices.ts`)

| Function | Endpoint | Defaults | Returns |
|----------|----------|----------|---------|
| `getCurrentPrices` | GET `/prices/current` | region=us_ct | `{prices: CurrentPrice[]}` |
| `getPriceHistory` | GET `/prices/history` | region=us_ct, hours=24 | `{prices: PriceDataPoint[]}` |
| `getPriceForecast` | GET `/prices/forecast` | region=us_ct, hours=24 | `{forecast: PriceForecast[]}` |
| `getOptimalPeriods` | GET `/prices/optimal-periods` | region=us_ct, hours=24 | `{periods: [{start,end,avgPrice}]}` |

### Suppliers API (`lib/api/suppliers.ts`)

| Function | Endpoint | Defaults | Returns |
|----------|----------|----------|---------|
| `getSuppliers` | GET `/suppliers` | region=us_ct, annual_usage? | `{suppliers[]}` |
| `getSupplier` | GET `/suppliers/:id` | -- | `Supplier` |
| `getRecommendation` | POST `/suppliers/recommend` | region=us_ct | `{recommendation}` |
| `compareSuppliers` | POST `/suppliers/compare` | -- | `{comparisons[]}` |
| `initiateSwitch` | POST `/suppliers/switch` | gdprConsent required | `{success, referenceNumber}` |
| `getSwitchStatus` | GET `/suppliers/switch/:ref` | -- | `{status, estimatedCompletionDate}` |

### Optimization API (`lib/api/optimization.ts`)

| Function | Endpoint | Defaults | Returns |
|----------|----------|----------|---------|
| `getOptimalSchedule` | POST `/optimization/schedule` | region? date? | `{schedules[], totalSavings, totalCost}` |
| `getOptimizationResult` | GET `/optimization/result` | region=us_ct | `OptimizationResult` |
| `saveAppliances` | POST `/optimization/appliances` | -- | `{success}` |
| `getAppliances` | GET `/optimization/appliances` | -- | `{appliances[]}` |
| `calculatePotentialSavings` | POST `/optimization/potential-savings` | region=us_ct | `{daily,weekly,monthly,annualSavings}` |

---

## 5. Hooks

### Price Hooks (`lib/hooks/usePrices.ts`) -- all TanStack `useQuery`

```pseudocode
useCurrentPrices(region="us_ct")   key:["prices","current",region]  refetch:60s  stale:55s
usePriceHistory(region, hours=24)  key:["prices","history",region,hours]          stale:60s
usePriceForecast(region, hours=24) key:["prices","forecast",region,hours] refetch:300s stale:180s
useOptimalPeriods(region, hours=24) key:["prices","optimal",region,hours] refetch:300s stale:180s
useRefreshPrices()                 -> invalidates all ["prices"] queries
```

### Supplier Hooks (`lib/hooks/useSuppliers.ts`)

```pseudocode
useSuppliers(region, annualUsage?)            key:["suppliers",region,annualUsage] stale:300s
useSupplier(supplierId)                       key:["supplier",id] enabled:!!id     stale:300s
useSupplierRecommendation(id, usage, region)  key:["recommendation",...] enabled:!!id&&usage>0
useInitiateSwitch()                           useMutation -> invalidates ["suppliers","recommendation"]
useSwitchStatus(ref)                          key:["switch-status",ref] refetch:60s
```

### Optimization Hooks (`lib/hooks/useOptimization.ts`)

```pseudocode
useOptimalSchedule({appliances,region,date})  key:["optimization","schedule",...] enabled:len>0
useOptimizationResult(date, region)           key:["optimization","result",...] enabled:!!date
useAppliances()                               key:["appliances"] stale:300s
useSaveAppliances()                           useMutation -> invalidates ["appliances","optimization"]
usePotentialSavings(appliances, region)       key:["potential-savings",...] enabled:len>0 stale:300s
```

### Realtime Hook (`lib/hooks/useRealtime.ts`)

```pseudocode
useRealtimePrices(region="us_ct", interval=30):
  ON_MOUNT (browser only):
    es = new EventSource(API_URL + "/prices/stream?region=" + region + "&interval=" + interval)
    es.onopen  -> isConnected = true
    es.onmessage -> parse PriceUpdate {region, supplier, price_per_kwh, currency, is_peak, timestamp}
                    SET lastPrice, INVALIDATE ["prices","current",region] + ["prices","history",region]
    es.onerror -> isConnected = false (auto-reconnects)
  ON_UNMOUNT: es.close()
  RETURNS: { isConnected, lastPrice, disconnect }
```

---

## 6. Authentication Flow

### Supabase Auth (`lib/auth/supabase.ts`)

Singleton client with `autoRefreshToken`, `persistSession`, `detectSessionInUrl`.
Tokens stored in localStorage under keys `auth_access_token` / `auth_refresh_token`.

### AuthProvider Initialization (`lib/hooks/useAuth.tsx`)

```pseudocode
ON_MOUNT:
  token = getStoredAccessToken()
  IF token:
    TRY: user = GET /auth/me (Bearer token)
    CATCH: TRY refresh with getStoredRefreshToken() -> re-store + re-fetch user
           CATCH: clearStoredTokens()
  SET isLoading = false
```

### Sign-In (Email/Password)

```pseudocode
signIn(email, password):
  {accessToken, refreshToken} = POST /auth/signin {email, password}
  storeTokens -> getCurrentUser(accessToken) -> SET user -> REDIRECT /dashboard
  ON ERROR: SET error message, re-throw
```

### OAuth (Google/GitHub)

```pseudocode
signInWithGoogle/GitHub():
  {url} = POST /auth/signin/oauth {provider, redirect_url: origin + "/auth/callback"}
  window.location.href = url    // full-page redirect

/auth/callback page:
  hashParams = parse window.location.hash for access_token + refresh_token
  IF error in searchParams: display error
  IF tokens present: storeTokens, verify user, REDIRECT /dashboard
  ELSE: display "No authentication tokens received"
```

### Protected Route Guard

```pseudocode
useRequireAuth(): IF not loading AND not authenticated -> REDIRECT /auth/login
```

---

## 7. Styling & Configuration

### Next.js Config (`next.config.js`)

```pseudocode
output: "standalone"           | reactStrictMode: true
poweredByHeader: false         | compress: true
optimizePackageImports: ["date-fns", "lucide-react", "recharts"]
images: remotePatterns [localhost, *.supabase.co], formats [avif, webp]

SECURITY_HEADERS (all routes):
  X-Frame-Options: DENY | X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()

REWRITES: /api/:path* -> NEXT_PUBLIC_API_URL/:path*  (proxy to FastAPI)
ENV: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL
```

### Format Utilities (`lib/utils/format.ts`)

```pseudocode
formatCurrency(amount, currency="USD"):
  Intl.NumberFormat "en-US" {minFrac:2, maxFrac:2}, prepend symbol {USD:"$", GBP:pound, EUR:euro}
formatDuration(hours): "Xh Ym" | "Xh" | "Ym"
formatTime(dateString, is24Hour=true): date-fns format "HH:mm" or "h:mm a"
formatEnergy(kWh): >= 1000 -> "X.XX MWh", else "X.XX kWh"
formatPricePerKwh, formatPercentage, formatDateTime, formatDate, formatRelativeTime
```

---

## 8. TDD Anchors

### Component Tests

```
TEST "SavingsTracker renders savings"       -> $1.85 in Today, $12.30 in Week, $45.50 in Month
TEST "SavingsTracker streak levels"         -> 3d=bronze, 8d=silver, 15d=gold, 31d=legendary
TEST "SavingsTracker progress cap"          -> monthlySavings=75 (goal=50) -> width=100%
TEST "Dashboard loading skeleton"           -> mock isLoading:true -> testId "dashboard-loading"
TEST "Dashboard current price"              -> mock price:0.22 stable -> "$0.22", "Stable"
TEST "Dashboard decreasing banner"          -> mock trend:decreasing -> "Prices dropping" visible
TEST "Suppliers grid/table toggle"          -> click table btn -> ComparisonTable, click grid -> cards
TEST "Suppliers SwitchWizard opens"         -> click select -> modal visible
TEST "Optimize quick-add appliance"         -> click "Washing Machine" -> appears in list, store.len=1
TEST "Optimize button disabled no appliances" -> empty appliances -> button disabled
TEST "Settings persists to localStorage"    -> change annualUsage=12000 -> persisted in storage key
```

### Hook Tests

```
TEST "useCurrentPrices polls every 60s"     -> refetchInterval=60000
TEST "useRealtimePrices SSE connect"        -> EventSource URL has region=us_ct, onopen->connected
TEST "useRealtimePrices invalidates on msg" -> onmessage -> invalidate ["prices","current","us_ct"]
TEST "useRealtimePrices error graceful"     -> onerror -> isConnected=false, no crash
TEST "useOptimalSchedule disabled empty"    -> appliances=[] -> enabled=false, data=undefined
TEST "useInitiateSwitch cache invalidation" -> onSuccess -> invalidate ["suppliers","recommendation"]
```

### API Layer Tests

```
TEST "apiClient.get query params"           -> params {region:"us_ct"} -> URL has ?region=us_ct
TEST "apiClient non-OK JSON error"          -> 404 {detail:"Not found"} -> ApiClientError
TEST "apiClient non-JSON error"             -> 500 no JSON -> uses statusText
```

### Auth Tests

```
TEST "AuthProvider init from token"         -> stored token -> getCurrentUser -> authenticated
TEST "AuthProvider refresh expired"         -> expired token + valid refresh -> new token stored
TEST "signIn redirects dashboard"           -> success -> router.push("/dashboard")
TEST "signOut clears and redirects"         -> tokens cleared, router.push("/auth/login")
TEST "useRequireAuth redirects"             -> not authenticated -> router.push("/auth/login")
TEST "OAuth callback hash tokens"           -> #access_token=tok -> stored, redirect /dashboard
TEST "OAuth callback error display"         -> ?error=access_denied -> error text + back button
```

### Format Tests

```
TEST "formatCurrency USD"         -> 1234.5 = "$1,234.50", -5.1 = "-$5.10"
TEST "formatDuration"             -> 1.5 = "1h 30m", 2 = "2h", 0.5 = "30m"
TEST "formatEnergy"               -> 1500 = "1.50 MWh", 500 = "500.00 kWh"
```
