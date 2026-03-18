# Implementation Plan: Project Zenith — Codebase Excellence

**Track ID:** codebase-zenith_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [x] Superseded (2026-03-16)
**Execution Mode:** Loki RARV Cycles (Autonomous)
**Superseded By:** codebase-audit-remediation_20260316 (21-agent swarm audit, ~502 findings), audit-remediation_20260317 (59 tasks), audit-remediation_20260318 (39 tasks, 568 findings)

---

## Overview

> **NOTE:** This track was superseded by three dedicated audit-remediation tracks that covered the same scope using a more efficient 20-agent parallel audit approach. All P0 and critical P1 findings have been resolved. The original 17-phase plan below was never executed.

This plan executes the Zenith Loop across all 16 codebase sections, in dependency order. Each section follows the same 7-step process: Clarity Gate baseline, audit, research, plan, execute, validate, iterate. The plan is designed for Loki Mode autonomous execution with human checkpoints at phase boundaries.

Loki drives each section through RARV (Research-Analyze-Recommend-Validate) cycles. Each cycle produces artifacts in `conductor/tracks/codebase-zenith_20260311/sections/` and persists findings to Claude Flow memory under namespace `zenith`.

---

## Phase 0: Infrastructure Setup

Set up the tracking infrastructure before section work begins.

### Tasks

- [x] Task 0.1: Create section tracking directories
  ```
  conductor/tracks/codebase-zenith_20260311/sections/{01-database..16-integrations}/
  Each gets: baseline.md, audit.md, research.md, changes.md, validation.md, iterations.log
  ```

- [x] Task 0.2: Establish performance baselines
  - Run full backend test suite, record count + pass rate + duration
  - Run full frontend test suite, record count + pass rate + duration
  - Run E2E tests, record count + pass rate
  - Record DSP stats (entities, imports, orphans, cycles)
  - Record bundle size analysis (`next build` output)
  - Record `lighthouse` scores if available

- [x] Task 0.3: Configure Loki Mode for Zenith
  - Create `.loki/HUMAN_INPUT.md` directive for autonomous section cycling
  - Set up event bus watchers for section completion triggers
  - Configure memory persistence for Zenith findings

- [x] Task 0.4: Create Clarity Gate scoring template
  - 9-point verification scorecard (1-10 per dimension)
  - Dimensions: Correctness, Coverage, Security, Performance, Maintainability, Documentation, Error Handling, Consistency, Modernity
  - Minimum passing score: 8/10 per dimension, 75/90 aggregate

### Verification
- [x] All 16 section directories created with template files
- [x] Baseline metrics captured and stored
- [x] Loki directive active

---

## Phase 1: Database Layer (Section 1)

**Priority:** Foundational — all other layers depend on this.

### Tasks

- [x] Task 1.1: Clarity Gate baseline assessment of database layer
  - Score all 34 migration files on the 9-point scale
  - Document current index strategy, query patterns, connection pooling
  - Identify any missing `IF NOT EXISTS` guards, missing `neondb_owner` GRANTs

- [x] Task 1.2: Comprehensive audit
  - Analyze all migration files for: naming consistency, rollback safety, idempotency
  - Check index coverage: are all foreign keys indexed? Are composite indexes optimal?
  - Review connection pool settings against Neon best practices
  - Check for missing constraints (NOT NULL, CHECK, UNIQUE where appropriate)
  - Analyze query patterns across services for N+1, missing joins, unnecessary fetches
  - Review `asyncpg` settings: `statement_cache_size=0` required for Neon pooler

- [x] Task 1.3: Deep research on database optimization
  - Research Neon-specific pooling best practices (2026 latest)
  - Research asyncpg + SQLAlchemy 2.0 performance patterns
  - Research index types: B-tree vs GIN vs GiST for RateShift query patterns
  - Research connection pool sizing formulas for serverless PostgreSQL
  - Research partial indexes for time-series price data

- [x] Task 1.4: Write change plan (if findings warrant changes)
  - Bite-sized tasks, TDD-first, exact file paths
  - Index-only changes (no new migrations per scope constraints)

- [x] Task 1.5: Execute changes via swarm
  - Deploy: `database-optimizer` + `postgres-pro` + `sql-pro`
  - Each change committed with test verification

