# Claude Code Environment Snapshot

> **Owner**: Devin McGrath | **Machine**: macOS Darwin 25.3.0 | **Model**: Claude Opus 4.6
> **Generated**: 2026-03-23 | **Purpose**: Master prompt design reference for environment-aware AI orchestration

---

## 1. Capabilities Inventory

### Summary Counts

| Category | Count | Notes |
|----------|-------|-------|
| Skills | 2,102 | 832 Composio app automations, 135 Antigravity (ag-*), 116 Azure, 43 vendor-specific, 14 HIG, 203 learned patterns |
| Agents | 171 | Specialist `.md` definitions in `~/.claude/agents/` |
| Slash Commands | 204 | Orchestration, analysis, SPARC, GitHub, memory, hooks, workflows |
| MCP Servers (global) | 8 | Neon, hf-datasets, 1Password, claude-in-chrome, claude-flow, Figma, financial-server, context7 |
| MCP Servers (project) | 14 | claude-flow, loki-mode, agentic-flow, chroma-mcp, octagon, greptimedb, clickhouse, google-workspace, + 6 more |
| Integration Manifests | 33 | `~/.claude/integrations/` — vendor, curated, composio bundles |
| Hooks | 5 | PreToolUse (2), PostToolUse (1), Stop (2) |

### Core Orchestration Frameworks

| ID | Type | Description | Invocation | Sweet Spot |
|----|------|-------------|------------|------------|
| **Loki Mode** | Autonomous agent | Takes PRD to deployed product via RARV loops; fully autonomous | `/loki-mode` or Loki SKILL.md | Greenfield features, multi-phase autonomous builds, PRD execution |
| **Claude Flow** | Agent orchestration | 215+ MCP tools; swarm init, agent spawn, task orchestrate, memory, hooks | `mcp__claude-flow__*` tools | Multi-agent coordination, memory persistence, swarm management |
| **Agentic Flow** | Agent framework | 34 agents, 8 skills via `af-*` namespace; SPARC integration | `mcp__agentic-flow__*` tools | Analysis, pair programming, verification, SPARC workflows |
| **SPARC** | Methodology framework | Spec→Pseudocode→Architecture→Refinement→Completion with 16 modes | `/sparc:*` commands | Structured development cycles, TDD, security review, architecture |
| **Auto-Orchestrator** | Routing brain | Classifies tasks into 4 tiers; selects strategy (direct→agent→team→swarm→Loki) | Auto-fires on Task/TeamCreate via hooks | Every task — sits between user request and execution path |
| **Skill Router** | Meta-skill | Routes tasks to best skill from 2,100+; vendor-first priority | Consulted during planning | Skill selection, conflict resolution, swarm skill assignment |
| **Conductor** | Track management | Tracks multi-sprint work with plan.md checklists; 19 tracks (all complete) | `conductor/tracks/` directory | Multi-day audit/remediation sprints, phased rollouts |

### Agent Types (171 Specialists)

| Category | Examples | Count (approx) |
|----------|----------|----------------|
| **Backend** | backend-architect, backend-developer, django-developer, spring-boot-engineer, laravel-specialist | ~15 |
| **Frontend** | frontend-developer, react-pro, react-specialist, vue-expert, angular-architect, nextjs-developer | ~10 |
| **Full-Stack** | fullstack-developer, rapid-prototyper | ~5 |
| **DevOps/Infra** | devops-engineer, kubernetes-specialist, docker-expert, terraform-engineer, cloud-architect, sre-engineer | ~20 |
| **Security** | security-engineer, security-auditor, penetration-tester, compliance-auditor, incident-responder | ~10 |
| **Data/ML** | data-scientist, data-engineer, ml-engineer, mlops-engineer, nlp-engineer, llm-architect | ~10 |
| **Language Pro** | python-pro, typescript-pro, golang-pro, rust-engineer, java-architect, cpp-pro, swift-expert | ~20 |
| **Quality** | qa-expert, test-automator, code-review-expert, debugger, performance-engineer | ~10 |
| **Business** | product-manager, business-analyst, market-researcher, legal-advisor, risk-manager | ~10 |
| **Orchestration** | multi-agent-coordinator, task-distributor, context-manager, studio-coach, studio-producer | ~10 |
| **Swarm** | code-review-swarm, multi-repo-swarm, swarm-pr, swarm-issue, release-swarm, sync-coordinator | ~10 |
| **Creative/Growth** | tiktok-strategist, trend-researcher, whimsy-injector, content-marketer, seo-specialist | ~10 |
| **Other** | browser, mcp-developer, game-developer, blockchain-developer, iot-engineer, embedded-systems | ~30 |

