# Frontend API Patterns

> Reference for the RateShift frontend API layer. Last updated: 2026-03-25.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Base Client (client.ts)](#base-client-clientts)
  - [Request Flow](#request-flow)
  - [HTTP Methods](#http-methods)
  - [Retry Logic](#retry-logic)
  - [401 Handling and Redirect-Loop Prevention](#401-handling-and-redirect-loop-prevention)
  - [Empty Response Handling](#empty-response-handling)
- [Circuit Breaker (circuit-breaker.ts)](#circuit-breaker-circuit-breakerts)
  - [States](#states)
  - [Configuration](#configuration)
  - [State Transitions](#state-transitions)
  - [Fallback URL](#fallback-url)
- [Environment Configuration (env.ts)](#environment-configuration-envts)
- [Domain API Clients](#domain-api-clients)
- [Error Handling Pattern](#error-handling-pattern)
- [Adding a New API Client](#adding-a-new-api-client)

---

## Architecture Overview

```
Component
  -> React Query Hook (frontend/lib/hooks/*.ts)
    -> Domain API Client (frontend/lib/api/*.ts)
      -> Base API Client (frontend/lib/api/client.ts)
        -> Circuit Breaker (frontend/lib/api/circuit-breaker.ts)
          -> CF Worker Gateway (api.rateshift.app)
            -> Render Backend (origin)
          OR (circuit open)
          -> Render Backend directly (fallback)
```

All API requests flow through a single `apiClient` singleton that handles:
1. URL construction with circuit breaker routing
2. Authentication via httpOnly session cookies (`credentials: 'include'`)
3. Automatic retry with exponential backoff for 5xx/network errors
4. 401 detection and redirect to login with loop protection
5. Circuit breaker state management for CF Worker gateway resilience

---

## Base Client (client.ts)

**File:** `frontend/lib/api/client.ts`

### Request Flow

Every request follows this path:

1. **URL resolution** -- `circuitBreaker.getBaseUrl()` decides whether to use the primary URL (`/api/v1` or `NEXT_PUBLIC_API_URL`) or the fallback URL (`NEXT_PUBLIC_FALLBACK_API_URL`)
2. **Headers** -- `Content-Type: application/json` always. When in fallback mode, adds `X-Fallback-Mode: true`
3. **Credentials** -- All requests include `credentials: 'include'` for httpOnly cookie-based auth
4. **Retry** -- Up to 2 retries with exponential backoff (500ms, 1000ms) for 5xx and network errors
5. **Response handling** -- JSON parsing, 401 redirect, error extraction, circuit breaker state updates

### HTTP Methods

The `apiClient` object exposes five methods, all with the same signature pattern:

```typescript
apiClient.get<T>(endpoint, params?, options?)    // GET with query params
apiClient.post<T>(endpoint, data?, options?)     // POST with JSON body
apiClient.put<T>(endpoint, data?, options?)      // PUT with JSON body
apiClient.patch<T>(endpoint, data?, options?)     // PATCH with JSON body
apiClient.delete<T>(endpoint, data?, options?)   // DELETE with optional body
```

- `endpoint`: Path relative to base URL (e.g., `/prices/current`)
- `params`: For GET -- `Record<string, string | number | boolean | (string | number | boolean)[]>`, serialized to URL search params. Array values are appended as multiple params with the same key
- `data`: For POST/PUT/PATCH/DELETE -- any JSON-serializable value
- `options`: `{ signal?: AbortSignal }` for request cancellation

All methods return `Promise<T>` where `T` is the expected response type.

### Retry Logic

```
MAX_RETRIES = 2
RETRY_BASE_MS = 500

Attempt 0: immediate
Attempt 1: wait 500ms
Attempt 2: wait 1000ms (500 * 2^1)
```

**Retryable conditions:**
- `ApiClientError` with status >= 500
- `TypeError` (network failures -- fetch throws TypeError when the network is unreachable)

**Non-retryable conditions:**
- `AbortError` (immediately re-thrown, no retries, no circuit breaker tracking)
- Any 4xx error (thrown immediately)

**Circuit breaker tracking:** Gateway errors (502, 503, 1027) are recorded as circuit breaker failures, but only after all retries are exhausted.

### 401 Handling and Redirect-Loop Prevention

When a 401 response is received:

1. **Auth page suppression** -- If the current path starts with `/auth/`, no redirect occurs (prevents loops on login/signup pages)
2. **Deduplication** -- A `redirectInFlight` flag ensures only one redirect can be in progress at a time
3. **Counter-based safety valve** -- A `sessionStorage` counter tracks consecutive 401 redirects within a 10-second window. After 2 redirects, further 401s are suppressed
4. **Counter auto-expiry** -- The counter resets after 10 seconds of inactivity, preventing permanent lock-out
5. **Callback URL preservation** -- The current path is preserved as `callbackUrl` in the login URL. If a `callbackUrl` already exists in the current URL, it is reused (prevents nesting)
6. **Same-origin validation** -- `isSafeRedirect()` validates callback URLs to prevent open redirect attacks

The `handle401Redirect()` function is exported so non-apiClient code (e.g., the agent SSE handler) can use the same redirect-loop prevention logic.

On any successful response, the redirect counter is reset.

### Empty Response Handling

Responses with status 204 (No Content), 205 (Reset Content), or `content-length: 0` are returned as `undefined` instead of attempting JSON parsing.

---

## Circuit Breaker (circuit-breaker.ts)

**File:** `frontend/lib/api/circuit-breaker.ts`

Implements the circuit breaker pattern for API gateway resilience. When the Cloudflare Worker gateway returns repeated 502/503/1027 errors, the circuit opens and requests automatically fall back to calling the Render backend directly.

### States

| State | Behavior |
|-------|----------|
| `CLOSED` | Normal operation. Requests go to the primary URL (CF Worker gateway) |
| `OPEN` | Gateway is down. Requests go to the fallback URL (Render backend directly) |
| `HALF_OPEN` | Probing primary after cooldown. Next request tests whether the gateway has recovered |

### Configuration

```typescript
const circuitBreaker = new CircuitBreaker({
  failureThreshold: 3,       // 3 consecutive gateway errors to open
  resetTimeoutMs: 30_000,    // 30s before probing primary again
  fallbackUrl: FALLBACK_API_URL,  // Direct Render backend URL
  primaryUrl: API_URL,            // CF Worker gateway URL
  halfOpenSuccessThreshold: 3,    // 3 consecutive successes to close (default)
});
```

### State Transitions

```
CLOSED --[3 failures]--> OPEN --[30s timeout]--> HALF_OPEN
                                                    |
                          OPEN <--[any failure]-----+
                                                    |
                         CLOSED <--[3 successes]----+
```

**Gateway error codes:** 502 (Bad Gateway), 503 (Service Unavailable), 1027 (Cloudflare Worker error)

**Key behaviors:**
- **CLOSED -> OPEN**: After `failureThreshold` (3) consecutive gateway errors
- **OPEN -> HALF_OPEN**: Automatic transition when `resetTimeoutMs` (30s) has elapsed since the last failure (lazy evaluation in the `state` getter)
- **HALF_OPEN -> CLOSED**: After `halfOpenSuccessThreshold` (3) consecutive successful probe requests
- **HALF_OPEN -> OPEN**: On any single failure during probing, resets the success counter

**Success recording:**
- In CLOSED state: resets failure counter (normal operation)
- In HALF_OPEN state: accumulates consecutive successes; only closes circuit after reaching the threshold

### Fallback URL

The fallback URL bypasses the CF Worker and sends requests directly to the Render backend. This is configured via the `NEXT_PUBLIC_FALLBACK_API_URL` environment variable.

When in fallback mode:
- `circuitBreaker.isFallbackMode()` returns `true`
- An `X-Fallback-Mode: true` header is added to all requests
- The backend can detect this header for logging/metrics purposes

If no fallback URL is configured (empty string), the circuit breaker still tracks state but always returns the primary URL.

---

## Environment Configuration (env.ts)

**File:** `frontend/lib/config/env.ts`

All public environment variables are centralized here with sensible defaults and production validation.

| Variable | Export | Default | Description |
|----------|--------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `API_URL` | `/api/v1` | Full API base URL including path prefix. In development, relative path is proxied by Next.js rewrites |
| `NEXT_PUBLIC_FALLBACK_API_URL` | `FALLBACK_API_URL` | `''` (empty) | Direct Render backend URL for circuit breaker fallback. Example: `https://electricity-optimizer.onrender.com/api/v1` |
| `NEXT_PUBLIC_APP_URL` | `APP_URL` | `http://localhost:3000` | Public-facing app URL for Better Auth trusted origins |
| `NEXT_PUBLIC_SITE_URL` | `SITE_URL` | `https://rateshift.app` | Canonical URL for SEO metadata |
| `NEXT_PUBLIC_CLARITY_PROJECT_ID` | `CLARITY_PROJECT_ID` | `''` | Microsoft Clarity project ID |
| `NEXT_PUBLIC_ONESIGNAL_APP_ID` | `ONESIGNAL_APP_ID` | `''` | OneSignal web push app ID |

Additionally exports: `API_ORIGIN` (scheme + host without path, derived from `API_URL`), `IS_PRODUCTION`, `IS_TEST`, `IS_DEV`.

**Production behavior:** The `env()` helper throws immediately on missing required variables in production, failing the build or server start fast.

---

## Domain API Clients

All domain clients are in `frontend/lib/api/` and follow the same pattern: import `apiClient` from `./client`, define request/response types, export async functions.

| File | Description | Endpoints |
|------|-------------|-----------|
| `affiliate.ts` | Affiliate click tracking | `POST /affiliate/click` |
| `agent.ts` | RateShift AI assistant (SSE streaming, async tasks, usage) | `POST /agent/query`, `POST /agent/task`, `GET /agent/task/:id`, `GET /agent/usage` |
| `alerts.ts` | Price alert CRUD and trigger history | `GET/POST /alerts`, `PUT/DELETE /alerts/:id`, `GET /alerts/history` |
| `cca.ts` | Community Choice Aggregation programs | `GET /cca/detect`, `GET /cca/compare/:id`, `GET /cca/info/:id`, `GET /cca/programs` |
| `circuit-breaker.ts` | Circuit breaker class (not an API client) | -- |
| `client.ts` | Base HTTP client singleton | -- |
| `community-solar.ts` | Community solar programs and savings | `GET /community-solar/programs`, `GET /community-solar/savings`, `GET /community-solar/program/:id`, `GET /community-solar/states` |
| `community.ts` | Community posts, voting, reporting, stats | `GET/POST /community/posts`, `PUT /community/posts/:id`, `POST /community/posts/:id/vote`, `POST /community/posts/:id/report`, `GET /community/stats` |
| `export.ts` | Rate data export (JSON/CSV) | `GET /export/rates`, `GET /export/types` |
| `forecast.ts` | Multi-utility rate forecasting | `GET /forecast/:utilityType`, `GET /forecast` |
| `gas-rates.ts` | Natural gas rates, history, stats, comparison | `GET /rates/natural-gas/`, `GET /rates/natural-gas/history`, `GET /rates/natural-gas/stats`, `GET /rates/natural-gas/deregulated-states`, `GET /rates/natural-gas/compare` |
| `heating-oil.ts` | Heating oil prices, history, dealers | `GET /rates/heating-oil`, `GET /rates/heating-oil/history`, `GET /rates/heating-oil/dealers`, `GET /rates/heating-oil/compare` |
| `neighborhood.ts` | Neighborhood rate comparison | `GET /neighborhood/compare` |
| `notifications.ts` | In-app notification CRUD | `GET /notifications`, `GET /notifications/count`, `PUT /notifications/:id/read` |
| `optimization.ts` | Schedule optimization and appliances | `POST /optimization/schedule`, `GET /optimization/result`, `POST/GET /optimization/appliances`, `POST /optimization/potential-savings` |
| `portal.ts` | Portal-based utility connections | `POST /connections/portal`, `POST /connections/portal/:id/scrape` |
| `prices.ts` | Electricity prices (current, history, forecast, compare, optimal) | `GET /prices/current`, `GET /prices/history`, `GET /prices/forecast`, `GET /prices/compare`, `GET /prices/optimal-periods` |
| `profile.ts` | User profile CRUD | `GET/PUT /users/profile` |
| `propane.ts` | Propane prices, history, comparison, timing | `GET /rates/propane`, `GET /rates/propane/history`, `GET /rates/propane/compare`, `GET /rates/propane/timing` |
| `rate-changes.ts` | Detected rate changes and alert preferences | `GET /rate-changes`, `GET/PUT /rate-changes/preferences` |
| `reports.ts` | Optimization reports | `GET /reports/optimization` |
| `savings.ts` | Combined savings across utility types | `GET /savings/combined` |
| `suppliers.ts` | Supplier listing, comparison, switching, user management | `GET /suppliers`, `GET /suppliers/:id`, `POST /suppliers/recommend`, `POST /suppliers/compare`, `POST /suppliers/switch`, `GET /suppliers/switch/:ref`, `GET/PUT/DELETE /user/supplier`, `POST /user/supplier/link`, `GET /user/supplier/accounts`, `DELETE /user/supplier/accounts/:id` |
| `utility-discovery.ts` | Utility availability by state | `GET /utility-discovery/discover`, `GET /utility-discovery/completion` |
| `water.ts` | Water rates, benchmarks, tips | `GET /rates/water`, `GET /rates/water/benchmark`, `GET /rates/water/tips` |

---

## Error Handling Pattern

Errors propagate through three layers:

### Layer 1: API Client (`client.ts`)

```
fetch() -> handleResponse() -> throws ApiClientError
```

`ApiClientError` includes:
- `message`: Human-readable error from response body (`detail` or `message` field)
- `status`: HTTP status code
- `details`: Full error response body (for structured errors)

Special cases:
- **401**: Triggers `handle401Redirect()` and returns a never-resolving promise (stops further processing)
- **AbortError**: Re-thrown immediately without retries or circuit breaker tracking

### Layer 2: Domain API Client (`api/*.ts`)

Most domain clients pass errors through without modification. Some add domain-specific handling:

```typescript
// connections: convert 403 to upgrade prompt
if (err instanceof ApiClientError && err.status === 403) {
  throw Object.assign(new Error('upgrade'), { status: 403 });
}

// agent: 401 uses handle401Redirect() for SSE (non-apiClient) requests
if (response.status === 401) {
  if (handle401Redirect()) return;
}
```

### Layer 3: React Query Hook (`hooks/*.ts`)

TanStack Query catches thrown errors and exposes them via `error` in the query result. Components access errors through:

```tsx
const { data, error, isLoading } = usePrices(region);

if (error) {
  // error is the ApiClientError instance
  if (error.status === 403) return <UpgradePrompt />;
  return <ErrorMessage message={error.message} />;
}
```

**Retry configuration** is hook-specific:
- Most hooks use TanStack Query's default retry (3 retries with exponential backoff)
- `useConnections`, `useAgentStatus`: `retry: false` (no TanStack retry; apiClient still retries 5xx)
- `useSavingsSummary`: `retry: 1` (single retry)

---

## Adding a New API Client

### Step 1: Create the domain API client

Create `frontend/lib/api/my-feature.ts`:

```typescript
import { apiClient } from './client'

// Define request/response types
export interface MyFeatureResponse {
  items: MyFeatureItem[]
  total: number
}

export interface CreateMyFeatureRequest {
  name: string
  value: number
}

// Export async functions
export async function getMyFeatures(
  params?: { region?: string },
  signal?: AbortSignal,
): Promise<MyFeatureResponse> {
  const query: Record<string, string> = {}
  if (params?.region) query.region = params.region
  return apiClient.get<MyFeatureResponse>('/my-feature', query, { signal })
}

export async function createMyFeature(
  body: CreateMyFeatureRequest,
): Promise<MyFeatureItem> {
  return apiClient.post<MyFeatureItem>('/my-feature', body)
}
```

**Key patterns:**
- Always accept `signal?: AbortSignal` on GET functions (for React Query cancellation)
- Build query params as `Record<string, string>` -- all values must be strings
- Use `apiClient.get<T>()` with explicit generic for type inference
- Export both the types and the functions

### Step 2: Create the React Query hook

Create `frontend/lib/hooks/useMyFeature.ts`:

```typescript
'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getMyFeatures,
  createMyFeature,
  type CreateMyFeatureRequest,
} from '@/lib/api/my-feature'

export function useMyFeatures(region: string | null | undefined) {
  return useQuery({
    queryKey: ['my-feature', region],
    queryFn: ({ signal }) => getMyFeatures({ region: region! }, signal),
    enabled: !!region,
    staleTime: 300_000, // 5 minutes
  })
}

export function useCreateMyFeature() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: CreateMyFeatureRequest) => createMyFeature(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-feature'] })
    },
  })
}
```

**Key patterns:**
- Add `'use client'` directive at the top
- Pass `{ signal }` from `queryFn` to the API function for automatic cancellation
- Use `enabled` to gate queries on required parameters
- Destructure primitive values into `queryKey` to avoid reference-equality issues
- Invalidate related queries on mutation success
- Choose `staleTime` based on data freshness requirements:
  - Real-time data: 30-60s (prices, notifications)
  - Moderate data: 5min (suppliers, savings)
  - Slow-changing data: 1-24h (deregulated states, water tips)
  - Static data: 7d+ (export types)

### Step 3: Use in a component

```tsx
'use client'

import { useMyFeatures, useCreateMyFeature } from '@/lib/hooks/useMyFeature'
import { useSettingsStore } from '@/lib/store/settings'

export function MyFeaturePage() {
  const region = useSettingsStore((s) => s.region)
  const { data, isLoading, error } = useMyFeatures(region)
  const createFeature = useCreateMyFeature()

  if (isLoading) return <Skeleton />
  if (error) return <ErrorCard message={error.message} />

  return (
    <div>
      {data?.items.map(item => <Card key={item.id} item={item} />)}
      <button onClick={() => createFeature.mutate({ name: 'New', value: 42 })}>
        Create
      </button>
    </div>
  )
}
```
