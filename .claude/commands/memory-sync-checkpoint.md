# Memory Sync Checkpoint

Mid-session memory synchronization checkpoint. Runs the same workflow as `/memory-sync-swarm` (Phases 1-7) but **STOPS after board sync** — does NOT end the session. Use when you want to persist all memory, run learning sweep, update docs, commit, and sync boards without closing out.

For end-of-session sync (includes session end cleanup), use `/memory-sync-swarm` instead.

## Prerequisites

Same 21 skills as `/memory-sync-swarm` (loaded automatically in Phase 1).

## Execution

### Phase 1: Load Skills

Load all 21 skills (16 memory/learning + 5 orchestration). See `/memory-sync-swarm` for full list.

### Phase 2: Audit

Create a team named `memory-sync-checkpoint`. Audit ALL memory systems (same 11 checks as swarm variant):

1. Claude Flow memory, 2. Auto-memory (MEMORY.md), 3. Loki 3-tier, 4. AgentDB patterns,
5. Session registries, 6. Integration manifests, 7. Loki timeline, 8. Board sync state,
9. Conversation memory, 10. Memory forensics, 11. Pattern currency

Document all gaps. Produce structured gap report.

### Phase 3: Parallel Memory Updates (spawn 4 agents)

**Agent 1: claude-flow-agent** -- Claude Flow memory (5+ entries, project/patterns namespaces)
**Agent 2: loki-agent** -- Loki 3-tier files (skip if absent)
**Agent 3: learning-agent** -- Learned skill files (3+ patterns)
**Agent 4: agentdb-agent** -- AgentDB patterns in Claude Flow

### Phase 4: Learning Sweep (spawn 2-3 agents, after Phase 3)

**Agent 5: forensics-agent** -- Memory forensics + conflict resolution
**Agent 6: deep-learning-agent** -- Continuous learning + conversation memory extraction
**Agent 7: neural-agent** -- Flow-nexus neural patterns (skip if unavailable)

### Phase 5: Documentation Swarm (spawn 3 agents, after Phase 4)

**Agent A: claude-md-agent** -- Update CLAUDE.md
**Agent B: memory-md-agent** -- Update MEMORY.md
**Agent C: docs-agent** -- Update codemaps + other docs

### Phase 6: Git Commit & Push

1. `git status` -- identify changed files (never `-uall`)
2. `git add` specific files (NEVER `git add -A`)
3. Commit with descriptive message + `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
4. `git push origin <current-branch>`
5. Verify clean state

### Phase 7: Board Sync + Notion (FINAL PHASE)

```bash
[ -x .claude/hooks/board-sync/sync-boards.sh ] && .claude/hooks/board-sync/sync-boards.sh
[ -x .claude/hooks/board-sync/loki-event-sync.sh ] && .claude/hooks/board-sync/loki-event-sync.sh
```

Trigger Notion sync via Rube recipe: `mcp__rube__RUBE_EXECUTE_RECIPE` with recipe ID `rcp_73Kc9K65YC5T`.

**>>> STOP HERE <<<**

After Phase 7:
1. Shut down all team agents
2. Delete team
3. Report summary of what was synced
4. Session continues -- keep working normally

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
                    >>> STOP <<<
```

## Invocation

```
/memory-sync-checkpoint
```
