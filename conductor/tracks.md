# Tracks Registry

| Status | Track ID | Title | Created | Updated |
| ------ | -------- | ----- | ------- | ------- |
| [x] | full-stack-bugs_20260310 | Full-Stack Bug Remediation | 2026-03-10 | 2026-03-10 |
| [x] | codebase-zenith_20260311 | Project Zenith — Superseded by audit-remediation tracks | 2026-03-11 | 2026-03-18 |
| [x] | cf-worker-resilience_20260311 | CF Worker API Gateway Resilience & Rate Limit Overhaul | 2026-03-11 | 2026-03-11 |
| [x] | otel-distributed-tracing_20260311 | OpenTelemetry Distributed Tracing | 2026-03-11 | 2026-03-11 |
| [x] | mu-wave0-prereqs_20260311 | Multi-Utility Wave 0 — Pre-requisites (NREL + Cache Retention) | 2026-03-11 | 2026-03-11 |
| [x] | mu-wave1-foundation_20260311 | Multi-Utility Wave 1 — Schema Foundation + Growth Basics | 2026-03-11 | 2026-03-11 |
| [x] | mu-wave2-first-expansion_20260311 | Multi-Utility Wave 2 — Natural Gas + Community Solar | 2026-03-11 | 2026-03-11 |
| [x] | mu-wave3-depth_20260311 | Multi-Utility Wave 3 — CCA, Heating Oil, Alerting, SEO, Affiliate | 2026-03-11 | 2026-03-11 |
| [x] | mu-wave4-breadth_20260311 | Multi-Utility Wave 4 — Propane, Water, Premium Analytics | 2026-03-11 | 2026-03-18 |
| [x] | mu-wave5-unification_20260311 | Multi-Utility Wave 5 — Unified Dashboard, Community, Security | 2026-03-11 | 2026-03-12 |

| [x] | perf-optimization_20260316 | Performance Optimization — Brainstorm-Validated | 2026-03-16 | 2026-03-16 |

| [x] | dependency-upgrade_20260317 | Dependency Upgrade — Security Remediation & Major Version Bumps | 2026-03-17 | 2026-03-17 |

| [x] | audit-remediation_20260317 | Codebase Audit Remediation 2026-03-17 | 2026-03-17 | 2026-03-17 |

| [x] | verification-gates_20260318 | Verification & Integration Quality Gates | 2026-03-18 | 2026-03-18 |

| [x] | audit-remediation_20260318 | Codebase Audit Remediation 2026-03-18 (568 findings, 39 tasks) | 2026-03-18 | 2026-03-18 |

| [x] | audit-remediation_20260319 | Codebase Audit Remediation 2026-03-19 (514 findings, 66 tasks) | 2026-03-19 | 2026-03-19 |

| [x] | audit-remediation_20260323 | Codebase Audit Remediation 2026-03-23 (~560 findings, 75 tasks, 9 sprints) | 2026-03-23 | 2026-03-23 |

| [~] | pre-launch-completion_20260407 | Pre-Launch Completion — Infra, GA4, Code TODOs, CF Data Quality. **Sprint 2 partial: Task 2.1 visual regression baseline DONE 2026-05-11 (workflow fixed across 3 commits, 12 chromium-linux baselines committed). Remaining: 2.2 status page, 2.3 social media accounts** | 2026-04-07 | 2026-05-11 |
| [x] | launch-execution_20260407 | Product Hunt Launch Execution — SUPERSEDED 2026-05-15 by `ph-relaunch-jun2_20260515`. The Apr 14 2026 launch never happened; Phase 0 deliverables (PH account, date selection) preserved as historical record. Jun 2 2026 attempt is tracked in the new conductor track | 2026-04-07 | 2026-05-15 |
| [ ] | post-launch-growth_20260407 | Post-Launch Growth & Scaling — Infra Triggers, Product Expansion, Community (17 tasks, trigger-gated, starts post-launch). Gate still closed pending launch-execution resumption | 2026-04-07 | 2026-05-11 |

| [x] | zenith-p0-fixes_20260312 | Zenith P0 — Production Safety Fixes (superseded by audit-remediation line) | 2026-03-12 | 2026-05-11 |
| [x] | codebase-audit-remediation_20260316 | Codebase Audit Remediation 2026-03-16 (5 sprints: security, reliability, tests/deps, correctness, polish) | 2026-03-16 | 2026-05-11 |
| [x] | launch-readiness_20260323 | Launch-Gap Analysis | 2026-03-23 | 2026-05-11 |

