# Codebase Audit Remediation — Conductor Track

**Track**: `codebase-audit-remediation_20260316`
**Created**: 2026-03-16
**Source**: 21-agent swarm audit (19 reports, ~502 findings)
**Method**: Loki-coordinated parallel agent sprints

## Sprint Execution Order

| Sprint | Status | Commit | Description |
|--------|--------|--------|-------------|
| Sprint 0 | COMPLETE | `40e06c9` | Security Critical — 18 P0 fixes, 25 files |
| Sprint 2 | IN PROGRESS | — | Test Integrity & Dependencies — 12 tasks, 6 agents |
| Sprint 1 | QUEUED | — | Auth, Reliability & Race Conditions — 17 P1 fixes |
| Sprint 3 | QUEUED | — | Correctness & UX — 17 P2 fixes |
| Sprint 4 | QUEUED | — | Polish & Forward-Compat — 12 P3 fixes |

> Note: Sprint 2 (test foundation) executes before Sprint 1 (reliability) so that
> improved tests catch any regressions introduced by Sprint 1 reliability changes.

## Workstream Naming Convention

Each sprint is decomposed into **workstreams** (WS) that run as parallel agents:

```
WS-{Sprint}{Letter}-{agent-name}
Example: WS-2A-tests, WS-2B-contracts, WS-1A-race-conditions
```

## Verification Strategy

- Each sprint: full test suite before AND after
- Sprint 0: manual security review of each fix (DONE)
- Sprint 2: verify test count increases (only assertion quality improves)
- Sprint 1: run security E2E after race condition fixes
- All sprints: update CLAUDE.md + memory with patterns discovered

## Audit Reports

Source: `.audit-2026-03-16/*.md` (01-20, excluding 17-accessibility)

## Cross-Cutting Themes

| ID | Theme | Sprints | Status |
|----|-------|---------|--------|
| T1 | SQL Injection via f-string | S0 | FIXED |
| T2 | IDOR / Missing Authorization | S0 | FIXED |
| T3 | Race Conditions (TOCTOU) | S0+S1 | PARTIAL |
| T4 | ORM/Pydantic Confusion | S0 | FIXED |
| T5 | Test Integrity Crisis | S2 | IN PROGRESS |
| T6 | Missing Error Boundaries & Cancel | S0+S2 | IN PROGRESS |
| T7 | Dependency Staleness & Security | S2 | IN PROGRESS |
| T8 | GDPR & Compliance Gaps | S0+S1 | PARTIAL |
| T9 | API Key Leakage in URLs | S1 | QUEUED |
| T10 | Design System Drift | S3 | QUEUED |
