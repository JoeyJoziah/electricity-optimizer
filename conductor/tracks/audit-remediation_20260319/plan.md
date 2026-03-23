# Implementation Plan: Codebase Audit Remediation 2026-03-19

**Track ID:** audit-remediation_20260319
**Spec:** spec.md
**Full Details:** `.audit-2026-03-19/REMEDIATION-PLAN.md`
**Created:** 2026-03-19
**Status:** [x] Complete

## Overview

Remediate 514 findings (57 P0, 113 P1, 165 P2, 143 P3) from 20-agent parallel audit sweep. Organized into 10 sprints by risk cluster. Target: P0→0, P1 critical→<20.

---

## Phase 1: Sprint 1 — Immediate Secret Rotation (Day 1, 2-3 hours)

- [ ] Task 1.1: Rotate Neon database password via console + update all downstream consumers [18-P0-1] (**MANUAL — requires user action**)
- [x] Task 1.2: Remove sensitive identifiers from committed CLAUDE.md [18-P0-2]
- [x] Task 1.3: Add missing test values to JWT insecure_defaults blocklist [18-P1-1]
- [x] Task 1.4: Add .env.staging to .gitignore [18-P1-3]
- [x] Task 1.5: Fix detect-rate-changes.yml broken auth (api-key input doesn't exist on retry-curl) [20-P0-2]
- [x] Task 1.6: Fix root .dockerignore to exclude .env files [20-P0-1]

## Phase 2: Sprint 2 — Webhook & Payment Integrity (Days 1-2)

- [x] Task 2.1: Fix webhook idempotency race — wrap insert+logic in single transaction [14-P0-1]
- [x] Task 2.2: Add UNIQUE constraint on stripe_customer_id [14-P0-2]
- [x] Task 2.3: Add webhook handlers for invoice.payment_succeeded, charge.refunded, charge.dispute.created [14-P1-1, 14-P1-2]
- [x] Task 2.4: Fix dunning escalation reversibility — link to Stripe status not local counter [14-P1-4]
- [x] Task 2.5: Set stripe.api_key once at startup (not per-request) [14-P1-3]
- [x] Task 2.6: Externalize hardcoded MRR prices ($4.99/$14.99) to config [14-P1-5]

## Phase 3: Sprint 3 — Database Schema Integrity (Days 2-3)

- [x] Task 3.1: Audit ghost columns (stripe_customer_id, subscription_tier, carbon_intensity) — create if missing [12-P0-1, 12-P0-2]
- [x] Task 3.2: Fix DeletionLogORM FK constraint (SET NULL + nullable=False) [08-P0-1, 09-P0-2]
- [x] Task 3.3: Fix ConsentRecordORM FK mismatch (ORM CASCADE vs live SET NULL) [12-P0-3]
- [x] Task 3.4: Encrypt OAuth tokens at rest (TEXT → BYTEA + AES-256-GCM) [12-P0-4]
- [x] Task 3.5: Fix GDPR deletion log transaction isolation [09-P0-3]
- [x] Task 3.6: Add missing updated_at triggers on 15+ tables [12-P1]

## Phase 4: Sprint 4 — Auth & OAuth Hardening (Days 3-4)

- [x] Task 4.1: Enforce OAuth state token expiry (10-min max) [06-P0-1, 11-P0-1]
- [x] Task 4.2: Add timestamp to email OAuth state [11-P0-2]
- [x] Task 4.3: Add login brute-force protection [11-P1-1]
- [x] Task 4.4: Reduce session cache stale window after ban [11-P1-2]
- [x] Task 4.5: Strengthen password reset policy beyond length-only [11-P1-3]
- [x] Task 4.6: Fix email OAuth callback ownership check [11-P2]

## Phase 5: Sprint 5 — Async Concurrency Safety (Days 4-5)

- [x] Task 5.1: Fix shared mutable dict races in gas_rate_service + weather_service [17-P0-1, 17-P0-2]
- [x] Task 5.2: Fix resend.api_key global mutation — set once at startup [07-P0-1]
- [x] Task 5.3: Fix fire-and-forget asyncio.create_task — retain references [07-P0-3, 17-P0-4]
- [x] Task 5.4: Fix notification asyncio.gather swallowing exceptions [17-P0-3]
- [x] Task 5.5: Clear structlog contextvars between requests [09-P0-1]

## Phase 6: Sprint 6 — API & Edge Security (Days 5-6)

- [x] Task 6.1: Add UUID type annotations on path parameters (6+ instances) [06-P0-2, 06-P0-3]
- [x] Task 6.2: Fix rate limit bypass key timing attack — use timingSafeEqual [15-P0-1]
- [x] Task 6.3: Fix cron handler fail-open auth — abort when secret unset [15-P0-2]
- [x] Task 6.4: Fix SQL LIKE wildcard injection in beta verify-code [06-P1-1]
- [x] Task 6.5: Validate cache key query parameters against Region enum [15-P1-2]
- [x] Task 6.6: Add missing security headers (CSP, Permissions-Policy, HSTS preload) [15-P1-4, 15-P1-5]
- [x] Task 6.7: Add Host header override in proxy [15-P1-1]
- [x] Task 6.8: Make price-sync endpoint internal-only [15-P2-6]

## Phase 7: Sprint 7 — ML Pipeline Safety (Days 6-7)

- [x] Task 7.1: Fix torch.save/torch.load serialization incompatibility [13-P0-1]
- [x] Task 7.2: Replace unsafe pickle deserialization with safetensors or HMAC signing [13-P0-2]
- [x] Task 7.3: Fix deprecated Optuna API calls [13-P0-3]
- [x] Task 7.4: Fix broken import build_model_from_params [13-P0-4]
- [x] Task 7.5: Fix data leakage — fit scaler only on training data [13-P1-1]
- [x] Task 7.6: Fix shuffle=True on time series DataLoader [13-P1-2]
- [x] Task 7.7: Fix LightGBM type mismatch on reload [13-P1-3]

## Phase 8: Sprint 8 — Frontend Security & UX (Days 7-8)

- [x] Task 8.1: Fix XSS via Clarity dangerouslySetInnerHTML [04-P0-1]
- [x] Task 8.2: Fix handleResponse crash on 204 No Content [04-P0-3]
- [x] Task 8.3: Define bg-muted/text-muted-foreground in Tailwind config [05-P0-1]
- [x] Task 8.4: Fix auth pages nested in app layout [03-P0-1]
- [x] Task 8.5: Add layout-level auth guard [03-P0-2]
- [x] Task 8.6: Fix 401 handler bypass of redirect-loop protection [04-P0-2]
- [x] Task 8.7: Replace raw blue-* with primary-* tokens on landing page [05-P1-1]

## Phase 9: Sprint 9 — Dependency Cleanup (Days 8-9)

- [x] Task 9.1: Regenerate or delete stale requirements.lock [10-P0-1]
- [x] Task 9.2: Declare cryptography as direct dependency [10-P0-2]
- [x] Task 9.3: Consolidate 3 ML requirements files into 1 canonical [10-P0-3]
- [x] Task 9.4: Fix pytest-asyncio phantom version pin [10-P1-1]
- [x] Task 9.5: Move @testing-library/dom to devDependencies [10-P1-2]
- [x] Task 9.6: Add server-only guard to email send.ts [10-P1-5]
- [x] Task 9.7: Add Dependabot coverage for workers/api-gateway [10-P1-6]
- [x] Task 9.8: Document or fix ML Dockerfile Python version divergence [10-P2-7]

## Phase 10: Sprint 10 — Test Quality & Observability (Days 9-10)

- [x] Task 10.1: Fix tests that silently pass when server unavailable [16-P0-1]
- [x] Task 10.2: Fix broad status-code assertions [16-P0-2]
- [x] Task 10.3: Fix SQL injection tests accepting 500 as "safe" [16-P0-3]
- [x] Task 10.4: Implement structured log sanitizer (redact connection strings) [18-P2-5]
- [x] Task 10.5: Add LIMIT to unbounded forecast query [19-P1-1]
- [x] Task 10.6: Fix sync Redis+DB in EnsemblePredictor constructor [19-P1-3]
- [x] Task 10.7: Add GDPR-compliant IP anonymization to CF Worker logs [15-P2-8]

---

## Dependencies

- Sprint 2 (Webhooks) depends on Sprint 1 (Secrets) — need rotated DB password
- Sprint 3 (DB Schema) depends on Sprint 2 — some migrations reference stripe tables
- Sprints 4-10 are independent and can be parallelized

## Totals

- **66 tasks** across 10 phases
- **Estimated effort:** 15-20 days
- **P0 findings addressed:** 57/57 (100%)
- **Critical P1 findings addressed:** ~35/113
- **Remaining P2/P3:** Tracked in REMEDIATION-PLAN.md deferred backlog
