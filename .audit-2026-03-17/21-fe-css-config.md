# Audit Report: Frontend CSS & Configuration
## Date: 2026-03-17
## Auditor: Claude Code (claude-sonnet-4-6)

---

### Executive Summary

Seven configuration files and two constants modules were reviewed covering the full
frontend build surface: Tailwind CSS, PostCSS, global styles, Jest, TypeScript,
package.json, ESLint, chart tokens, and region constants.

The configuration layer is well-structured for a Next.js 16 / React 19 project.
Design tokens are consistently applied, the chart token abstraction is solid, and
the Jest 30 + jsdom 26 workaround is correctly implemented. No secrets or credentials
were found in any configuration file.

**Three issues warrant immediate attention** before the production launch:

1. `'unsafe-inline'` on `script-src` in the production CSP negates XSS protection for all
   inline scripts — the most impactful security exposure in the entire config set.
2. `'unsafe-inline'` on `style-src` prevents future adoption of nonces and is
   inconsistent with the stated security posture.
3. The `better-auth/react` Jest mock is missing `changePassword` and `magicLinkClient`
   methods that are actively used by production components, creating false-positive
   test coverage.

The remaining findings are medium/low priority improvements that should be addressed
in the next hardening sprint.

---

### Findings

#### P0 — Critical

**[P0-01] `script-src 'unsafe-inline'` ships to production — XSS protection nullified**

- **File**: `frontend/next.config.js`, line 58
- **Severity**: Critical — defeats the primary purpose of the Content Security Policy

The production CSP contains:
```js
`script-src 'self' 'unsafe-inline' https://*.clarity.ms https://cdn.onesignal.com`
```

`'unsafe-inline'` allows any inline `<script>` tag or event handler attribute to
execute. This means a successful XSS injection (e.g. via an unsanitised recharts
tooltip, a JSONB field rendered as HTML, or a third-party library vulnerability) can
run arbitrary JavaScript despite the policy being in place. The CSP is effectively
disabled for the threat class it is meant to mitigate.

**Root cause**: Next.js injects runtime inline scripts. Without a nonce or
`'strict-dynamic'`, `'unsafe-inline'` is the escape hatch developers reach for.

**Recommended fix — nonce-based CSP with middleware**:

```ts
// frontend/middleware.ts
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { randomBytes } from 'crypto'

export function middleware(request: NextRequest) {
  const nonce = randomBytes(16).toString('base64')
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' https://*.clarity.ms https://cdn.onesignal.com`,
    "style-src 'self' 'unsafe-inline'",   // styles addressed separately — see P1-01
    // ... rest of directives
  ].join('; ')

  const response = NextResponse.next({
    request: { headers: new Headers({ ...request.headers, 'x-nonce': nonce }) },
  })
  response.headers.set('Content-Security-Policy', csp)
  return response
}
```

Then pass the nonce to `next/script` and the Next.js `<Script>` component:

```tsx
// app/layout.tsx
import { headers } from 'next/headers'

