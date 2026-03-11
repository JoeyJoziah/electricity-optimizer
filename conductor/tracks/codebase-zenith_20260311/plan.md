# Implementation Plan: Project Zenith — Codebase Excellence

**Track ID:** codebase-zenith_20260311
**Spec:** spec.md
**Created:** 2026-03-11
**Status:** [ ] Not Started
**Execution Mode:** Loki RARV Cycles (Autonomous)

---

## Overview

This plan executes the Zenith Loop across all 16 codebase sections, in dependency order. Each section follows the same 7-step process: Clarity Gate baseline, audit, research, plan, execute, validate, iterate. The plan is designed for Loki Mode autonomous execution with human checkpoints at phase boundaries.

Loki drives each section through RARV (Research-Analyze-Recommend-Validate) cycles. Each cycle produces artifacts in `conductor/tracks/codebase-zenith_20260311/sections/` and persists findings to Claude Flow memory under namespace `zenith`.

---

## Phase 0: Infrastructure Setup

Set up the tracking infrastructure before section work begins.

### Tasks

- [ ] Task 0.1: Create section tracking directories
  ```
  conductor/tracks/codebase-zenith_20260311/sections/{01-database..16-integrations}/
  Each gets: baseline.md, audit.md, research.md, changes.md, validation.md, iterations.log
  ```

- [ ] Task 0.2: Establish performance baselines
  - Run full backend test suite, record count + pass rate + duration
  - Run full frontend test suite, record count + pass rate + duration
  - Run E2E tests, record count + pass rate
  - Record DSP stats (entities, imports, orphans, cycles)
  - Record bundle size analysis (`next build` output)
  - Record `lighthouse` scores if available

- [ ] Task 0.3: Configure Loki Mode for Zenith
  - Create `.loki/HUMAN_INPUT.md` directive for autonomous section cycling
  - Set up event bus watchers for section completion triggers
  - Configure memory persistence for Zenith findings

- [ ] Task 0.4: Create Clarity Gate scoring template
  - 9-point verification scorecard (1-10 per dimension)
  - Dimensions: Correctness, Coverage, Security, Performance, Maintainability, Documentation, Error Handling, Consistency, Modernity
  - Minimum passing score: 8/10 per dimension, 75/90 aggregate

### Verification
- [ ] All 16 section directories created with template files
- [ ] Baseline metrics captured and stored
- [ ] Loki directive active

---

## Phase 1: Database Layer (Section 1)

**Priority:** Foundational — all other layers depend on this.

### Tasks

- [ ] Task 1.1: Clarity Gate baseline assessment of database layer
  - Score all 34 migration files on the 9-point scale
  - Document current index strategy, query patterns, connection pooling
  - Identify any missing `IF NOT EXISTS` guards, missing `neondb_owner` GRANTs

- [ ] Task 1.2: Comprehensive audit
  - Analyze all migration files for: naming consistency, rollback safety, idempotency
  - Check index coverage: are all foreign keys indexed? Are composite indexes optimal?
  - Review connection pool settings against Neon best practices
  - Check for missing constraints (NOT NULL, CHECK, UNIQUE where appropriate)
  - Analyze query patterns across services for N+1, missing joins, unnecessary fetches
  - Review `asyncpg` settings: `statement_cache_size=0` required for Neon pooler

- [ ] Task 1.3: Deep research on database optimization
  - Research Neon-specific pooling best practices (2026 latest)
  - Research asyncpg + SQLAlchemy 2.0 performance patterns
  - Research index types: B-tree vs GIN vs GiST for RateShift query patterns
  - Research connection pool sizing formulas for serverless PostgreSQL
  - Research partial indexes for time-series price data

- [ ] Task 1.4: Write change plan (if findings warrant changes)
  - Bite-sized tasks, TDD-first, exact file paths
  - Index-only changes (no new migrations per scope constraints)

