# RateShift — Project Instructions

> Last validated: 2026-03-17 (Audit remediation 59/59 COMPLETE — CF Worker 3 cron triggers. Backend 2,686 tests, Frontend 2,039 tests (154 suites), E2E 1,605 (25 specs, 5 browsers), Worker 90, ML 611 = ~7,031 total. 53 migrations (053: notification_dedup_index). 53 tables (44 public + 9 neon_auth). 15 sidebar nav items. 32 GHA workflows. DSP graph: 474 entities, 940+ imports, 1 real cycle. GHA estimated ~1,283 min/mo.)

## Session Initialization Protocol (MANDATORY)

At the START of every new conversation, before doing any user-requested work, run these steps **in order**:

### Step 1: Claude Flow + Memory
```
Call mcp__claude-flow__hooks_session-start with startDaemon: true, restoreLatest: true
Call mcp__claude-flow__memory_stats to confirm memory DB is active (expect 17+ entries)
```

### Step 2: Loki Mode Activation
```bash
# Verify Loki is operational
loki --version          # expect v5.53.0+
loki provider set claude  # ensure Claude provider

# Rebuild memory index if stale (PYTHONPATH workaround required)
PYTHONPATH="$HOME/.claude/skills/loki-mode" python3 -c "
from memory.layers import IndexLayer
import os
layer = IndexLayer('/Users/devinmcgrath/projects/electricity-optimizer/.loki/memory')
layer.update([])
print('Loki memory index: OK')
"

# Process any pending events from previous sessions
/Users/devinmcgrath/projects/electricity-optimizer/.claude/hooks/board-sync/loki-event-sync.sh
```

### Step 3: Board Sync Health Check
```bash
# Verify sync script is operational
ls -la .claude/hooks/board-sync/sync-boards.sh  # must be executable
```

### Step 4: Memory Cross-Sync Verification
```
Call mcp__claude-flow__memory_search with query "loki" to verify bidirectional sync
```

### Step 5: Agentic-Flow Availability Check
```bash
# Verify agentic-flow MCP tools are accessible (optional — only if using af-* agents)
# Tools namespaced as mcp__agentic-flow__*
```

### Skip Conditions
- Skip if user says "skip init"
- Skip if all 5 steps were already run this conversation
- On failure: warn user, attempt partial init, continue with what works

## Loki Mode

- **Version**: v5.53.0, Provider: Claude (Opus 4.6 for planning AND development)
- **MCP**: Registered in `.mcp.json` (python3 -m mcp.server)
- **Event Bus**: `.loki/events/pending/` → `loki-event-sync.sh` → board sync + memory persist
- **Memory**: 3-tier (episodic + semantic + procedural), namespace `rateshift`
- **PYTHONPATH fix**: Always prefix `loki memory` CLI commands with `PYTHONPATH="$HOME/.claude/skills/loki-mode"`
- **Human directives**: Edit `.loki/HUMAN_INPUT.md` to inject directives into RARV cycles
- **PRD template**: `.loki/prd-template.md` — use for new feature PRDs
- **Dashboard**: `loki dashboard` on port 57374 (manual start)

### Loki Agent Skills (project-specific)
- **EnergyDataAgent**: EIA/NREL APIs, Region enum, utility types, state regulations
- **NeonDBAgent**: 44 public + 9 neon_auth = 53 tables (53 migrations: init_neon through 053_notification_dedup_index), Neon project `cold-rice-23455092`, UUID PKs, migration patterns
- **StripeAgent**: Async billing, $4.99 Pro/$14.99 Business, webhook flow
- **MLPipelineAgent**: Ensemble predictor, HNSW vector store, observation loop, nightly learning

## Agentic-Flow Integration (2026-03-04)

- **Source**: `/Users/devinmcgrath/projects/agentic-flow` (v2.0.2-alpha)
- **MCP Server**: `agentic-flow` in `.mcp.json`, tools as `mcp__agentic-flow__*`
- **Agents** (34 symlinked via af-* namespace): core (5), analysis (3), architecture (1), development (1), testing (4), github (8), sparc (4), devops (1), documentation (1), data (1), goal (3), templates (2)
- **Skills** (8): af-github-code-review, af-pair-programming, af-performance-analysis, af-hooks-automation, af-verification-quality, af-sparc-methodology, af-skill-builder, af-stream-chain
- **Commands** (7): af-github, af-pair, af-sparc, af-verify, af-analysis, af-hooks, af-workflows
- **Helpers** (4): af-auto-commit.sh, af-health-monitor.sh, af-security-scanner.sh, af-checkpoint-manager.sh
- **Excluded**: 32 agents, 29 skills (consensus, federation, v3, Flow Nexus, SONA, hive-mind — internal or redundant)
- **Rollback**: `~/.claude/integrations/agentic-flow-electricity-optimizer.json`

