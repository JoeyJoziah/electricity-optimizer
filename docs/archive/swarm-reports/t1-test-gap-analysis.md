> **DEPRECATED** — This document is archived for historical reference only. It may contain outdated information. See current documentation in the parent `docs/` directory.

---

# T1: Frontend Test Gap Analysis

> Generated: 2026-03-03
> Analyst: test-writer agent (frontend-review-swarm)

---

## Summary

- **Total pages**: 19
- **Pages with tests**: 4 (architecture page, prices page, suppliers page — via `__tests__/pages/`, plus architecture page from `__tests__/app/dev/`)
- **Pages with NO tests**: 15
- **Layouts tested**: 1 of 3 (`(dev)/layout.tsx` has tests)
- **Layouts untested**: 2 (`app/layout.tsx`, `app/(app)/layout.tsx`)
- **Components untested**: 2 (`AccountLinkStep`, `QueryProvider`)

---

## 1. Untested Pages

### Marketing Pages (app root)

| Page | File Path | Notes |
|------|-----------|-------|
| Landing / Home | `frontend/app/page.tsx` | Pure static JSX; renders nav, hero, features grid, pricing preview, footer |
| Pricing | `frontend/app/pricing/page.tsx` | Pure static JSX; 3-tier pricing cards, FAQ, footer |
| Privacy Policy | `frontend/app/privacy/page.tsx` | Pure static content; nav + prose sections |
| Terms of Service | `frontend/app/terms/page.tsx` | Pure static content; nav + prose sections |

---

## Coverage Gap Estimate

Based on `jest.config.js` coverage threshold of 70% across branches/functions/lines/statements:

- `app/**/*.{ts,tsx}` is included in coverage collection
- 15 untested pages + 2 untested layouts represent a significant gap in `app/` coverage
- Current passing count: 1,126 frontend tests across 64 suites
- Estimated tests needed to close gaps: ~120-180 new tests across 17 new test files

---

*This report is an archived analysis of test coverage gaps identified during swarm audits.*