export default function RootLayout({ children }) {
  const nonce = headers().get('x-nonce') ?? ''
  return (
    <html>
      <head><Script nonce={nonce} ... /></head>
      <body>{children}</body>
    </html>
  )
}
```

`'strict-dynamic'` ensures scripts loaded by trusted first-party scripts are
automatically trusted, which covers the OneSignal and Clarity SDKs transitively.

**Interim mitigation** (if nonce refactor cannot land before launch): add a report-only
shadow policy via `Content-Security-Policy-Report-Only` with `report-uri` pointing at
Sentry so violations are visible without breaking anything, then ship the nonce fix
in the next sprint.

---

#### P1 — High

**[P1-01] `style-src 'unsafe-inline'` blocks nonce adoption for styles**

- **File**: `frontend/next.config.js`, line 59
- **Severity**: High — prevents a path to full CSP hardening

```js
"style-src 'self' 'unsafe-inline'",
```

This is partially unavoidable today because Tailwind, Recharts, and the Radix/Headless
UI ecosystem inject inline styles. However, documenting this explicitly and tracking
it is important:

1. When Tailwind 4 (CSS-first config) ships and the project migrates, inline style
   injection from the build pipeline will be eliminated, making a nonce approach
   feasible for styles too.
2. At minimum, add a comment in `next.config.js` explaining why this is present and
   link to a tracking issue, so it is not silently accepted as permanent.

```js
// 'unsafe-inline' required: Tailwind v3 and Recharts inject inline styles at runtime.
// Track removal in: https://github.com/JoeyJoziah/electricity-optimizer/issues/XXX
// Re-evaluate after Tailwind v4 migration.
"style-src 'self' 'unsafe-inline'",
```

---

**[P1-02] Jest `better-auth/react` mock is missing `changePassword` and `magicLink` methods**

- **File**: `frontend/__mocks__/better-auth-react.js`
- **Affected components**: any Settings page component that calls `authClient.changePassword()`

The mock returned by `createAuthClient()` does not include:
- `changePassword` (used in Settings per CLAUDE.md: "Better Auth: `authClient.changePassword`")
- `magicLink` plugin methods (the real client is created with `magicLinkClient()`)
- `updateUser` (typical profile update surface)

When a test file imports `authClient` from `@/lib/auth/client`, the mock substitutes
`better-auth/react` via `moduleNameMapper`, so any component calling
`authClient.changePassword(...)` in a test will get `undefined` instead of a function
and either silently no-op or throw `TypeError: authClient.changePassword is not a
function`. This produces false-green tests for the Settings password-change flow.

**Fix**:
```js
// frontend/__mocks__/better-auth-react.js
function createAuthClient() {
  return {
    useSession: () => ({ data: null, isPending: false, error: null }),
    signIn: {
      email: async () => ({ data: null, error: null }),
      social: async () => ({ data: null, error: null }),
    },
    signUp: {
      email: async () => ({ data: null, error: null }),
    },
    signOut: async () => ({ data: null, error: null }),
    getSession: async () => ({ data: null, error: null }),
    forgetPassword: async () => ({ data: null, error: null }),
    // ADD: methods used by Settings and magic-link flows
    changePassword: async () => ({ data: null, error: null }),
    updateUser: async () => ({ data: null, error: null }),
    magicLink: {
      sendMagicLink: async () => ({ data: null, error: null }),
    },
  }
}
```

---

**[P1-03] TypeScript `strict` mode is missing `noUncheckedIndexedAccess`**

- **File**: `frontend/tsconfig.json`
- **Severity**: High — common source of runtime `undefined` errors that TypeScript will not catch

`"strict": true` enables a useful baseline (strictNullChecks, noImplicitAny,
strictFunctionTypes, etc.) but does **not** include `noUncheckedIndexedAccess`. This
means array element access and object index access return `T` rather than `T |
undefined`, so code like:

```ts
const prices = getPriceHistory()  // PricePoint[]
const first = prices[0]           // typed as PricePoint, could be undefined
console.log(first.price)          // runtime crash if array is empty
```

...compiles without error. For a data-heavy application pulling live API data this is
a meaningful risk — empty arrays from API responses will cause runtime crashes that
the type system could have prevented.

**Fix** — add to `compilerOptions`:
```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "exactOptionalPropertyTypes": true
  }
}
```

`noImplicitReturns` and `exactOptionalPropertyTypes` are also recommended for
production code of this scale. Note: enabling `noUncheckedIndexedAccess` on an
existing codebase will surface type errors; plan for a short remediation pass.

---

**[P1-04] ESLint `@typescript-eslint/no-explicit-any` is `"warn"` rather than `"error"`**

- **File**: `frontend/.eslintrc.json`, line 5
- **Severity**: High — `any` leakage defeats strict TypeScript in production code

```json
"@typescript-eslint/no-explicit-any": "warn"
```

Warnings do not fail CI. The three production suppressions already present in
non-test code (`ExcalidrawWrapper.tsx`, `InstallPrompt.tsx`, `useRealtime.ts`) suggest
this is being selectively silenced instead of typed properly.

**Fix**:
```json
"@typescript-eslint/no-explicit-any": "error"
```

Production code that genuinely needs escape hatches should use
`// eslint-disable-next-line @typescript-eslint/no-explicit-any` with an explanatory
comment, making `any` usage explicit and visible in code review. The existing test
file override (`"off"` in `overrides`) is appropriate and should remain.

