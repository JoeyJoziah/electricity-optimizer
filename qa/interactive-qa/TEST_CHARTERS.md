# Interactive QA Test Charters -- RateShift

> Created: 2026-03-25
> Campaign: User-driven interactive QA with Claude-in-Chrome instrumentation

---

## Charter Index

| ID | Area | Risk | Status |
|----|------|------|--------|
| TC-001 | Auth: Signup + Email Verification | High | Not started |
| TC-002 | Auth: Login (email + GitHub OAuth) | High | Not started |
| TC-003 | Auth: Google OAuth | High | Not started |
| TC-004 | Auth: Password Reset | Medium | Not started |
| TC-005 | Onboarding Wizard | High | Not started |
| TC-006 | Dashboard: Main + Setup Checklist | High | Not started |
| TC-007 | Dashboard: Utility Tabs (Gas, Oil, Propane, Water, Solar) | Medium | Not started |
| TC-008 | Prices: Real-Time + SSE Streaming | High | Not started |
| TC-009 | Connections: UtilityAPI Direct Sync | High | Not started |
| TC-010 | Connections: Bill Upload | High | Not started |
| TC-011 | Connections: Email OAuth Import | High | Not started |
| TC-012 | Connections: Portal Scrape | Medium | Not started |
| TC-013 | Optimize: Load Scheduling | Medium | Not started |
| TC-014 | Suppliers: Comparison + Selection | Medium | Not started |
| TC-015 | Alerts: CRUD + History | Medium | Not started |
| TC-016 | AI Assistant: Chat + SSE Streaming | High | Not started |
| TC-017 | Billing: Stripe Checkout + Plan Upgrade | High | Not started |
| TC-018 | Billing: Tier Gating (Free vs Pro vs Business) | High | Not started |
| TC-019 | Settings: Profile + Preferences | Low | Not started |
| TC-020 | Community: Posts + Voting + Reporting | Medium | Not started |
| TC-021 | Analytics: Usage Charts | Low | Not started |
| TC-022 | Notifications: Push + Bell | Medium | Not started |
| TC-023 | Public Pages: Landing, Pricing, Terms, Privacy | Low | Not started |
| TC-024 | Public Rates: /rates/[state]/[utility] SEO pages | Low | Not started |
| TC-025 | Mobile Responsive: Sidebar + Key Flows | Medium | Not started |
| TC-026 | Error Handling: 404, Error Boundaries, Offline | Medium | Not started |
| TC-027 | Performance: Page Load, API Latency, Cold Starts | High | Not started |
| TC-028 | Security: CORS, CSP, Auth Bypass Attempts | High | Not started |

---

## Charter Details

### TC-001: Auth -- Signup + Email Verification
- **Area**: Authentication & Onboarding
- **Risk**: HIGH
- **Flow**: Landing -> "Get Started" -> Signup form -> Email verification -> Redirect to onboarding
- **Problem spots**:
  - Resend email delivery reliability (100/day free tier limit)
  - Email verification link expiry and error handling
  - Better Auth `{data, error}` contract -- never throws, must handle both
  - Input validation edge cases (long names, unicode, duplicate emails)
- **Existing E2E**: `authentication.spec.ts` covers basic flow

### TC-002: Auth -- Login (Email + GitHub OAuth)
- **Area**: Authentication
- **Risk**: HIGH
- **Flow**: Login page -> Email/password OR GitHub OAuth -> Redirect to dashboard
- **Problem spots**:
  - GitHub OAuth callback URL correctness (App ID 3466397)
  - Session persistence across tabs/refreshes
  - Wrong password error messaging
  - Rate limiting on login attempts
- **Existing E2E**: `authentication.spec.ts`