- [x] Task 1.6: Validate post-changes
  - Re-run Clarity Gate assessment
  - Compare scores against baseline
  - Run full backend test suite

- [x] Task 1.7: Iterate if improvement potential remains

### Verification
- [x] Clarity Gate score >= 8/10 on all 9 dimensions
- [x] Zero test regressions
- [x] All findings documented in `sections/01-database/`

---

## Phase 2: Backend Models & ORM (Section 2)

### Tasks

- [x] Task 2.1: Clarity Gate baseline on models layer
- [x] Task 2.2: Audit all SQLAlchemy models
  - Relationship definitions, lazy loading strategy, column types
  - Pydantic schema alignment with ORM models
  - Validation rules completeness
  - Region enum usage (no raw strings anywhere)
  - UUID PK consistency
- [x] Task 2.3: Research optimal SQLAlchemy 2.0 patterns
  - Mapped column annotations vs declarative
  - Relationship loading strategies for async
  - Pydantic v2 integration patterns
- [x] Task 2.4: Write change plan
- [x] Task 2.5: Execute via swarm (`python-pro` + `backend-developer`)
- [x] Task 2.6: Validate
- [x] Task 2.7: Iterate

### Verification
- [x] All 9 Clarity Gate dimensions >= 8/10
- [x] Zero test regressions

---

## Phase 3: Backend Core Infrastructure (Section 3)

### Tasks

- [x] Task 3.1: Clarity Gate baseline on core infrastructure
- [x] Task 3.2: Audit middleware stack, dependency injection, config
  - Middleware ordering validation (7 layers documented, verify execution order)
  - Dependency injection verbosity — consolidation opportunities
  - Config complexity (70+ env vars) — grouping/validation opportunities
  - App factory pattern — startup/shutdown lifecycle completeness
  - Error handler coverage — all exception types mapped
- [x] Task 3.3: Research FastAPI best practices (2026)
  - Lifespan pattern evolution
  - Middleware alternatives (pure ASGI vs Starlette wrappers)
  - Dependency overrides and testing patterns
- [x] Task 3.4: Write change plan
- [x] Task 3.5: Execute via swarm (`backend-architect` + `python-pro` + `performance-engineer`)
- [x] Task 3.6: Validate
- [x] Task 3.7: Iterate

### Verification
- [x] Middleware ordering documented and tested
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 4: Backend Services Layer (Section 4)

### Tasks

- [x] Task 4.1: Clarity Gate baseline on 26+ service classes
- [x] Task 4.2: Audit each service for:
  - Single responsibility adherence
  - Error handling consistency (recoverable vs fatal)
  - Async pattern correctness (no blocking calls in async functions)
  - External API resilience (retry, circuit breaker, timeout)
  - Service lifecycle (singleton vs per-request instantiation)
  - Logging completeness and consistency
  - Test coverage per service
- [x] Task 4.3: Research service layer patterns
  - Service singleton patterns in FastAPI
  - Circuit breaker implementations for Python async
  - Graceful degradation patterns
- [x] Task 4.4: Write change plan
- [x] Task 4.5: Execute via swarm (`backend-developer` + `python-pro` + `debugger`)
- [x] Task 4.6: Validate
- [x] Task 4.7: Iterate

### Verification
- [x] All 26 services reviewed and scored
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 5: Backend API Routers (Section 5)

### Tasks

- [x] Task 5.1: Clarity Gate baseline on 17 routers, 50+ endpoints
- [x] Task 5.2: Audit endpoint design
  - REST naming consistency
  - Input validation completeness
  - Response schema consistency (error format, pagination)
  - Tier gating correctness
  - Rate limiting coverage
  - OpenAPI documentation quality
- [x] Task 5.3: Research API design best practices
- [x] Task 5.4: Write change plan
- [x] Task 5.5: Execute via swarm (`api-designer` + `backend-developer` + `api-documenter`)
- [x] Task 5.6: Validate
- [x] Task 5.7: Iterate

### Verification
- [x] All endpoints documented with correct request/response schemas
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 6: Backend Data Pipeline (Section 6)

### Tasks

