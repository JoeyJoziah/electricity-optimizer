# RateShift — Project Instructions

> Last validated: 2026-05-26. Tests: ~6,362 passing (3,437 BE + 2,069 FE + 729 ML + 127 Worker) + 10 integration skipped + ~1,642 E2E (Playwright, run separately) = ~8,014 total. 69 migrations, 70 tables (61 public + 9 neon_auth), 36 GHA workflows. See MEMORY.md for session-level detail.
>
> **PH Launch**: POSTPONED INDEFINITELY (original Apr 14 date passed). Conductor: 23 tracks, all with plan.md/tasks.md/execution.md in sync.

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

### Step 3: Board Sync Health Check (CONDITIONAL — only when board-sync is relevant)
```bash
ls -la .claude/hooks/board-sync/sync-boards.sh  # must be executable
```

### Step 4: Memory Cross-Sync (CONDITIONAL — only when loki memory operations needed)
```
Call mcp__claude-flow__memory_search with query "loki" to verify bidirectional sync
```

### Step 5: Agentic-Flow Check (CONDITIONAL — only when using af-* agents)
```bash
# Tools namespaced as mcp__agentic-flow__*
```

### Skip Conditions
- Skip if user says "skip init"
- Skip if Steps 1-2 were already run this conversation
- Steps 3-5 are conditional — skip unless the session task requires them
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
- **NeonDBAgent**: 61 public + 9 neon_auth = 70 tables (69 migrations: init_neon through 069_supplier_offers), Neon project `cold-rice-23455092`, UUID PKs, migration patterns
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

## Paperclip.ai (Local Agent Orchestration, 2026-03-31, restructured 2026-04-09)

- **Server**: localhost:3100 (manual start via `cd ~/.paperclip && pnpm dev`)
- **Config**: `~/.paperclip/instances/default/config.json`
- **Tasks**: `~/.paperclip/tasks/` (file-based agent communication)
- **Canonical Org**: `paperclip/AGENTS.md` + `paperclip/.paperclip.yaml` — 6 agents total
- **Active Agents**: CEO (Haiku, 24h), CTO (Sonnet, 12h), COO (Haiku, 6h), DataOps (Bash, 3h), Engineer (Claude Code, on-demand)
- **Planned**: Growth (Haiku, 24h) — deploy post-PH launch
- **Company ID**: `99c6bb83-300d-4cf6-ab09-de64f1649f4d`
- **Layer**: Strategy/delegation — sits above Claude Flow/Loki/AF. Never touches code directly
- **Budget**: ~$26/mo allocated, $38/mo hard cap. CEO+CTO+COO ~$11, Engineer $15 cap, DataOps $0
- **Scripts**: `paperclip/scripts/` — 9 bash scripts (4 populate + reconcile-escalations + populate-budget + populate-codebase-stats + dataops-runner + setup)
- **Env**: `~/.paperclip/env` — sources INTERNAL_API_KEY for DataOps scripts
- **Ack Protocol**: Agents write to `~/.paperclip/tasks/ack-{role}.md` after reading directives
- **Memory**: Each LLM agent has `memory/YYYY-MM-DD.md` in its instructions dir, reads last 3 on startup
- **Data flow**: One-way only (real systems → Paperclip task files). Paperclip agents never write to Claude Flow memory, trigger Loki RARV cycles, or duplicate GHA/CF Worker crons
- **IMPORTANT**: Paperclip is `.gitignore`d (both `paperclip/` and `.paperclip/`). Machine-specific setup

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

