# Electricity Optimizer — Project Instructions

> Last validated: 2026-03-04

## Session Initialization Protocol (MANDATORY)

At the START of every new conversation, before doing any user-requested work, run these steps **in order**:

### Step 1: Claude Flow + Memory
```
Call mcp__claude-flow__hooks_session-start with startDaemon: true, restoreLatest: true
Call mcp__claude-flow__memory_stats to confirm memory DB is active (expect 8+ entries)
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
- **Memory**: 3-tier (episodic + semantic + procedural), namespace `electricity-optimizer`
- **PYTHONPATH fix**: Always prefix `loki memory` CLI commands with `PYTHONPATH="$HOME/.claude/skills/loki-mode"`
- **Human directives**: Edit `.loki/HUMAN_INPUT.md` to inject directives into RARV cycles
- **PRD template**: `.loki/prd-template.md` — use for new feature PRDs
- **Dashboard**: `loki dashboard` on port 57374 (manual start)

### Loki Agent Skills (project-specific)
- **EnergyDataAgent**: EIA/NREL APIs, Region enum, utility types, state regulations
- **NeonDBAgent**: 14-table schema, endpoint quirk (us-east-1), UUID PKs, migration patterns
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
- **App automations** (832): Composio (composio-* prefix)
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
- **Frontend**: Next.js 14 + TypeScript (proxied to backend via `/api/v1/*` rewrites)
- **Database**: Neon PostgreSQL — app endpoint is `ep-withered-morning` (us-east-1), NOT Neon MCP endpoint
- **API URLs**: `NEXT_PUBLIC_API_URL=/api/v1` (relative, proxied); `BACKEND_URL=https://electricity-optimizer.onrender.com` (server-side)
- **ML**: Ensemble predictor with HNSW vector search, adaptive learning
- **Payments**: Stripe (Free/$4.99 Pro/$14.99 Business)
- **Agent Orchestration**: Claude Flow + Loki Mode + Agentic-Flow (af-* namespace, 34 agents, 8 skills) + 2,099 skills via multi-repo integration
- **Board Sync**: GitHub Projects #4 + Notion roadmap (auto-sync on edits)

## Critical Reminders

1. **DB Endpoint**: App uses `ep-withered-morning-aix83cfw-pooler.c-4.us-east-1.aws.neon.tech` — migrations via Neon MCP go to WRONG endpoint
2. **conftest.py**: `mock_sqlalchemy_select` fixture patches model attrs — MUST add new fields when adding columns
3. **Tests**: Always use `.venv/bin/python -m pytest`, never system Python
4. **Security**: Swagger/ReDoc disabled in prod, API keys via 1Password vault "Electricity Optimizer"
5. **Region enum**: `backend/models/region.py` — all 50 states + DC + international, never raw strings
6. **UUID PKs**: All primary keys use UUID type; GRANTs use `neondb_owner` role
7. **Agentic-flow symlinks**: Machine-specific (`.gitignore`d). Re-run integration if cloned fresh. MCP tools: `mcp__agentic-flow__*`, no conflict with `mcp__claude-flow__*`
8. **Multi-repo skill symlinks**: Machine-specific (`.gitignore`d). Re-run `~/.claude/scripts/multi-repo-integrate.sh` if cloned fresh. Verify with `~/.claude/scripts/verify-skills.sh`

## Autonomous Workflow (when Loki is driving)

After every completed task, automatically:
1. Run affected test suites
2. Update docs/codemaps if code changed
3. Trigger board sync (GitHub Projects + Notion)
4. Persist memory to Claude Flow
5. Extract learning patterns
6. Commit with descriptive message + Co-Authored-By headers