### TC-003: Auth -- Google OAuth
- **Area**: Authentication
- **Risk**: HIGH -- KNOWN GAP (LG-001)
- **Flow**: Login page -> Google button -> OAuth consent -> Callback -> Dashboard
- **Problem spots**:
  - **Client secret never captured** -- button will likely fail entirely
  - GOOGLE_CLIENT_ID/SECRET are placeholder on Render
  - OAuth state HMAC validation (5-part format with 10-min expiry)
- **Existing E2E**: None
- **Notes**: Likely a BLOCKER. Test to confirm failure mode, then decide if we fix or disable the button.

### TC-004: Auth -- Password Reset
- **Area**: Authentication
- **Risk**: MEDIUM
- **Flow**: Login -> "Forgot password" -> Enter email -> Check email -> Reset link -> New password -> Login
- **Problem spots**:
  - Email delivery (Resend primary, Gmail SMTP fallback)
  - Token expiry UX
  - Password strength validation consistency FE/BE

### TC-005: Onboarding Wizard
- **Area**: Onboarding
- **Risk**: HIGH
- **Flow**: Post-signup redirect -> Region selection -> Utility provider -> Plan type -> Dashboard
- **Problem spots**:
  - Region enum completeness (50 states + DC)
  - Utility provider data availability per state
  - Wizard state persistence if user refreshes mid-flow
  - Skip/back navigation behavior

### TC-006: Dashboard -- Main + Setup Checklist
- **Area**: Core Dashboard
- **Risk**: HIGH
- **Flow**: Authenticated user -> /dashboard -> See setup checklist, summary cards, recent data
- **Problem spots**:
  - Empty state when no connections exist
  - Setup checklist dynamic status (Suppliers green dot)
  - Loading skeleton appearance
  - Data freshness after connection setup
- **Existing E2E**: `dashboard.spec.ts`, `dashboard-tabs.spec.ts`

### TC-007: Dashboard -- Utility Tabs (Gas, Oil, Propane, Water, Solar)
- **Area**: Multi-utility dashboards
- **Risk**: MEDIUM
- **Flow**: Sidebar -> Gas Rates / Heating Oil / Propane / Water / Solar -> View data or empty states
- **Problem spots**:
  - Natural Gas was previously broken (LG-002 FIXED) -- verify fix holds
  - Each tab should show appropriate empty state if no data
  - Community Solar may have limited data
- **Existing E2E**: `dashboard-tabs.spec.ts`

### TC-008: Prices -- Real-Time + SSE Streaming
- **Area**: Core Feature (Business tier)
- **Risk**: HIGH
- **Flow**: /prices -> View current rates -> SSE stream updates -> Filter by region
- **Problem spots**:
  - SSE connection lifecycle (connect, reconnect on drop, cleanup)
  - Tier gating (Business-only for SSE streaming)
  - Circuit breaker fallback when CF Worker returns 502/503
  - Price data staleness indicators
- **Existing E2E**: `prices.spec.ts`, `sse-streaming.spec.ts`

### TC-009: Connections -- UtilityAPI Direct Sync
- **Area**: Utility Integration
- **Risk**: HIGH
- **Flow**: /connections -> "Add Connection" -> UtilityAPI -> Authorize -> Auto-sync
- **Problem spots**:
  - UTILITYAPI_KEY is MISSING on Render
  - OAuth state validation (HMAC, 10-min expiry)
  - Connection status polling/refresh
  - Error handling on API failures
  - CORS through CF Worker proxy
- **Existing E2E**: None specific to connections

### TC-010: Connections -- Bill Upload
- **Area**: Utility Integration
- **Risk**: HIGH
- **Flow**: /connections -> "Upload Bill" -> Select file -> Extract rates -> Show results
- **Problem spots**:
  - File type validation (PDF, image formats)
  - Extraction accuracy from different bill formats
  - Large file handling
  - Error messaging on extraction failure