| [~] | ci-red-triage_20260515 | CI Red Triage — 4 originally-planned failures (Phase 1 pip-audit ✅, Phase 2 migration SERIAL ✅, Phase 3 npm audit HALTED on Next 16 unfixable, Phase 4 lint config drift ✅ ruff replaces black+flake8). +5 latent reds SPLIT 2026-05-15 into: `ci-migration-apply-jsonb_20260515`, `ci-ml-tensorflow-py312_20260515`, `ci-frontend-build-nextconfig_20260515`, `ci-frontend-lint-workflow_20260515`, `ci-integration-sqlalchemy-session_20260515`. Phase 3 (npm audit) remains the only open item on this parent track | 2026-05-15 | 2026-05-15 |
| [~] | ph-relaunch-jun2_20260515 | Product Hunt Relaunch — Jun 2 2026 12:01am PT. Wraps remaining 6 PRD scope items + #4 activation + #13 residual + dress rehearsal + go/no-go gate. Depends on `ci-red-triage_20260515` (CI green) + `pre-launch-completion_20260407` Task 2.3 (social handles overlap). Slip rule: 1-week max to Jun 9, second slip → PRD v4 rewrite | 2026-05-15 | 2026-05-15 |
| [x] | ci-pydantic-import_20260515 | CI Backend Cannot Boot — ✅ FIXED 2026-05-15 (run `25932772064`). Removed `safety==3.0.0` from `requirements-dev.txt`; pydantic stays at 2.12.5; backend now boots in CI. Downstream failures (#9 integration fixture, new #11 rate-limit assertions) are unrelated and tracked separately | 2026-05-15 | 2026-05-15 |
| [~] | ci-migration-apply-jsonb_20260515 | CI Migration Apply — ✅ FIX MERGED 2026-05-15 (commit `f95fffe3`). Idempotent DROP DEFAULT → cast(`array_to_json(...)::jsonb`) → SET DEFAULT `'[]'::jsonb` in 003_reconcile_schema. Docker-verified via postgres:16-alpine. **Awaiting CI green confirmation.** Caveat: apply-from-scratch step will still fail downstream on migration 004 (`stripe_customer_id` missing) — see `ci-migration-004-stripe-customer-id_20260515` | 2026-05-15 | 2026-05-15 |
| [~] | ci-ml-tensorflow-py312_20260515 | CI ML Tests — ✅ FIX MERGED 2026-05-15 (commit `69e253b8`). Bumped to `tensorflow==2.17.1` + `tensorboard==2.17.1` + `tf-keras==2.17.0` shim. 6 touchpoints verified import-compatible under Keras 3.14.1. **Awaiting CI green.** Caveat: pandas 2.1.0 also lacks Py3.12 wheels — see `ci-pandas-py312_20260515` | 2026-05-15 | 2026-05-15 |
| [~] | ci-frontend-build-nextconfig_20260515 | CI Frontend Build — ✅ FIX MERGED 2026-05-15 (commit `911528b9`). Root cause was NOT ESM/syntax — `next.config.js:12` was a `throw` guard requiring `NEXT_PUBLIC_APP_URL` in production; CI runs `next build` with `NODE_ENV=production` but doesn't set that env var. Wrapped throw in `if (process.env.CI && !process.env.VERCEL) { warn } else { throw }`. Vercel deploy safety preserved. **Awaiting CI green.** Verification gap: `npm run build` not run locally (no node_modules in worktree) | 2026-05-15 | 2026-05-15 |
| [ ] | ci-frontend-lint-workflow_20260515 | CI Frontend Lint — 🛑 SCOPE EXPANDED 2026-05-15. Original hypothesis (workflow shell typo) was WRONG. Root cause: `next lint` was REMOVED in Next 16; the CLI parses `lint` as positional project-dir arg, producing the misleading directory error. Fix requires migrating from `next lint` to direct ESLint + bumping `eslint` 8→9 (v8.57.1 incompatible with `eslint-config-next@16.0.7` flat-config) + migrating `.eslintrc.json` → `eslint.config.mjs`. Workflow-only patch insufficient. See expanded plan.md. Launch-blocker for `ph-relaunch-jun2_20260515` | 2026-05-15 | 2026-05-15 |
| [~] | ci-integration-sqlalchemy-session_20260515 | CI Backend Integration Tests — ✅ FIX MERGED 2026-05-15 (commit `338cfd13`). Single call site at `backend/tests/integration/conftest.py:70`. Replaced `@session.sync_session.event.listens_for(...)` with module-level `@event.listens_for(session.sync_session, ...)`. Skip-if-no-DATABASE_URL guard already in place at conftest.py:27. 10 tests collect cleanly. **Awaiting CI green.** | 2026-05-15 | 2026-05-15 |
| [ ] | ci-migration-004-stripe-customer-id_20260515 | CI Migration Apply (continued) — `004_performance_indexes.sql:12` fails on fresh replay: `column "stripe_customer_id" does not exist`. Discovered 2026-05-15 by `ci-migration-apply-jsonb_20260515` agent during Docker verification. Migration 004 references a column that doesn't exist at that point in history. Likely needs guard or reordering. Launch-blocker for `ph-relaunch-jun2_20260515` | 2026-05-15 | 2026-05-15 |
| [ ] | ci-pandas-py312_20260515 | CI ML Tests (continued) — `pandas==2.1.0` in `ml/requirements.txt` has no cp312 wheels on PyPI. Discovered 2026-05-15 by `ci-ml-tensorflow-py312_20260515` agent. Lowest cp312-compatible is `pandas==2.1.1` (1-line patch bump). Launch-blocker for `ph-relaunch-jun2_20260515` | 2026-05-15 | 2026-05-15 |

<!-- Tracks registered by /conductor:new-track -->
