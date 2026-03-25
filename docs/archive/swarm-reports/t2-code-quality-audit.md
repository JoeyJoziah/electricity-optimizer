> **DEPRECATED** — This document is archived for historical reference only. It may contain outdated information. See current documentation in the parent `docs/` directory.

---

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

**Note**: All 5 Excalidraw-related `any` uses are in `components/dev/` which is gated behind dev-only access (triple gate: `notFound()` if not development). These are lower risk but still improvable with a local `ExcalidrawElement` type alias.

---

## 2. Type Suppression Inventory

### `@ts-ignore` / `@ts-expect-error` / `@ts-nocheck`

**Zero occurrences found.** The codebase has no TypeScript suppressions, which is excellent.

---

## 3. Pattern Consistency Analysis

### 3.1 Error Handling Patterns

**Three distinct patterns are in use, which is appropriate:**

| Pattern | Where Used | Files |
|---------|-----------|-------|
| **Next.js `error.tsx` boundaries** | Route-level errors | 7 files: root + dashboard, prices, suppliers, connections, optimize, settings |
| **Local `setError()` state** | Form/component-level errors | connections/* (9 components), suppliers/SwitchWizard, suppliers/SupplierAccountForm |
| **Toast notifications (`useToast`)** | User feedback after actions | settings/page.tsx only |

---

## 4. ESLint Configuration Analysis

### Current State

The project uses `eslint-config-next` (v14.2.25) with ESLint 8. **There is no custom `.eslintrc.*` file** — the project relies entirely on the default Next.js ESLint configuration.

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
    "react/jsx-no-target-blank": "error"
  }
}
```

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total `any` occurrences | 62 |
| Production code `any` | 9 (2 fixable, 7 library boundary) |
| Test code `any` | 53 |
| `@ts-ignore/@ts-expect-error/@ts-nocheck` | 0 |
| ESLint suppressions | 4 (all in tests, all justified) |

---

*This report is an archived analysis of code quality metrics from March 2026 audits.*
