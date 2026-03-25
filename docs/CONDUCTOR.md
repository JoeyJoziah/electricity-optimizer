# Conductor Framework

**Last Updated**: 2026-03-25

The conductor framework is a track-based project management system used to organize and execute multi-sprint work within RateShift. It provides structured context for AI-assisted development, ensuring that large initiatives are broken into manageable, verifiable phases.

---

## Overview

Conductor tracks are the primary mechanism for planning and executing significant work items: feature development, audit remediations, dependency upgrades, and performance optimization. Each track contains a specification, implementation plan, and structured progress tracking.

The framework was initialized on 2026-03-10 and has since managed 18+ completed tracks covering everything from initial bug fixes to comprehensive codebase audits with 75+ tasks.

---

## Directory Structure

```
conductor/
├── index.md                    # Navigation hub with all tracks listed
├── product.md                  # Product definition (RateShift)
├── product-guidelines.md       # Voice, tone, design principles, accessibility
├── workflow.md                 # TDD policy, commit strategy, code review, verification
├── tech-stack.md               # Technology choices
├── tracks.md                   # Tracks registry (auto-populated)
├── setup_state.json            # Framework initialization state
│
├── code_styleguides/
│   ├── python.md               # Python style conventions
│   ├── typescript.md           # TypeScript style conventions
│   ├── sql.md                  # SQL migration conventions
│   └── shell.md                # Shell script conventions
│
└── tracks/
    ├── full-stack-bugs_20260310/
    │   ├── index.md            # Track overview + status
    │   ├── spec.md             # Requirements specification
    │   └── plan.md             # Implementation plan
    │
    ├── codebase-zenith_20260311/
    │   ├── index.md
    │   ├── spec.md
    │   ├── phase0-baseline.md
    │   └── sections/           # 16 section-specific directories
    │       ├── 01-database/
    │       │   ├── baseline.md
    │       │   ├── audit.md
    │       │   ├── research.md
    │       │   ├── changes.md
    │       │   ├── validation.md
    │       │   └── iterations.log
    │       ├── 02-models-orm/
    │       │   └── ...
    │       └── ... (through 16-integrations/)
    │
    └── <track-id>/
        ├── index.md            # Always present
        ├── spec.md             # Always present
        ├── plan.md             # Optional
        └── metadata.json       # Optional
```

---

## How Tracks Work

### Track Naming Convention

Tracks follow the pattern `<descriptive-name>_<YYYYMMDD>`:
- `full-stack-bugs_20260310` -- what + when created
- `audit-remediation_20260323` -- allows multiple tracks of the same type

### Track Lifecycle

```
CREATED -> IN PROGRESS -> VERIFICATION -> COMPLETE
                |                |
                v                v
            BLOCKED          FAILED (reopens)
```

### Key Files

| File | Purpose |
|------|---------|
| `index.md` | Track title, ID, status, and links to other documents. Always present. |
| `spec.md` | Requirements specification: context, scope, acceptance criteria, phases. |
| `plan.md` | Implementation plan: task breakdown, dependencies, estimates. |
| `metadata.json` | Optional structured metadata (dates, assignees, tags). |

### `setup_state.json`

The framework-level state file tracks:
- `status`: Current framework status (`complete` after initial setup)
- `project_type`: `brownfield` (existing codebase) or `greenfield`
- `completed_sections`: Which setup wizard sections have been completed
- `answers`: Captured project context (name, stack, policies, etc.)
- `files_created`: List of all generated framework files

---

## All 18+ Completed Tracks