### TC-011: Connections -- Email OAuth Import
- **Area**: Utility Integration
- **Risk**: HIGH
- **Flow**: /connections -> "Email Import" -> OAuth (Gmail/Outlook) -> Scan emails -> Extract rates
- **Problem spots**:
  - GMAIL_CLIENT_ID/SECRET MISSING on Render
  - OUTLOOK_CLIENT_ID/SECRET MISSING on Render
  - OAuth callback flow reliability
  - Email scanning batch processing

### TC-012: Connections -- Portal Scrape
- **Area**: Utility Integration
- **Risk**: MEDIUM
- **Flow**: /connections -> "Portal Login" -> Enter utility credentials -> Scrape rates
- **Problem spots**:
  - AES-256-GCM encrypted credential storage
  - 5 supported utilities (Duke, PG&E, Con Edison, ComEd, FPL)
  - Scrape timing and rate limiting
  - Credential error handling

### TC-013: Optimize -- Load Scheduling
- **Area**: Core Feature
- **Risk**: MEDIUM
- **Flow**: /optimize -> View optimal windows -> Schedule high-energy tasks
- **Problem spots**:
  - ML forecast data dependency
  - Time zone handling
  - Empty state when no price data available
- **Existing E2E**: `optimization.spec.ts`

### TC-014: Suppliers -- Comparison + Selection
- **Area**: Core Feature
- **Risk**: MEDIUM
- **Flow**: /suppliers -> Browse suppliers -> Compare rates -> Select current supplier
- **Problem spots**:
  - Supplier data freshness
  - Rate comparison accuracy
  - Selection persists in settings store
  - Green dot indicator in sidebar
- **Existing E2E**: `supplier-selection.spec.ts`, `supplier-switching.spec.ts`

### TC-015: Alerts -- CRUD + History
- **Area**: Notifications
- **Risk**: MEDIUM
- **Flow**: /alerts -> Create alert (region, threshold, window) -> View history -> Edit/delete
- **Problem spots**:
  - AlertForm validation (region enum, threshold bounds)
  - Free tier: 1 alert limit enforcement
  - Dedup cooldowns (immediate=1h, daily=24h, weekly=7d)
  - History tab data population

### TC-016: AI Assistant -- Chat + SSE Streaming
- **Area**: AI Feature (tiered)
- **Risk**: HIGH
- **Flow**: /assistant -> Type question -> SSE stream response -> Follow-up
- **Problem spots**:
  - Gemini 3 Flash rate limits (10 RPM/250 RPD free)
  - Groq Llama 3.3 fallback on 429
  - Rate limits: Free=3/day, Pro=20/day, Business=unlimited
  - SSE streaming disconnect/reconnect
  - Usage counter accuracy
  - WCAG accessibility of AgentChat component (recently overhauled)
- **Existing E2E**: None

### TC-017: Billing -- Stripe Checkout + Plan Upgrade
- **Area**: Payments
- **Risk**: HIGH
- **Flow**: Settings or paywall -> Choose plan -> Stripe checkout -> Return -> Verify upgrade
- **Problem spots**:
  - Stripe test vs live mode
  - Webhook delivery (payment_failed resolves via stripe_customer_id)
  - Return URL correctness
  - Plan change mid-billing-cycle
- **Existing E2E**: `billing-flow.spec.ts`
- **CAUTION**: Do NOT trigger real charges. Use Stripe test cards only.

### TC-018: Billing -- Tier Gating
- **Area**: Payments / Access Control
- **Risk**: HIGH
- **Flow**: Free user -> Try accessing Pro/Business feature -> See paywall/upgrade prompt
- **Problem spots**:
  - `require_tier()` gates 7+ endpoints
  - 30s cache TTL (in-memory + Redis)
  - Correct feature mapping per tier
  - Graceful paywall UX (not just 403)

### TC-019: Settings -- Profile + Preferences
- **Area**: User Management
- **Risk**: LOW
- **Flow**: /settings -> Update name, email prefs, region -> Save
- **Problem spots**:
  - Form validation
  - Settings persistence across sessions
  - Region dropdown completeness
- **Existing E2E**: `settings.spec.ts`

