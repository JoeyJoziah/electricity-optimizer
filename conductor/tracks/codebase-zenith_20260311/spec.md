# PRD: Project Zenith — Comprehensive Codebase Excellence Audit & Optimization

**Track ID:** codebase-zenith_20260311
**Type:** Feature (Meta-Initiative)
**Created:** 2026-03-11
**Status:** Draft
**Execution Mode:** Loki Mode (Autonomous RARV Cycles)

---

## Executive Summary

Project Zenith is a systematic, exhaustive audit and optimization initiative that methodically examines every section of the RateShift codebase — backend, frontend, middleware, database, ML pipeline, edge workers, CI/CD, and all integration layers — with a fine-tooth comb. Each section undergoes a rigorous cycle: **audit > research > plan > execute > validate > iterate** until no further improvements can be made, then moves to the next section. The initiative terminates only when the entire codebase has been optimized to its practical ceiling.

## Problem Statement

RateShift has grown rapidly to 353 DSP entities, 715 imports, 42 database tables, 3,392+ tests, 24 CI/CD workflows, and a Cloudflare Worker edge layer. While functional and deployed, no systematic review has been conducted to ensure every component meets its optimal state across performance, security, maintainability, test coverage, and architectural coherence. Organic growth inevitably introduces:

- Suboptimal patterns that persist because "it works"
- Performance bottlenecks hidden behind acceptable-enough latency
- Security surface area that expands with each integration
- Test coverage gaps in edge cases and error paths
- Architectural drift from ideal patterns as features accumulate
- 126 DSP orphan entities that may indicate dead code or missing connections
- Dependency bloat and outdated packages
- Frontend bundle size and rendering optimization opportunities

## Goals & Success Metrics

### Primary Goals

1. **Maximize code quality** — Every file reviewed, every pattern validated against best practices
2. **Maximize performance** — Identify and eliminate all measurable bottlenecks
3. **Maximize security posture** — Full OWASP Top 10 audit, dependency vulnerability scan, auth flow review
4. **Maximize test confidence** — Close all coverage gaps, add missing edge case tests
5. **Maximize maintainability** — Reduce complexity, improve naming, enforce consistency
6. **Resolve all DSP orphans** — 126 orphan entities either reconnected or pruned

### Success Metrics (Exit Criteria)

| Metric | Current | Target |
|--------|---------|--------|
| Backend test count | ~1,917 | Maintained or increased |
| Frontend test count | ~1,475 | Maintained or increased |
| Backend coverage | 80% threshold | 85%+ actual |
| Frontend coverage | 80% threshold | 85%+ actual |
| DSP orphans | 126 | <10 |
| DSP cycles | 0 | 0 (maintained) |
| Lighthouse Performance | Unknown | 90+ |
| Lighthouse Accessibility | Unknown | 95+ |
| TTFB (p95) | Unknown | <200ms |
| API response time (p95) | Unknown | <500ms |
| Bundle size (main) | Unknown | Minimized |
| Security vulnerabilities | Unknown | 0 critical/high |
| Dependency freshness | Unknown | All within 1 major version |

## Scope — 16 Codebase Sections

Each section is audited as an independent unit with its own cycle. Sections are ordered by dependency depth (foundational layers first).

### Section 1: Database Layer
- **Scope**: All 34 migration files, schema design, index strategy, query patterns
- **Files**: `backend/migrations/`, model definitions, database connection setup
- **Focus**: Index optimization, query plan analysis, schema normalization, migration safety

### Section 2: Backend Models & ORM
- **Scope**: All SQLAlchemy models, Pydantic schemas, Region enum, type definitions
- **Files**: `backend/models/`, `backend/schemas/`
- **Focus**: Model relationships, field types, validation rules, serialization performance

### Section 3: Backend Core Infrastructure
- **Scope**: FastAPI app setup, middleware stack, dependency injection, configuration
- **Files**: `backend/main.py`, `backend/config.py`, `backend/deps.py`, middleware files
- **Focus**: Middleware ordering, startup/shutdown lifecycle, config management, error handling

### Section 4: Backend Services Layer
- **Scope**: All business logic services
- **Files**: `backend/services/` (billing, connections, dunning, scraper, agent, email, etc.)
- **Focus**: Service cohesion, error handling patterns, async patterns, retry logic, external API resilience

### Section 5: Backend API Routers
- **Scope**: All API endpoint definitions, request/response contracts
- **Files**: `backend/api/v1/` (all router files including internal endpoints)
- **Focus**: Endpoint design, input validation, response schemas, error responses, rate limiting integration

### Section 6: Backend Data Pipeline
- **Scope**: Internal cron-triggered endpoints, data ingestion, market research
- **Files**: `backend/api/v1/internal/`, data pipeline modules
- **Focus**: Pipeline reliability, idempotency, failure recovery, monitoring

