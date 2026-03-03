# T2: Frontend Code Quality Audit

> Audited: 2026-03-03
> Scope: `/Users/devinmcgrath/projects/electricity-optimizer/frontend/`

---

## 1. `any` Type Inventory

**Total occurrences**: 62 across 14 files

### Production Code (4 files, 9 occurrences)

#### P0 — Fixable (production, non-library)

| File | Line | Code | Classification |
|------|------|------|----------------|
| `app/(app)/beta-signup/page.tsx` | 40 | `(window as any).gtag` | **Fixable** — declare `gtag` on `Window` interface |
| `app/(app)/beta-signup/page.tsx` | 41 | `(window as any).gtag(...)` | **Fixable** — same fix as above |

#### P1 — Library boundary (Excalidraw interop)

| File | Line | Code | Classification |
|------|------|------|----------------|
| `components/dev/ExcalidrawWrapper.tsx` | 21 | `elements: readonly any[]` | **Library boundary** — Excalidraw lacks exported element type |
| `components/dev/ExcalidrawWrapper.tsx` | 27 | `elements: readonly any[], appState: any, files: any` | **Library boundary** — Excalidraw onChange callback signature |
| `components/dev/ExcalidrawWrapper.tsx` | 36 | `initialData={initialData as any}` | **Library boundary** — Excalidraw InitialData type mismatch |
| `components/dev/ExcalidrawWrapper.tsx` | 37 | `onChange={handleChange as any}` | **Library boundary** — Excalidraw onChange type mismatch |
| `components/dev/DiagramEditor.tsx` | 29 | `elements: readonly any[]` | **Library boundary** — inherited from ExcalidrawWrapper prop |

**Note**: All 5 Excalidraw-related `any` uses are in `components/dev/` which is gated behind dev-only access (triple gate: `notFound()` if not development). These are lower risk but still improvable with a local `ExcalidrawElement` type alias.

### Test-Only Code (10 files, 53 occurrences)

#### P2 — Test files

| File | Count | Common Patterns |
|------|-------|----------------|
| `__tests__/components/prices/PricesContent.test.tsx` | 12 | Mock factory params (`props: any`), module mocks (`...args: any[]`), state (`any[]`) |
| `__tests__/pages/prices.test.tsx` | 11 | Same pattern: dynamic import mocks, component props, hook mocks |
| `__tests__/components/suppliers/SuppliersContent.test.tsx` | 7 | Mock state (`any = null`), selector types, spread args |
| `__tests__/pages/suppliers.test.tsx` | 6 | Component mock props, spread args |
| `__tests__/hooks/usePrices.test.tsx` | 4 | Spread args on mock API functions |
| `__tests__/components/dev/DiagramEditor.test.tsx` | 4 | Mock component props (`props: any`) |
| `__tests__/components/dev/DiagramList.test.tsx` | 3 | Mock icon props |
| `__tests__/app/dev/architecture.test.tsx` | 2 | Mock component props |
| `__tests__/api/dev/diagrams/route.test.ts` | 2 | `as any` for partial mock objects |
| `__tests__/api/dev/diagrams/name.route.test.ts` | 2 | `as any` for partial mock objects |
| `__tests__/components/dev/ExcalidrawWrapper.test.tsx` | 2 | Dynamic import mock, component props |

**Recurring test patterns that use `any`**:
1. `(...args: any[]) => mockFn(...args)` — mock API function passthrough (24 occurrences)
2. `(props: any) => <div ...>` — mock component renderers (11 occurrences)
3. `(selector: (state: any) => any) =>` — zustand store selector mocks (4 occurrences)
4. `as any` — partial mock objects for Request/Response (4 occurrences)
5. `React.ComponentType<any>` — dynamic import state (2 occurrences)
6. `let mockVar: any = null` — mutable mock state (1 occurrence)

---

## 2. Type Suppression Inventory

### `@ts-ignore` / `@ts-expect-error` / `@ts-nocheck`

**Zero occurrences found.** The codebase has no TypeScript suppressions, which is excellent.

### ESLint Suppressions

| File | Line | Suppression | Reason |
|------|------|-------------|--------|
| `__tests__/pages/suppliers.test.tsx` | 50 | `eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text` | Mock Image component |
| `__tests__/components/suppliers/SuppliersContent.test.tsx` | 20 | `eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text` | Mock Image component |
| `__tests__/components/dashboard/DashboardContent.test.tsx` | 14 | `eslint-disable-next-line @typescript-eslint/no-require-imports` | Dynamic require in test |
| `__tests__/components/dashboard/DashboardContent.test.tsx` | 16 | `eslint-disable-next-line @typescript-eslint/no-require-imports` | Dynamic require in test |

All 4 suppressions are in test files only, and each is justified:
- The `@next/next/no-img-element` disables are for mock Next.js Image components
- The `@typescript-eslint/no-require-imports` disables are for dynamic module re-imports in tests

