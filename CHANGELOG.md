# Changelog

All notable changes to RateShift (formerly Electricity Optimizer) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.0] - 2026-03-16

### Added
- **End-to-End Performance Optimization**: 9 optimizations across backend + frontend validated via multi-agent brainstorming.
  - Backend: SQL aggregate `get_price_trend_aggregates()` (CTE+ROW_NUMBER), Redis+in-memory tier cache (30s TTL), rate limiter eviction fix (`setdefault`+10K sweep), moderation timeout 30s to 5s.
  - Frontend: SSE partial-merge `setQueryData`, `React.memo` on 4 dashboard components, CLS fix, NotificationBell background refetch disabled, 4 `loading.tsx` skeleton loaders.
- **All connection types fixed**: Direct login, email scan, bill upload, portal scrape, and UtilityAPI connections fully operational.
- **Test isolation**: conftest autouse fixture for `_tier_cache` (fixed 15 flaky tests).

### Changed
- Backend tests: 2,478 to 2,480. Frontend tests: 1,835 to 1,841. Total: ~5,680.
- Full documentation refresh: ARCHITECTURE.md, DEVELOPER_GUIDE.md, 5 ADRs, all codemaps/API ref/DB schema/testing docs updated.

## [1.3.0] - 2026-03-12

### Added
- **Wave 5: Unification**: Unified tabbed multi-utility dashboard, community features (posts, voting, reporting), AI moderation (Groq `classify_content()` primary, Gemini fallback), nh3 XSS sanitization.
- **Security hardening**: OWASP ZAP weekly scan (`owasp-zap.yml`), `pip-audit` in backend CI, `npm audit --audit-level=high` in frontend CI. `.zap/rules.tsv` with 5 false-positive suppression rules.
- **Community tables**: Migrations 048-049 (community_posts, community_votes, community_reports). 15 sidebar nav items.

### Changed
- Backend tests: 2,306 to 2,478. Frontend tests: 1,718 to 1,835.

## [1.2.0] - 2026-03-12

### Added
- **Wave 4: Breadth** — Water rates (WaterRateService, 7 methods, `/rates/water`, migration 047), Propane rates (PropaneService, 6 methods, `/rates/propane/*`, migration 046), SEO pages for propane and water.
- **Wave 3: Depth** — CCA detection (14 programs seeded), heating oil tracking (15 dealers seeded), rate change alerting, SEO engine (153 ISR pages), affiliate revenue tracking, scalability prep.
- Migrations 042-049 deployed (cca_programs, heating_oil_prices/dealers, alerting tables, affiliate_clicks, propane_prices, water_rates, utility_feature_flags, community_tables).

## [1.1.0] - 2026-03-12

### Added
- **Wave 2: Infrastructure** — Natural gas rates, community solar programs, onboarding v2 (simplified from 215 to 43 lines), data quality framework (freshness thresholds, anomaly detection, source failure alerts).
- **OpenTelemetry Distributed Tracing**: `traced()` context manager, 10 services instrumented (16 span types), 37 tracing tests, Grafana Cloud Tempo connected.
- **CF Worker Resilience**: Graceful KV degradation (fail-open), middleware reordering, native rate limiting bindings, frontend circuit breaker (auto-fallback to Render), per-isolate observability counters.
- **Project Zenith audit**: 16-section Clarity Gate audit, all sections PASS. P0 fixes: session cache TTL 300 to 60s, generic circuit breaker, CI git-add scoping.

### Changed
- Database: 33 to 44 public tables, migrations through 041. GHA workflows: 28 to 30.
- Backend tests: 1,917 to 2,306. Frontend tests: 1,475 to 1,718.

## [1.0.0] - 2026-03-11

