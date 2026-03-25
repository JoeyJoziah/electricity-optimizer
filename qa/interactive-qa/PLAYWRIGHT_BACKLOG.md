# Playwright E2E Test Backlog -- RateShift

> Created: 2026-03-25
> Updated: 2026-03-25
> Existing specs: 25 (1,605 tests across 5 browsers)

## Current E2E Coverage

| Spec | Area | Tests |
|------|------|-------|
| authentication.spec.ts | Auth flows | Signup, login, logout |
| onboarding.spec.ts | Onboarding wizard | Basic flow |
| onboarding-flow.spec.ts | Onboarding wizard | Extended scenarios |
| dashboard.spec.ts | Dashboard | Main view |
| dashboard-tabs.spec.ts | Dashboard | Utility tabs |
| prices.spec.ts | Prices | Price display |
| sse-streaming.spec.ts | Prices | SSE real-time |
| billing-flow.spec.ts | Billing | Stripe checkout |
| community.spec.ts | Community | Posts, votes |
| optimization.spec.ts | Optimize | Load scheduling |
| supplier-selection.spec.ts | Suppliers | Selection flow |
| supplier-switching.spec.ts | Suppliers | Switching flow |
| switching.spec.ts | Switching | Plan switching |
| settings.spec.ts | Settings | User prefs |
| full-journey.spec.ts | E2E journey | Complete user flow |
| api-contracts.spec.ts | API | FE/BE contract checks |
| edge-cases.spec.ts | Edge cases | Boundary conditions |
| matrix.spec.ts | Matrix | Cross-browser |
| performance.spec.ts | Performance | Load times |
| page-load.spec.ts | Performance | Page load metrics |
| visual-regression.spec.ts | Visual | Screenshot diffs |
| accessibility.spec.ts | A11y | WCAG compliance |
| missing-pages.spec.ts | Navigation | 404 handling |
| mobile.spec.ts | Responsive | Mobile layouts |
| gdpr-compliance.spec.ts | Compliance | GDPR flows |

## Missing / Needed Tests

| Priority | Area | Description | Triggered By |
|----------|------|-------------|--------------|
| P0 | Connections | No E2E spec for connection creation (any type) | Gap analysis |
| P0 | AI Assistant | No E2E spec for /assistant chat flow | Gap analysis |
| P0 | Alerts | No E2E spec for /alerts CRUD + history | Gap analysis |
| P1 | Notifications | No E2E spec for NotificationBell behavior | Gap analysis |
| P1 | Google OAuth | No test for Google OAuth (button exists but will fail) | LG-001 |
| P1 | Tier gating | No E2E spec for paywall/upgrade prompt UX | Gap analysis |
| P2 | Public rates | No E2E spec for /rates/[state]/[utility] pages | Gap analysis |
| P2 | Analytics | No E2E spec for /analytics charts | Gap analysis |

## Flaky / Needs Repair

_(Will populate as issues are discovered during interactive testing)_