- [ ] Task 1.5: Execute changes via swarm
  - Deploy: `database-optimizer` + `postgres-pro` + `sql-pro`
  - Each change committed with test verification

- [ ] Task 1.6: Validate post-changes
  - Re-run Clarity Gate assessment
  - Compare scores against baseline
  - Run full backend test suite

- [ ] Task 1.7: Iterate if improvement potential remains

### Verification
- [ ] Clarity Gate score >= 8/10 on all 9 dimensions
- [ ] Zero test regressions
- [ ] All findings documented in `sections/01-database/`

---

## Phase 2: Backend Models & ORM (Section 2)

### Tasks

- [ ] Task 2.1: Clarity Gate baseline on models layer
- [ ] Task 2.2: Audit all SQLAlchemy models
  - Relationship definitions, lazy loading strategy, column types
  - Pydantic schema alignment with ORM models
  - Validation rules completeness
  - Region enum usage (no raw strings anywhere)
  - UUID PK consistency
- [ ] Task 2.3: Research optimal SQLAlchemy 2.0 patterns
  - Mapped column annotations vs declarative
  - Relationship loading strategies for async
  - Pydantic v2 integration patterns
- [ ] Task 2.4: Write change plan
- [ ] Task 2.5: Execute via swarm (`python-pro` + `backend-developer`)
- [ ] Task 2.6: Validate
- [ ] Task 2.7: Iterate

### Verification
- [ ] All 9 Clarity Gate dimensions >= 8/10
- [ ] Zero test regressions

---

## Phase 3: Backend Core Infrastructure (Section 3)

### Tasks

- [ ] Task 3.1: Clarity Gate baseline on core infrastructure
- [ ] Task 3.2: Audit middleware stack, dependency injection, config
  - Middleware ordering validation (7 layers documented, verify execution order)
  - Dependency injection verbosity — consolidation opportunities
  - Config complexity (70+ env vars) — grouping/validation opportunities
  - App factory pattern — startup/shutdown lifecycle completeness
  - Error handler coverage — all exception types mapped
- [ ] Task 3.3: Research FastAPI best practices (2026)
  - Lifespan pattern evolution
  - Middleware alternatives (pure ASGI vs Starlette wrappers)
  - Dependency overrides and testing patterns
- [ ] Task 3.4: Write change plan
- [ ] Task 3.5: Execute via swarm (`backend-architect` + `python-pro` + `performance-engineer`)
- [ ] Task 3.6: Validate
- [ ] Task 3.7: Iterate

### Verification
- [ ] Middleware ordering documented and tested
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 4: Backend Services Layer (Section 4)

### Tasks

- [ ] Task 4.1: Clarity Gate baseline on 26+ service classes
- [ ] Task 4.2: Audit each service for:
  - Single responsibility adherence
  - Error handling consistency (recoverable vs fatal)
  - Async pattern correctness (no blocking calls in async functions)
  - External API resilience (retry, circuit breaker, timeout)
  - Service lifecycle (singleton vs per-request instantiation)
  - Logging completeness and consistency
  - Test coverage per service
- [ ] Task 4.3: Research service layer patterns
  - Service singleton patterns in FastAPI
  - Circuit breaker implementations for Python async
  - Graceful degradation patterns
- [ ] Task 4.4: Write change plan
- [ ] Task 4.5: Execute via swarm (`backend-developer` + `python-pro` + `debugger`)
- [ ] Task 4.6: Validate
- [ ] Task 4.7: Iterate

### Verification
- [ ] All 26 services reviewed and scored
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 5: Backend API Routers (Section 5)

### Tasks

- [ ] Task 5.1: Clarity Gate baseline on 17 routers, 50+ endpoints
- [ ] Task 5.2: Audit endpoint design
  - REST naming consistency
  - Input validation completeness
  - Response schema consistency (error format, pagination)
  - Tier gating correctness
  - Rate limiting coverage
  - OpenAPI documentation quality