Additional rules worth adding:
```json
"@typescript-eslint/consistent-type-imports": ["error", { "prefer": "type-imports" }],
"@typescript-eslint/no-floating-promises": "error",
"import/no-duplicates": "error"
```

`no-floating-promises` is particularly important given the async auth and API call
patterns throughout the codebase.

---

**[P1-05] `tailwind.config.ts` content globs miss `lib/**` and root-level `.tsx` files**

- **File**: `frontend/tailwind.config.ts`, lines 5-9
- **Severity**: High — Tailwind classes used in utility modules or root pages are not scanned

Current content paths:
```ts
content: [
  './pages/**/*.{js,ts,jsx,tsx,mdx}',
  './components/**/*.{js,ts,jsx,tsx,mdx}',
  './app/**/*.{js,ts,jsx,tsx,mdx}',
],
```

Missing paths:
- `./lib/**/*.{ts,tsx}` — classes conditionally constructed in hook/utility files
  (e.g. `lib/utils`, `lib/hooks`) will not be included in the CSS output
- `./middleware.ts` — if middleware constructs class names (unlikely but possible)

The `components/` glob does cover the primary component tree, but `lib/` utilities
that use `clsx()` or `cn()` to build conditional class strings are not scanned.
If any such class is not used anywhere in `app/` or `components/` it will be purged
from the production bundle and cause invisible styling regressions.

**Fix**:
```ts
content: [
  './pages/**/*.{js,ts,jsx,tsx,mdx}',
  './components/**/*.{js,ts,jsx,tsx,mdx}',
  './app/**/*.{js,ts,jsx,tsx,mdx}',
  './lib/**/*.{ts,tsx}',
  './middleware.ts',
],
```

---

#### P2 — Medium

**[P2-01] `darkMode: 'class'` in Tailwind is configured but zero `dark:` classes exist**

- **Files**: `frontend/tailwind.config.ts` line 4, `frontend/app/globals.css` line 15
- **Severity**: Medium — dead configuration creates future confusion and bundle overhead

`tailwind.config.ts` declares `darkMode: 'class'`, which causes Tailwind to generate
a `dark:` variant for every utility class. With 0 `dark:` usages across the entire
component tree (confirmed by grep), this adds CSS variant overhead for no benefit.
`globals.css` correctly documents this via `color-scheme: light` and its comment, but
the configuration inconsistency will mislead future contributors.

**Options**:
1. **Remove `darkMode: 'class'`** — eliminates dead variant generation, truest
   representation of current state. Add it back when dark mode is actually built.
2. **Keep it but add a `// TODO: dark mode — no components use dark: yet` comment**
   directly in `tailwind.config.ts` rather than only in `globals.css`.

Option 1 is recommended; Tailwind's CSS output is smaller without the variant, and
the config change is trivial to revert.

---

**[P2-02] Duplicate animation definitions between `tailwind.config.ts` and `globals.css`**

- **Files**: `frontend/tailwind.config.ts` lines 76-115, `frontend/app/globals.css` lines 157-176
- **Severity**: Medium — keyframe names are defined once but animation shorthand is duplicated

The keyframes (`slideDown`, `slideUp`, `fadeIn`, `scaleIn`, `shimmer`) are
canonically in `tailwind.config.ts` as Tailwind keyframes. The `globals.css` adds
hand-written `.animate-*` CSS classes that duplicate the animation timing values:

```css
/* globals.css — duplicates what tailwind.config.ts already provides as animate-slide-down */
.animate-slideDown { animation: slideDown 0.2s ease-out; }
```

But Tailwind generates `animate-slide-down` (kebab-case) from the config's
`'slide-down': 'slideDown 0.2s ease-out'` animation entry. The two naming conventions
(`animate-slide-down` from Tailwind vs `.animate-slideDown` from CSS) coexist for
backward compatibility with markup, but this is fragile: a timing change updated in
only one place will create visual inconsistencies.

The comment in `globals.css` acknowledges this ("kept here for backwards-compat"),
but the correct long-term fix is to migrate all markup to use the Tailwind utility
classes and remove the CSS class duplicates.