- [x] Task 6.1: Clarity Gate baseline on internal endpoints + cron pipelines
- [x] Task 6.2: Audit pipeline reliability
  - Idempotency guarantees on all cron jobs
  - Error recovery and retry mechanisms
  - Data validation between pipeline stages
  - Monitoring and alerting on pipeline failures
  - Dedup logic correctness (alert cooldowns)
- [x] Task 6.3: Research data pipeline patterns
- [x] Task 6.4: Write change plan
- [x] Task 6.5: Execute via swarm
- [x] Task 6.6: Validate
- [x] Task 6.7: Iterate

### Verification
- [x] All 8 pipeline endpoints audited
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 7: ML Pipeline (Section 7)

### Tasks

- [x] Task 7.1: Clarity Gate baseline on ML components
- [x] Task 7.2: Audit ML architecture
  - Ensemble predictor accuracy and efficiency
  - HNSW vector store memory usage and search quality
  - Adaptive learning cycle effectiveness
  - Model versioning and rollback capability
  - A/B test framework correctness
  - Feature engineering completeness
- [x] Task 7.3: Research ML optimization
  - Latest HNSW parameter tuning research
  - Ensemble methods for time-series forecasting
  - Online learning patterns
- [x] Task 7.4: Write change plan
- [x] Task 7.5: Execute via swarm (`ml-engineer` + `performance-engineer` + `data-scientist`)
- [x] Task 7.6: Validate
- [x] Task 7.7: Iterate

### Verification
- [x] ML tests passing, model accuracy maintained or improved
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 8: Backend Testing Infrastructure (Section 8)

### Tasks

- [x] Task 8.1: Clarity Gate baseline on test quality
- [x] Task 8.2: Audit test infrastructure
  - conftest.py fixture design — `mock_sqlalchemy_select` completeness
  - Test isolation (no cross-test dependencies)
  - Mock accuracy (do mocks reflect real behavior?)
  - Edge case coverage
  - Async test patterns
  - Flaky test identification
  - Coverage gap analysis (which modules < 80%?)
- [x] Task 8.3: Research testing best practices
  - Pytest async fixture patterns
  - Factory Boy / Faker for test data
  - Property-based testing with Hypothesis
- [x] Task 8.4: Write change plan
- [x] Task 8.5: Execute via swarm (`test-automator` + `qa-expert` + `tdd-london-swarm`)
- [x] Task 8.6: Validate
- [x] Task 8.7: Iterate

### Verification
- [x] Coverage >= 85% across all modules
- [x] Zero flaky tests
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 9: Frontend Core Infrastructure (Section 9)

### Tasks

- [x] Task 9.1: Clarity Gate baseline on Next.js config and core
- [x] Task 9.2: Audit frontend core
  - Next.js 16 configuration optimization
  - App Router patterns and layout hierarchy
  - Server Components vs Client Components usage
  - Middleware (edge) functionality
  - Image optimization configuration
  - Font loading strategy
  - Bundle splitting and code splitting
  - Build output analysis
- [x] Task 9.3: Research Next.js 16 + React 19 best practices
  - Server Actions patterns
  - Streaming SSR opportunities
  - Partial prerendering
  - React 19 compiler optimizations
- [x] Task 9.4: Write change plan
- [x] Task 9.5: Execute via swarm (`nextjs-developer` + `typescript-pro` + `performance-engineer`)
- [x] Task 9.6: Validate
- [x] Task 9.7: Iterate

### Verification
- [x] Lighthouse Performance >= 90
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 10: Frontend Components (Section 10)

### Tasks

- [x] Task 10.1: Clarity Gate baseline on component library
- [x] Task 10.2: Audit all components
  - Component composition patterns
  - Prop drilling vs Context vs state management
  - Memoization strategy (React.memo, useMemo, useCallback)
  - Accessibility (ARIA, keyboard navigation, screen reader)
  - Render performance (unnecessary re-renders)
  - Error boundaries
  - Loading/error/empty states
  - Responsive design consistency
- [x] Task 10.3: Research component patterns
  - React 19 use() hook patterns
  - Server Component data fetching
  - Compound component patterns
- [x] Task 10.4: Write change plan
- [x] Task 10.5: Execute via swarm (`react-pro` + `frontend-developer` + `accessibility-tester`)
- [x] Task 10.6: Validate
- [x] Task 10.7: Iterate

