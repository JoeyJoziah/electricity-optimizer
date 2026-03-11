# RateShift Frontend

Modern Next.js 16 + React 19 frontend for electricity price optimization and cost management.

## Overview

RateShift's frontend provides a comprehensive dashboard for users to monitor electricity rates, manage connections, receive price alerts, and get AI-powered optimization recommendations. Built with cutting-edge React 19 and TypeScript, it delivers a responsive, accessible experience across all devices.

**Live**: https://rateshift.app

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **UI Library**: React 19 with TypeScript
- **Styling**: Tailwind CSS with custom design tokens
- **State Management**: TanStack Query v5 (server state), React Context (auth/UI state)
- **Forms**: React Hook Form + custom Input component
- **API Client**: Fetch API with auth interceptors
- **Testing**: Jest + React Testing Library (1,439+ unit tests)
- **E2E Testing**: Playwright (634 tests)
- **Accessibility**: jest-axe (51 tests), WCAG AA compliant
- **Charts**: Recharts for data visualization
- **Email**: Resend SDK + nodemailer fallback
- **Notifications**: OneSignal SDK v3+ for push notifications
- **Dev Tools**: TypeScript, ESLint, OpenAPI type generation

## Project Structure

```
frontend/
├── app/                          # Next.js App Router
│   ├── layout.tsx               # Root layout (all pages)
│   ├── globals.css              # Global styles + design tokens
│   ├── (dev)/                   # Dev-only routes
│   │   └── architecture/        # Architecture diagram editor
│   ├── page.tsx                 # Home page (/)
│   ├── pricing/                 # Pricing page (/pricing)
│   ├── privacy/                 # Privacy policy (/privacy)
│   ├── terms/                   # Terms of service (/terms)
│   └── (app)/                   # Authenticated app routes (sidebar layout)
│       ├── layout.tsx           # Sidebar + navigation
│       ├── dashboard/           # Home dashboard
│       ├── prices/              # Current electricity prices
│       ├── suppliers/           # Available suppliers
│       ├── connections/         # Utility account connections
│       ├── optimize/            # AI optimization recommendations
│       ├── alerts/              # Price threshold alerts + history
│       ├── assistant/           # AI agent chat interface
│       ├── settings/            # User account settings
│       ├── onboarding/          # First-time user setup
│       ├── beta-signup/         # Early access sign-up
│       └── auth/                # Authentication flows
│           ├── login/
│           ├── signup/
│           ├── callback/        # OAuth callback
│           ├── verify-email/
│           ├── forgot-password/
│           └── reset-password/
├── components/
│   ├── ui/                      # Core UI components
│   │   ├── input.tsx            # Enhanced text input (labelSuffix, success state)
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── badge.tsx
│   │   ├── modal.tsx
│   │   ├── skeleton.tsx
│   │   └── toast.tsx
│   ├── auth/                    # Auth form components
│   │   ├── LoginForm.tsx
│   │   ├── SignupForm.tsx
│   │   ├── ForgotPasswordForm.tsx
│   │   ├── ResetPasswordForm.tsx
│   │   └── VerifyEmailForm.tsx
│   ├── alerts/                  # Alert management
│   │   ├── AlertForm.tsx        # Region, threshold, optimal window selection
│   │   ├── AlertsList.tsx
│   │   └── AlertHistory.tsx
│   ├── connections/             # Connection management
│   │   ├── ConnectionsOverview.tsx
│   │   ├── DirectLoginForm.tsx
│   │   ├── BillUploadForm.tsx
│   │   └── BillViewer.tsx
│   ├── agent/                   # AI agent interface
│   │   ├── AgentChat.tsx        # Message thread UI
│   │   ├── AgentControls.tsx    # Query/task submission
│   │   └── AgentUsage.tsx       # Rate limit display
│   ├── notifications/
│   │   ├── NotificationBell.tsx # Sidebar icon + dropdown
│   │   └── NotificationCenter.tsx
│   ├── pricing/                 # Pricing page components
│   ├── dashboard/               # Dashboard widgets + charts
│   ├── suppliers/               # Supplier comparison UI
│   └── providers/               # Context providers
│       ├── QueryProvider.tsx    # TanStack Query setup
│       └── ...other providers
├── lib/
│   ├── hooks/                   # Custom React hooks
│   │   ├── useAuth.ts          # Auth state + login/logout/signup
│   │   ├── useAgent.ts         # AI agent (stream/task/usage)
│   │   ├── useAlerts.ts        # Alert CRUD + history
│   │   ├── useConnections.ts   # Connections list + OAuth
│   │   ├── useNotifications.ts # Push notification state
│   │   ├── usePrices.ts        # Current + historical prices
│   │   ├── useSuppliers.ts     # Supplier list + details
│   │   ├── useSavings.ts       # Savings calculation
│   │   ├── useOptimization.ts  # Optimization recommendations
│   │   ├── useProfile.ts       # User profile data
│   │   └── ...other hooks
│   ├── api/                     # API client functions
│   │   ├── auth.ts
│   │   ├── alerts.ts
│   │   ├── prices.ts
│   │   ├── connections.ts
│   │   ├── agent.ts
│   │   └── ...other endpoints
│   ├── contexts/                # React contexts
│   │   ├── toast-context.tsx
│   │   └── ...other contexts
│   ├── utils/                   # Utility functions
│   │   ├── url.ts              # isSafeRedirect()
│   │   ├── format.ts
│   │   └── ...other utils
│   ├── email/                   # Email utilities
│   │   └── send.ts             # Resend + nodemailer fallback
│   ├── analytics/               # Analytics setup
│   │   └── clarity.ts          # Microsoft Clarity script
│   └── types/                   # TypeScript type definitions
├── __tests__/                   # Test files (mirror structure)
│   ├── components/
│   ├── lib/
│   ├── a11y/                   # Accessibility tests (jest-axe)
│   └── ...
├── e2e/                         # Playwright E2E tests
│   ├── auth.spec.ts
│   ├── dashboard.spec.ts
│   ├── alerts.spec.ts
│   └── ...
├── public/                      # Static assets
│   └── ...
└── package.json
```