### Skill Namespaces

| Prefix | Source | Count | Domain |
|--------|--------|-------|--------|
| `composio-` | Composio App Automations | 832 | Gmail, Slack, GitHub, Stripe, Notion, 800+ SaaS integrations |
| `ag-` | Antigravity Curated | 135 | Backend, frontend, security, testing, architecture best practices |
| `azure-` | Azure SDKs | 116 | Azure identity, storage, cosmos, AI, monitor, eventhub |
| `hig-` | Human Interface Guidelines | 14 | Apple HIG components, foundations, patterns |
| `vercel-` | Vercel Labs | 4 | React patterns, web design, deployment, composition |
| `better-auth-` | Better Auth | 6 | Auth creation, email/password, organization, security, 2FA |
| `sentry-` | Sentry | 8 | Code review, PR creation, bug finding, security review |
| `tob-` | Trail of Bits | 12 | Static analysis (Semgrep, CodeQL, SARIF), supply chain, sharp edges |
| `cf-` | Cloudflare | 3 | Workers, web perf, best practices |
| `neon-` | Neon Database | 2 | Postgres, claimable instances |
| `stripe-` | Stripe | 2 | Best practices, upgrade |
| `af-` | Agentic Flow | 8 skills | GitHub review, pair programming, SPARC, verification, hooks |
| `conductor-` | Conductor Framework | 6 | Track implement, manage, new-track, revert, setup, status |
| `loki-mode` | Loki Mode | 1 | Autonomous multi-agent PRD-to-production |

### Key Slash Commands (Selection of 204)

| Command | Type | Description |
|---------|------|-------------|
| `/sparc:sparc` | Orchestrator | Full SPARC methodology workflow |
| `/sparc:architect` | SPARC mode | Architecture design phase |
| `/sparc:tdd` | SPARC mode | Test-driven development cycle |
| `/sparc:security-review` | SPARC mode | Security audit via SPARC |
| `/sparc:batch-executor` | SPARC mode | Batch execution of planned tasks |
| `/commit` | Git | Structured commit workflow |
| `/create-pr` | Git | Pull request creation |
| `/fix-github-issue` | Git | Issue resolution workflow |
| `/loki-mode` | Autonomous | Engage Loki Mode for autonomous execution |
| `/swarm-advanced` | Swarm | Advanced multi-agent swarm orchestration |
| `/parallel-agents` | Swarm | Dispatch parallel agent workers |
| `/memory-sync-swarm` | Memory | Synchronize memory across all 8 systems |
| `/memory-sync-checkpoint` | Memory | Create memory checkpoint |
| `/context-prime` | Context | Prime context for optimal routing |
| `/clean` | Maintenance | Clean stale files and state |
| `/act` | Execution | Direct action execution |
| `/todo` | Tracking | Task management |
| `/create-prd` | Planning | Generate product requirements document |
| `/github:code-review` | GitHub | Automated code review |
| `/github:pr-manager` | GitHub | PR management with swarm coordination |
| `/github:workflow-automation` | GitHub | GHA workflow creation/optimization |
| `/github:release-swarm` | GitHub | Multi-package release orchestration |
| `/automation:smart-agents` | Automation | Intelligent agent selection |
| `/automation:self-healing` | Automation | Self-healing CI/CD workflows |
| `/monitoring:swarm-monitor` | Monitoring | Real-time swarm status tracking |
| `/analysis:performance-bottlenecks` | Analysis | Identify performance bottlenecks |
| `/analysis:token-usage` | Analysis | Token cost analysis |
| `/hooks:pre-task` / `/hooks:post-task` | Hooks | Pre/post task learning hooks |