- [ ] Task 5.3: Research API design best practices
- [ ] Task 5.4: Write change plan
- [ ] Task 5.5: Execute via swarm (`api-designer` + `backend-developer` + `api-documenter`)
- [ ] Task 5.6: Validate
- [ ] Task 5.7: Iterate

### Verification
- [ ] All endpoints documented with correct request/response schemas
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 6: Backend Data Pipeline (Section 6)

### Tasks

- [ ] Task 6.1: Clarity Gate baseline on internal endpoints + cron pipelines
- [ ] Task 6.2: Audit pipeline reliability
  - Idempotency guarantees on all cron jobs
  - Error recovery and retry mechanisms
  - Data validation between pipeline stages
  - Monitoring and alerting on pipeline failures
  - Dedup logic correctness (alert cooldowns)
- [ ] Task 6.3: Research data pipeline patterns
- [ ] Task 6.4: Write change plan
- [ ] Task 6.5: Execute via swarm
- [ ] Task 6.6: Validate
- [ ] Task 6.7: Iterate

### Verification
- [ ] All 8 pipeline endpoints audited
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 7: ML Pipeline (Section 7)

### Tasks

- [ ] Task 7.1: Clarity Gate baseline on ML components
- [ ] Task 7.2: Audit ML architecture
  - Ensemble predictor accuracy and efficiency
  - HNSW vector store memory usage and search quality
  - Adaptive learning cycle effectiveness
  - Model versioning and rollback capability
  - A/B test framework correctness
  - Feature engineering completeness
- [ ] Task 7.3: Research ML optimization
  - Latest HNSW parameter tuning research
  - Ensemble methods for time-series forecasting
  - Online learning patterns
- [ ] Task 7.4: Write change plan
- [ ] Task 7.5: Execute via swarm (`ml-engineer` + `performance-engineer` + `data-scientist`)
- [ ] Task 7.6: Validate
- [ ] Task 7.7: Iterate

### Verification
- [ ] ML tests passing, model accuracy maintained or improved
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 8: Backend Testing Infrastructure (Section 8)

### Tasks

- [ ] Task 8.1: Clarity Gate baseline on test quality
- [ ] Task 8.2: Audit test infrastructure
  - conftest.py fixture design — `mock_sqlalchemy_select` completeness
  - Test isolation (no cross-test dependencies)
  - Mock accuracy (do mocks reflect real behavior?)
  - Edge case coverage
  - Async test patterns
  - Flaky test identification
  - Coverage gap analysis (which modules < 80%?)
- [ ] Task 8.3: Research testing best practices
  - Pytest async fixture patterns
  - Factory Boy / Faker for test data
  - Property-based testing with Hypothesis
- [ ] Task 8.4: Write change plan
- [ ] Task 8.5: Execute via swarm (`test-automator` + `qa-expert` + `tdd-london-swarm`)
- [ ] Task 8.6: Validate
- [ ] Task 8.7: Iterate

### Verification
- [ ] Coverage >= 85% across all modules
- [ ] Zero flaky tests
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 9: Frontend Core Infrastructure (Section 9)

### Tasks

- [ ] Task 9.1: Clarity Gate baseline on Next.js config and core
- [ ] Task 9.2: Audit frontend core
  - Next.js 16 configuration optimization
  - App Router patterns and layout hierarchy
  - Server Components vs Client Components usage
  - Middleware (edge) functionality
  - Image optimization configuration
  - Font loading strategy
  - Bundle splitting and code splitting
  - Build output analysis
- [ ] Task 9.3: Research Next.js 16 + React 19 best practices
  - Server Actions patterns
  - Streaming SSR opportunities
  - Partial prerendering
  - React 19 compiler optimizations
- [ ] Task 9.4: Write change plan
- [ ] Task 9.5: Execute via swarm (`nextjs-developer` + `typescript-pro` + `performance-engineer`)
- [ ] Task 9.6: Validate
- [ ] Task 9.7: Iterate