**Fix path**:
1. Grep for usages of `.animate-slideDown`, `.animate-fadeIn`, etc. in JSX markup
2. Replace with Tailwind equivalents (`animate-slide-down`, `animate-fade-in`, etc.)
3. Remove the CSS class block from `globals.css` (lines 157-176)
4. Remove the comment about backward compatibility

---

**[P2-03] `shimmer` animation duration inconsistency: 2s in CSS vs 1.5s in Tailwind config**

- **Files**: `frontend/app/globals.css` line 174, `frontend/tailwind.config.ts` line 84
- **Severity**: Medium — visible timing discrepancy between skeleton and shimmer usages

In `globals.css`:
```css
/* .animate-shimmer uses 2s */
.animate-shimmer { animation: shimmer 2s linear infinite; }
/* .skeleton uses 1.5s */
animation: shimmer 1.5s ease-in-out infinite;
```

In `tailwind.config.ts`:
```ts
/* Tailwind animate-shimmer uses 1.5s ease-in-out */
'shimmer': 'shimmer 1.5s ease-in-out infinite',
```

Three different animation profiles use the same `shimmer` keyframe with three
different timings (2s/linear, 1.5s/ease-in-out, 1.5s/ease-in-out). The `.skeleton`
class and the Tailwind utility agree at 1.5s, but `.animate-shimmer` in CSS is 2s.
Any component using `.animate-shimmer` directly will animate noticeably slower than
one using `.skeleton` or `animate-shimmer` (the Tailwind utility).

**Fix**: Standardise to 1.5s ease-in-out everywhere. Update `globals.css` line 174:
```css
.animate-shimmer {
  animation: shimmer 1.5s ease-in-out infinite;
  background-size: 200% 100%;
}
```

---

**[P2-04] `jest.config.js` has no `coverageReporters` — CI coverage format is undefined**

- **File**: `frontend/jest.config.js`
- **Severity**: Medium — `jest --ci --coverage` produces lcov by default but no HTML or JSON Summary

The config sets a `coverageThreshold` (80% across all metrics) but does not specify
`coverageReporters`. Jest defaults to `['text', 'lcov']` in CI mode. This means:
- No `json-summary` reporter, so coverage data is not machine-readable for PR comments
- No HTML report for local inspection
- Potentially no integration with Vercel or GitHub Actions step summaries

Recommended addition:
```js
const customJestConfig = {
  // ...existing config...
  coverageReporters: ['text', 'lcov', 'json-summary', 'html'],
  coverageDirectory: '<rootDir>/coverage',
}
```

`json-summary` enables coverage badge generation and PR comment annotations via
`jest-coverage-report-action`.

---

**[P2-05] `postcss.config.js` uses CommonJS `module.exports` while the project is ESM-capable**

- **File**: `frontend/postcss.config.js`
- **Severity**: Low-Medium — inconsistency with the TypeScript-first config convention

`tailwind.config.ts` is a proper TypeScript file. `postcss.config.js` is plain
CommonJS. There is no functional problem today, but when the project eventually
enables `"type": "module"` in `package.json` (likely with Next.js 17 or Tailwind 4
migration), this file will break.