- **Backend**: FastAPI + Python 3.12 (`.venv/bin/python` for all pytest). **Deploy pipeline**: `.github/workflows/build-and-push-backend.yml` auto-builds Docker image on every push to main touching `backend/**`, pushes `dmpcg/electricity-optimizer-backend:{latest,short-sha}`, fires Render deploy hook, then polls `/health` for verification (closed the 34-day deploy gap). Dockerfile uses BuildKit pip cache mount, ARG PYTHON_IMAGE, appuser service account. FastAPI `/health` accepts both GET and HEAD (UptimeRobot defaults to HEAD probes)
- **Frontend**: Next.js 16 + React 19 + TypeScript (proxied to backend via `/api/v1/*` rewrites). `.npmrc` has `legacy-peer-deps=true` (eslint 8 + eslint-config-next 16.x compat)
- **Database**: Neon PostgreSQL — project `cold-rice-23455092` ("energyoptimize"), endpoint `ep-withered-morning` (us-east-1), 61 public + 9 neon_auth = 70 tables total (69 migrations: init_neon through 069_supplier_offers)
- **Supplier pricing**: Vendor-neutral via `supplier_offers` table (migration 069) + `SupplierOfferSource` adapter layer (`backend/services/pricing/` — `base.py` protocol, `regional_estimate.py`). Read path (`GET /suppliers`, `POST /suppliers/recommend`) is source-agnostic; only wired source is `RegionalEstimateSource` (`is_estimate=true`, computed live). Repo: `repositories/supplier_offer_repository.py`. Legacy `tariffs` table is DEPRECATED (empty, unlinked). EnergyBot is treated as a COMPETITOR — `energybot_service` + `available_plans` remain dormant.
- **API URLs**: `NEXT_PUBLIC_API_URL=/api/v1` (relative, proxied); `BACKEND_URL=https://api.rateshift.app` (server-side, routes through CF Worker)
- **Edge Layer**: Cloudflare Worker `rateshift-api-gateway` at `api.rateshift.app/*` — 2-tier caching (Cache API + KV with cacheTtl), native rate limiting bindings (120/30/600 per min, zero KV cost), bot detection, internal auth, CORS, security headers, graceful KV degradation (fail-open), per-isolate metrics counters, `/internal/gateway-stats` endpoint. CF Account: `b41be0d03c76c0b2cc91efccdb7a10df`. KV: CACHE only (rate limiting migrated to native bindings). SSL: Full (Strict). Deploy: `deploy-worker.yml`. Health: `gateway-health.yml` (12h). Cron: `[triggers] crons = ["*/10 * * * *", "0 */3 * * *", "0 */6 * * *", "30 */6 * * *"]` (keep-alive every 10min, check-alerts every 3h, price-sync every 6h, observe-forecasts 30min after price-sync). Secrets: ORIGIN_URL, INTERNAL_API_KEY, RATE_LIMIT_BYPASS_KEY. Proxy: Location header rewriting on redirects (prevents leaking Render origin URL). **Cache hygiene** (2026-05-11): `/health` is never cached (bypass), `storeInCache` gated to `method === "GET"` (HEAD/GET key collision was poisoning cache), origin fetch wrapped in `AbortSignal.timeout(25s)` + `AbortSignal.any([..., request.signal])` (504 on origin timeout, 499 on client disconnect). `head_sampling_rate=0.25` for observability. Source: `workers/api-gateway/` (19 files, 127 tests). Frontend circuit breaker: auto-fallback to Render on 502/503 (public endpoints only)
- **ML**: Ensemble predictor with HNSW vector search, adaptive learning
- **Payments**: Stripe (Free/$4.99 Pro/$14.99 Business), payment_failed webhook resolves user via stripe_customer_id. **Plan gating**: `require_tier("pro"/"business")` dependency on 7 endpoints (forecast, savings, recommendations=pro; prices/stream=business). Free tier: 1 alert limit. **UtilityAPI Add-On**: $2.25/meter/mo (50% markup on $1.50 UtilityAPI cost), all tiers via Stripe subscription items. Service: `backend/services/utilityapi_billing_service.py`. Endpoint: `GET /billing/addon-pricing`. Migration 065: `stripe_subscription_item_id` + `utilityapi_meter_count` on user_connections. Env var: `STRIPE_PRICE_UTILITYAPI_METER`
- **Email**: Resend (primary, domain `rateshift.app` verified, DKIM/SPF/DMARC, TLS enforced) + Gmail SMTP fallback. Sender: `RateShift <noreply@rateshift.app>`. Frontend uses nodemailer for SMTP
- **Domain**: `rateshift.app` (Cloudflare Registrar, zone `ac03dd28616da6d1c4b894c298c1da58`). Frontend: Vercel. Backend: Render `api.rateshift.app`. Resend email domain ID: `20c95ef2-42f4-4040-be75-2026e97e35c9`
- **Notifications**: OneSignal push (user binding via login(userId) post-auth) + email alerts
- **Monitoring**: UptimeRobot status page (PSP 984675) at https://stats.uptimerobot.com/d4sbPJ124X — 4 monitors UP (Frontend, Backend Health, API Smoke Test, Neon DB Pooler)
- **Visual Regression**: 12 chromium-linux baselines committed at `frontend/e2e/visual-regression.spec.ts-snapshots/*-linux.png`. `.gitignore` excludes only `*-darwin.png` (per-dev snapshots)
- **Alerts**: `/internal/check-alerts` endpoint with dedup cooldowns (immediate=1h, daily=24h, weekly=7d). **UI**: `/alerts` page with CRUD, history tabs, AlertForm (region/thresholds/optimal windows). Sidebar Bell icon
- **Automation**: 9 workflows planned (docs/AUTOMATION_PLAN.md). ALL PHASES COMPLETE (0-3), 7/7 workflows live. Self-Healing CI/CD: auto-format, retry-curl, notify-slack, validate-migrations, self-healing-monitor, E2E resilience. **Dependabot**: `.github/dependabot.yml` (pip/npm/github-actions, weekly Monday, grouped minor+patch)
- **AI Agent** (prod 2026-03-11): "RateShift AI" — Gemini 3 Flash Preview (primary, free 10 RPM/250 RPD) + Groq Llama 3.3 70B (fallback on 429) + Composio tools (1K actions/month). Feature flag: `ENABLE_AI_AGENT=true`. Rate limits: Free=3/day, Pro=20/day, Business=unlimited. SSE streaming via `POST /agent/query`, async jobs via `POST /agent/task`, usage via `GET /agent/usage`. Service: `backend/services/agent_service.py`. API: `backend/api/v1/agent.py`. Frontend: `/assistant` page with `AgentChat` component. Migrations 031-033 applied. 13 tests in `test_agent_service.py`. Render env vars: 52 total (all real values, zero gaps as of 2026-04-08). OAuth: GitHub (set), Google (set), Gmail (set, same client as Google), Outlook (set, Azure app "RateShift Email Scanner"), UTILITYAPI_KEY (set). OAUTH_STATE_SECRET + ML_MODEL_SIGNING_KEY: SET (64-char hex each)
- **Agent Orchestration**: Claude Flow + Loki Mode + Agentic-Flow (af-* namespace, 34 agents, 8 skills) + 2,099 skills via multi-repo integration
- **Auto Rate Switcher** (2026-04-03): Autonomous plan switching for Pro tier. 6 tables (migration 066): user_agent_settings, user_plans, available_plans, meter_readings, switch_audit_log, switch_executions. 8 backend services. API: `/agent-switcher/*` (15 public + 2 internal). Frontend: `/auto-switcher` (3 pages). GHA: `agent-switcher-scan.yml` (daily), `sync-available-plans.yml` (daily), `db-maintenance.yml` (weekly). Self-healing monitor: 21 workflows (was 18)
- **DSP (Data Structure Protocol)**: `.dsp/` codebase graph — 585 entities (543 source + 42 external), 1127 imports, 1 real cycle (alert_service↔alert_renderer). CLI: `python3 dsp-cli.py --root . <command>`. UID map: `.dsp/uid_map.json`. Auto-discovery bootstrap: `python3 scripts/dsp_auto_bootstrap.py` (rebuilds from scratch in ~1.5s). **Rebuild rule**: wipe `.dsp/` first (`rm -rf .dsp && python3 dsp-cli.py --root . init`) — bootstrap appends, doesn't replace. **Maintenance protocol below is mandatory** — see "DSP Maintenance Protocol"
- **Slack**: Workspace `electricityoptimizer.slack.com` (T0AK0AJV5NE). Channels: `#incidents` (C0AKV2TK257), `#deployments` (C0AKCN6T02Z), `#metrics` (C0AKDD7P2HX). Webhook: `SLACK_INCIDENTS_WEBHOOK_URL` GHA secret + 1Password. Composio connection: `ca_jI3-cs-HrXPY` (Note: workspace named electricityoptimizer but project is RateShift)
- **Board Sync**: GitHub Projects #4 (local hooks). Notion via Rube recipe only (every 6h, rcp_73Kc9K65YC5T). Hub page: `31bb9fc9-1d9d-813e-a108-fd7d4ef49fd7`, Tracker DB: `31bb9fc9-1d9d-81ed-815a-d6fb35ec0d3f`