## Multi-Repo Skill Integration (2026-03-04)

- **Total**: 2,099 skills, 204 commands, 189 agents (2,492 entities)
- **Sources**: 15 GitHub repos (7 curated + 7 vendor + 1 existing)
- **Vendor skills** (37): Vercel (4), Better Auth (6), Neon (2), Stripe (2), Sentry (8), Trail of Bits (12), Cloudflare (3)
- **Curated** (1,087): Antigravity bundles (ag-* prefix for 136 conflicts)
- **App automations** (832): Composio (composio-* prefix) — 16 active connections (gmail, github, firecrawl, sentry, vercel, resend, stripe, render, googlesheets, googledrive, uptimerobot, onesignal, better_stack, slack, notion, neon)
- **Commands** (23 new): hesreallyhim slash commands (acc-* prefix for 1 conflict)
- **Routing optimizer**: `~/.claude/skills/skill-router/` — SKILL.md + registry.json + swarm-routes.json
- **Priority**: vendor-first > project-specific > curated bundles > general
- **Manifests**: `~/.claude/integrations/*.json` (10 files, one per source)
- **Verify**: `~/.claude/scripts/verify-skills.sh`
- **Rollback**: `~/.claude/scripts/rollback-integration.sh <manifest-name>`
- **Namespace prefixes**: vercel-, better-auth-, sentry-, tob-, cf-, ag-, composio-, acc-
- **Symlinks**: Machine-specific (`.gitignore`d). Re-run integration if cloned fresh

## Architecture Quick Reference