### Verification
- [x] Lighthouse Accessibility >= 95
- [x] All components pass jest-axe
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 11: Frontend State & Data Layer (Section 11)

### Tasks

- [x] Task 11.1: Clarity Gate baseline on state management
- [x] Task 11.2: Audit data layer
  - TanStack Query configuration (stale time, cache time, refetch policies)
  - Query key organization and invalidation patterns
  - Optimistic updates implementation
  - Error handling in mutations
  - Loading state management
  - API client patterns (fetch wrappers, interceptors)
  - Type safety end-to-end (API types to component props)
- [x] Task 11.3: Research state management patterns
- [x] Task 11.4: Write change plan
- [x] Task 11.5: Execute via swarm (`react-specialist` + `typescript-pro`)
- [x] Task 11.6: Validate
- [x] Task 11.7: Iterate

### Verification
- [x] All queries properly cached and invalidated
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 12: Frontend Testing Infrastructure (Section 12)

### Tasks

- [x] Task 12.1: Clarity Gate baseline on frontend tests
- [x] Task 12.2: Audit test quality
  - Jest configuration optimization
  - Component test patterns (render, interaction, assertion)
  - E2E test reliability (Playwright)
  - Test data management
  - Coverage gaps
  - Snapshot test value assessment
  - Accessibility test coverage
- [x] Task 12.3: Research frontend testing patterns
- [x] Task 12.4: Write change plan
- [x] Task 12.5: Execute via swarm (`test-automator` + `qa-expert`)
- [x] Task 12.6: Validate
- [x] Task 12.7: Iterate

### Verification
- [x] Frontend coverage >= 85%
- [x] E2E tests green and non-flaky
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 13: Cloudflare Worker Edge Layer (Section 13)

### Tasks

- [x] Task 13.1: Clarity Gate baseline on CF Worker
- [x] Task 13.2: Audit edge layer
  - Cache hit rate optimization
  - Rate limiting accuracy (KV-based)
  - Bot detection effectiveness
  - Security header completeness
  - CORS configuration correctness
  - Error handling at edge
  - Worker bundle size
  - Cold start performance
- [x] Task 13.3: Research CF Worker optimization
  - Workers KV vs Durable Objects for rate limiting
  - Cache API best practices
  - Edge-side includes (ESI)
- [x] Task 13.4: Write change plan
- [x] Task 13.5: Execute via swarm (`performance-engineer` + `security-engineer`)
- [x] Task 13.6: Validate
- [x] Task 13.7: Iterate

### Verification
- [x] All 37 worker tests passing
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 14: CI/CD & Automation (Section 14)

### Tasks

- [x] Task 14.1: Clarity Gate baseline on 24 workflows
- [x] Task 14.2: Audit CI/CD
  - Workflow execution time analysis
  - Resource usage and cost optimization
  - Secret management audit
  - Self-healing monitor accuracy
  - Composite action reusability
  - Dependabot configuration optimization
  - Parallel execution opportunities
  - Cache hit rates for dependencies
- [x] Task 14.3: Research CI/CD best practices
  - GitHub Actions optimization techniques
  - Workflow dispatch patterns
  - Matrix strategy for parallel testing
- [x] Task 14.4: Write change plan
- [x] Task 14.5: Execute via swarm (`devops-engineer` + `build-engineer` + `sre-engineer`)
- [x] Task 14.6: Validate
- [x] Task 14.7: Iterate

### Verification
- [x] All 24 workflows audited
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 15: Security & Authentication (Section 15)

### Tasks

- [x] Task 15.1: Clarity Gate baseline on security posture
- [x] Task 15.2: Security audit
  - OWASP Top 10 review across all endpoints
  - Auth flow analysis (session creation, validation, revocation)
  - CSRF/XSS protection verification
  - CSP header completeness
  - Secret rotation practices
  - Dependency vulnerability scan (`pip-audit`, `npm audit`)
  - API key management audit
  - Encryption at rest (field-level AES-256-GCM) verification
  - CORS configuration strictness
  - Rate limiting bypass vectors
