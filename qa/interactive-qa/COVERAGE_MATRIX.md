# Interactive QA Coverage Matrix -- RateShift

> Created: 2026-03-25
> Updated: 2026-03-25

## Legend

| Status | Meaning |
|--------|---------|
| -- | Not tested |
| IN PROGRESS | Currently being tested |
| PASS | Tested, no issues found |
| ISSUES | Tested, issues logged (see ISSUES.md) |
| BLOCKED | Cannot test (missing config, credentials, etc.) |

---

## Coverage Table

| Flow | Charter | Priority | Status | Notes |
|------|---------|----------|--------|-------|
| Signup + Email Verification | TC-001 | P0 | -- | |
| Login (email + GitHub OAuth) | TC-002 | P0 | -- | |
| Google OAuth | TC-003 | P0 | -- | Known gap: secret not captured (LG-001) |
| Password Reset | TC-004 | P1 | -- | |
| Onboarding Wizard | TC-005 | P0 | -- | |
| Dashboard Main | TC-006 | P0 | ISSUES | IQA-001 fixed (reload loop), needs re-verify |
| Utility Tabs (Gas/Oil/Propane/Water/Solar) | TC-007 | P1 | -- | Gas fixed in LG-002 |
| Prices + SSE Streaming | TC-008 | P0 | -- | Business tier gated |
| Connections: UtilityAPI | TC-009 | P0 | -- | UTILITYAPI_KEY missing |
| Connections: Bill Upload | TC-010 | P0 | -- | |
| Connections: Email Import | TC-011 | P0 | -- | Gmail/Outlook creds missing |
| Connections: Portal Scrape | TC-012 | P1 | -- | |
| Optimize / Load Scheduling | TC-013 | P1 | -- | |
| Suppliers Comparison | TC-014 | P1 | -- | |
| Alerts CRUD + History | TC-015 | P1 | -- | |
| AI Assistant Chat | TC-016 | P0 | -- | Tiered rate limits |
| Billing: Stripe Checkout | TC-017 | P0 | -- | Test cards only! |
| Billing: Tier Gating | TC-018 | P0 | -- | |
| Settings | TC-019 | P2 | -- | |
| Community | TC-020 | P1 | -- | AI moderation |
| Analytics | TC-021 | P2 | -- | |
| Notifications (Push + Bell) | TC-022 | P1 | -- | |
| Public Pages | TC-023 | P2 | -- | OG image missing (LG-020) |
| Public Rates SEO | TC-024 | P2 | -- | |
| Mobile Responsive | TC-025 | P1 | -- | |
| Error Handling | TC-026 | P1 | -- | |
| Performance | TC-027 | P0 | -- | Cold starts (LG-010) |
| Security | TC-028 | P0 | -- | |

---

## Summary

- **Total charters**: 28
- **P0 (must test)**: 12
- **P1 (should test)**: 10
- **P2 (nice to test)**: 6
- **Tested**: 1/28 (partial)
- **Issues found**: 1 (IQA-001, P0, resolved)