### Added
- **AI Agent (RateShift AI)**: Gemini 3 Flash primary (free 10 RPM/250 RPD) with Groq Llama 3.3 70B fallback. SSE streaming via `POST /agent/query`, async jobs via `POST /agent/task`, usage stats via `GET /agent/usage`. Rate limits: Free=3/day, Pro=20/day, Business=unlimited. Frontend `/assistant` page with AgentChat component.
- **Cloudflare Workers API Gateway**: Full edge layer at `api.rateshift.app/*`. 2-tier caching (Cache API + KV), KV rate limiting (standard 120/min, strict 30/min, internal 600/min), bot detection via heuristic scoring, internal auth (constant-time X-API-Key compare), CORS origin allowlist, security headers (HSTS, X-Content-Type-Options, X-Frame-Options).
- **Domain Migration**: rateshift.app purchased via Cloudflare Registrar. DKIM/SPF/DMARC configured on Resend. Full DNS setup with A record to Vercel, CNAME api to Render proxied via CF Worker.
- **Notification Delivery Tracking**: Migration 029 adds `error_message` column, delivery_status tracking. NotificationRepository and error handling throughout notification pipeline.
- **A/B Testing Framework**: Migration 030 introduces `model_predictions`, `model_versions`, `ab_tests`, `ab_outcomes` tables. ABTestService with SHA-256 deterministic assignment. Consistent hashing ensures same user always sees same variant.
- **Model Versioning**: Track model versions across predictions, enable rollback capability, versioned feature stores in HNSW vector index.
- **OpenTelemetry Support**: Opt-in via OTEL_ENABLED flag. OTLP/HTTP exporter with fallback to console and silent modes. Instrumentation for FastAPI, asyncpg, requests.
- **Beta to Public Signup Transition**: Backward-compatible `/beta/*` routes with validation_postcode on beta signups. Clean public signup path without postcode requirement.
- **NotificationDispatcher & NotificationBell UI**: Central dispatch service wired into check_alerts and dunning-cycle workflows. Frontend Bell icon with useNotifications hook, unread count, delivery status.
- **Beta Invites System**: Batch invite endpoint, invite-stats, conversion tracking. Supports bulk CSV upload for early access users.

### Changed
- **Brand Rename**: Electricity Optimizer renamed to RateShift throughout codebase (16+ files).
- **Frontend Stack**: Next.js 14 upgraded to Next.js 16, React 18 upgraded to React 19. Resolved eslint 9 compatibility via `.npmrc` legacy-peer-deps=true.
- **Testing Library**: @testing-library/react upgraded to v16 for React 19 compatibility.
- **CORS Configuration**: Updated for rateshift.app domain (both root and www subdomain).
- **Email Sender**: Updated to `RateShift <noreply@rateshift.app>` across Render, Vercel, and Resend.
- **Self-Healing CI/CD**: 3 new composite actions (retry-curl, notify-slack, validate-migrations). All 12 cron workflows enhanced with exponential backoff retry logic and Slack failure alerts to #incidents. self-healing-monitor auto-creates issues after 3+ consecutive failures.
- **Automation Phases**: All 3 phases complete (7/7 workflows live). Phase 1: Sentry, Deploy, GitHub to Slack/Notion. Phase 2: check-alerts, fetch-weather, market-research, sync-connections, scrape-rates. Phase 3: dunning-cycle, kpi-report.
- **Render Environment**: 34 env vars expanded to 38 with AI agent keys (GEMINI_API_KEY, GROQ_API_KEY, COMPOSIO_API_KEY, ENABLE_AI_AGENT).
- **GHA Cost Optimization**: CI/CD overhaul reduced cost from 6,360 to 3,720 min/month (-41%). Python 3.12 standardized, schedule conflicts resolved, composite actions consolidated.

### Fixed
- **URI_TOO_LONG (414)**: Price update endpoint refactored to handle large supplier lists via pagination.
- **Design System Consistency**: Input component refactored with labelSuffix, labelRight, success props. All auth forms (login, signup, forgot password, reset) now use shared Input component. Zero raw Tailwind colors in auth pages.
- **Connection Feature Bugs**: Migrations 021-022 address email OAuth failure modes, bill upload timeout handling, settings page regressions.
- **Neon Auth Session Tracking**: Active user detection uses `neon_auth.session."updatedAt"` (quoted identifiers). No separate `last_login_at` column.
- **Migrations Never Applied**: Full audit discovered migrations 029-033 code was deployed but schema was missing. All 5 migrations applied to Neon production via MCP.
- **Gitleaks False Positives**: Allowlist added for `.dsp/uid_map.json` hex hashes.
- **CSP Clarity.ms Integration**: Added `https://*.clarity.ms` to script-src and img-src directives.
- **Maintenance Endpoint Resilience**: `/internal/maintenance/cleanup` runs tasks independently, returns `{status: "partial"}` on partial failures instead of 500.