- **Backend**: FastAPI + Python 3.12 (`.venv/bin/python` for all pytest)
- **Frontend**: Next.js 16 + React 19 + TypeScript (proxied to backend via `/api/v1/*` rewrites). `.npmrc` has `legacy-peer-deps=true` (eslint 8 + eslint-config-next 16.x compat)
- **Database**: Neon PostgreSQL — project `cold-rice-23455092` ("energyoptimize"), endpoint `ep-withered-morning` (us-east-1), 44 public + 9 neon_auth = 53 tables total (53 migrations: init_neon through 053_notification_dedup_index)
- **API URLs**: `NEXT_PUBLIC_API_URL=/api/v1` (relative, proxied); `BACKEND_URL=https://api.rateshift.app` (server-side, routes through CF Worker)
- **Edge Layer**: Cloudflare Worker `rateshift-api-gateway` at `api.rateshift.app/*` — 2-tier caching (Cache API + KV with cacheTtl), native rate limiting bindings (120/30/600 per min, zero KV cost), bot detection, internal auth, CORS, security headers, graceful KV degradation (fail-open), per-isolate metrics counters, `/internal/gateway-stats` endpoint. CF Account: `b41be0d03c76c0b2cc91efccdb7a10df`. KV: CACHE only (rate limiting migrated to native bindings). SSL: Full (Strict). Deploy: `deploy-worker.yml`. Health: `gateway-health.yml` (12h). Cron: `[triggers] crons = ["0 */3 * * *", "0 */6 * * *", "30 */6 * * *"]` (check-alerts every 3h, price-sync every 6h, observe-forecasts 30min after price-sync). Source: `workers/api-gateway/` (18 files, 90 tests). Frontend circuit breaker: auto-fallback to Render on 502/503 (public endpoints only)
- **ML**: Ensemble predictor with HNSW vector search, adaptive learning
- **Payments**: Stripe (Free/$4.99 Pro/$14.99 Business), payment_failed webhook resolves user via stripe_customer_id. **Plan gating**: `require_tier("pro"/"business")` dependency on 7 endpoints (forecast, savings, recommendations=pro; prices/stream=business). Free tier: 1 alert limit
- **Email**: Resend (primary, domain `rateshift.app` verified, DKIM/SPF/DMARC, TLS enforced) + Gmail SMTP fallback. Sender: `RateShift <noreply@rateshift.app>`. Frontend uses nodemailer for SMTP
- **Domain**: `rateshift.app` (Cloudflare Registrar, zone `ac03dd28616da6d1c4b894c298c1da58`). Frontend: Vercel. Backend: Render `api.rateshift.app`. Resend email domain ID: `20c95ef2-42f4-4040-be75-2026e97e35c9`
- **Notifications**: OneSignal push (user binding via login(userId) post-auth) + email alerts
- **Alerts**: `/internal/check-alerts` endpoint with dedup cooldowns (immediate=1h, daily=24h, weekly=7d). **UI**: `/alerts` page with CRUD, history tabs, AlertForm (region/thresholds/optimal windows). Sidebar Bell icon
- **Automation**: 9 workflows planned (docs/AUTOMATION_PLAN.md). ALL PHASES COMPLETE (0-3), 7/7 workflows live. Self-Healing CI/CD: auto-format, retry-curl, notify-slack, validate-migrations, self-healing-monitor, E2E resilience. **Dependabot**: `.github/dependabot.yml` (pip/npm/github-actions, weekly Monday, grouped minor+patch)
- **AI Agent** (prod 2026-03-11): "RateShift AI" — Gemini 3 Flash Preview (primary, free 10 RPM/250 RPD) + Groq Llama 3.3 70B (fallback on 429) + Composio tools (1K actions/month). Feature flag: `ENABLE_AI_AGENT=true`. Rate limits: Free=3/day, Pro=20/day, Business=unlimited. SSE streaming via `POST /agent/query`, async jobs via `POST /agent/task`, usage via `GET /agent/usage`. Service: `backend/services/agent_service.py`. API: `backend/api/v1/agent.py`. Frontend: `/assistant` page with `AgentChat` component. Migrations 031-033 applied. 13 tests in `test_agent_service.py`. Render env vars: 41 total (34 prior + 4 AI + 3 OTel: GEMINI_API_KEY, GROQ_API_KEY, COMPOSIO_API_KEY, ENABLE_AI_AGENT, OTEL_ENABLED, OTEL_EXPORTER_OTLP_ENDPOINT, GRAFANA_INSTANCE_ID)
- **Agent Orchestration**: Claude Flow + Loki Mode + Agentic-Flow (af-* namespace, 34 agents, 8 skills) + 2,099 skills via multi-repo integration
- **DSP (Data Structure Protocol)**: `.dsp/` codebase graph — 474 entities (436 source + 38 external), 940+ imports, 1 real cycle (alert_service↔alert_renderer). CLI: `python3 dsp-cli.py --root . <command>`. UID map: `.dsp/uid_map.json`. Auto-discovery bootstrap: `python3 scripts/dsp_auto_bootstrap.py` (rebuilds from scratch in ~1.2s). **Important**: wipe `.dsp/` before rebuilding (`rm -rf .dsp && python3 dsp-cli.py --root . init`) — the bootstrap script appends, doesn't replace. Use `search`, `get-recipients`, `get-children --depth N` before refactoring
- **Slack**: Workspace `electricityoptimizer.slack.com` (T0AK0AJV5NE). Channels: `#incidents` (C0AKV2TK257), `#deployments` (C0AKCN6T02Z), `#metrics` (C0AKDD7P2HX). Webhook: `SLACK_INCIDENTS_WEBHOOK_URL` GHA secret + 1Password. Composio connection: `ca_jI3-cs-HrXPY` (Note: workspace named electricityoptimizer but project is RateShift)
- **Board Sync**: GitHub Projects #4 (local hooks). Notion via Rube recipe only (every 6h, rcp_73Kc9K65YC5T). Hub page: `31bb9fc9-1d9d-813e-a108-fd7d4ef49fd7`, Tracker DB: `31bb9fc9-1d9d-81ed-815a-d6fb35ec0d3f`

## Critical Reminders