> See [REMINDERS.md](REMINDERS.md) for 22 critical reminders, cron jobs, and maintenance procedures.

## DSP Maintenance Protocol (MANDATORY)

The `.dsp/` graph is a first-class artifact. **It must stay in sync with the codebase on every change.** Before any non-trivial refactor, query the graph first (`search`, `find-by-source`, `get-recipients`, `get-children --depth N`) — this is cheaper than re-reading files and surfaces breakage upstream.

### When code changes, update DSP in the same turn

| Code change | Required DSP command |
|---|---|
| **New file/module** | `create-object <relpath> "<purpose>"` |
| **New exported function** | `create-function <file>#<name> "<purpose>" --owner <obj-uid>` + `create-shared <owner> <func-uid>` |
| **Added import** | `add-import <importer> <imported> "<why>"` (create `--kind external` first if new dep) |
| **Removed import** | `remove-import <importer> <imported>` |
| **Added export** | `create-shared <owner> <child>` |
| **Removed export** | `remove-shared <owner> <child>` |
| **Renamed/moved file** | `move-entity <uid> <new-relpath>` (UID stable) |
| **Deleted file** | `remove-entity <uid>` (cascades) |
| **Purpose changed** | `update-description <uid> "<new purpose>"` |
| **Import reason changed** | `update-import-why <importer> <imported> "<new why>"` |
| **Internal-only edit (no signature/import change)** | **No DSP update needed** |

