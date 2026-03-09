# Memory Sync Swarm v2

Full-spectrum memory synchronization, learning extraction, documentation swarm, and session persistence. Runs ALL 8 phases including session end. For mid-session sync without session end, use `/memory-sync-checkpoint` instead.

## Prerequisites

These skills will be loaded automatically in Phase 1:

**Core Memory & Learning (16):**
- data-structure-protocol, memory-sync-swarm, continuous-learning, agentdb-memory-patterns
- sparc:memory-manager, af-sparc:memory-manager, automation:session-memory, memory-systems
- agent-memory-systems, agent-memory-mcp, flow-nexus-neural, flow-nexus-swarm
- conversation-memory, frontend-patterns, backend-patterns, memory-forensics

**Orchestration (5):**
- sparc:batch-executor, optimization:parallel-execution, optimization:parallel-execute
- sparc:integration, verification-loop

## Execution

### Phase 1: Load Skills

Load all 21 skills listed above via the Skill tool. If a skill fails to load, log a warning and continue.

### Phase 2: Audit

Create a team named `memory-sync-swarm`. Start by auditing ALL memory systems to identify what needs updating:

1. **Claude Flow memory** (sql.js, 384-dim HNSW) -- check entry count via `mcp__claude-flow__memory_stats`, search for recent session topics
2. **Auto-memory** (`MEMORY.md`) -- read and compare against current session state
3. **Loki 3-tier memory** (`.loki/memory/`) -- check episodic/, semantic/, skills/ for staleness
4. **AgentDB patterns** -- search Claude Flow `patterns` namespace for coverage gaps
5. **Session registries** (`.claude/logs/*.jsonl`) -- verify edit-registry, session-changes are current
6. **Integration manifests** (`~/.claude/integrations/`) -- verify manifests match installed symlinks
7. **Loki timeline** (`.loki/memory/timeline.json`) -- check last_updated and active_context
8. **Board sync state** -- check `.claude/.board-sync.last` for last sync time
9. **Conversation memory** -- analyze session for implicit patterns, decisions, corrections
10. **Memory forensics** -- detect stale/orphaned/conflicting entries across stores
11. **Pattern currency** -- are documented frontend/backend patterns still accurate?

Document all gaps found. Produce a structured gap report.

### Phase 3: Parallel Memory Updates (spawn 4 agents)

**Agent 1: claude-flow-agent** (subagent_type: `general-purpose`)
- Store session summary, key decisions, new patterns, integration details in Claude Flow
- Use `mcp__claude-flow__memory_store` with `upsert: true`
- Target namespaces: `project`, `patterns`. Minimum 5 entries

**Agent 2: loki-agent** (subagent_type: `general-purpose`)
- Create/update Loki 3-tier memory files: episodic/, semantic/, skills/
- Update `.loki/memory/timeline.json`. Process pending events
- Skip if `.loki/memory/` absent

**Agent 3: learning-agent** (subagent_type: `general-purpose`)
- Extract reusable patterns using continuous-learning skill
- Create learned skill files at `~/.claude/skills/learned/`
- Categories: error_resolution, user_corrections, workarounds, debugging_techniques, project_specific
- Minimum 3 patterns

**Agent 4: agentdb-agent** (subagent_type: `general-purpose`)
- Store AgentDB-style patterns in Claude Flow `patterns` namespace
- Types: procedural, decision, problem-solving, template, error-handling, verification
- Include confidence scores and tags

### Phase 4: Learning Sweep (spawn 2-3 agents, after Phase 3 completes)

**Agent 5: forensics-agent** (subagent_type: `general-purpose`)
- Scan ALL memory stores for stale, orphaned, conflicting entries
- Resolve: update, remove, or consolidate

**Agent 6: deep-learning-agent** (subagent_type: `general-purpose`)
- Apply continuous-learning methodology to full session
- Extract implicit patterns: decisions, corrections, pivots, conventions
- Re-score existing patterns based on session validation

**Agent 7: neural-agent** (subagent_type: `general-purpose`, SKIP if flow-nexus-neural unavailable)
- Neural pattern analysis across memory stores
- Identify cross-store clusters and consolidation opportunities

### Phase 5: Documentation Swarm (spawn 3 agents, after Phase 4 completes)

**Agent A: claude-md-agent** (subagent_type: `general-purpose`)
- Update `CLAUDE.md` -- architecture, counts, dates, reminders, integrations

**Agent B: memory-md-agent** (subagent_type: `general-purpose`)
- Update `MEMORY.md` -- Architecture, Key Patterns, Milestones, test counts

**Agent C: docs-agent** (subagent_type: `general-purpose`)
- Update codemaps, `docs/AUTOMATION_PLAN.md`, `.loki/memory/timeline.json`, manifests

### Phase 6: Git Commit & Push

1. `git status` -- identify changed files (never `-uall`)
2. `git add` specific files (NEVER `git add -A`)
3. Commit with descriptive message + `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
4. `git push origin <current-branch>`
5. Verify clean state

### Phase 7: Board Sync + Notion

```bash
[ -x .claude/hooks/board-sync/sync-boards.sh ] && .claude/hooks/board-sync/sync-boards.sh
[ -x .claude/hooks/board-sync/loki-event-sync.sh ] && .claude/hooks/board-sync/loki-event-sync.sh
```

Trigger Notion sync via Rube recipe: `mcp__rube__RUBE_EXECUTE_RECIPE` with recipe ID `rcp_73Kc9K65YC5T`.

### Phase 8: Session End

1. Store session-end entry in Claude Flow (`sessions` namespace)
2. Run `npx claude-flow hooks session-end --session-id "<descriptive-id>" --save-state --export-metrics --generate-summary --cleanup-temp`
3. Shut down all team agents
4. Delete team

## Task Dependency Graph

```
Phase 1: [Load Skills]
Phase 2: [Audit] ─────────────────────────────────────────────┐
                                                                v
Phase 3: [Claude Flow] [Loki] [Learning] [AgentDB]            (4 parallel)
              │           │        │          │
              └───────────┴────────┴──────────┘
                          v
Phase 4: [Forensics] [Deep-Learning] [Neural]                  (2-3 parallel)
              │            │             │
              └────────────┴─────────────┘
                          v
Phase 5: [CLAUDE.md] [MEMORY.md] [Docs]                       (3 parallel)
              │           │         │
              └───────────┴─────────┘
                          v
Phase 6:      [Git Commit & Push]
                          v
Phase 7:    [Board Sync + Notion]
                          v
Phase 8:        [Session End]
```

## Team Configuration

```
Team name: memory-sync-swarm
Agents: Up to 10 workers across 3 parallel phases + team lead
Task count: 14
```

## Invocation

```
/memory-sync-swarm
```