### Verification
- [ ] Lighthouse Performance >= 90
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 10: Frontend Components (Section 10)

### Tasks

- [ ] Task 10.1: Clarity Gate baseline on component library
- [ ] Task 10.2: Audit all components
  - Component composition patterns
  - Prop drilling vs Context vs state management
  - Memoization strategy (React.memo, useMemo, useCallback)
  - Accessibility (ARIA, keyboard navigation, screen reader)
  - Render performance (unnecessary re-renders)
  - Error boundaries
  - Loading/error/empty states
  - Responsive design consistency
- [ ] Task 10.3: Research component patterns
  - React 19 use() hook patterns
  - Server Component data fetching
  - Compound component patterns
- [ ] Task 10.4: Write change plan
- [ ] Task 10.5: Execute via swarm (`react-pro` + `frontend-developer` + `accessibility-tester`)
- [ ] Task 10.6: Validate
- [ ] Task 10.7: Iterate

### Verification
- [ ] Lighthouse Accessibility >= 95
- [ ] All components pass jest-axe
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 11: Frontend State & Data Layer (Section 11)

### Tasks

- [ ] Task 11.1: Clarity Gate baseline on state management
- [ ] Task 11.2: Audit data layer
  - TanStack Query configuration (stale time, cache time, refetch policies)
  - Query key organization and invalidation patterns
  - Optimistic updates implementation
  - Error handling in mutations
  - Loading state management
  - API client patterns (fetch wrappers, interceptors)
  - Type safety end-to-end (API types to component props)
- [ ] Task 11.3: Research state management patterns
- [ ] Task 11.4: Write change plan
- [ ] Task 11.5: Execute via swarm (`react-specialist` + `typescript-pro`)
- [ ] Task 11.6: Validate
- [ ] Task 11.7: Iterate

### Verification
- [ ] All queries properly cached and invalidated
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 12: Frontend Testing Infrastructure (Section 12)

### Tasks

- [ ] Task 12.1: Clarity Gate baseline on frontend tests
- [ ] Task 12.2: Audit test quality
  - Jest configuration optimization
  - Component test patterns (render, interaction, assertion)
  - E2E test reliability (Playwright)
  - Test data management
  - Coverage gaps
  - Snapshot test value assessment
  - Accessibility test coverage
- [ ] Task 12.3: Research frontend testing patterns
- [ ] Task 12.4: Write change plan
- [ ] Task 12.5: Execute via swarm (`test-automator` + `qa-expert`)
- [ ] Task 12.6: Validate
- [ ] Task 12.7: Iterate

### Verification
- [ ] Frontend coverage >= 85%
- [ ] E2E tests green and non-flaky
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 13: Cloudflare Worker Edge Layer (Section 13)

### Tasks

- [ ] Task 13.1: Clarity Gate baseline on CF Worker
- [ ] Task 13.2: Audit edge layer
  - Cache hit rate optimization
  - Rate limiting accuracy (KV-based)
  - Bot detection effectiveness
  - Security header completeness
  - CORS configuration correctness
  - Error handling at edge
  - Worker bundle size
  - Cold start performance
- [ ] Task 13.3: Research CF Worker optimization
  - Workers KV vs Durable Objects for rate limiting
  - Cache API best practices
  - Edge-side includes (ESI)
- [ ] Task 13.4: Write change plan
- [ ] Task 13.5: Execute via swarm (`performance-engineer` + `security-engineer`)
- [ ] Task 13.6: Validate
- [ ] Task 13.7: Iterate

### Verification
- [ ] All 37 worker tests passing
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 14: CI/CD & Automation (Section 14)

### Tasks

- [ ] Task 14.1: Clarity Gate baseline on 24 workflows
- [ ] Task 14.2: Audit CI/CD
  - Workflow execution time analysis
  - Resource usage and cost optimization
  - Secret management audit
  - Self-healing monitor accuracy
  - Composite action reusability
  - Dependabot configuration optimization
  - Parallel execution opportunities
  - Cache hit rates for dependencies