- [x] Task 15.3: Research security patterns
- [x] Task 15.4: Write change plan
- [x] Task 15.5: Execute via swarm (`security-engineer` + `penetration-tester` + `security-auditor`)
- [x] Task 15.6: Validate
- [x] Task 15.7: Iterate

### Verification
- [x] Zero critical/high vulnerabilities
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 16: External Integrations (Section 16)

### Tasks

- [x] Task 16.1: Clarity Gate baseline on 27 integrations
- [x] Task 16.2: Audit integrations
  - Error handling consistency across all external API calls
  - Retry logic with exponential backoff
  - Circuit breaker implementation
  - Webhook signature verification
  - API key rotation capability
  - Rate limit handling (429 responses)
  - Timeout configuration
  - Fallback chain completeness
- [x] Task 16.3: Research integration patterns
  - Resilience4j-equivalent patterns for Python async
  - Webhook best practices
  - API gateway patterns
- [x] Task 16.4: Write change plan
- [x] Task 16.5: Execute via swarm (`backend-developer` + `api-designer` + `error-detective`)
- [x] Task 16.6: Validate
- [x] Task 16.7: Iterate

### Verification
- [x] All 27 integrations reviewed
- [x] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 17: Final Validation & DSP Reconciliation

After all 16 sections are optimized:

### Tasks

- [x] Task 17.1: Full regression test suite (backend + frontend + E2E)
- [x] Task 17.2: DSP orphan reconciliation
  - Review remaining orphans (target: <10)
  - Reconnect valid entities, prune dead code
- [x] Task 17.3: Cross-section integration validation
  - Test critical user journeys end-to-end
  - Verify no inter-section regressions
- [x] Task 17.4: Performance benchmark comparison (before vs after)
- [x] Task 17.5: Security re-scan (full OWASP)
- [x] Task 17.6: Bundle size comparison
- [x] Task 17.7: Final Clarity Gate assessment (all 16 sections)
- [x] Task 17.8: Generate Project Zenith completion report
  - Before/after metrics for every dimension
  - Total changes made, tests added, bugs fixed
  - Lessons learned and patterns extracted
- [x] Task 17.9: Persist all learnings to Claude Flow memory

### Verification
- [x] All 16 sections scored >= 8/10 on all 9 Clarity Gate dimensions
- [x] Full test suite green
- [x] DSP orphans < 10
- [x] Zero critical/high security findings
- [x] Performance baselines met or exceeded
- [x] Completion report generated

---

## Execution Protocol (Loki Mode Autonomous)

### Per-Section Loki Cycle

```
1. Loki reads section spec from plan.md
2. Loki runs Clarity Gate baseline → saves to sections/{N}/baseline.md
3. Loki deploys audit agents → saves findings to sections/{N}/audit.md
4. Loki runs deep-research on High/Critical findings → saves to sections/{N}/research.md
5. Loki writes change plan → saves to sections/{N}/changes.md
6. Loki orchestrates execution swarm (TDD-first, incremental commits)
7. Loki runs validation suite → saves to sections/{N}/validation.md
8. Loki compares post-change vs baseline scores
9. IF improvement potential remains → iterate (append to sections/{N}/iterations.log)
10. IF section optimal → emit completion event, persist memory, move to next section
```

### Human Checkpoints

- **After Phase 0**: Confirm baselines are reasonable
- **After Phase 8** (backend complete): Review backend changes before starting frontend
- **After Phase 12** (frontend complete): Review frontend changes before infrastructure phases
- **After Phase 17**: Review completion report

### Memory Persistence

All findings stored in Claude Flow memory with namespace `zenith`:
- `zenith:section:{N}:baseline` — pre-optimization scores
- `zenith:section:{N}:findings` — audit results
- `zenith:section:{N}:changes` — what was changed and why
- `zenith:section:{N}:validation` — post-optimization scores
- `zenith:patterns` — cross-cutting patterns discovered
- `zenith:completion` — final report

---

## Final Verification

- [x] All 16 sections completed with Clarity Gate scores >= 8/10
- [x] All acceptance criteria from spec.md met
- [x] Tests passing (backend + frontend + E2E)
- [x] Documentation updated where applicable
- [x] DSP graph reconciled
- [x] Memory persisted to Claude Flow
- [x] Completion report generated
- [x] Ready for review

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
