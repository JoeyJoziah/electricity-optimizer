# Conductor - RateShift

Navigation hub for project context and feature development.

## Quick Links

- [Product Definition](product.md)
- [Product Guidelines](product-guidelines.md)
- [Tech Stack](tech-stack.md)
- [Workflow](workflow.md)
- [Tracks Registry](tracks.md)
- [Code Style Guides](code_styleguides/)

## Active Tracks

- [x] [Full-Stack Bug Remediation](tracks/full-stack-bugs_20260310/) — 8 bugs across CI/CD, security, and frontend config (complete)
- [x] [Project Zenith — Codebase Excellence](tracks/codebase-zenith_20260311/) — 16-section comprehensive audit & optimization (audit phase complete, all sections PASS)
- [ ] [Zenith P0 — Production Safety Fixes](tracks/zenith-p0-fixes_20260312/) — 3 P0 fixes: session cache TTL, backend circuit breaker, CI git-add scoping (3 phases, 9 tasks)
- [ ] [CF Worker Resilience](tracks/cf-worker-resilience_20260311/) — KV write exhaustion fix, middleware reordering, zero-KV rate limiting, frontend fallback (5 phases, 38 tasks)

- [ ] [OpenTelemetry Distributed Tracing](tracks/otel-distributed-tracing_20260311/) — Custom spans for 26 services, Grafana Cloud export, TDD (4 phases, 22 tasks)

### Multi-Utility Platform Expansion ("US Uswitch")
> Design doc: [docs/plans/2026-03-11-multi-utility-expansion.md](../docs/plans/2026-03-11-multi-utility-expansion.md) | 23 epics across 4 tracks, 6 waves | $0/mo -> $26/mo at Wave 2

- [x] [Wave 0 — Pre-requisites](tracks/mu-wave0-prereqs_20260311/) — NREL API domain migration, cache table retention (3 new cleanup methods, 39 tests) — **Complete**
- [x] [Wave 1 — Schema Foundation](tracks/mu-wave1-foundation_20260311/) — utility_accounts CRUD + 18 tests, referral system + 15 tests, PWA manifest/SW/install prompt + 11 tests, 2 migrations (038-039) — **Complete**
- [ ] [Wave 2 — First Expansion](tracks/mu-wave2-first-expansion_20260311/) — Natural gas (EIA), community solar (EnergySage), onboarding V2, data quality (5 phases, 25 tasks)
- [ ] [Wave 3 — Depth](tracks/mu-wave3-depth_20260311/) — CCA detection, heating oil, rate change alerting, SEO, affiliate revenue (7 phases, 28 tasks)
- [ ] [Wave 4 — Breadth](tracks/mu-wave4-breadth_20260311/) — Propane tracking, water benchmarking, premium analytics, CI/CD evolution (5 phases, 19 tasks)
- [ ] [Wave 5 — Unification](tracks/mu-wave5-unification_20260311/) — Unified multi-utility dashboard, community features, security hardening (4 phases, 19 tasks)

<!-- Auto-populated by /conductor:new-track -->

## Getting Started

Run `/conductor:new-track` to create your first feature track.