### Security
- **Cloudflare Workers Hardening**: Constant-time X-API-Key comparison, bot detection scoring, CORS strict allowlist, security headers enforcement.
- **Container & Secret Scanning**: Trivy vulnerability scanning in build pipeline, gitleaks secret detection on PRs and main branch.
- **Code Analysis**: security-scan.yml fails on high/critical findings.
- **Deploy Safety**: No skip_tests bypass. Test job mandatory for production deploys. Python 3.12 standardized across all CI.

### Removed
- **Legacy Domain**: electricity-optimizer.app retired in favor of rateshift.app.
- **Memory Error Patterns Namespace**: Purged 2,589 stale error-pattern entries from Claude Flow memory.

## [0.9.0] - 2026-03-09

### Added
- **DSP Codebase Graph**: 326 entities (301 objects, 25 external deps), 327 imports with WHY reasons, 11 shared exports, 0 cycles. CLI: `python3 dsp-cli.py --root . <command>`. Commands: search, get-recipients, get-children, find-by-source, detect-cycles, get-stats.
- **Conductor Framework**: 11 files including setup_state, tracks, spec/plan/metadata/index.md per track. First track: full-stack-bugs_20260310 (8 bugs, 4 phases, 14 tasks).

### Changed
- **Slack Workspace Migration**: Moved to electricityoptimizer.slack.com (T0AK0AJV5NE) from previous workspace. Channels: #incidents, #deployments, #metrics.
- **Memory Sync Swarm**: Consolidated 4,418+ entries across Claude Flow and Loki Mode. Cross-verification via memory_search.
- **Notion Hub Rebuild**: 3-tier database structure (Tracker, Automation, Architecture Decisions). Updated sync via Rube recipe every 6 hours.

## [0.8.0] - 2026-03-06