### Section 7: ML Pipeline
- **Scope**: Ensemble predictor, HNSW vector store, adaptive learning, model training
- **Files**: ML-related modules throughout backend
- **Focus**: Model accuracy, inference latency, training efficiency, feature engineering

### Section 8: Backend Testing Infrastructure
- **Scope**: All test files, conftest.py fixtures, mocking patterns
- **Files**: `backend/tests/`, `conftest.py`
- **Focus**: Test quality, fixture design, mock accuracy, coverage gaps, flaky test elimination

### Section 9: Frontend Core Infrastructure
- **Scope**: Next.js config, App Router setup, layouts, routing, middleware
- **Files**: `frontend/next.config.*`, `frontend/app/layout.*`, `frontend/middleware.*`
- **Focus**: SSR/SSG strategy, routing performance, middleware efficiency, config optimization

### Section 10: Frontend Components
- **Scope**: All React components organized by feature area
- **Files**: `frontend/components/` (connections, alerts, dashboard, auth, agent, etc.)
- **Focus**: Component composition, prop drilling vs context, memo optimization, accessibility, render performance

### Section 11: Frontend State & Data Layer
- **Scope**: TanStack Query setup, API client, hooks, context providers
- **Files**: `frontend/lib/`, `frontend/hooks/`, query client configuration
- **Focus**: Cache strategy, query invalidation, optimistic updates, error boundaries, loading states

### Section 12: Frontend Testing Infrastructure
- **Scope**: Jest config, test utilities, component tests, E2E tests
- **Files**: `frontend/__tests__/`, `frontend/playwright/`, `jest.config.*`
- **Focus**: Test patterns, mock quality, E2E reliability, accessibility testing

### Section 13: Cloudflare Worker Edge Layer
- **Scope**: API gateway worker, caching, rate limiting, bot detection
- **Files**: `workers/api-gateway/` (16 files, 37 tests)
- **Focus**: Edge performance, cache hit rates, rate limit accuracy, security headers

### Section 14: CI/CD & Automation
- **Scope**: All 24 GitHub Actions workflows, composite actions, Dependabot config
- **Files**: `.github/workflows/`, `.github/actions/`
- **Focus**: Pipeline speed, reliability, self-healing accuracy, resource usage, secret management

### Section 15: Security & Authentication
- **Scope**: Auth flow (Better Auth + Neon Auth), session management, API key handling, CORS, CSP
- **Files**: Auth-related code across backend and frontend
- **Focus**: Session security, CSRF/XSS protection, secret rotation, permission model, OAuth flows

### Section 16: External Integrations
- **Scope**: Stripe, Resend, OneSignal, Sentry, EIA/NREL APIs, Composio, UtilityAPI
- **Files**: Integration code across services and frontend
- **Focus**: Error handling, retry logic, circuit breakers, webhook verification, API key management

## Process Per Section (The Zenith Loop)

For each of the 16 sections, execute the following loop:

```
CLARITY GATE (Baseline)
    |
    v
AUDIT (Fine-tooth comb analysis)
    |
    v
RESEARCH (Deep research for better approaches)
    |
    v
PLAN (Write full change plan)
    |
    v
EXECUTE (Swarm of experts)
    |
    v
VALIDATE (Integration + regression tests)
    |
    v
ITERATE? --yes--> back to AUDIT
    |
    no (confirmed optimal)
    |
    v
NEXT SECTION
```

### Step 1: Clarity Gate (Baseline Assessment)

Using the Clarity Gate skill's 9-point verification framework, establish an epistemic baseline for the section:
- Factual accuracy of current implementation
- Completeness of test coverage
- Consistency with documented architecture
- Currency of dependencies and patterns
- Absence of known vulnerabilities

**Output**: Quality scorecard with numeric ratings per dimension.

### Step 2: Audit (Comprehensive Analysis)

Deploy specialized audit agents per section type:
- **Code quality**: Complexity metrics, naming consistency, DRY violations, dead code
- **Performance**: Profiling, hot paths, memory allocation, query N+1 detection
- **Security**: OWASP scanning, input validation, output encoding, auth bypass vectors
- **Testing**: Coverage gaps, missing edge cases, assertion quality, flaky tests
- **Architecture**: Coupling analysis, cohesion metrics, dependency direction violations

**Output**: Detailed findings report with severity classification (Critical/High/Medium/Low/Info).

### Step 3: Research (Deep Investigation)

For each High/Critical finding, launch `/deep-research` + `/research-engineer`:
- Survey current best practices for the specific pattern/technology
- Compare against industry-leading implementations
- Evaluate alternative approaches with trade-off analysis
- Check for newer library versions or replacement candidates
- Assess if the current approach is already optimal

**Output**: Research report per finding with recommended approach and rationale.

### Step 4: Plan (Change Specification)