### MCP Server Capabilities

| Server | Domain | Key Tools |
|--------|--------|-----------|
| **claude-flow** | Orchestration | `swarm_init`, `agent_spawn`, `task_orchestrate`, `memory_store/search/retrieve`, `hooks_*`, `workflow_*`, `performance_*`, `neural_*` (215+ tools) |
| **Neon** | Database | `run_sql`, `create_branch`, `describe_table_schema`, `prepare_database_migration`, `list_slow_queries` |
| **hf-datasets** | ML Data | `hf_dataset_search`, `hf_dataset_upload_file`, `hf_dataset_info` |
| **1password** | Secrets | Credential access via `op://` URIs |
| **claude-in-chrome** | Browser | `navigate`, `read_page`, `javascript_tool`, `form_input`, `gif_creator`, `tabs_*` |
| **context7** | Docs | `resolve-library-id`, `get-library-docs` — live documentation lookup |
| **Figma** | Design | `get_design_context`, `get_screenshot`, `generate_diagram` |
| **financial-server** | Finance | `qbo_*` (QuickBooks), `origin_*` (personal finance) |
| **loki-mode** | Autonomous | RARV cycle management, event bus, task queue |
| **agentic-flow** | Agent orchestration | `agentic_flow_agent`, `agent_booster_*`, `agentdb_*` |
| **chroma-mcp** | Vector DB | Embedding storage and semantic search |

---

## 2. Orchestration & Automation

### Architecture Diagram

```
                              USER REQUEST
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │  Auto-Orchestrator   │  ← PreToolUse hook classifies
                        │  (Tier 1-4 routing)  │     every Task/TeamCreate
                        └─────────┬───────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
        ┌──────────┐     ┌──────────────┐     ┌──────────────┐
        │  DIRECT   │     │  AGENT/TEAM  │     │  LOKI MODE   │
        │ (Tier 1)  │     │  (Tier 2-3)  │     │  (Tier 4)    │
        │ Inline    │     │  Claude Flow  │     │  Autonomous  │
        │ execution │     │  orchestrates │     │  RARV cycles │
        └──────────┘     └──────┬───────┘     └──────┬───────┘
                                │                     │
                    ┌───────────┼─────────┐           │
                    ▼           ▼         ▼           ▼
              ┌─────────┐ ┌────────┐ ┌────────┐ ┌─────────┐
              │ Single   │ │ Team   │ │ Swarm  │ │ RARV    │
              │ Agent    │ │ (2-4)  │ │ (5-12) │ │ Loop    │
              │ Task()   │ │ Team   │ │ Swarm  │ │ Reason  │
              │          │ │ Create │ │ Init   │ │ Act     │
              └────┬─────┘ └───┬────┘ └───┬────┘ │ Reflect │
                   │           │           │     │ Verify  │
                   └───────────┼───────────┘     └────┬────┘
                               ▼                      │
                    ┌──────────────────┐               │
                    │  Skill Router    │               │
                    │  (vendor-first   │               │
                    │   priority)      │               │
                    └────────┬─────────┘               │
                             │                         │
                    ┌────────┼─────────┐               │
                    ▼        ▼         ▼               │
              ┌──────┐ ┌────────┐ ┌────────┐           │
              │SPARC  │ │Conduct-│ │Learned │           │
              │Phases │ │or Track│ │Skills  │           │
              │S→P→A  │ │plan.md │ │(203)   │           │
              │→R→C   │ │checks  │ │        │           │
              └──────┘ └────────┘ └────────┘           │
                                                       ▼
                                              ┌──────────────┐
                                              │  Memory Layer │
                                              │  (8 systems)  │
                                              └──────────────┘
```

