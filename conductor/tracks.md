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

| [~] | ci-red-triage_20260515 | CI Red Triage — Phase 1 pip-audit ✅, Phase 2 migration SERIAL ✅, Phase 4 lint ruff ✅. **Phase 3 npm audit RESOLVED 2026-05-21 via allow-list** (`.github/scripts/check_npm_audit.py` — fails on high/critical except documented `next`/`kysely` exceptions, review 2026-07-01; blanket `npm audit fix` reverted as non-targeted). All 5 split latent-red children now closed/fixed. Local main + push pending → then parent closes. | 2026-05-15 | 2026-05-21 |
| [~] | ph-relaunch-jun2_20260515 | Product Hunt Relaunch — Jun 2 2026 12:01am PT. Wraps remaining 6 PRD scope items + #4 activation + #13 residual + dress rehearsal + go/no-go gate. Depends on `ci-red-triage_20260515` (CI green) + `pre-launch-completion_20260407` Task 2.3 (social handles overlap). Slip rule: 1-week max to Jun 9, second slip → PRD v4 rewrite | 2026-05-15 | 2026-05-15 |
| [x] | ci-pydantic-import_20260515 | CI Backend Cannot Boot — ✅ FIXED 2026-05-15 (run `25932772064`). Removed `safety==3.0.0` from `requirements-dev.txt`; pydantic stays at 2.12.5; backend now boots in CI. Downstream failures (#9 integration fixture, new #11 rate-limit assertions) are unrelated and tracked separately | 2026-05-15 | 2026-05-15 |
| [x] | ci-migration-apply-jsonb_20260515 | CI Migration Apply (003 jsonb) — fix merged (`f95fffe3`). **VALIDATED 2026-05-21** via Neon ephemeral-branch replay: 003 applies cleanly in a full fresh-from-scratch chain (68/68, psql ON_ERROR_STOP=1, CI-identical). | 2026-05-15 | 2026-05-21 |
| [~] | ci-ml-tensorflow-py312_20260515 | CI ML Tests — install fixed (TF 2.17.1 cp312) AND the runtime Keras-3 regression now FIXED 2026-05-21: CNN-LSTM migrated to Keras 3 (MedianMAE metric for the 3-quantile `[?,24,3]` output, register_keras_serializable on custom classes, lower<=upper enforcement, fig.savefig). `ml/tests/` on main = **723 passed, 9 skipped, 0 failed, 0 errors**. CI's `testpaths=tests` excludes the pre-existing script-style `test_forecaster.py` (4 fixture errors). Local main + push pending → ML Tests CI expected green. | 2026-05-15 | 2026-05-21 |
| [x] | ci-frontend-build-nextconfig_20260515 | CI Frontend Build — fix (commit `911528b9`): `next.config.js` throw-guard for `NEXT_PUBLIC_APP_URL` wrapped in `if (process.env.CI && !process.env.VERCEL) { warn } else { throw }`. **VALIDATED 2026-05-21**: `CI=true npm run build` (empty env) completes locally — guard warns, no throw (closes prior "not run locally" gap); Frontend Build job green in CI run `25939815464`. | 2026-05-15 | 2026-05-21 |
| [x] | ci-frontend-lint-workflow_20260515 | CI Frontend Lint pipeline (ESLint 8.56→9.17 flat-config migration, commit `21f85b87`). **VALIDATED 2026-05-21**: `npm run lint` executes cleanly via `eslint.config.mjs` (no crash); zero `next lint` twins in workflows; no husky lint hook. Closed for its scope (pipeline executes). The 91 errors + 15 warnings the running linter surfaces are owned by `ci-frontend-lint-baseline_20260515` (that's where the CI-green gate lives). | 2026-05-15 | 2026-05-21 |
| [x] | ci-integration-sqlalchemy-session_20260515 | CI Backend Integration Tests — fix (commit `338cfd13`): module-level `@event.listens_for(session.sync_session, ...)` replacing `Session.event`. **VALIDATED 2026-05-21**: 10 tests collect cleanly in 0.04s (no AttributeError) with `.venv` python; SQLAlchemy 2.0.49; zero stale `Session.event` refs codebase-wide; skipif guard present. Deferred: live-DB *pass* run (Docker down, prod unsafe) — skip-clean path (what CI runs) verified. | 2026-05-15 | 2026-05-21 |
| [x] | ci-migration-004-stripe-customer-id_20260515 | CI Migration Apply (004/037 stripe guard) — fix merged (`1fd2d1eb`, DO-block guard on 004 + 037). **VALIDATED 2026-05-21** via Neon replay: both apply cleanly in full fresh chain (68/68). The real stripe_customer_id-missing failure is at 056, fixed under `ci-migration-chain-replay_20260515`. | 2026-05-15 | 2026-05-21 |
| [x] | ci-pandas-py312_20260515 | CI ML Tests (pandas portion) — bump `pandas==2.1.0`→`2.1.1` (commit `f81d0d24`). **VALIDATED 2026-05-21**: pandas 2.1.1 cp312 wheel installs on py3.12.12, imports as 2.1.1, compatible with numpy 1.26.0; zero pandas-related failures in the full ML suite (all 30 ML failures are Keras/matplotlib, tracked in `ci-ml-tensorflow-py312_20260515`). | 2026-05-15 | 2026-05-21 |
| [~] | ci-frontend-lint-baseline_20260515 | Frontend Lint Baseline Cleanup — **DONE + validated 2026-05-21, PUSH PENDING.** `npm run lint` → 0 errors (from 91); 15 no-console warnings retained; full FE suite 3437/3437; config untouched, no rules disabled. Actual breakdown differed from prediction: 17 react-hooks errors (set-state-in-effect/static-components/purity/refs) — all REAL bugs fixed at root cause, none Playwright FPs; 39 no-unused-vars; 35 react/display-name fixed by naming wrappers; 0 no-require-imports. Merged to LOCAL main; push gated separately from migration approval. | 2026-05-15 | 2026-05-21 |
| [~] | ci-migration-chain-replay_20260515 | CI Migration Chain Replay — **FIXED + replay-validated 2026-05-21 (68/68, 0 failed) on a Neon ephemeral branch, psql CI-identical; PENDING COMMIT/PUSH.** Triaged via prod-fork ground truth: real failures were 017 (×2: status, utility_type), 035 (neon_auth.user), 053 + 062 (DATE(timestamptz) not IMMUTABLE), 056 (stripe_customer_id), 061 (model_name→model_version, INFERRED). Original report's 049/051/059 were Docker CONCURRENTLY false-positives; `neondb_owner` was a Docker-env artifact (exists on real Neon). 6 files edited, all additive/guarded (prod-safe). 2 flags: 061 inferred-intent; idempotency re-run fails on 6 OTHER untouched migrations (pre-existing, not CI-tested). | 2026-05-15 | 2026-05-21 |
| [x] | ci-frontend-flaky-tests_20260515 | Frontend Flaky Test Cleanup — 6 files fixed (`decisionPresentation` via fake timers; `ConnectionsOverview` / `RateChangeFeed` / `SupplierSelector` / `ConnectionRates` / `ComparisonTable` via `userEvent.setup({ delay: null })`); 2 inventoried files (`CommunitySolarContent`, `useReports`) had no determinism defect, left untouched. **VALIDATED 2026-05-21**: 8-file set 10/10 consecutive green (108 tests/run), full FE suite 3/3 consecutive @ 3437/3437, fix commit `9340309e` confirmed in origin/main. No `--testTimeout`/`.skip()` regressions. | 2026-05-15 | 2026-05-21 |

<!-- Tracks registered by /conductor:new-track -->