### TC-020: Community -- Posts + Voting + Reporting
- **Area**: Social Feature
- **Risk**: MEDIUM
- **Flow**: /community -> Create post -> Vote -> Report inappropriate content
- **Problem spots**:
  - AI moderation (Groq classify_content, Gemini fallback, fail-closed 30s)
  - XSS sanitization (nh3)
  - Rate limit: 10 posts/hour
  - Report threshold: 5 unique reporters auto-hides
  - GDPR CASCADE on user deletion
- **Existing E2E**: `community.spec.ts`

### TC-021: Analytics -- Usage Charts
- **Area**: Data Visualization
- **Risk**: LOW
- **Flow**: /analytics -> View consumption charts, cost trends, savings
- **Problem spots**:
  - Chart rendering with no data
  - Date range picker behavior
  - Mobile responsiveness of charts

### TC-022: Notifications -- Push + Bell
- **Area**: Notifications
- **Risk**: MEDIUM
- **Flow**: Trigger event -> Bell icon updates -> Click to view -> Mark read
- **Problem spots**:
  - OneSignal push binding via login(userId)
  - NotificationBell real-time update
  - Empty notifications state
  - Notification preferences in settings

### TC-023: Public Pages -- Landing, Pricing, Terms, Privacy
- **Area**: Marketing / Legal
- **Risk**: LOW
- **Flow**: unauthenticated -> /, /pricing, /terms, /privacy
- **Problem spots**:
  - SEO metadata (OG image MISSING per LG-020)
  - Responsive layout
  - CTA buttons link correctly
  - Pricing page matches actual Stripe plans ($4.99/$14.99)

### TC-024: Public Rates -- /rates/[state]/[utility]
- **Area**: SEO / Public Data
- **Risk**: LOW
- **Flow**: Direct URL or search -> /rates/california/pge -> View rate data
- **Problem spots**:
  - Dynamic route parameter validation
  - Data availability per state/utility combo
  - 404 for invalid state/utility

### TC-025: Mobile Responsive
- **Area**: Cross-device
- **Risk**: MEDIUM
- **Flow**: Resize browser / use mobile device -> Navigate all key flows
- **Problem spots**:
  - Sidebar collapse/hamburger behavior
  - Form inputs on mobile keyboards
  - Chart rendering at narrow widths
  - Touch targets (44px minimum)
- **Existing E2E**: `mobile.spec.ts`

### TC-026: Error Handling -- 404, Boundaries, Offline
- **Area**: Resilience
- **Risk**: MEDIUM
- **Flow**: Navigate to invalid URL -> See 404. Disconnect network -> See offline state. Trigger backend error -> See error boundary.
- **Problem spots**:
  - 29 error boundaries (are they all styled consistently?)
  - Offline detection and recovery
  - API timeout handling (30s via middleware)
  - CF Worker circuit breaker fallback to Render

### TC-027: Performance -- Page Load, API Latency, Cold Starts
- **Area**: Performance
- **Risk**: HIGH
- **Flow**: Fresh navigation to each key page. Measure TTFB, LCP, CLS.
- **Problem spots**:
  - Render free tier cold starts (20-30s after idle) -- CRITICAL for launch (LG-010)
  - CF Worker keepalive cron (*/10 min) mitigates but doesn't eliminate
  - Large dashboard data loads
  - SSE connection establishment time
- **Existing E2E**: `performance.spec.ts`, `page-load.spec.ts`

### TC-028: Security -- CORS, CSP, Auth Bypass
- **Area**: Security
- **Risk**: HIGH
- **Flow**: Inspect headers, attempt cross-origin requests, test unauthenticated access to protected endpoints
- **Problem spots**:
  - CF Worker CORS headers (previously had production failures)
  - Location header rewriting on 3xx redirects (prevents Render URL leak)
  - CSP header completeness
  - Internal endpoints require X-API-Key
  - Swagger/ReDoc disabled in prod