Using `/plan-writing` and `/writing-plans` skills:
- Write bite-sized tasks (2-5 min each) for every approved change
- TDD-first: test before implementation for each change
- Exact file paths, exact code, exact verification commands
- Group by risk level (low-risk first, high-risk last)
- Include rollback strategy for each change

**Output**: Implementation plan in `docs/plans/` format.

### Step 5: Execute (Swarm Deployment)

Orchestrate a specialized agent swarm per section:

| Section Type | Swarm Composition |
|-------------|-------------------|
| Database | `database-optimizer` + `postgres-pro` + `sql-pro` |
| Backend Core | `backend-architect` + `python-pro` + `fastapi-pro` |
| Backend Services | `backend-developer` + `python-pro` + `debugger` |
| API Layer | `api-designer` + `backend-developer` + `api-documenter` |
| ML Pipeline | `ml-engineer` + `performance-engineer` + `data-scientist` |
| Frontend Core | `nextjs-developer` + `typescript-pro` + `performance-engineer` |
| Frontend Components | `react-pro` + `frontend-developer` + `accessibility-tester` |
| Frontend State | `react-specialist` + `typescript-pro` + `performance-engineer` |
| Workers | `cloudflare-workers-expert` + `performance-engineer` + `security-engineer` |
| CI/CD | `devops-engineer` + `build-engineer` + `sre-engineer` |
| Security | `security-engineer` + `penetration-tester` + `security-auditor` |
| Integrations | `backend-developer` + `api-designer` + `error-detective` |
| Testing | `test-automator` + `qa-expert` + `tdd-london-swarm` |

Each swarm member operates on specific tasks from the plan. Changes are committed incrementally with TDD verification at each step.

### Step 6: Validate (Post-Change Verification)

After all planned changes for a section:
1. Run full test suite (backend + frontend + E2E)
2. Run Clarity Gate re-assessment (compare against baseline)
3. Run integration tests across affected boundaries
4. Performance benchmark comparison (before vs after)
5. Security re-scan if security-related changes were made
6. DSP graph update and orphan recount

**Output**: Validation report with before/after comparison.

### Step 7: Iterate Decision

Compare post-change Clarity Gate scores against baseline:
- If any dimension degraded: **mandatory fix before proceeding**
- If improvement potential remains (>5% gain achievable): **iterate with new audit**
- If section has reached practical optimality: **mark complete, move to next section**

Iteration terminates when:
- All Clarity Gate dimensions score 9/10 or higher
- Performance benchmarks show <2% remaining improvement potential
- Security scan returns 0 findings
- Code review by `architect-reviewer` agent confirms no further structural improvements

## Non-Functional Requirements

- **Zero downtime**: All changes must be backward-compatible and deployable incrementally
- **Zero regression**: Full test suite must pass at every commit
- **Audit trail**: Every change linked to a finding, with before/after evidence
- **Reversibility**: Every change must be independently revertable
- **Memory persistence**: All findings, decisions, and patterns stored in Claude Flow memory for future reference

## Out of Scope

- New feature development (this is optimization-only)
- Database schema changes that require new migrations (index-only changes are in scope)
- UI/UX redesigns (accessibility fixes and performance improvements are in scope)
- Infrastructure provider changes (Render, Vercel, Neon stay as-is)
- Pricing model changes
- Third-party API replacements (unless a direct drop-in improvement exists)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Regression from optimization changes | Medium | High | Full test suite at every commit, TDD-first approach |
| Scope creep into feature development | High | Medium | Strict out-of-scope enforcement, Skeptic agent review |
| Diminishing returns on later iterations | High | Low | Hard exit criteria, practical optimality threshold |
| Context window exhaustion | Medium | Medium | Section isolation, stream-chain pipeline chaining |
| Breaking production during changes | Low | Critical | Incremental deploys, rollback strategy per change |

## Decision Log

| # | Decision | Alternatives | Rationale |
|---|----------|-------------|-----------|
| 1 | 16 sections, foundational-first order | Random order, risk-first order | Foundational changes (DB, models) propagate benefits to higher layers |
| 2 | TDD-first for all changes | Post-hoc testing | Workflow.md mandates strict TDD; prevents regression |
| 3 | Clarity Gate as baseline/exit metric | Ad-hoc quality assessment | Provides consistent, comparable scoring across sections |
| 4 | Swarm-per-section, not single expert | Single agent per section | Specialized agents catch domain-specific issues a generalist would miss |
| 5 | Iterate until practical optimality | Fixed iteration count | Variable complexity per section; some need 1 pass, others need 5 |
| 6 | Zero new migrations in scope | Allow schema changes | Reduces risk; index changes via existing migration framework only |

---

_Generated by Conductor + Multi-Agent Brainstorming. PRD validated through Primary Designer, Skeptic, Constraint Guardian, User Advocate, and Integrator review roles._