### Added
- **Automation Phase 1**: 3 Rube recipes scheduled. Sentry alerts to Slack #incidents (15min), Deploy status to Slack + BetterStack (hourly), GitHub to Notion (6h).
- **Automation Phase 2**: 5 GHA cron workflows. check-alerts (*/30min, dedup cooldowns), fetch-weather (*/6h, parallel asyncio.gather + Semaphore(10)), market-research (daily 2am), sync-connections (*/2h), scrape-rates (daily 3am).
- **Automation Phase 3**: Stripe dunning-cycle (daily 7am, 7-day grace period) and kpi-report (daily 6am, Google Sheets + Slack #metrics). Migration 024: payment_retry_history table.
- **Production Audit Grade A-**: 16 findings remediated. Tier gating via `require_tier()` on 7 endpoints. Free tier: 1 alert limit. Alerts UI at `/alerts` page. Health monitoring via `/internal/health-data`.
- **Self-Healing CI/CD Foundation**: RequestBodySizeLimitMiddleware (1 MB), RequestTimeoutMiddleware (30s, excludes internal batch endpoints and `/prices/stream`).

### Changed
- **Migration 023**: Model adjustments for Neon Auth integration.
- **Migration 024**: Payment retry history tracking with 24h dedup for dunning notifications.
- **Migration 025**: 3 cache tables added for weather, market data, price snapshots.
- **Middleware Configuration**: GHA workflows exclude `/api/v1/internal/*` from 30s timeout, 60s available for batch operations.

## [0.7.0] - 2026-03-04

### Added
- **Agentic-Flow Integration**: 34 symlinked agents via SPARC mode (af-* namespace). 8 skills, 7 commands, 4 helpers. MCP tools: mcp__agentic-flow__*.
- **Multi-Repo Skill Integration**: 2,099 skills across 15 GitHub repos. Vendor skills (37): Vercel, Better Auth, Neon, Stripe, Sentry, Trail of Bits, Cloudflare. Curated (1,087). Composio connections (16 active). Routing optimizer at `skill-router/`.
- **Composio Integrations**: 9 new connections (Gmail, GitHub, Firecrawl, Sentry, Vercel, Resend, Stripe, Render, Google Sheets).

### Changed
- **UI/UX Design System Overhaul**: Input component refactoring. Standardized colors (blue-*->primary-*, red-*->danger-*, green-*->success-*). CSS variables in globals.css, Tailwind shadow/animation tokens.
- **Auth Forms Refactored**: LoginForm, SignupForm, ForgotPassword, ResetPassword, VerifyEmail all use shared Input component.
- **Connections Feature Fixes**: Bug fixes for email OAuth, bill upload timeout, settings page. Migrations 021-022.

## [0.6.0] - 2026-03-03

### Fixed
- **URI_TOO_LONG (414)**: Price update endpoint now handles large supplier lists via pagination.
- **Design System**: Input component enhanced with labelSuffix, labelRight, success props.

## [0.5.0] - 2026-03-02

### Changed
- **Swarm Audit**: 6 batches covering 107 files. Identified refactoring opportunities, tech debt, and consolidation targets.

## [0.4.0] - 2026-02-26

### Added
- **Nationwide Expansion**: Support for all 50 states + DC + international regions via Region enum.

## [0.3.0] - 2026-02-25

### Added
- **Connection Feature (5 Phases)**: Foundation, Bill OCR, Email OAuth, UtilityAPI sync, Analytics dashboard. schema: connection_extracted_rates uses effective_date, supplier_name from user_connections.

## [0.2.0] - 2026-02-23

### Added
- **Multi-Utility Support**: Expanded to handle multiple utility providers per user.
- **Neon Auth Integration**: Session-based auth with Better Auth, httpOnly cookies, Resend email (verification, magic link, password reset).
- **Adaptive Learning System**: ML ensemble predictor with HNSW vector store. Observation loop for continuous improvement.
- **Payment Tiers**: Free, Pro ($4.99/mo), Business ($14.99/mo) via Stripe.
- **Email Notifications**: Resend primary + Gmail SMTP fallback via nodemailer. Sender: `RateShift <noreply@rateshift.app>`.
- **Alerts System**: Price threshold alerts with dedup cooldowns (immediate=1h, daily=24h, weekly=7d). UI at `/alerts` page.
- **OneSignal Push Notifications**: User binding via `loginOneSignal(userId)` post-auth.

## [0.1.0] - 2026-02-01

### Added
- **Project Foundation**: FastAPI backend + Next.js frontend. Neon PostgreSQL (21 public + 9 neon_auth tables).
- **Core Features**: Multi-region electricity rate optimization, supplier discovery, automated bill analysis.
- **ML Pipeline**: Ensemble predictor with adaptive learning, HNSW vector search.
- **Payments**: Stripe integration with Free/Pro/Business tiers.
- **Testing**: Backend 1,400+ tests (pytest), Frontend 1,400+ tests (Jest), E2E (Playwright).
- **CI/CD**: 23 GitHub Actions workflows, Dependabot for dependency updates.
- **Documentation**: API reference, deployment guides, security audits.

[Unreleased]: https://github.com/JoeyJoziah/electricity-optimizer/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/JoeyJoziah/electricity-optimizer/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/JoeyJoziah/electricity-optimizer/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/JoeyJoziah/electricity-optimizer/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/JoeyJoziah/electricity-optimizer/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v1.0.0
[0.9.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v0.9.0
[0.8.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v0.8.0
[0.7.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v0.7.0
[0.6.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v0.6.0
[0.5.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v0.5.0
[0.4.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v0.4.0
[0.3.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v0.3.0
[0.2.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v0.2.0
[0.1.0]: https://github.com/JoeyJoziah/electricity-optimizer/releases/tag/v0.1.0