### Bulk-change escape hatch

If a single task touches >15 files with structural changes (cross-cutting refactor, codemod, large rename, generated-code regen), incremental updates lose value — **wipe and rebuild instead**:
```bash
rm -rf .dsp && python3 dsp-cli.py --root . init && python3 scripts/dsp_auto_bootstrap.py
```
Then commit `.dsp/` separately from the code change with a descriptive `chore(dsp):` message.

### Verification (run at end of any session that touched DSP)

```bash
python3 dsp-cli.py --root . get-stats        # entity/import counts should match scale of change
python3 dsp-cli.py --root . detect-cycles    # only the known alert_service↔alert_renderer cycle is acceptable
python3 dsp-cli.py --root . get-orphans | wc -l   # spike here = forgot to wire imports
```

### Pre-refactor query playbook

Before changing any file with non-trivial fan-in:
1. `find-by-source <relpath>` → get the UID
2. `get-recipients <uid>` → list of importers + their reasons (this tells you the blast radius)
3. `get-entity <uid>` → verify imports and shared list
4. Plan the refactor against that map, not by re-reading files

## Autonomous Workflow (when Loki is driving)

After every completed task, automatically:
1. Run affected test suites
2. **Update `.dsp/` per DSP Maintenance Protocol** (incremental commands OR wipe-and-rebuild if >15 files changed)
3. Update docs/codemaps if code changed
4. Trigger board sync (GitHub Projects only — Notion via Rube recipe)
5. Persist memory to Claude Flow
6. Extract learning patterns
7. Commit with descriptive message + Co-Authored-By headers (DSP changes in a separate `chore(dsp):` commit when bulk-rebuilding)