### Memory Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    8 MEMORY SYSTEMS                      │
├─────────────────────────────────────────────────────────┤
│ 1. Claude Flow SQL.js    │ HNSW vectors, 384-dim        │
│    mcp__claude-flow__    │ Namespaces: system, patterns  │
│    memory_*              │ 17+ entries, persistent       │
├──────────────────────────┼──────────────────────────────┤
│ 2. Loki 3-Tier Memory   │ Episodic + Semantic +         │
│    .loki/memory/         │ Procedural layers             │
│                          │ Namespace: rateshift          │
├──────────────────────────┼──────────────────────────────┤
│ 3. Auto-Memory (MEMORY.md)│ ~/.claude/projects/*/memory/│
│    Persists across convos │ Topic files: patterns.md,   │
│                           │ architecture.md, etc.        │
├──────────────────────────┼──────────────────────────────┤
│ 4. Learned Skills         │ ~/.claude/skills/learned/    │
│    203 pattern files      │ YAML frontmatter + markdown  │
├──────────────────────────┼──────────────────────────────┤
│ 5. AgentDB (agentic-flow)│ HNSW-indexed vector store    │
│    mcp__agentic-flow__   │ Pattern search + stats        │
│    agentdb_*             │                               │
├──────────────────────────┼──────────────────────────────┤
│ 6. Chroma MCP            │ Vector DB for embeddings      │
│    chroma-mcp server     │ Semantic search across docs   │
├──────────────────────────┼──────────────────────────────┤
│ 7. Project Intelligence  │ .project-intelligence/        │
│    MASTER_TODO_REGISTRY   │ State, signals, queue, plans │
├──────────────────────────┼──────────────────────────────┤
│ 8. Continuity State      │ .loki/CONTINUITY.md           │
│    Session summaries      │ Commit chains, test counts   │
└──────────────────────────┴──────────────────────────────┘
```

### Orchestration Playbook

**When to use each orchestrator:**

- **Direct Inline (Tier 1)**: Single-file edits, lookups, typos, config changes. <20 words, 1 file. No agents needed.
- **Single Agent via `Task()` (Tier 2)**: Bug fixes, small features, test writing. 2-5 files. Pick specialist agent type (e.g., `python-pro`, `react-specialist`, `debugger`).
- **Team via `TeamCreate()` (Tier 2-3)**: Features spanning backend+frontend, coordinated refactors. 3-8 agents with task list. Use Conductor tracks for multi-day work.
- **Swarm via `mcp__claude-flow__swarm_init` (Tier 3)**: Audits, large migrations, security reviews, performance optimization. 5-12 parallel agents with dependency DAGs. Non-overlapping file scopes.
- **SPARC Pipeline (Tier 3)**: Structured development with explicit phases. Use when you need Spec→Pseudocode→Architecture→Refinement→Completion discipline. Good for new services and complex refactors.
- **Loki Mode (Tier 4)**: Autonomous PRD-to-production. Multi-phase execution with RARV cycles. Requires `--dangerously-skip-permissions`. Uses `.loki/queue/pending.json` for task queue, `.loki/state/orchestrator.json` for phase tracking. Ideal for greenfield features with PRDs.

**Model Tier Strategy (inferred):**

| Role | Model | When |
|------|-------|------|
| Architect / Lead | Opus 4.6 | Planning, complex reasoning, code review |
| Implementer | Sonnet 4.6 | Feature building, test writing, most coding |
| Scout / Helper | Haiku 4.5 | Quick searches, formatting, simple queries |
| Memory Sync | Sonnet (not Haiku) | Haiku hits prompt limits with 2,000+ skills context |

**Hooks Pipeline:**

1. **PreToolUse** (every tool): `session-init-check.sh` — one-time reminder to run session initialization
2. **PreToolUse** (Task/TeamCreate): `classify-task.sh` — advisory tier classification (never blocks)
3. **PostToolUse** (Task/TeamCreate): `log-routing-decision.sh` — logs agent type selection for learning
4. **Stop**: `evaluate-session.sh` — extracts patterns from session into learned skills
5. **Stop**: `session-end-persist.sh` — persists state and cleans up session markers

---

## 3. Projects & Repos

### Active Projects

| Project | Path | Stack | Status |
|---------|------|-------|--------|
| **RateShift** | `~/projects/electricity-optimizer` | Next.js 16 + React 19 + FastAPI + Neon PG + CF Workers | Production. 7,386 tests. 61 migrations. 53 tables. 32 GHA workflows. Primary active project |
| **Ruflo / Claude Flow** | `~/projects/ruflo` | Node.js / TypeScript CLI + MCP | v3.5 stable. 5,800+ commits. 215 MCP tools. Foundation for all orchestration |
| **Agentic Flow** | `~/projects/agentic-flow` | Node.js | v2.0.2-alpha. 34 agents, 8 skills. SPARC integration engine |
| **Tax Prep 2025** | `~/projects/tax-prep-2025` | Python scripts + JSON warehouse | TY2025 filing. 27 entities. Gmail scan + Origin + QBO automation |
| **Financial MCP Server** | `~/projects/financial-mcp-server` | Python MCP server | QuickBooks + Origin Financial API bridge |
| **Investment Analysis Platform** | `~/Documents/GitHub/investment-analysis-platform` | Flask + React + MongoDB | Real estate + financial analysis tool. Docker-compose deployable |
| **Real Estate Analyzer** | `~/Documents/GitHub/real-estate-analyzer` | Flask + React + MongoDB | Property analysis, risk assessment, opportunity scoring |
| **Agency Agents** | `~/projects/agency-agents` | Mixed | Agent templates: design, engineering, marketing, product, game-dev |

### RateShift (Primary Project) — Detail

- **Domain**: `rateshift.app` — automatically shift consumers to lower electricity rates
- **Frontend**: Vercel (Next.js 16 + React 19 + TypeScript). 2,039 tests (154 suites). 15 sidebar nav items
- **Backend**: Render (FastAPI + Python 3.12). 2,976 tests. 42 env vars
- **Database**: Neon PostgreSQL project `cold-rice-23455092`. 53 tables (44 public + 9 neon_auth). 61 migrations through 061
- **Edge**: CF Worker `rateshift-api-gateway` at `api.rateshift.app`. 3 cron triggers. 90 tests. 2-tier caching + native rate limiting
- **ML**: Ensemble predictor with HNSW vector search. 676 tests. HMAC model signing
- **E2E**: 1,605 tests across 25 specs and 5 browsers (Playwright)
- **AI Agent**: Gemini 3 Flash + Groq Llama 3.3 70B fallback. SSE streaming. Rate-limited by tier
- **Payments**: Stripe (Free/$4.99 Pro/$14.99 Business). Dunning cycle. Plan gating on 7+ endpoints
- **Auth**: Better Auth (scrypt). GitHub OAuth complete. Google OAuth in progress
- **Email**: Resend (primary) + Gmail SMTP (fallback). Domain-verified DKIM/SPF/DMARC
- **Monitoring**: OTel → Grafana Cloud (Tempo). Sentry error tracking. Self-healing CI/CD (33 GHA workflows)
- **Orchestrators used**: Loki Mode, Claude Flow, Agentic Flow, SPARC, Conductor (18 tracks all complete), Auto-Orchestrator, DSP graph (474 entities)
- **Monthly cost**: $0 (all free tiers)

### Skill & Config Sources (15 GitHub Repos)

| Repo | Location | Content |
|------|----------|---------|
| awesome-claude-skills | `~/Documents/GitHub/awesome-claude-skills/` | Community skills (symlinked) |
| investment-analysis-platform | `~/Documents/GitHub/investment-analysis-platform/` | Investment analysis skills |
| awesome-claude-code (hesreallyhim) | Integrated | 23 commands (acc-* prefix) |
| Antigravity bundles | Integrated | 136 skills (ag-* prefix) |
| Vendor: Vercel, Better Auth, Neon, Stripe, Sentry, Trail of Bits, Cloudflare | `~/.claude/integrations/vendor-*.json` | 43 vendor skills |
| Composio App Automations | `~/.claude/integrations/composio-app-skills.json` | 832 SaaS integrations |
| 7 community curated repos | `~/.claude/integrations/*.json` | ~1,087 curated skills |

---

## 4. Preferences & Constraints

### Quality Bars

| Area | Standard | Source |
|------|----------|--------|
| **Testing** | All tests must pass before commit. Tests are sacred — never delete failing tests. `.venv/bin/python -m pytest` only | CLAUDE.md, Loki rules |
| **Commits** | Atomic, descriptive. `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`. Never commit secrets | CLAUDE.md, global config |
| **Security** | OWASP top 10 awareness. No command injection, XSS, SQLi. Swagger disabled in prod. HMAC model signing. AES-256-GCM encryption for credentials | CLAUDE.md, audit tracks |
| **Database** | UUID PKs. `neondb_owner` role. Migrations must be idempotent (`IF NOT EXISTS`). GDPR CASCADE on user-linked FKs | CLAUDE.md |
| **API** | Region enum (never raw strings). Internal endpoints require `X-API-Key`. 30s timeout exclusion for internal routes | CLAUDE.md |
| **Frontend** | `loading.tsx` + `error.tsx` for every route. isSafeRedirect() for redirects. CSS custom properties for chart colors | Patterns |
| **CI/CD** | Self-healing with `retry-curl` + `notify-slack`. Auto-format (Black + isort). E2E retry on flakes | Automation plan |
| **Done Definition** | Code written + tests passing + docs updated + board sync + memory persisted + patterns extracted | Loki RARV, CLAUDE.md |

### Token & Cost Preferences

| Preference | Detail | Source |
|------------|--------|--------|
| Default model | Opus 4.6 (set in `settings.json`) | Explicit config |
| Agent model routing | Opus for architects, Sonnet for implementers, Haiku for scouts | Auto-Orchestrator |
| Haiku limitation | Hits prompt limits with 2,100+ skills context — use Sonnet minimum for memory-sync | Learned pattern |
| GHA cost | Optimized from ~4,470 min/mo to ~1,283 min/mo. Consolidated daily crons. CF Worker cron triggers for zero-GHA-cost periodic tasks | Cost analysis |
| Monthly infra | $0 target — all free tiers (Neon, Render, Vercel, CF Workers, Grafana Cloud) | CLAUDE.md |
| Explore agents | Exceed prompt limits with 2,000+ skills — use direct inline audits for comprehensive reviews | Learned pattern |

### Behavioral Constraints

- **Verify before building**: Always check if "planned future work" is already implemented — docs lag behind code
- **No over-engineering**: Only make changes directly requested or clearly necessary
- **Conservative with destructive actions**: Confirm before push, delete, reset. Measure twice, cut once
- **asyncio.gather + shared AsyncSession = corruption**: Use sequential loops for DB operations
- **Pre-commit framework**: `.pre-commit-config.yaml` (not husky). Never use both
- **GitHub CLI auth**: `gh` authenticated as `JoeyJoziah`, not `devinmcgrath`
- **1Password**: Vault "Electricity Optimizer" (28+ mappings). Use UUID for items with special chars in titles
- **Parallel agent file conflicts**: Assign non-overlapping file scopes to concurrent agents; edit shared files sequentially

### Session Protocol (Mandatory)

Every session must initialize in order:
1. Claude Flow session-start + memory stats verification
2. Loki Mode activation (verify version, rebuild memory index, process pending events)
3. Board Sync health check
4. Memory cross-sync verification
5. Agentic-Flow availability check (optional)

---

## 5. Example Workflows

### Recipe 1: Greenfield Feature Build with Loki + Swarms

**When**: Building a complete new feature from a PRD (e.g., new billing page, community feature, integration)

**Steps**:
1. **PRD Creation**: `/create-prd` or write to `.loki/prds/feature-name.md` using `.loki/prd-template.md`
2. **Engage Loki Mode**: `/loki-mode` — Loki reads PRD, creates task queue in `.loki/queue/pending.json`
3. **RARV Execution**: Loki autonomously cycles: Reason→Act→Reflect→Verify per task
   - Creates migrations (`neon-postgres` skill), backend services, API routes, frontend pages
   - Runs tests after each task, commits atomically
4. **Conductor Track**: Create via `/conductor-new-track` for progress tracking across sessions
5. **Swarm Phase** (if large): `mcp__claude-flow__swarm_init` with 5-8 agents for parallel implementation
   - Skill Router assigns vendor-first skills per phase (swarm-routes.json)
   - Non-overlapping file scopes prevent conflicts
6. **Verification**: Full test suite (`.venv/bin/python -m pytest` + `npm test` + E2E)
7. **Post-Build**: Board sync → memory persist → pattern extraction → commit

**Runs in**: `~/projects/electricity-optimizer`

---

### Recipe 2: Codebase Audit & Remediation Sprint

**When**: Systematic quality hardening, security audit, or tech debt reduction

**Steps**:
1. **Audit Scan**: Use Trail of Bits skills (`/tob-static-analysis-semgrep`, `/tob-entry-point-analyzer`, `/tob-insecure-defaults`) + Sentry skills (`/sentry-security-review`, `/sentry-find-bugs`)
2. **Findings Triage**: Classify into P0-P3. Create Conductor track: `/conductor-new-track`
3. **Sprint Planning**: Divide into 5-10 sprints with dependency DAG. Create tasks via `TaskCreate`
4. **Parallel Agent Execution**: Spawn 5-7 background agents (`Task` tool with `run_in_background: true`)
   - Assign non-overlapping file scopes per agent
   - Each agent gets specific sprint tasks + skill assignments from swarm-routes.json
5. **Sequential Merge**: After agents complete, merge changes. Run full test suite
6. **Migration Creation**: If schema changes needed, use Neon MCP tools with idempotent patterns
7. **Conductor Verification**: `grep -c '\- \[ \]' conductor/tracks/*/plan.md` — zero unchecked items
8. **Documentation**: Update CLAUDE.md test counts, migration counts, table counts

**Runs in**: `~/projects/electricity-optimizer`
**Example**: audit-remediation_20260323 — 75 tasks, 9 sprints, ~560 findings, 7 parallel agents

---

### Recipe 3: Financial Modeling / Tax Workflow

**When**: Tax preparation, investment analysis, or financial reporting

**Steps**:
1. **Data Gathering**: Use `financial-server` MCP tools
   - `qbo_profit_and_loss` / `qbo_balance_sheet` for business financials
   - `origin_transactions` / `origin_net_worth` for personal finance
   - Gmail scan via Composio (`composio-gmail-automation`) for tax documents
2. **Document Processing**: Scripts in `~/projects/tax-prep-2025/scripts/`
   - `scan_gmail.py` — automated document discovery
   - Warehouse organization by IRS category
3. **Analysis**: Investment analysis via `~/Documents/GitHub/investment-analysis-platform/`
   - Risk assessment, opportunity scoring, tax benefit analysis
4. **Checklist Tracking**: `checklist.json` master checklist with 27 entities
5. **Report Generation**: `checklist-report.md` dashboard

**Runs in**: `~/projects/tax-prep-2025` and `~/Documents/GitHub/investment-analysis-platform`

---

### Recipe 4: SPARC-Driven Service Development

**When**: Building a new backend service or complex refactor with explicit methodology

**Steps**:
1. **Specification**: `/sparc:spec-pseudocode` — define objectives, scope, constraints
2. **Pseudocode**: `/sparc:spec-pseudocode` — high-level logic with TDD anchors
3. **Architecture**: `/sparc:architect` — system diagrams, service boundaries, data flow
4. **Refinement**: Cycle through:
   - `/sparc:tdd` — write failing tests first, then implement
   - `/sparc:debug` — fix issues found during TDD
   - `/sparc:security-review` — security audit before completion
   - `/sparc:refinement-optimization-mode` — performance optimization
5. **Completion**: `/sparc:integration` — integrate with existing system
6. **Documentation**: `/sparc:docs-writer` — API docs, architecture records
7. **Deployment**: `/sparc:devops` — CI/CD pipeline, deployment procedures

**Runs in**: Any project. Especially useful for `~/projects/electricity-optimizer` services

---

### Recipe 5: Multi-Agent Code Review & PR Management

**When**: Reviewing PRs, conducting code reviews, or managing release cycles

**Steps**:
1. **PR Analysis**: `/github:code-review` or spawn `code-review-swarm` agent
   - Automated security review via `sentry-code-review`
   - Static analysis via `tob-differential-review`
   - Style check via `coding-standards` skill
2. **Swarm Review** (for large PRs): `mcp__claude-flow__swarm_init` with specialized reviewers
   - Security agent, performance agent, test coverage agent, architecture agent
   - Each reviews independently, findings merged
3. **Iteration**: `/github:pr-enhance` or `/sentry-iterate-pr` for addressing feedback
4. **Release**: `/github:release-swarm` for multi-package release orchestration
   - Parallel changelog generation, cross-repo version coordination
   - Progressive deployment with rollback capability
5. **Post-Merge**: Board sync, memory update, Slack notification via `notify-slack`

**Runs in**: Any Git repository. Primary use in `~/projects/electricity-optimizer`

---

## Appendix: Quick Reference

| Resource | Location |
|----------|----------|
| Global config | `~/.claude/settings.json` |
| Permissions | `~/.claude/settings.local.json` (239 rules) |
| Agents | `~/.claude/agents/` (171 files) |
| Skills | `~/.claude/skills/` (2,102 entries) |
| Commands | `~/.claude/commands/` (204 entries) |
| Learned patterns | `~/.claude/skills/learned/` (203 files) |
| Integration manifests | `~/.claude/integrations/` (33 files) |
| Skill router | `~/.claude/skills/skill-router/` (registry.json, swarm-routes.json) |
| Auto-orchestrator | `~/.claude/skills/auto-orchestrator/` |
| Loki Mode | `~/.claude/skills/loki-mode/` |
| Project memory | `~/.claude/projects/-Users-devinmcgrath-projects-electricity-optimizer/memory/` |
| Conductor tracks | `~/projects/electricity-optimizer/conductor/tracks/` (19 tracks, all complete) |
| DSP graph | `~/projects/electricity-optimizer/.dsp/` (474 entities, 940+ imports) |
| Loki state | `~/projects/electricity-optimizer/.loki/` |
| Project intelligence | `~/projects/electricity-optimizer/.project-intelligence/` |
| GHA workflows | `~/projects/electricity-optimizer/.github/workflows/` (32 files) |
| MCP config (project) | `~/projects/electricity-optimizer/.mcp.json` (14 servers) |
| GitHub | `JoeyJoziah/electricity-optimizer` (gh CLI auth'd as JoeyJoziah) |
| 1Password vault | "Electricity Optimizer" (28+ credential mappings) |
| Neon project | `cold-rice-23455092` ("energyoptimize") |
| CF Account | `b41be0d03c76c0b2cc91efccdb7a10df` |
| Slack workspace | `electricityoptimizer.slack.com` (T0AK0AJV5NE) |
