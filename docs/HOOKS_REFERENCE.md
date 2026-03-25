# Frontend Hooks Reference

> Auto-generated from source files in `frontend/lib/hooks/`. Last updated: 2026-03-25.

All hooks use [TanStack React Query](https://tanstack.com/query) unless otherwise noted. Query hooks return `UseQueryResult<T>` (with `data`, `isLoading`, `error`, etc.). Mutation hooks return `UseMutationResult<T>`.

---

## Table of Contents

- [Core](#core)
  - [useAuth](#useauth)
  - [useRequireAuth](#userequireauth)
  - [useProfile](#useprofile)
  - [useUpdateProfile](#useupdateprofile)
  - [useNotifications](#usenotifications)
  - [useNotificationCount](#usenotificationcount)
  - [useMarkRead](#usemarkread)
  - [useMarkAllRead](#usemarkallread)
- [Pricing](#pricing)
  - [useCurrentPrices](#usecurrentprices)
  - [usePriceHistory](#usepricehistory)
  - [usePriceForecast](#usepriceforecast)
  - [useOptimalPeriods](#useoptimalperiods)
  - [useRefreshPrices](#userefreshprices)
  - [useForecast](#useforecast)
  - [useForecastTypes](#useforecasttypes)
  - [useSavingsSummary](#usesavingssummary)
  - [useRateChanges](#useratechanges)
  - [useAlertPreferences](#usealertpreferences)
  - [useUpsertAlertPreference](#useupsertalertpreference)
  - [useOptimalSchedule](#useoptimalschedule)
  - [useOptimizationResult](#useoptimizationresult)
  - [useSavedAppliances](#usesavedappliances)
  - [useSaveAppliances](#usesaveappliances)
  - [usePotentialSavings](#usepotentialsavings)
- [Connections](#connections)
  - [useConnections](#useconnections)
- [Utilities](#utilities)
  - [useGasRates](#usegasrates)
  - [useGasHistory](#usegashistory)
  - [useGasStats](#usegasstats)
  - [useDeregulatedGasStates](#usederegulatedgasstates)
  - [useGasSupplierComparison](#usegassuppliercomparison)
  - [useHeatingOilPrices](#useheatingoilprices)
  - [useHeatingOilHistory](#useheatingoilhistory)
  - [useHeatingOilDealers](#useheatingoildealers)
  - [useHeatingOilComparison](#useheatingoilcomparison)
  - [usePropanePrices](#usepropaneprices)
  - [usePropaneHistory](#usepropanehistory)
  - [usePropaneComparison](#usepropanecomparison)
  - [usePropaneTiming](#usepropanetiming)
  - [useWaterRates](#usewaterrates)
  - [useWaterBenchmark](#usewaterbenchmark)
  - [useWaterTips](#usewatertips)
  - [useUtilityDiscovery](#useutilitydiscovery)
  - [useUtilityCompletion](#useutilitycompletion)
- [Community](#community)
  - [useCommunityPosts](#usecommunityposts)
  - [useCreatePost](#usecreatepost)
  - [useToggleVote](#usetogglevote)
  - [useReportPost](#usereportpost)
  - [useCommunityStats](#usecommunitystats)
  - [useCommunitySolarPrograms](#usecommunitySolarprograms)
  - [useCommunitySolarSavings](#usecommunitySolarsavings)
  - [useCommunitySolarProgram](#usecommunitySolarprogram)
  - [useCommunitySolarStates](#usecommunitySolarstates)
  - [useCCADetect](#useccadetect)
  - [useCCACompare](#useccacompare)
  - [useCCAInfo](#useccainfo)
  - [useCCAPrograms](#useccaprograms)
  - [useNeighborhoodComparison](#useneighborhoodcomparison)
  - [useCombinedSavings](#usecombinedsavings)
- [AI/Agent](#aiagent)
  - [useAgentQuery](#useagentquery)
  - [useAgentStatus](#useagentstatus)
- [Analytics](#analytics)
  - [useOptimizationReport](#useoptimizationreport)
  - [useExportRates](#useexportrates)
  - [useExportTypes](#useexporttypes)
  - [useDiagramList](#usediagramlist)
  - [useDiagram](#usediagram)
  - [useSaveDiagram](#usesavediagram)
  - [useCreateDiagram](#usecreatediagram)
- [Alerts](#alerts)
  - [useAlerts](#usealerts)
  - [useAlertHistory](#usealerthistory)
  - [useCreateAlert](#usecreatealert)
  - [useUpdateAlert](#useupdatealert)
  - [useDeleteAlert](#usedeletealert)
- [Suppliers](#suppliers)
  - [useSuppliers](#usesuppliers)
  - [useSupplier](#usesupplier)
  - [useSupplierRecommendation](#usesupplierrecommendation)
  - [useCompareSuppliers](#usecomparesuppliers)
  - [useInitiateSwitch](#useinitiateswitch)
  - [useSwitchStatus](#useswitchstatus)
  - [useUserSupplier](#useusersupplier)
  - [useSetSupplier](#usesetsupplier)
  - [useRemoveSupplier](#useremovesupplier)
  - [useLinkAccount](#uselinkaccount)
  - [useUserSupplierAccounts](#useusersupplieraccounts)
  - [useUnlinkAccount](#useunlinkaccount)
- [Location](#location)
  - [useGeocoding](#usegeocoding)
- [Real-time](#real-time)
  - [useRealtimePrices](#userealtimeprices)
  - [useRealtimeOptimization](#userealtimeoptimization)
  - [useRealtimeSubscription](#userealtimesubscription)

---

## Core

### useAuth

**File:** `frontend/lib/hooks/useAuth.tsx`

Provides authentication state and methods via a React Context backed by Better Auth. Session management uses httpOnly cookies (no localStorage tokens). Must be used within an `<AuthProvider>`.

**Parameters:** None

**Returns:** `AuthContextType`

| Field | Type | Description |
|-------|------|-------------|
| `user` | `AuthUser \| null` | Current user (id, email, name, emailVerified, createdAt) |
| `isLoading` | `boolean` | True while session is being resolved |
| `isAuthenticated` | `boolean` | True when `user` is non-null |
| `error` | `string \| null` | Last auth error message |
| `profileFetchFailed` | `boolean` | True when backend profile fetch failed (prevents false onboarding redirects) |
| `signIn` | `(email, password) => Promise<void>` | Email/password sign-in |
| `signUp` | `(email, password, name?) => Promise<void>` | Email/password registration |
| `signOut` | `() => Promise<void>` | Sign out and clear all state |
| `signInWithGoogle` | `() => Promise<void>` | OAuth via Google |
| `signInWithGitHub` | `() => Promise<void>` | OAuth via GitHub |
| `sendMagicLink` | `(email) => Promise<void>` | Passwordless magic link |
| `clearError` | `() => void` | Clear the error state |

```tsx
const { user, isLoading, signIn, signOut } = useAuth();

if (isLoading) return <Spinner />;
if (!user) return <LoginPrompt />;
return <Dashboard user={user} onLogout={signOut} />;
```

### useRequireAuth

**File:** `frontend/lib/hooks/useAuth.tsx`

Wrapper around `useAuth` that redirects to `/auth/login` when the user is not authenticated.

**Parameters:** None

**Returns:** `AuthContextType` (same as `useAuth`)

```tsx
const { user } = useRequireAuth();
// Safe to assume user is non-null after loading completes
```

### useProfile

**File:** `frontend/lib/hooks/useProfile.ts`

Fetches the authenticated user's profile from the backend. On success, syncs the backend region into the Zustand settings store so all hooks/components see the correct region.

**Parameters:** None

**Returns:** `UseQueryResult<UserProfile>` -- fields: email, name, region, utility_types, current_supplier_id, annual_usage_kwh, onboarding_completed

**Query Key:** `['user-profile']` | **Stale Time:** 60s

```tsx
const { data: profile, isLoading } = useProfile();
if (profile?.region) {
  console.log(`User region: ${profile.region}`);
}
```

### useUpdateProfile

**File:** `frontend/lib/hooks/useProfile.ts`

Mutation hook for updating the user's profile. On success, updates the `['user-profile']` query cache and syncs region to Zustand.

**Parameters (mutationFn):** `UpdateProfileData` -- optional fields: name, region, utility_types, current_supplier_id, annual_usage_kwh, onboarding_completed

**Returns:** `UseMutationResult<UserProfile, Error, UpdateProfileData>`

```tsx
const updateProfile = useUpdateProfile();
updateProfile.mutate({ region: "NY", onboarding_completed: true });
```

### useNotifications

**File:** `frontend/lib/hooks/useNotifications.ts`

Fetches the full list of unread notifications. Intended for use when the notification panel is open.

**Parameters:** None

**Returns:** `UseQueryResult<GetNotificationsResponse>` -- `{ notifications: Notification[], total: number }`

**Query Key:** `['notifications']` | **Stale Time:** 30s

```tsx
const { data } = useNotifications();
return data?.notifications.map(n => <NotificationItem key={n.id} notification={n} />);
```

### useNotificationCount

**File:** `frontend/lib/hooks/useNotifications.ts`

Polls the unread notification count every 120 seconds. Used for the bell badge. Pauses polling when the browser tab is hidden.

**Parameters:** None

**Returns:** `UseQueryResult<GetNotificationCountResponse>` -- `{ unread: number }`

**Query Key:** `['notifications', 'count']` | **Stale Time:** 60s | **Refetch Interval:** 120s

```tsx
const { data } = useNotificationCount();
return <BellIcon badge={data?.unread ?? 0} />;
```

### useMarkRead

**File:** `frontend/lib/hooks/useNotifications.ts`

Mutation to mark a single notification as read. Invalidates both the notification list and count queries.

**Parameters (mutationFn):** `id: string`

**Returns:** `UseMutationResult`

```tsx
const markRead = useMarkRead();
markRead.mutate(notification.id);
```

### useMarkAllRead

**File:** `frontend/lib/hooks/useNotifications.ts`

Mutation to mark all unread notifications as read (client-side batch). Invalidates both notification list and count queries.

**Parameters (mutationFn):** None

**Returns:** `UseMutationResult`

```tsx
const markAllRead = useMarkAllRead();
<button onClick={() => markAllRead.mutate()}>Mark all read</button>
```

---

## Pricing

### useCurrentPrices

**File:** `frontend/lib/hooks/usePrices.ts`

Fetches current electricity prices for a region. Returns `ApiCurrentPriceResponse` (snake_case); use `normalisePriceResponse()` to convert to camelCase for UI components.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `region` | `string \| null \| undefined` | Region code; query disabled when falsy |

**Returns:** `UseQueryResult<ApiCurrentPriceResponse>`

**Query Key:** `['prices', 'current', region]` | **Stale Time:** 55s | **Refetch Interval:** 60s

```tsx
const { data } = useCurrentPrices(region);
```

### usePriceHistory

**File:** `frontend/lib/hooks/usePrices.ts`

Fetches paginated historical electricity prices.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `region` | `string \| null \| undefined` | -- | Region code |
| `hours` | `number` | `24` | Converted to days internally |
| `enabled` | `boolean` | `true` | Gate for waterfall staggering |

**Returns:** `UseQueryResult<ApiPriceHistoryResponse>`

**Query Key:** `['prices', 'history', region, days]` | **Stale Time:** 60s

```tsx
const { data } = usePriceHistory(region, 48, !!currentPrices);
```

### usePriceForecast

**File:** `frontend/lib/hooks/usePrices.ts`

Fetches ML-generated price forecast. Requires Pro tier.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `region` | `string \| null \| undefined` | -- | Region code |
| `hours` | `number` | `24` | Forecast horizon |
| `enabled` | `boolean` | `true` | Gate for waterfall staggering |

**Returns:** `UseQueryResult<ApiPriceForecastResponse>`

**Query Key:** `['prices', 'forecast', region, hours]` | **Stale Time:** 3min | **Refetch Interval:** 5min

```tsx
const { data: forecast } = usePriceForecast(region, 24);
```

### useOptimalPeriods

**File:** `frontend/lib/hooks/usePrices.ts`

Fetches low-cost windows for energy usage in the next N hours.

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `region` | `string \| null \| undefined` | -- |
| `hours` | `number` | `24` |

**Returns:** `UseQueryResult<{ periods: Array<{ start, end, avgPrice }> }>`

**Query Key:** `['prices', 'optimal', region, hours]` | **Stale Time:** 3min | **Refetch Interval:** 5min

```tsx
const { data } = useOptimalPeriods(region, 24);
data?.periods.forEach(p => console.log(p.start, p.end, p.avgPrice));
```

### useRefreshPrices

**File:** `frontend/lib/hooks/usePrices.ts`

Returns a memoized callback that invalidates all price queries. No automatic fetching.

**Parameters:** None

**Returns:** `() => void`

```tsx
const refresh = useRefreshPrices();
<button onClick={refresh}>Refresh Prices</button>
```

### useForecast

**File:** `frontend/lib/hooks/useForecast.ts`

Fetches a rate forecast for any utility type (electricity, gas, propane, etc.).

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `utilityType` | `string \| undefined` | Utility type key; query disabled when falsy |
| `state` | `string \| undefined` | State code (optional) |
| `horizonDays` | `number \| undefined` | Forecast horizon in days (optional) |

**Returns:** `UseQueryResult<ForecastResponse>` -- includes current_rate, forecasted_rate, trend, confidence, model, r_squared

**Query Key:** `['forecast', utilityType, state, horizonDays]` | **Stale Time:** 30min

```tsx
const { data } = useForecast("electricity", "NY", 30);
```

### useForecastTypes

**File:** `frontend/lib/hooks/useForecast.ts`

Fetches the list of utility types that support forecasting.

**Parameters:** None

**Returns:** `UseQueryResult<ForecastTypesResponse>` -- `{ supported_types, description }`

**Query Key:** `['forecast', 'types']` | **Stale Time:** 24h

```tsx
const { data } = useForecastTypes();
data?.supported_types.forEach(t => console.log(t));
```

### useSavingsSummary

**File:** `frontend/lib/hooks/useSavings.ts`

Fetches the authenticated user's savings summary. Gracefully returns undefined when not authenticated (401).

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `enabled` | `boolean` | `true` |

**Returns:** `UseQueryResult<SavingsSummary>` -- total, weekly, monthly, streak_days, currency

**Query Key:** `['savings', 'summary']` | **Stale Time:** 5min

```tsx
const { data } = useSavingsSummary();
console.log(`Monthly savings: $${data?.monthly}`);
```

### useRateChanges

**File:** `frontend/lib/hooks/useRateChanges.ts`

Fetches recent rate changes, optionally filtered by utility type, region, days, or limit.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `params` | `{ utility_type?, region?, days?, limit? }` | Optional filters |

**Returns:** `UseQueryResult<GetRateChangesResponse>` -- `{ changes: RateChange[], total }`

**Query Key:** `['rate-changes', utility_type, region, days, limit]` | **Stale Time:** 5min

```tsx
const { data } = useRateChanges({ region: "NY", utility_type: "electricity" });
```

### useAlertPreferences

**File:** `frontend/lib/hooks/useRateChanges.ts`

Fetches the user's per-utility alert preferences.

**Parameters:** None

**Returns:** `UseQueryResult<GetAlertPreferencesResponse>` -- `{ preferences: AlertPreference[] }`

**Query Key:** `['alert-preferences']` | **Stale Time:** 60s

### useUpsertAlertPreference

**File:** `frontend/lib/hooks/useRateChanges.ts`

Mutation to create or update a per-utility alert preference. Invalidates `['alert-preferences']`.

**Parameters (mutationFn):** `UpsertPreferenceRequest` -- utility_type, enabled?, channels?, cadence?

**Returns:** `UseMutationResult<AlertPreference>`

### useOptimalSchedule

**File:** `frontend/lib/hooks/useOptimization.ts`

Computes the optimal usage schedule for a set of appliances, region, and date.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `request` | `GetOptimalScheduleRequest` | `{ appliances, region?, date? }` |

**Returns:** `UseQueryResult<GetOptimalScheduleResponse>` -- schedules, totalSavings, totalCost

**Query Key:** `['optimization', 'schedule', applianceIds, region, date]` | **Stale Time:** 3min | **Enabled:** when appliances array is non-empty

```tsx
const { data } = useOptimalSchedule({ appliances: myAppliances, region: "CA" });
```

### useOptimizationResult

**File:** `frontend/lib/hooks/useOptimization.ts`

Fetches the optimization result for a specific date and region.

**Parameters:**
| Param | Type |
|-------|------|
| `date` | `string` |
| `region` | `string \| null \| undefined` |

**Returns:** `UseQueryResult<OptimizationResult>`

**Query Key:** `['optimization', 'result', date, region]` | **Stale Time:** 60s

### useSavedAppliances

**File:** `frontend/lib/hooks/useOptimization.ts`

Fetches the user's persisted appliance list from the backend (distinct from the local Zustand store).

**Parameters:** None

**Returns:** `UseQueryResult<{ appliances: Appliance[] }>`

**Query Key:** `['appliances']` | **Stale Time:** 5min

### useSaveAppliances

**File:** `frontend/lib/hooks/useOptimization.ts`

Mutation to persist the user's appliance list. Invalidates `['appliances']` and `['optimization']` queries.

**Parameters (mutationFn):** `Appliance[]`

**Returns:** `UseMutationResult<{ success: boolean }>`

```tsx
const save = useSaveAppliances();
save.mutate(appliances);
```

### usePotentialSavings

**File:** `frontend/lib/hooks/useOptimization.ts`

Calculates potential savings for a set of appliances and region. Uses `JSON.stringify` for stable query key identity.

**Parameters:**
| Param | Type |
|-------|------|
| `appliances` | `Appliance[]` |
| `region` | `string \| null \| undefined` |

**Returns:** `UseQueryResult<{ dailySavings, weeklySavings, monthlySavings, annualSavings }>`

**Query Key:** `['potential-savings', stableAppliancesKey, region]` | **Stale Time:** 5min

---

## Connections

### useConnections

**File:** `frontend/lib/hooks/useConnections.ts`

Fetches the user's utility connections. Maps backend `connection_type` to frontend `method` for compatibility. Throws a special `{ status: 403 }` error on 403 (tier upgrade required).

**Parameters:** None

**Returns:** `UseQueryResult<ConnectionsResponse>` -- `{ connections: Connection[] }`

**Query Key:** `['connections']` | **Stale Time:** 30s | **Retry:** disabled

```tsx
const { data, error } = useConnections();
if (error?.status === 403) return <UpgradePrompt />;
```

---

## Utilities

### useGasRates

**File:** `frontend/lib/hooks/useGasRates.ts`

Fetches current natural gas rates for a region.

**Parameters:**
| Param | Type |
|-------|------|
| `region` | `string \| null \| undefined` |
| `limit` | `number \| undefined` |

**Returns:** `UseQueryResult<GasRatesResponse>` -- region, is_deregulated, prices[]

**Query Key:** `['gas-rates', region, limit]` | **Stale Time:** 5min

### useGasHistory

**File:** `frontend/lib/hooks/useGasRates.ts`

Fetches natural gas price history for a region over a given number of days.

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `region` | `string \| null \| undefined` | -- |
| `days` | `number` | `30` |

**Returns:** `UseQueryResult<GasHistoryResponse>`

**Query Key:** `['gas-rates', 'history', region, days]` | **Stale Time:** 5min

### useGasStats

**File:** `frontend/lib/hooks/useGasRates.ts`

Fetches aggregate statistics (avg, min, max) for natural gas in a region.

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `region` | `string \| null \| undefined` | -- |
| `days` | `number` | `7` |

**Returns:** `UseQueryResult<GasStatsResponse>`

**Query Key:** `['gas-rates', 'stats', region, days]` | **Stale Time:** 5min

### useDeregulatedGasStates

**File:** `frontend/lib/hooks/useGasRates.ts`

Fetches the list of states with deregulated natural gas markets. No parameters required.

**Parameters:** None

**Returns:** `UseQueryResult<GasDeregulatedStatesResponse>` -- `{ count, states[] }`

**Query Key:** `['gas-rates', 'deregulated-states']` | **Stale Time:** 1h

### useGasSupplierComparison

**File:** `frontend/lib/hooks/useGasRates.ts`

Compares natural gas suppliers in a region to find the cheapest option.

**Parameters:**
| Param | Type |
|-------|------|
| `region` | `string \| null \| undefined` |

**Returns:** `UseQueryResult<GasCompareResponse>` -- suppliers[], cheapest

**Query Key:** `['gas-rates', 'compare', region]` | **Stale Time:** 5min

### useHeatingOilPrices

**File:** `frontend/lib/hooks/useHeatingOil.ts`

Fetches heating oil prices, optionally filtered by state.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<HeatingOilPricesResponse>` -- prices[], tracked_states[]

**Query Key:** `['heating-oil', 'prices', state]` | **Stale Time:** 1h

### useHeatingOilHistory

**File:** `frontend/lib/hooks/useHeatingOil.ts`

Fetches heating oil price history for a state over a number of weeks.

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `state` | `string \| undefined` | -- |
| `weeks` | `number \| undefined` | -- |

**Returns:** `UseQueryResult<HeatingOilHistoryResponse>` -- history[], comparison

**Query Key:** `['heating-oil', 'history', state, weeks]` | **Stale Time:** 1h

### useHeatingOilDealers

**File:** `frontend/lib/hooks/useHeatingOil.ts`

Fetches heating oil dealers for a state.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<HeatingOilDealersResponse>` -- `{ state, count, dealers[] }`

**Query Key:** `['heating-oil', 'dealers', state]` | **Stale Time:** 24h

### useHeatingOilComparison

**File:** `frontend/lib/hooks/useHeatingOil.ts`

Compares a state's heating oil price against the national average with cost estimates.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<HeatingOilComparison>` -- price_per_gallon, national_avg, difference_pct, estimated costs

**Query Key:** `['heating-oil', 'comparison', state]` | **Stale Time:** 1h

### usePropanePrices

**File:** `frontend/lib/hooks/usePropane.ts`

Fetches propane prices, optionally filtered by state.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<PropanePricesResponse>` -- prices[], tracked_states[]

**Query Key:** `['propane', 'prices', state]` | **Stale Time:** 1h

### usePropaneHistory

**File:** `frontend/lib/hooks/usePropane.ts`

Fetches propane price history for a state.

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `state` | `string \| undefined` | -- |
| `weeks` | `number \| undefined` | -- |

**Returns:** `UseQueryResult<PropaneHistoryResponse>`

**Query Key:** `['propane', 'history', state, weeks]` | **Stale Time:** 1h

### usePropaneComparison

**File:** `frontend/lib/hooks/usePropane.ts`

Compares a state's propane price against the national average.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<PropaneComparison>`

**Query Key:** `['propane', 'comparison', state]` | **Stale Time:** 1h

### usePropaneTiming

**File:** `frontend/lib/hooks/usePropane.ts`

Returns buy/wait/neutral timing advice based on current vs. average propane prices.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<PropaneTimingAdvice>` -- timing ('good' | 'wait' | 'neutral'), advice string

**Query Key:** `['propane', 'timing', state]` | **Stale Time:** 24h

### useWaterRates

**File:** `frontend/lib/hooks/useWater.ts`

Fetches water utility rates, optionally filtered by state.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<WaterRatesResponse>` -- rates[] with tiered pricing

**Query Key:** `['water', 'rates', state]` | **Stale Time:** 24h

### useWaterBenchmark

**File:** `frontend/lib/hooks/useWater.ts`

Benchmarks water costs for a state at a given usage level against other municipalities.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |
| `usageGallons` | `number \| undefined` |

**Returns:** `UseQueryResult<WaterBenchmark>` -- avg/min/max monthly cost, per-municipality breakdown

**Query Key:** `['water', 'benchmark', state, usageGallons]` | **Stale Time:** 24h

### useWaterTips

**File:** `frontend/lib/hooks/useWater.ts`

Fetches static water conservation tips with estimated savings per tip.

**Parameters:** None

**Returns:** `UseQueryResult<WaterTipsResponse>` -- tips[], estimated_annual_savings_gallons

**Query Key:** `['water', 'tips']` | **Stale Time:** 7 days

### useUtilityDiscovery

**File:** `frontend/lib/hooks/useUtilityDiscovery.ts`

Discovers available utility types for a state (deregulated, regulated, or available).

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| null \| undefined` |

**Returns:** `UseQueryResult<UtilityDiscoveryResponse>` -- state, count, utilities[]

**Query Key:** `['utility-discovery', state]` | **Stale Time:** 1h

```tsx
const { data } = useUtilityDiscovery("TX");
data?.utilities.forEach(u => console.log(u.label, u.status));
```

### useUtilityCompletion

**File:** `frontend/lib/hooks/useUtilityDiscovery.ts`

Checks what percentage of available utility types the user is tracking.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| null \| undefined` |
| `trackedTypes` | `string[]` |

**Returns:** `UseQueryResult<CompletionResponse>` -- tracked, available, percent, missing[]

**Query Key:** `['utility-completion', state, trackedTypes.join(',')]` | **Stale Time:** 1h

---

## Community

### useCommunityPosts

**File:** `frontend/lib/hooks/useCommunity.ts`

Fetches paginated community posts filtered by region and utility type.

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `region` | `string \| undefined` | -- |
| `utilityType` | `string \| undefined` | -- |
| `page` | `number` | `1` |

**Returns:** `UseQueryResult<PostsResponse>` -- posts[], total, page, pages

**Query Key:** `['community', 'posts', region, utilityType, page]` | **Stale Time:** 2min

### useCreatePost

**File:** `frontend/lib/hooks/useCommunity.ts`

Mutation to create a community post. Invalidates post and stats queries.

**Parameters (mutationFn):** `CreatePostPayload` -- title, body, utility_type, region, post_type, rate_per_unit?, supplier_name?

**Returns:** `UseMutationResult<CommunityPost>`

### useToggleVote

**File:** `frontend/lib/hooks/useCommunity.ts`

Mutation to toggle an upvote on a post. Invalidates post queries.

**Parameters (mutationFn):** `postId: string`

**Returns:** `UseMutationResult`

### useReportPost

**File:** `frontend/lib/hooks/useCommunity.ts`

Mutation to report a post for moderation. Invalidates post queries.

**Parameters (mutationFn):** `{ postId: string; reason?: string }`

**Returns:** `UseMutationResult`

### useCommunityStats

**File:** `frontend/lib/hooks/useCommunity.ts`

Fetches community statistics for a region (user count, post count, average savings).

**Parameters:**
| Param | Type |
|-------|------|
| `region` | `string \| undefined` |

**Returns:** `UseQueryResult<CommunityStatsResponse>`

**Query Key:** `['community', 'stats', region]` | **Stale Time:** 5min

### useCommunitySolarPrograms

**File:** `frontend/lib/hooks/useCommunitySolar.ts`

Fetches community solar programs available in a state, optionally filtered by enrollment status.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| null \| undefined` |
| `enrollmentStatus` | `'open' \| 'waitlist' \| 'closed' \| undefined` |

**Returns:** `UseQueryResult<CommunitySolarProgramsResponse>` -- state, count, programs[]

**Query Key:** `['community-solar', 'programs', state, enrollmentStatus]` | **Stale Time:** 10min

### useCommunitySolarSavings

**File:** `frontend/lib/hooks/useCommunitySolar.ts`

Calculates projected community solar savings given a monthly bill and savings percentage. Includes input validation using `isValidNumericInput()` (max bill $50,000, max savings 100%).

**Parameters:**
| Param | Type |
|-------|------|
| `monthlyBill` | `string \| null` |
| `savingsPercent` | `string \| null` |

**Returns:** `UseQueryResult<CommunitySolarSavingsResponse>` -- monthly/annual/5-year savings

**Query Key:** `['community-solar', 'savings', monthlyBill, savingsPercent]` | **Stale Time:** 5min

### useCommunitySolarProgram

**File:** `frontend/lib/hooks/useCommunitySolar.ts`

Fetches details for a single community solar program by ID.

**Parameters:**
| Param | Type |
|-------|------|
| `programId` | `string \| null` |

**Returns:** `UseQueryResult<CommunitySolarProgramDetail>`

**Query Key:** `['community-solar', 'program', programId]` | **Stale Time:** 10min

### useCommunitySolarStates

**File:** `frontend/lib/hooks/useCommunitySolar.ts`

Fetches all states that have community solar programs with program counts.

**Parameters:** None

**Returns:** `UseQueryResult<CommunitySolarStatesResponse>` -- total_states, states[]

**Query Key:** `['community-solar', 'states']` | **Stale Time:** 1h

### useCCADetect

**File:** `frontend/lib/hooks/useCCA.ts`

Detects whether a given zip code or state falls within a Community Choice Aggregation (CCA) program.

**Parameters:**
| Param | Type |
|-------|------|
| `zipCode` | `string \| undefined` |
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<CCADetectResponse>` -- `{ in_cca: boolean, program: CCAProgram | null }`

**Query Key:** `['cca', 'detect', zipCode, state]` | **Stale Time:** 1h

```tsx
const { data } = useCCADetect("94102");
if (data?.in_cca) console.log(data.program.program_name);
```

### useCCACompare

**File:** `frontend/lib/hooks/useCCA.ts`

Compares a CCA's rate against the default utility rate to calculate savings.

**Parameters:**
| Param | Type |
|-------|------|
| `ccaId` | `string \| undefined` |
| `defaultRate` | `number \| undefined` |

**Returns:** `UseQueryResult<CCACompareResponse>` -- savings_per_kwh, estimated_monthly_savings, is_cheaper

**Query Key:** `['cca', 'compare', ccaId, defaultRate]` | **Stale Time:** 1h | **Enabled:** when both params present and defaultRate > 0

### useCCAInfo

**File:** `frontend/lib/hooks/useCCA.ts`

Fetches details for a specific CCA program.

**Parameters:**
| Param | Type |
|-------|------|
| `ccaId` | `string \| undefined` |

**Returns:** `UseQueryResult<CCAProgram>`

**Query Key:** `['cca', 'info', ccaId]` | **Stale Time:** 1h

### useCCAPrograms

**File:** `frontend/lib/hooks/useCCA.ts`

Lists CCA programs, optionally filtered by state.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<CCAListResponse>` -- `{ count, programs[] }`

**Query Key:** `['cca', 'programs', state]` | **Stale Time:** 1h

### useNeighborhoodComparison

**File:** `frontend/lib/hooks/useNeighborhood.ts`

Compares the user's rate against their neighborhood for a given utility type.

**Parameters:**
| Param | Type |
|-------|------|
| `region` | `string \| undefined` |
| `utilityType` | `string \| undefined` |

**Returns:** `UseQueryResult<NeighborhoodComparison>` -- percentile, user_rate, cheapest_supplier, potential_savings

**Query Key:** `['neighborhood', 'compare', region, utilityType]` | **Stale Time:** 10min

### useCombinedSavings

**File:** `frontend/lib/hooks/useCombinedSavings.ts`

Fetches the user's combined savings across all tracked utility types.

**Parameters:** None

**Returns:** `UseQueryResult<CombinedSavingsResponse>` -- total_monthly_savings, breakdown[], savings_rank_pct

**Query Key:** `['savings', 'combined']` | **Stale Time:** 5min

```tsx
const { data } = useCombinedSavings();
console.log(`Saving $${data?.total_monthly_savings}/month across ${data?.breakdown.length} utilities`);
```

---

## AI/Agent

### useAgentQuery

**File:** `frontend/lib/hooks/useAgent.ts`

Manages streaming agent queries via SSE. Uses raw `useState`/`useCallback` (not TanStack Query). Supports abort/cancel and auto-cleanup on unmount.

**Parameters:** None (prompt is passed to `sendQuery`)

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `AgentMessage[]` | Full conversation history (user + assistant + error + tool messages) |
| `isStreaming` | `boolean` | True while SSE stream is active |
| `error` | `string \| null` | Last error message |
| `sendQuery` | `(prompt: string) => Promise<void>` | Send a new query to the agent |
| `cancel` | `() => void` | Abort the current streaming request |
| `reset` | `() => void` | Clear all messages and errors |

```tsx
const { messages, isStreaming, sendQuery, cancel, reset } = useAgentQuery();

<button onClick={() => sendQuery("What's my cheapest rate?")}>Ask</button>
<button onClick={cancel} disabled={!isStreaming}>Cancel</button>
<button onClick={reset}>New Chat</button>

{messages.map(msg => <ChatMessage key={msg.id} message={msg} />)}
```

### useAgentStatus

**File:** `frontend/lib/hooks/useAgent.ts`

Fetches the current user's agent usage limits (used, limit, remaining, tier).

**Parameters:** None

**Returns:** `UseQueryResult<AgentUsage>` -- used, limit, remaining, tier

**Query Key:** `['agent', 'usage']` | **Stale Time:** 60s | **Retry:** disabled

```tsx
const { data } = useAgentStatus();
console.log(`${data?.remaining}/${data?.limit} queries remaining (${data?.tier} tier)`);
```

---

## Analytics

### useOptimizationReport

**File:** `frontend/lib/hooks/useReports.ts`

Fetches a comprehensive optimization report for a state, including all utility types, costs, and savings opportunities.

**Parameters:**
| Param | Type |
|-------|------|
| `state` | `string \| undefined` |

**Returns:** `UseQueryResult<OptimizationReport>` -- utilities[], savings_opportunities[], total spend/savings

**Query Key:** `['reports', 'optimization', state]` | **Stale Time:** 1h

### useExportRates

**File:** `frontend/lib/hooks/useExport.ts`

Exports rate data for a utility type in JSON or CSV format. Disabled by default; set `enabled=true` to trigger the fetch.

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `utilityType` | `string \| undefined` | -- |
| `format` | `'json' \| 'csv'` | `'json'` |
| `state` | `string \| undefined` | -- |
| `enabled` | `boolean` | `false` |

**Returns:** `UseQueryResult<ExportResponse>`

**Query Key:** `['export', 'rates', utilityType, format, state]` | **Stale Time:** 5min

### useExportTypes

**File:** `frontend/lib/hooks/useExport.ts`

Fetches the list of supported export types, formats, and limits.

**Parameters:** None

**Returns:** `UseQueryResult<ExportTypesResponse>` -- supported_types[], formats[], max_days, max_rows

**Query Key:** `['export', 'types']` | **Stale Time:** 24h

### useDiagramList

**File:** `frontend/lib/hooks/useDiagrams.ts`

Fetches the list of architecture diagrams (dev-only feature). Uses local `/api/dev/diagrams` endpoint, not the backend API client.

**Parameters:** None

**Returns:** `UseQueryResult<DiagramEntry[]>` -- name, updatedAt per diagram

**Query Key:** `['diagrams', 'list']`

### useDiagram

**File:** `frontend/lib/hooks/useDiagrams.ts`

Fetches a single diagram's data by name.

**Parameters:**
| Param | Type |
|-------|------|
| `name` | `string \| null` |

**Returns:** `UseQueryResult<DiagramData>` -- name, data (arbitrary JSON)

**Query Key:** `['diagrams', 'detail', name]`

### useSaveDiagram

**File:** `frontend/lib/hooks/useDiagrams.ts`

Mutation to save diagram data. Invalidates both diagram detail and list queries.

**Parameters (mutationFn):** `{ name: string; data: Record<string, unknown> }`

**Returns:** `UseMutationResult`

### useCreateDiagram

**File:** `frontend/lib/hooks/useDiagrams.ts`

Mutation to create a new diagram. Invalidates the diagram list.

**Parameters (mutationFn):** `name: string`

**Returns:** `UseMutationResult<{ name: string; created: boolean }>`

---

## Alerts

### useAlerts

**File:** `frontend/lib/hooks/useAlerts.ts`

Fetches the user's alert configurations.

**Parameters:** None

**Returns:** `UseQueryResult<GetAlertsResponse>` -- `{ alerts: Alert[], total }`

**Query Key:** `['alerts']` | **Stale Time:** 30s

```tsx
const { data } = useAlerts();
data?.alerts.map(a => <AlertCard key={a.id} alert={a} />);
```

### useAlertHistory

**File:** `frontend/lib/hooks/useAlerts.ts`

Fetches paginated alert trigger history.

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `page` | `number` | `1` |
| `pageSize` | `number` | `20` |

**Returns:** `UseQueryResult<GetAlertHistoryResponse>` -- items[], total, page, pages

**Query Key:** `['alerts', 'history', page, pageSize]` | **Stale Time:** 30s

### useCreateAlert

**File:** `frontend/lib/hooks/useAlerts.ts`

Mutation to create a new alert configuration. Invalidates `['alerts']`.

**Parameters (mutationFn):** `CreateAlertRequest` -- region, currency?, price_below?, price_above?, notify_optimal_windows?

**Returns:** `UseMutationResult<Alert>`

```tsx
const createAlert = useCreateAlert();
createAlert.mutate({ region: "NY", price_below: 0.10 });
```

### useUpdateAlert

**File:** `frontend/lib/hooks/useAlerts.ts`

Mutation to update an existing alert. Invalidates `['alerts']`.

**Parameters (mutationFn):** `{ id: string; body: UpdateAlertRequest }`

**Returns:** `UseMutationResult<Alert>`

### useDeleteAlert

**File:** `frontend/lib/hooks/useAlerts.ts`

Mutation to delete an alert. Invalidates `['alerts']`.

**Parameters (mutationFn):** `id: string`

**Returns:** `UseMutationResult<{ deleted: boolean; alert_id: string }>`

---

## Suppliers

### useSuppliers

**File:** `frontend/lib/hooks/useSuppliers.ts`

Fetches available electricity suppliers for a region.

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `region` | `string \| null \| undefined` | -- |
| `annualUsage` | `number \| undefined` | -- |
| `enabled` | `boolean` | `true` |

**Returns:** `UseQueryResult<GetSuppliersResponse>` -- suppliers[], total

**Query Key:** `['suppliers', region, annualUsage]` | **Stale Time:** 5min

### useSupplier

**File:** `frontend/lib/hooks/useSuppliers.ts`

Fetches a single supplier by ID.

**Parameters:**
| Param | Type |
|-------|------|
| `supplierId` | `string` |

**Returns:** `UseQueryResult<Supplier>`

**Query Key:** `['supplier', supplierId]` | **Stale Time:** 5min

### useSupplierRecommendation

**File:** `frontend/lib/hooks/useSuppliers.ts`

Gets a supplier recommendation based on the user's current supplier, usage, and region.

**Parameters:**
| Param | Type |
|-------|------|
| `currentSupplierId` | `string` |
| `annualUsage` | `number` |
| `region` | `string \| null \| undefined` |

**Returns:** `UseQueryResult<GetRecommendationResponse>` -- recommendation object

**Query Key:** `['recommendation', currentSupplierId, annualUsage, region]` | **Stale Time:** 5min

### useCompareSuppliers

**File:** `frontend/lib/hooks/useSuppliers.ts`

Compares multiple suppliers side-by-side. Uses sorted JSON.stringify for stable query key identity.

**Parameters:**
| Param | Type |
|-------|------|
| `supplierIds` | `string[]` |
| `annualUsage` | `number` |

**Returns:** `UseQueryResult<{ comparisons: Supplier[] }>`

**Query Key:** `['compare', stableIdsKey, annualUsage]` | **Stale Time:** 5min

### useInitiateSwitch

**File:** `frontend/lib/hooks/useSuppliers.ts`

Mutation to initiate a supplier switch. Invalidates supplier and recommendation queries.

**Parameters (mutationFn):** `InitiateSwitchRequest` -- newSupplierId, gdprConsent, currentSupplierId?

**Returns:** `UseMutationResult<InitiateSwitchResponse>` -- success, referenceNumber, estimatedCompletionDate

### useSwitchStatus

**File:** `frontend/lib/hooks/useSuppliers.ts`

Polls the status of a supplier switch every 60 seconds.

**Parameters:**
| Param | Type |
|-------|------|
| `referenceNumber` | `string` |

**Returns:** `UseQueryResult<{ status, estimatedCompletionDate, lastUpdated }>`

**Query Key:** `['switch-status', referenceNumber]` | **Refetch Interval:** 60s

### useUserSupplier

**File:** `frontend/lib/hooks/useSuppliers.ts`

Fetches the authenticated user's currently selected supplier.

**Parameters:** None

**Returns:** `UseQueryResult<{ supplier: UserSupplierResponse | null }>`

**Query Key:** `['user-supplier']` | **Stale Time:** 60s

### useSetSupplier

**File:** `frontend/lib/hooks/useSuppliers.ts`

Mutation to set the user's current supplier. Invalidates user-supplier and supplier queries.

**Parameters (mutationFn):** `supplierId: string`

**Returns:** `UseMutationResult<UserSupplierResponse>`

### useRemoveSupplier

**File:** `frontend/lib/hooks/useSuppliers.ts`

Mutation to remove the user's current supplier. Invalidates user-supplier query.

**Parameters (mutationFn):** None

**Returns:** `UseMutationResult<{ message: string }>`

### useLinkAccount

**File:** `frontend/lib/hooks/useSuppliers.ts`

Mutation to link a utility account to a supplier.

**Parameters (mutationFn):** `LinkAccountRequest` -- supplier_id, account_number, meter_number?, service_zip?, account_nickname?, consent_given

**Returns:** `UseMutationResult<LinkedAccountResponse>`

### useUserSupplierAccounts

**File:** `frontend/lib/hooks/useSuppliers.ts`

Fetches all linked supplier accounts (masked account/meter numbers).

**Parameters:** None

**Returns:** `UseQueryResult<{ accounts: LinkedAccountResponse[] }>`

**Query Key:** `['user-supplier-accounts']` | **Stale Time:** 60s

### useUnlinkAccount

**File:** `frontend/lib/hooks/useSuppliers.ts`

Mutation to unlink a specific supplier account.

**Parameters (mutationFn):** `supplierId: string`

**Returns:** `UseMutationResult<{ message: string }>`

---

## Location

### useGeocoding

**File:** `frontend/lib/hooks/useGeocoding.ts`

Imperative geocoding hook that converts an address string to coordinates and state code. Uses `useState`/`useCallback` (not TanStack Query). Handles request deduplication (cancels previous in-flight requests via AbortController) and discards stale responses using a request ID counter.

**Parameters:** None

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `geocode` | `(address: string) => Promise<GeocodeResult \| null>` | Trigger a geocode lookup |
| `loading` | `boolean` | True while geocoding is in progress |
| `error` | `string \| null` | Last error message |

`GeocodeResult`: `{ lat, lng, state, formatted_address }`

```tsx
const { geocode, loading, error } = useGeocoding();

const handleSearch = async (address: string) => {
  const result = await geocode(address);
  if (result?.state) {
    setRegion(result.state);
  }
};
```

---

## Real-time

### useRealtimePrices

**File:** `frontend/lib/hooks/useRealtime.ts`

Subscribes to real-time price updates via Server-Sent Events (SSE). Uses `@microsoft/fetch-event-source` instead of native `EventSource` to include session cookies. Automatically pauses when the browser tab is hidden. Features exponential backoff (1s to 30s cap) on connection errors. On new data, performs a partial-merge update of the React Query cache (updates matching supplier entries in-place).

**Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `region` | `string \| null \| undefined` | -- |
| `interval` | `number` | `30` |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `isConnected` | `boolean` | True when SSE connection is active |
| `lastPrice` | `PriceUpdate \| null` | Most recent price update received |
| `disconnect` | `() => void` | Manually close the SSE connection |

```tsx
const { isConnected, lastPrice } = useRealtimePrices(region);
if (lastPrice) {
  console.log(`${lastPrice.supplier}: $${lastPrice.price_per_kwh}/kWh`);
}
```

### useRealtimeOptimization

**File:** `frontend/lib/hooks/useRealtime.ts`

Polls for optimization updates by invalidating the `['optimization']` query key every 60 seconds. Acts as a fallback for SSE.

**Parameters:** None

**Returns:** `{ isConnected: boolean }`

### useRealtimeSubscription

**File:** `frontend/lib/hooks/useRealtime.ts`

Generic hook for subscribing to any table changes. Polls every 30 seconds as a universal fallback. The `onUpdate` callback is stored in a ref to prevent interval restarts when callers pass inline arrow functions.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `config` | `RealtimeConfig` | `{ table, event?, filter? }` |
| `onUpdate` | `(payload: unknown) => void \| undefined` | Callback on each poll tick |

**Returns:** `{ isConnected: boolean, lastUpdate: Date | null }`

```tsx
const { isConnected, lastUpdate } = useRealtimeSubscription(
  { table: 'prices', event: 'INSERT' },
  (payload) => console.log('New price:', payload)
);
```