---

## 3. Pattern Consistency Analysis

### 3.1 Error Handling Patterns

**Three distinct patterns are in use, which is appropriate:**

| Pattern | Where Used | Files |
|---------|-----------|-------|
| **Next.js `error.tsx` boundaries** | Route-level errors | 7 files: root + dashboard, prices, suppliers, connections, optimize, settings |
| **Local `setError()` state** | Form/component-level errors | connections/* (9 components), suppliers/SwitchWizard, suppliers/SupplierAccountForm |
| **Toast notifications (`useToast`)** | User feedback after actions | settings/page.tsx only |

**Finding**: The `useToast` hook is only used in 1 production component (`settings/page.tsx`). All connection/supplier components use inline `setError()` state with local error UI. This is consistent within each domain but creates a **split pattern**:
- **Settings**: Toast-based feedback (non-blocking)
- **Connections/Suppliers**: Inline error state (blocking UI)

**Recommendation**: This split is acceptable because connections forms need inline validation feedback while settings uses action confirmation. However, success feedback after connection operations (sync, delete, create) could benefit from toasts instead of just error handling.

### 3.2 Loading State Patterns

**Two patterns are in use:**

| Pattern | Where Used | Consistency |
|---------|-----------|-------------|
| **Next.js `loading.tsx` with `<Skeleton>`** | Route-level (5 routes: dashboard, prices, suppliers, connections, optimize) | Consistent |
| **`<Loader2>` spinner from Lucide** | Component-level (ConnectionsOverview, ConnectionCard, ConnectionAnalytics, SupplierPicker) | Consistent |

**Finding**: Good separation. Route-level uses skeleton layouts. Component-level uses Loader2 spinners. The dev components (DiagramEditor, DiagramList, ExcalidrawWrapper) also use `<Skeleton>` for component-level loading, which is slightly inconsistent with the Loader2 pattern in other components, but is isolated to dev-only code.

### 3.3 Data Fetching Patterns

**Three distinct patterns are in use:**

| Pattern | Where Used | Count |
|---------|-----------|-------|
| **React Query (`useQuery`/`useMutation`)** | Hooks: `useSuppliers`, `usePrices`, `useOptimization`, `useSavings`, `useProfile`, `useDiagrams`, `NotificationBell` | 7 hook files |
| **Direct `fetch()` with `useState`** | Connections components (Overview, Card, Analytics, DirectLogin, EmailFlow, UploadFlow, BillUpload, Rates) | 8 component files |
| **SSE via `useRealtime`** | Real-time price/table subscriptions | 1 hook file |

**Critical Finding**: The connections domain exclusively uses manual `fetch()` + `useState` + `useEffect` instead of React Query. This creates:
- No automatic caching, deduplication, or background refetching
- Manual loading/error state management (duplicated in each component)
- No query invalidation coordination between connection components
- The `ConnectionAnalytics` component alone has 4 separate `fetch` + `setState` + `useEffect` data-fetching blocks, each with identical boilerplate

**Recommendation (P1)**: Migrate connections data fetching to React Query hooks (e.g., `useConnections`, `useConnectionRates`, `useConnectionAnalytics`) to match the pattern used by suppliers, prices, and optimization. This would eliminate ~200 lines of duplicated fetch/error/loading boilerplate.

### 3.4 State Management

| Layer | Tool | Usage |
|-------|------|-------|
| **Global client state** | Zustand (`useSettingsStore`) | Settings only (region, currency, units) |
| **Server state** | React Query | Suppliers, prices, optimization, savings, profile, diagrams |
| **Local UI state** | `useState` | Forms, modals, loading flags |
| **Auth** | Better Auth (`useSession`, `signIn`, `signOut`) | Auth flow |

**Finding**: State management is well-organized. No prop drilling issues observed. React Query is used for server cache, zustand for lightweight global settings — a clean separation.

---

## 4. ESLint Configuration Analysis

### Current State

The project uses `eslint-config-next` (v14.2.25) with ESLint 8. **There is no custom `.eslintrc.*` file** — the project relies entirely on the default Next.js ESLint configuration.

The `next lint` command in `package.json` uses Next.js's built-in ESLint integration which provides:
- `@next/next/*` rules (Next.js best practices)
- `react/react-in-jsx-scope` (off, not needed in Next.js)
- `react-hooks/rules-of-hooks` and `react-hooks/exhaustive-deps`
- Basic `@typescript-eslint` rules

### TypeScript Config

`tsconfig.json` has `"strict": true` enabled, which is good. This enforces:
- `strictNullChecks`, `noImplicitAny`, `strictFunctionTypes`, etc.

### Recommended ESLint Rules to Add

Create a `.eslintrc.json` in `frontend/`:

```json
{
  "extends": "next/core-web-vitals",
  "rules": {
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/no-unused-vars": ["error", {
      "argsIgnorePattern": "^_",
      "varsIgnorePattern": "^_"
    }],
    "@typescript-eslint/consistent-type-imports": "warn",
    "no-console": ["warn", { "allow": ["error", "warn"] }],
    "react/no-unescaped-entities": "error",
    "react/self-closing-comp": "warn",
    "react/jsx-no-target-blank": "error",
    "prefer-const": "error"
  },
  "overrides": [
    {
      "files": ["**/__tests__/**", "**/*.test.{ts,tsx}"],
      "rules": {
        "@typescript-eslint/no-explicit-any": "off"
      }
    }
  ]
}
```

**Key additions explained:**
1. `@typescript-eslint/no-explicit-any: "warn"` — Flags all `any` in production code (off in tests via override)
2. `@typescript-eslint/no-unused-vars` with underscore pattern — Catches unused vars while allowing intentional `_` prefixed ignores
3. `@typescript-eslint/consistent-type-imports` — Enforces `import type` for type-only imports (tree-shaking benefit)
4. `no-console` warning (allow error/warn) — Prevents stray `console.log` in production
5. `react/jsx-no-target-blank` — Security: prevents `target="_blank"` without `rel="noopener"`

### Missing Dev Dependencies for Enhanced Linting

The project already has `@typescript-eslint` rules available via `eslint-config-next`. For the full rule set, consider adding:
- `@typescript-eslint/eslint-plugin` (explicit, for granular rule control)
- `eslint-plugin-import` (import ordering, no duplicates)

---

## 5. Additional Findings

### 5.1 Console Logging in Production Code

| File | Line | Statement | Risk |
|------|------|-----------|------|
| `lib/api/client.ts` | 37 | `console.warn(...)` | Low — API client fallback warning |
| `lib/auth/server.ts` | 19 | `console.error(...)` | OK — critical auth init failure |
| `app/api/checkout/route.ts` | 37 | `console.error('Checkout error:', error)` | OK — API route error logging |
| `app/api/auth/[...all]/route.ts` | 38,43 | `console.error(...)` | OK — Auth error logging |
| `app/error.tsx` | 13 | `console.error('Application error:', error)` | OK — Error boundary |

**Assessment**: Console usage is minimal and appropriate. Only the `console.warn` in `client.ts` is debatable.

### 5.2 Missing Error Boundaries

No custom React Error Boundary components exist. The app relies entirely on Next.js `error.tsx` convention files (7 exist). Missing:
- No `global-error.tsx` at root level (would catch root layout errors)
- No `not-found.tsx` files detected

### 5.3 No ESLint Config File

The biggest tooling gap: no `.eslintrc.*` file exists. The project runs `next lint` which uses defaults, but cannot enforce project-specific rules like `no-explicit-any`.

---

## 6. Priority-Ordered Fix List

### P0: Critical (Production Code)

| # | Issue | Files | Effort |
|---|-------|-------|--------|
| 1 | Add `Window.gtag` type declaration | `beta-signup/page.tsx` | S (add `global.d.ts`) |
| 2 | Create `.eslintrc.json` with `no-explicit-any` rule | New file | S |
| 3 | Add `global-error.tsx` for root layout error catching | New file | S |

### P1: Major (Architecture/Patterns)

| # | Issue | Files | Effort |
|---|-------|-------|--------|
| 4 | Migrate connections data fetching to React Query hooks | 8 connection components | L |
| 5 | Create Excalidraw type aliases to replace `any[]` | `ExcalidrawWrapper.tsx`, `DiagramEditor.tsx` | S |
| 6 | Add `not-found.tsx` pages for app routes | New files | S |

### P2: Minor (Test Code)

| # | Issue | Files | Effort |
|---|-------|-------|--------|
| 7 | Replace `(...args: any[]) => mock(...)` with typed mock factories | 6 test files, ~24 occurrences | M |
| 8 | Replace `(props: any) => <div>` mock patterns with typed props | 6 test files, ~11 occurrences | M |
| 9 | Type zustand selector mocks | 3 test files, 4 occurrences | S |
| 10 | Replace `as any` partial mocks with proper test utilities | 2 test files, 4 occurrences | S |

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total `any` occurrences | 62 |
| Production code `any` | 9 (2 fixable, 7 library boundary) |
| Test code `any` | 53 |
| `@ts-ignore/@ts-expect-error/@ts-nocheck` | 0 |
| ESLint suppressions | 4 (all in tests, all justified) |
| Error handling patterns | 3 (boundaries + inline state + toast) — acceptable |
| Loading state patterns | 2 (Skeleton + Loader2) — consistent |
| Data fetching inconsistency | Connections uses raw fetch, rest uses React Query — **fix recommended** |
| Missing ESLint config | Yes — **create recommended** |