1. **Neon Project**: `cold-rice-23455092` ("energyoptimize"). Always use `projectId: "cold-rice-23455092"` with Neon MCP tools. Pooled endpoint: `ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech`. Direct endpoint (for migrations): `ep-withered-morning-aix83cfw.c-4.us-east-1.aws.neon.tech`. Branches: `production` (default), `vercel-dev` (preview deployments). 53 tables (44 public + 9 neon_auth), 53 migrations (latest: 053_notification_dedup_index). Note: Stale project `holy-pine-81107663` still exists in account, needs manual deletion via Neon console
2. **conftest.py**: `mock_sqlalchemy_select` fixture patches model attrs — MUST add new fields when adding columns
3. **Tests**: Always use `.venv/bin/python -m pytest`, never system Python
4. **Security**: Swagger/ReDoc disabled in prod, API keys via 1Password vault "RateShift"
5. **Region enum**: `backend/models/region.py` — all 50 states + DC + international, never raw strings
6. **UUID PKs**: All primary keys use UUID type; GRANTs use `neondb_owner` role
7. **Agentic-flow symlinks**: Machine-specific (`.gitignore`d). Re-run integration if cloned fresh. MCP tools: `mcp__agentic-flow__*`, no conflict with `mcp__claude-flow__*`
8. **Multi-repo skill symlinks**: Machine-specific (`.gitignore`d). Re-run `~/.claude/scripts/multi-repo-integrate.sh` if cloned fresh. Verify with `~/.claude/scripts/verify-skills.sh`
9. **Internal endpoints**: All `/api/v1/internal/*` routes require `X-API-Key` header and are excluded from RequestTimeoutMiddleware (30s). GHA workflows use `INTERNAL_API_KEY` repo secret
10. **Self-healing CI/CD**: 32 GHA workflows total (31 cron/CI + 1 manual-only). retry-curl retries on 5xx/429/408/000 with exponential backoff; 4xx (except 429/408) fails immediately. notify-slack uses `SLACK_INCIDENTS_WEBHOOK_URL` secret. self-healing-monitor auto-creates issues after 3+ failures with `self-healing` label
11. **Community**: `/community` page with posts, voting, reporting. AI moderation: Groq `classify_content()` primary, Gemini fallback, fail-closed 30s. nh3 XSS sanitization. Report threshold: 5 unique reporters auto-hides. Rate limit: 10 posts/hour. Community backend: `community_service.py`, `savings_aggregator.py`, `neighborhood_service.py`. Migration 049: 3 tables (community_posts, community_votes, community_reports). Migration 050: optimized partial indexes. Migration 051: GDPR CASCADE fixes for community + notifications FKs
12. **Tier cache**: 30s TTL (in-memory + Redis). Stripe webhook events update DB directly; cache self-heals within 30s. `require_tier()` gates 7+ endpoints
13. **Rate limiter Lua script**: Redis `:seq` counter keys now have TTL matching the main key (previously leaked without expiry)

## Cron Jobs & Maintenance

- **db-maintenance**: Weekly Sunday 3am UTC — database optimization, vacuum, analyze, index maintenance
- **Phase 1 LIVE**: Sentry→Slack (15min, `rcp_sQ1NKouFdXIe`), Deploy→Slack (hourly, `rcp_9f8mVE2Z_DSP`), GitHub→Notion (6h, `rcp_73Kc9K65YC5T`). Rube session: `drew`
- **Phase 2 COMPLETE** (5 GHA cron workflows):
  - `check-alerts.yml`: Manual trigger only (`workflow_dispatch`) — cron moved to CF Worker Cron Trigger (every 3h). `POST /internal/check-alerts` (price threshold alerts with dedup)
  - `price-sync.yml`: Manual trigger only (`workflow_dispatch`) — cron moved to CF Worker Cron Trigger (every 6h). `POST /internal/scrape-rates` (electricity price data ingestion)
  - `observe-forecasts.yml`: Manual trigger only (`workflow_dispatch`) — cron moved to CF Worker Cron Trigger (30min after price-sync, every 6h). `POST /internal/observe-forecasts` (backfill actual prices into forecast observations)
  - `fetch-weather.yml`: Every 12 hours (offset :15, was 6h, reduced for GHA cost optimization) — `POST /internal/fetch-weather` (parallelized with asyncio.gather + Semaphore(10))
  - `market-research.yml`: Daily 2am UTC — `POST /internal/market-research` (Tavily + Diffbot)
  - `sync-connections.yml`: Every 6 hours (was 2h, reduced 2026-03-16) — `POST /internal/sync-connections` (UtilityAPI auto-sync)
  - All use `INTERNAL_API_KEY` secret, `/api/v1/internal/` paths excluded from RequestTimeoutMiddleware