- [ ] Task 14.3: Research CI/CD best practices
  - GitHub Actions optimization techniques
  - Workflow dispatch patterns
  - Matrix strategy for parallel testing
- [ ] Task 14.4: Write change plan
- [ ] Task 14.5: Execute via swarm (`devops-engineer` + `build-engineer` + `sre-engineer`)
- [ ] Task 14.6: Validate
- [ ] Task 14.7: Iterate

### Verification
- [ ] All 24 workflows audited
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 15: Security & Authentication (Section 15)

### Tasks

- [ ] Task 15.1: Clarity Gate baseline on security posture
- [ ] Task 15.2: Security audit
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
- [ ] Task 15.3: Research security patterns
- [ ] Task 15.4: Write change plan
- [ ] Task 15.5: Execute via swarm (`security-engineer` + `penetration-tester` + `security-auditor`)
- [ ] Task 15.6: Validate
- [ ] Task 15.7: Iterate

### Verification
- [ ] Zero critical/high vulnerabilities
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 16: External Integrations (Section 16)

### Tasks

- [ ] Task 16.1: Clarity Gate baseline on 27 integrations
- [ ] Task 16.2: Audit integrations
  - Error handling consistency across all external API calls
  - Retry logic with exponential backoff
  - Circuit breaker implementation
  - Webhook signature verification
  - API key rotation capability
  - Rate limit handling (429 responses)
  - Timeout configuration
  - Fallback chain completeness
- [ ] Task 16.3: Research integration patterns
  - Resilience4j-equivalent patterns for Python async
  - Webhook best practices
  - API gateway patterns
- [ ] Task 16.4: Write change plan
- [ ] Task 16.5: Execute via swarm (`backend-developer` + `api-designer` + `error-detective`)
- [ ] Task 16.6: Validate
- [ ] Task 16.7: Iterate

### Verification
- [ ] All 27 integrations reviewed
- [ ] All 9 Clarity Gate dimensions >= 8/10

---

## Phase 17: Final Validation & DSP Reconciliation

After all 16 sections are optimized:

### Tasks

- [ ] Task 17.1: Full regression test suite (backend + frontend + E2E)
- [ ] Task 17.2: DSP orphan reconciliation
  - Review remaining orphans (target: <10)
  - Reconnect valid entities, prune dead code
- [ ] Task 17.3: Cross-section integration validation
  - Test critical user journeys end-to-end
  - Verify no inter-section regressions
- [ ] Task 17.4: Performance benchmark comparison (before vs after)
- [ ] Task 17.5: Security re-scan (full OWASP)
- [ ] Task 17.6: Bundle size comparison
- [ ] Task 17.7: Final Clarity Gate assessment (all 16 sections)
- [ ] Task 17.8: Generate Project Zenith completion report
  - Before/after metrics for every dimension
  - Total changes made, tests added, bugs fixed
  - Lessons learned and patterns extracted
- [ ] Task 17.9: Persist all learnings to Claude Flow memory

### Verification
- [ ] All 16 sections scored >= 8/10 on all 9 Clarity Gate dimensions
- [ ] Full test suite green
- [ ] DSP orphans < 10
- [ ] Zero critical/high security findings
- [ ] Performance baselines met or exceeded
- [ ] Completion report generated

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

- [ ] All 16 sections completed with Clarity Gate scores >= 8/10
- [ ] All acceptance criteria from spec.md met
- [ ] Tests passing (backend + frontend + E2E)
- [ ] Documentation updated where applicable
- [ ] DSP graph reconciled
- [ ] Memory persisted to Claude Flow
- [ ] Completion report generated
- [ ] Ready for review

---

_Generated by Conductor. Tasks will be marked [~] in progress and [x] complete._