| # | Track ID | Title | Date | Summary |
|---|----------|-------|------|---------|
| 1 | `full-stack-bugs_20260310` | Full-Stack Bug Remediation | 2026-03-10 | 8 bugs across CI/CD, security, and frontend config |
| 2 | `codebase-zenith_20260311` | Project Zenith -- Codebase Excellence | 2026-03-11 | 16-section comprehensive audit and optimization (all sections PASS) |
| 3 | `cf-worker-resilience_20260311` | CF Worker API Gateway Resilience | 2026-03-11 | KV write exhaustion fix, middleware reordering, zero-KV rate limiting, frontend fallback |
| 4 | `zenith-p0-fixes_20260312` | Zenith P0 Production Safety Fixes | 2026-03-12 | 3 P0 fixes: session cache TTL, backend circuit breaker, CI git-add scoping |
| 5 | `otel-distributed-tracing_20260311` | OpenTelemetry Distributed Tracing | 2026-03-11 | Custom spans for 26 services, Grafana Cloud export |
| 6 | `mu-wave0-prereqs_20260311` | Wave 0 -- Pre-requisites | 2026-03-11 | NREL API domain migration, cache table retention |
| 7 | `mu-wave1-foundation_20260311` | Wave 1 -- Schema Foundation | 2026-03-11 | utility_accounts CRUD, referral system, PWA manifest |
| 8 | `mu-wave2-first-expansion_20260311` | Wave 2 -- First Expansion | 2026-03-11 | Natural gas (EIA), community solar (EnergySage), onboarding V2 |
| 9 | `mu-wave3-depth_20260311` | Wave 3 -- Depth | 2026-03-11 | CCA detection, heating oil, rate change alerting, SEO, affiliate revenue |
| 10 | `mu-wave4-breadth_20260311` | Wave 4 -- Breadth | 2026-03-11 | Propane tracking, water benchmarking, premium analytics |
| 11 | `mu-wave5-unification_20260311` | Wave 5 -- Unification | 2026-03-11 | Unified multi-utility dashboard, community features, security hardening |
| 12 | `codebase-audit-remediation_20260316` | Codebase Audit Remediation | 2026-03-16 | Initial audit findings remediation |
| 13 | `perf-optimization_20260316` | Performance Optimization | 2026-03-16 | Brainstorm-validated performance improvements |
| 14 | `dependency-upgrade_20260317` | Dependency Upgrade | 2026-03-17 | Security remediation and major version bumps |
| 15 | `audit-remediation_20260317` | Audit Remediation (Mar 17) | 2026-03-17 | Codebase audit findings remediation |
| 16 | `audit-remediation_20260318` | Audit Remediation (Mar 18) | 2026-03-18 | Continued audit remediation |
| 17 | `verification-gates_20260318` | Verification & Integration Quality Gates | 2026-03-18 | Pre-commit hooks, pre-push gate, conductor verification, API contract checks |
| 18 | `audit-remediation_20260319` | Audit Remediation (Mar 19) | 2026-03-19 | 514 findings from 20-agent audit, 66 tasks across 10 sprints |
| 19 | `audit-remediation_20260323` | Audit Remediation (Mar 23) | 2026-03-23 | ~560 findings, 75 tasks across 9 sprints (security, auth, test quality, a11y) |
| 20 | `launch-readiness_20260323` | Launch-Gap Analysis | 2026-03-23 | 5-phase launch-readiness assessment producing prioritized gap backlog |

---

## Creating a New Track

### 1. Create the directory and files

```bash
mkdir -p conductor/tracks/<name>_<YYYYMMDD>
```

### 2. Create `index.md`

```markdown
# Track: <Title>

**ID:** <name>_<YYYYMMDD>
**Status:** Pending

## Documents

- [Specification](spec.md)
- [Implementation Plan](plan.md)
```

### 3. Create `spec.md`

Include:
- **Context**: Why this work is needed
- **Scope**: What is in/out of scope
- **Phases**: Breakdown into sequential phases
- **Tasks**: Specific items per phase with acceptance criteria
- **Success criteria**: How to verify completion

### 4. Register in `conductor/index.md`

Add the track to the "Active Tracks" section:
```markdown
- [ ] [Track Title](tracks/<name>_<YYYYMMDD>/) -- Brief description
```

### 5. Mark complete

When all tasks pass verification:
1. Update `index.md` status to `Complete`
2. Change the checkbox in `conductor/index.md` from `- [ ]` to `- [x]`

---

## Workflow Integration

### TDD Policy

Conductor enforces **strict TDD**: tests are written before implementation. Each phase requires:
1. All phase tasks marked complete
2. Tests pass (backend + frontend)
3. No regressions in existing functionality
4. Documentation updated if applicable

### Commit Strategy

All commits follow conventional commit format: `<type>(<scope>): <description>`

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`

### Verification Checkpoints

Manual verification is required after each phase completion:
- All phase tasks marked complete
- Tests pass
- No regressions
- Board sync triggered (GitHub Projects)
- Memory persisted to Claude Flow

---

## Integration with CI/CD

Conductor tracks interact with CI/CD in several ways:

1. **`validate-migrations` composite action**: Enforces migration conventions defined in conductor's SQL style guide (sequential numbering, `IF NOT EXISTS`, `neondb_owner`, no SERIAL)
2. **Self-healing monitor**: Tracks workflow failures, auto-creates GitHub issues after 3+ failures with the `self-healing` label
3. **Board sync hooks**: Post-commit and post-edit hooks trigger GitHub Projects #4 sync, keeping the project board in sync with conductor progress
4. **Pre-commit hooks**: Configured via `.pre-commit-config.yaml` for code quality (Black, isort, lint)

---

## Code Style Guides

The `conductor/code_styleguides/` directory contains language-specific conventions:

| Guide | Coverage |
|-------|----------|
| `python.md` | FastAPI patterns, Pydantic models, service layer, testing (pytest) |
| `typescript.md` | Next.js App Router, React 19, Zustand, TanStack Query, component patterns |
| `sql.md` | Migration conventions, UUID PKs, indexing, GRANT roles |
| `shell.md` | Bash scripting for GHA workflows, composite actions, deploy scripts |

---

## Related Documentation

- `CLAUDE.md` -- Project-level instructions and architecture quick reference
- `docs/AUTOMATION_PLAN.md` -- CI/CD workflow details
- `docs/WORKFLOWS.md` -- Full GHA workflow catalog
- `.project-intelligence/MASTER_TODO_REGISTRY.json` -- Cross-track task registry