## Key Pages

| Route | Purpose | Auth Required |
|-------|---------|---|
| `/` | Marketing home page | No |
| `/pricing` | Pricing plans and features | No |
| `/privacy` | Privacy policy | No |
| `/terms` | Terms of service | No |
| `/auth/login` | User login | No |
| `/auth/signup` | New user registration | No |
| `/auth/callback` | OAuth callback handler | No |
| `/auth/verify-email` | Email verification | No |
| `/auth/forgot-password` | Password reset request | No |
| `/auth/reset-password` | Password reset form | No |
| `/dashboard` | Main dashboard (account overview) | Yes |
| `/prices` | Current and historical prices | Yes |
| `/suppliers` | Available utility suppliers | Yes |
| `/connections` | Manage utility account connections | Yes |
| `/alerts` | Create and manage price alerts | Yes |
| `/optimize` | AI-powered recommendations | Yes |
| `/assistant` | AI agent chat interface | Yes |
| `/settings` | Account and billing settings | Yes |
| `/onboarding` | First-time user setup flow | Yes |
| `/beta-signup` | Early access registration | No |
| `/architecture` | Architecture diagram (dev only) | Yes + dev mode |

## Design System

### CSS Variables (globals.css)

- **Colors**: `--primary-*`, `--danger-*`, `--success-*`, `--gray-*` (Tailwind scale)
- **Spacing**: Standard Tailwind scale (rem-based)
- **Shadows**: `--card-shadow`, `--card-hover-shadow`, `--input-focus-shadow`
- **Animations**: `slide-down`, `slide-up`, `fade-in`, `scale-in`, `shimmer`

### Component Library

All pages use standardized `components/ui/` components with consistent styling. The enhanced `Input` component supports:

```typescript
<Input
  label="Email"
  labelSuffix="(required)"     // Optional text after label
  labelRight="Verified"        // Optional text on right
  success={isValid}            // Green checkmark
  successText="Email confirmed" // Text below input
  {...register('email')}
/>
```

## State Management

### TanStack Query (Server State)

```typescript
const { data: prices, isLoading, error } = usePrices();
const { mutate: createAlert } = useCreateAlert();
```

Benefits:
- Automatic caching and synchronization
- Stale time management (default 30s)
- Automatic refetch on window focus
- Built-in retry logic

### React Context (UI State)

- **AuthProvider**: User session, login/logout
- **ToastProvider**: Toast notifications
- **QueryProvider**: TanStack Query client

## API Integration

### Proxy Architecture

All API calls go through Next.js route rewrites:

```
Frontend: /api/v1/*
  -> Next.js rewrite
  -> BACKEND_URL=https://api.rateshift.app
  -> Cloudflare Worker
  -> Render origin
```

Session cookies pass transparently through the proxy.

### Environment Variables

```env
# Public (exposed to browser)
NEXT_PUBLIC_API_URL=/api/v1
NEXT_PUBLIC_OAUTH_GOOGLE_ENABLED=true
NEXT_PUBLIC_OAUTH_GITHUB_ENABLED=true

# Server-side only
BACKEND_URL=https://api.rateshift.app
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
EMAIL_FROM_ADDRESS=RateShift <noreply@rateshift.app>
```

## Development

### Install Dependencies

```bash
npm install
```

### Start Development Server

```bash
npm run dev
```

Server runs on http://localhost:3000. API calls are proxied to `BACKEND_URL`.

### Build for Production

```bash
npm run build
npm start
```

### Type Checking

```bash
npm run type-check
```

### Generate OpenAPI Types

```bash
npm run generate-types           # From live API
npm run generate-types:offline   # From saved OpenAPI spec
```

## Testing

### Unit Tests (Jest + React Testing Library)

```bash
npm test                    # Watch mode
npm run test:ci             # CI mode with coverage (80% threshold)
```

Coverage report in `coverage/`. Key patterns:

- Mock Better Auth via `__mocks__/better-auth-react.js`
- Use `@testing-library/react` for component testing
- Test accessibility with jest-axe (51 tests across 19 pages, 3 layouts)

### E2E Tests (Playwright)

```bash
npx playwright test                # Run all tests
npx playwright test --headed       # See browser
npx playwright test auth.spec.ts   # Single file
```

634 E2E tests cover auth flows, dashboard, alerts, connections, and critical paths. Retry logic handles timing flakes. Extended timeouts for API operations.

### Coverage Thresholds

- Branches: 80%
- Functions: 80%
- Lines: 80%
- Statements: 80%

## Performance

### Page Load Metrics

- Target: First Contentful Paint <1.5s
- Image optimization: Next.js `<Image>` component
- Code splitting: Automatic via route-based chunks
- Lazy loading: Suspense + React.lazy for heavy components

### Build Output

- Bundle size: ~150-200 KiB (gzipped)
- CSS-in-JS: Tailwind (static, no runtime overhead)
- JavaScript: Minified + tree-shaken

## Security

### Authentication

- Session-based via Better Auth
- httpOnly cookies with `__Secure-` prefix on HTTPS
- Email verification on signup
- Password reset via secure magic links
- OAuth (Google, GitHub) optional

### Content Security Policy (CSP)

Configured in `next.config.js`:

```
script-src 'self' https://*.clarity.ms
style-src 'self' 'unsafe-inline'
img-src 'self' data: https:
```

### API Security

- All API calls through Next.js proxy (prevents direct origin exposure)
- X-API-Key required on internal endpoints (server-side only)
- Request body size limit: 10 MB
- Request timeout: 30s (proxy via Cloudflare Worker)

## Known Issues & Patterns

- **Form authentication**: Use `FormData` for file uploads (BillUploadForm)
- **OneSignal**: Call `loginOneSignal(userId)` AFTER auth completes (in useAuth hook)
- **Safe redirects**: Use `isSafeRedirect()` from `lib/utils/url.ts` (prevents open redirects)
- **Promise timeout**: Frontend forms use `Promise.race` with 15s timeout for client-side timeout
- **Flash of content**: Use `useState<boolean|null>(null)` to guard against hydration mismatch

## Deployment

### Vercel

Frontend deploys automatically on push to `main` or PR creation. Custom domains: `rateshift.app` and `www.rateshift.app`.

Pre-deployment checks:
- `npm run type-check` passes
- `npm run test:ci` passes (80% coverage)
- `npx playwright test` passes

## Contributing

1. Follow Tailwind/React 19 patterns
2. Add tests for new components (jest-axe for a11y)
3. Update `components/ui/` for shared components
4. Use custom hooks from `lib/hooks/`
5. Ensure TypeScript strict mode compliance

## Resources

- [Next.js 16 Docs](https://nextjs.org/docs)
- [React 19 Docs](https://react.dev)
- [TanStack Query Docs](https://tanstack.com/query/latest)
- [Tailwind CSS Docs](https://tailwindcss.com/docs)
- [Better Auth Docs](https://www.better-auth.com/)