- **Utility Integration Track** (2 GHA cron workflows, 2026-03-11):
  - `scan-emails.yml`: Via `daily-data-pipeline.yml` (was standalone 4am cron, consolidated 2026-03-16) — `POST /internal/scan-emails` (batch scan all active email_import connections, extract rates from body + attachments)
  - `scrape-portals.yml`: Weekly Sunday 5am UTC — `POST /internal/scrape-portals` (batch scrape portal_scrape connections with Semaphore(2))
  - Portal endpoints: `POST /connections/portal` (create with encrypted creds), `POST /connections/portal/{id}/scrape` (trigger manual scrape)
  - PortalScraperService: httpx-based, 5 utilities (Duke Energy, PG&E, Con Edison, ComEd, FPL), AES-256-GCM encrypted credentials
  - Email extraction: `extract_rates_from_email()` + `download_gmail_attachments()`/`download_outlook_attachments()` + `extract_rates_from_attachments()` wired into scan endpoint
  - Diffbot rate extraction: `_extract_rate_from_diffbot_data()` wired into scrape-rates, embeds `_detected_rate_kwh` in JSONB
  - Frontend: PortalConnectionFlow.tsx (multi-step form), portal.ts API client, ConnectionMethodPicker 4th option
- **Phase 3 COMPLETE** (2 GHA cron workflows + migration 024):
  - `dunning-cycle.yml`: Daily 7am UTC — `POST /internal/dunning-cycle` (overdue payment escalation, 7-day grace period)
  - `kpi-report.yml`: Daily 6am UTC — `POST /internal/kpi-report` (business metrics aggregation)
  - Migration 024: `payment_retry_history` table (retry tracking, email history, escalation audit)
  - DunningService wired into `apply_webhook_action()` for real-time `invoice.payment_failed` handling
  - Email templates: `dunning_soft.html` (amber) + `dunning_final.html` (red, grace period warning)
- **Self-Healing CI/CD** (implemented 2026-03-06):
  - `self-healing-monitor.yml`: Daily 9am UTC — checks 18 workflows for repeated failures, auto-creates/closes GitHub issues
  - `retry-curl` composite action: Exponential backoff with jitter, 4xx fail-fast, 3 retries
  - `notify-slack` composite action: Color-coded severity alerts to `#incidents` (C0AKV2TK257)
  - `validate-migrations` composite action: Sequential numbering, IF NOT EXISTS, neondb_owner, no SERIAL
  - CI auto-format: Black + isort auto-fix on PRs (commit bot), fail on main
  - E2E resilience: Retry Playwright install, extended timeouts, rerun failed tests
  - All 12 cron workflows updated with retry-curl + notify-slack
  - Deploy pipeline: migration-gate job before deploy, Slack rollback notification
  - New secret required: `SLACK_INCIDENTS_WEBHOOK_URL`
  - New labels: `self-healing`, `automated`
- **Cost Optimization** (2026-03-16 to 2026-03-17):
  - `daily-data-pipeline.yml`: Daily 3am UTC — consolidated pipeline running scrape-rates, scan-emails, nightly-learning, detect-rate-changes sequentially (single checkout + warmup)
  - `e2e-tests.yml`: Removed daily cron trigger (still runs on push/PR)
  - `nightly-learning.yml`: Via `daily-data-pipeline.yml` (was standalone 4am cron)
  - `detect-rate-changes.yml`: Via `daily-data-pipeline.yml` (was standalone 6:30am cron)
  - `price-sync.yml` (Sprint 0-2): Moved to CF Worker Cron Trigger (every 6h) — saves ~240 min/mo
  - `observe-forecasts.yml` (Sprint 0-2): Moved to CF Worker Cron Trigger (30min after price-sync) — saves ~240 min/mo
  - Total estimated GHA savings: ~4,470 min/mo (from baseline). Current usage: ~1,283 min/mo (down from ~2,700 pre-optimization). Full analysis: `docs/COST_ANALYSIS.md`
- **Security Scanning** (Wave 5, 2026-03-12):
  - `owasp-zap.yml`: Weekly Sunday 4am UTC — OWASP ZAP baseline scan against Render backend (not CF Worker)
  - `pip-audit` in `_backend-tests.yml`: Fails on known Python dependency vulnerabilities
  - `npm audit --audit-level=high` in `ci.yml`: Fails on high/critical npm vulnerabilities
  - `.zap/rules.tsv`: 5 false-positive suppression rules

## Autonomous Workflow (when Loki is driving)

After every completed task, automatically:
1. Run affected test suites
2. Update docs/codemaps if code changed
3. Trigger board sync (GitHub Projects only — Notion via Rube recipe)
4. Persist memory to Claude Flow
5. Extract learning patterns
6. Commit with descriptive message + Co-Authored-By headers