**Fix** (rename and convert):
```js
// postcss.config.mjs
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

Next.js supports both `.js` (CommonJS) and `.mjs` (ESM) for PostCSS config, so this
is a safe rename.

---

**[P2-06] `globals.css` chart tokens define colors as hex strings; token system uses hex directly**

- **File**: `frontend/app/globals.css` lines 77-89
- **Severity**: Medium — inconsistency with the space-separated RGB pattern used for all other tokens

The surface/primary/semantic tokens all use the space-separated RGB value pattern
that enables `rgb(var(--token) / opacity)` usage with Tailwind:
```css
--color-background: 249 250 251;   /* space-separated R G B */
--color-primary: 59 130 246;
```

But the chart tokens use full hex values:
```css
--chart-1: #3b82f6;
--chart-grid: #e5e7eb;
--chart-axis: #6b7280;
```

The chart tokens are consumed exclusively by Recharts props and `chartTokens.ts`
CSS `var()` references — they are never used in `bg-[var(--chart-1)]` Tailwind
classes — so the inconsistency is not a functional bug today. However, if a future
chart needs opacity control (e.g. `rgba(var(--chart-1), 0.5)`), the hex format will
not work with that pattern.

The `chartColor` object in `chartTokens.ts` correctly uses `var(--chart-*)` references,
so Recharts components that need opacity on chart fills will need to hardcode opacity
or convert to RGB tuples at that point. Consider standardising upfront:

```css
/* Convert to space-separated RGB to enable opacity control later */
--chart-1: 59 130 246;    /* blue-500 */
--chart-2: 34 197 94;     /* green-500 */
```

And update `chartTokens.ts` to use `rgb(var(--chart-1))` format for Recharts props.

---

#### P3 — Low

**[P3-01] `tailwind.config.ts` has `plugins: []` — explicit empty array is unnecessary noise**

- **File**: `frontend/tailwind.config.ts`, line 121

An empty `plugins` array is Tailwind's default. The explicit declaration adds four
characters of noise and implies there might have been plugins that were removed.

```ts
// Remove this line — it's the default
plugins: [],
```

---

**[P3-02] `chartTokens.ts` places its `import type React` at the bottom of the file**

- **File**: `frontend/lib/constants/chartTokens.ts`, line 66

The file exports a `React.CSSProperties` typed constant and defers the import to the
very last line:
```ts
// React import needed for CSSProperties type above
import type React from 'react'
```

While TypeScript hoists type-only imports at compile time and this causes no runtime
bug, it violates the conventional "imports at the top of the file" structure enforced
by `import/order` (if that rule is ever added to ESLint). It also reads oddly: a
reader sees `React.CSSProperties` on line 53 before understanding where `React` comes
from.

**Fix** — move the import to line 1:
```ts
import type React from 'react'
```

---

**[P3-03] `transitionTimingFunction: 'ease-spring'` is a misnomer for a linear easing curve**

- **File**: `frontend/tailwind.config.ts`, line 117

```ts
transitionTimingFunction: {
  'ease-spring': 'cubic-bezier(0.4, 0, 0.2, 1)',
},
```

`cubic-bezier(0.4, 0, 0.2, 1)` is the Material Design "standard easing" — a gentle
ease-in/ease-out. It is not a spring animation (which would use a CSS `linear()`
function with oscillating control points, or a JS spring physics library). The name
`ease-spring` will mislead developers expecting bounce/overshoot behavior.

**Fix**: rename to a descriptor that matches the actual curve:
```ts
transitionTimingFunction: {
  'ease-standard': 'cubic-bezier(0.4, 0, 0.2, 1)',
},
```

Or, if a true spring feel is desired, use:
```ts
'ease-spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)',  // gentle overshoot
```

This is a cosmetic/documentation-level issue with no runtime impact.

---

**[P3-04] `globals.css` `.recharts-tooltip-wrapper` z-index override uses `!important`**

- **File**: `frontend/app/globals.css`, line 179-181

```css
.recharts-tooltip-wrapper {
  z-index: 100 !important;
}
```

The `!important` is a code smell indicating that Recharts' inline z-index style was
winning over this rule. The correct fix depends on context (stacking context of the
chart container), but the `!important` on a non-print rule is the only instance
outside the `@media print` block. It is low risk but worth noting for future
maintainers.

**Fix**: investigate the stacking context causing the conflict and either wrap the
chart container in a properly positioned element or use a CSS layer rule to override
Recharts' inline style without `!important`.

---

**[P3-05] `tsconfig.json` `target: "ES2020"` may be over-conservative for Vercel deployments**

- **File**: `frontend/tsconfig.json`, line 3

Next.js 16 with React 19 targets modern Chromium-based browsers. ES2020 is a
reasonable baseline, but ES2022 unlocks top-level `await`, `Array.at()`, and
`Object.hasOwn()` without needing polyfills. Since Vercel serves the compiled output
(not the raw TypeScript), the `target` here primarily affects which JS syntax TypeScript
emits for type checking. For Next.js projects, `"target": "ESNext"` is the idiomatic
choice because Next.js's own Babel/SWC pipeline handles the actual transpilation.

This is not a bug, but aligning `target` with `lib: ["esnext"]` (already set) would
remove a minor inconsistency.

---

**[P3-06] `package.json` has `@excalidraw/excalidraw` in `devDependencies` but it is used in production**

- **File**: `frontend/package.json`, line 39
- **Severity**: Low — may not matter for Vercel builds but is categorically wrong

```json
"devDependencies": {
  "@excalidraw/excalidraw": "^0.18.0",
```

`components/dev/DiagramEditor.tsx` imports from `@excalidraw/excalidraw`. If Vercel
performs a `npm install --production` (installing only `dependencies`), this component
will fail at runtime. Vercel's default build does install devDependencies during the
build step, which is why this has not surfaced as a problem — but it is wrong
semantically.

`@excalidraw/excalidraw` should move to `dependencies`, or the `DiagramEditor`
component should remain dev-only and be explicitly excluded from production builds
via a feature flag or dynamic import with an environment gate.

---

**[P3-07] `autoprefixer` version is pinned to `^10.4.27` but PostCSS 8.5.x is present**

- **File**: `frontend/package.json`

Autoprefixer 10.4.x is the correct companion for PostCSS 8. No issue here today, but
note that PostCSS 9 is in development and will require Autoprefixer 11. This is a
watch item, not a fix item.

---

### Statistics

| Severity | Count | Files Affected |
|----------|-------|----------------|
| P0 — Critical | 1 | `next.config.js` |
| P1 — High | 4 | `next.config.js`, `__mocks__/better-auth-react.js`, `tsconfig.json`, `.eslintrc.json`, `tailwind.config.ts` |
| P2 — Medium | 6 | `tailwind.config.ts`, `globals.css`, `jest.config.js`, `postcss.config.js`, `globals.css` (tokens) |
| P3 — Low | 7 | `tailwind.config.ts`, `chartTokens.ts`, `globals.css`, `tsconfig.json`, `package.json` |
| **Total** | **18** | **8 distinct files** |

### Files Reviewed

| File | Lines | Status |
|------|-------|--------|
| `frontend/tailwind.config.ts` | 124 | Issues: P1-05, P2-01, P2-02, P2-03, P3-01, P3-03 |
| `frontend/postcss.config.js` | 6 | Issues: P2-05 |
| `frontend/app/globals.css` | 261 | Issues: P2-02, P2-03, P2-06, P3-04 |
| `frontend/jest.config.js` | 33 | Issues: P2-04 |
| `frontend/tsconfig.json` | 42 | Issues: P1-03, P3-05 |
| `frontend/package.json` | 61 | Issues: P3-06 |
| `frontend/.eslintrc.json` | 23 | Issues: P1-04 |
| `frontend/next.config.js` | 96 | Issues: P0-01, P1-01 |
| `frontend/lib/constants/chartTokens.ts` | 66 | Issues: P3-02 |
| `frontend/lib/constants/regions.ts` | 118 | No issues |
| `frontend/__mocks__/better-auth-react.js` | 31 | Issues: P1-02 |
| `frontend/jest.setup.js` | 47 | No issues |
| `frontend/scripts/patch-jsdom-location.js` | 107 | No issues (well-documented) |

### Strengths Observed

- Chart design token abstraction (`chartTokens.ts`) is excellent: all four chart
  components consume tokens via the shared module, no hardcoded hex colors appear in
  chart props outside of the Google OAuth SVG brand marks (which are intentionally
  hardcoded per Google's branding requirements).
- The jsdom 26 postinstall patch is well-implemented with idempotent marker checking
  and clear documentation.
- Print media query styles are thorough and well-commented.
- `globals.css` space-separated RGB token convention enables opacity composition with
  Tailwind without needing CSS preprocessors.
- `next.config.js` build-time env var validation (`NEXT_PUBLIC_APP_URL` required in
  production) is a good practice that prevents silent misconfiguration at deploy time.
- `tsconfig.json` uses `"strict": true` and `"isolatedModules": true`, which are
  the correct settings for a Next.js + SWC project.
- ESLint test file overrides are correctly scoped to `**/__tests__/**` and
  `**/*.test.*`, preventing permissive test rules from leaking into production code.
- `legacy-peer-deps=true` in `.npmrc` is correctly scoped to the frontend directory
  rather than being a global npm setting, limiting its blast radius.
