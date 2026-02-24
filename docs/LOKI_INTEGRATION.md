# Loki Mode Integration Architecture

**Last Updated:** 2026-02-24
**Loki Version:** v5.53.0
**Provider:** Claude (Opus 4.6)

---

## Overview

Loki Mode provides autonomous RARV (Research, Act, Review, Verify) orchestration
for the Electricity Optimizer project. It integrates with Claude Flow for persistent
memory, AgentDB for vector-backed semantic search, and the board sync pipeline for
GitHub Projects and Notion synchronization. The system runs as an MCP server
registered in `.mcp.json` and activates automatically on each Claude Code session
via shell hooks.

### Integration chain

```
Loki Mode (MCP server)
  --> Claude Flow (daemon + 384-dim vector memory)
  --> AgentDB (HNSW vector store)
  --> Board Sync (sync-boards.sh)
  --> GitHub Projects #4 + Notion Roadmap
```

---

## Architecture

### System Component Map

```
+----------------------------+
|     Claude Code Session    |
+----------------------------+
  |  PreToolUse hook             |  Stop hook
  v                              v
activate-orchestration.sh    session-end-orchestration.sh
  |                              |
  +---> Claude Flow daemon       +---> Loki memory consolidation
  |       (memory: 384-dim)      +---> Event bus drain
  +---> Loki memory index        +---> Claude Flow state persist
  |       (IndexLayer)           +---> Board sync final drain
  +---> Loki event bus drain     +---> Cross-system memory sync
  +---> Board sync health        +---> Marker cleanup
```

### Directory Layout

```
.loki/
  CONTINUITY.md          Persisted RARV state (phase, cycle, merge sequence)
  HUMAN_INPUT.md         Human directives injected into RARV cycles
  prd-template.md        PRD template pre-filled with project constraints
  test-prd.md            Example PRD (health endpoint)
  dashboard/             Loki dashboard static assets (port 57374)
  events/
    pending/             Incoming event JSON files (file-based pub/sub)
    archive/             Processed events moved here after dispatch
  learning/
    signals/             Learning signal JSON files for cross-system sync
  logs/                  Loki internal logs
  memory/
    index.json           Top-level memory index
    namespaces.json      Namespace registry
    electricity-optimizer/
      episodic/          Session-scoped memories
      semantic/          Concept and domain knowledge
      skills/            Procedural / learned skills
      vectors/           384-dimensional vector embeddings
  state/
    provider             Current provider name ("claude")
```

### MCP Server Configuration (`.mcp.json`)

| Setting              | Value                        |
|----------------------|------------------------------|
| command              | `python3 -m mcp.server`      |
| cwd                  | `~/.claude/skills/loki-mode` |
| LOKI_PROVIDER        | `claude`                     |
| LOKI_PARALLEL        | `true`                       |
| LOKI_AUDIT_ENABLED   | `true`                       |
| LOKI_METRICS_ENABLED | `true`                       |
| LOKI_AUTO_PR         | `true`                       |
| LOKI_TELEMETRY_DISABLED | `true`                    |

---

## Auto-Initialization

### Session Start (PreToolUse hook)

The script `.claude/scripts/activate-orchestration.sh` fires on the first tool use
of each session. It is marker-guarded (`/tmp/claude-orchestration-active`) to run
exactly once per session and always exits 0 to avoid blocking tool execution.

**Activation sequence** (runs in background):

1. **Claude Flow daemon** -- starts via `npx claude-flow hooks session-start`,
   verifies memory entry count with `memory stats`.
2. **Loki memory index** -- rebuilds the `IndexLayer` using the PYTHONPATH
   workaround (see Troubleshooting). Scans `.loki/memory/` for the
   `electricity-optimizer` namespace.
3. **Loki event bus drain** -- counts pending JSON files in
   `.loki/events/pending/`. If any exist from a previous session, dispatches them
   through `loki-event-sync.sh`.
4. **Board sync health check** -- verifies `sync-boards.sh` is present and
   executable.
5. **Summary** -- logs how many of 3 systems (Claude Flow, Loki, Board Sync) came
   online. Output goes to `.claude/logs/orchestration-init.log`.

### Session End (Stop hook)

The script `.claude/scripts/session-end-orchestration.sh` fires on session stop and
performs an ordered shutdown:

1. **Loki memory consolidation** -- `loki memory consolidate` merges episodic
   memories into semantic storage.
2. **Event bus drain** -- processes all remaining pending events.
3. **Claude Flow state persist** -- `npx claude-flow hooks session-end` with
   `--saveState true --exportMetrics true`.
4. **Board sync drain** -- `sync-boards.sh drain --force` flushes queued syncs.
5. **Cross-system memory sync** -- counts learning signals in `.loki/learning/`
   and persists a summary to Claude Flow under the `project` namespace.
6. **Marker cleanup** -- removes `/tmp/claude-orchestration-active` and
   `/tmp/claude-session-init-marker`.

---

## Memory System

### 3-Tier Architecture

| Tier       | Directory                                         | Purpose                              |
|------------|---------------------------------------------------|--------------------------------------|
| Episodic   | `.loki/memory/electricity-optimizer/episodic/`     | Session-scoped observations          |
| Semantic   | `.loki/memory/electricity-optimizer/semantic/`     | Domain knowledge and concepts        |
| Procedural | `.loki/memory/electricity-optimizer/skills/`       | Learned patterns and procedures      |

All tiers share a vector index at `.loki/memory/electricity-optimizer/vectors/`
using 384-dimensional embeddings, compatible with Claude Flow's vector format.

### IndexLayer

The `IndexLayer` class (from `memory.layers` in `~/.claude/skills/loki-mode`)
manages the memory index at `.loki/memory/index.json`. On session start, it is
rebuilt with `layer.update([])` to pick up any files added outside the current
process.

Six project documentation files are indexed into the namespace for semantic
retrieval during RARV cycles:

- `CLAUDE.md` (project instructions)
- `docs/CODEMAP_BACKEND.md`
- `docs/CODEMAP_FRONTEND.md`
- `docs/DEPLOYMENT.md`
- `docs/INFRASTRUCTURE.md`
- `docs/TESTING.md`

### Namespace

The active namespace is `electricity-optimizer`, registered in
`.loki/memory/namespaces.json`. This isolates project memories from other Loki
Mode projects on the same machine.

### Bidirectional Sync with Claude Flow

Claude Flow uses a sql.js + HNSW vector index (384-dimension embeddings).
Synchronization occurs at two points:

- **Cycle complete events** -- `loki-event-sync.sh` stores cycle results in
  Claude Flow via `npx claude-flow memory store` under the `coordination`
  namespace.
- **Session end** -- learning signals from `.loki/learning/signals/` are
  summarized and persisted to the Claude Flow `project` namespace.

Cross-sync can be verified with:
```
mcp__claude-flow__memory_search query="loki"
```

---

## Event Bus

### Mechanism

File-based publish/subscribe. Loki writes JSON event files to
`.loki/events/pending/`. The dispatcher script `loki-event-sync.sh` reads,
processes, and moves each file to `.loki/events/archive/`.

### Event Types

| Type                | Action                                                      |
|---------------------|-------------------------------------------------------------|
| `task_complete`     | Triggers board sync (`sync-boards.sh drain --bg`)           |
| `phase_change`      | Updates `CONTINUITY.md` with new phase and cycle number     |
| `verification_fail` | Creates a GitHub issue with `bug,loki` labels via `gh`      |
| `cycle_complete`    | Persists cycle result to Claude Flow memory + full board sync |

### Event File Format

```json
{
  "id": "<uuid>",
  "type": "task_complete",
  "timestamp": "2026-02-23T16:30:00Z",
  "payload": {
    "task": "Add /api/v1/health endpoint",
    "description": "..."
  }
}
```

### Dispatcher Modes

```bash
# Process all pending events once (default)
.claude/hooks/board-sync/loki-event-sync.sh

# Watch mode -- poll every 2 seconds
.claude/hooks/board-sync/loki-event-sync.sh --watch

# Dry run -- show what would happen
.claude/hooks/board-sync/loki-event-sync.sh --dry-run
```

---

## Project-Specific Agents

Four agent skills are defined for this project in the CLAUDE.md Loki section. They
provide domain-specialized context when Loki assigns sub-tasks during RARV cycles.

| Agent             | Domain                                                        |
|-------------------|---------------------------------------------------------------|
| EnergyDataAgent   | EIA/NREL APIs, Region enum, utility types, state regulations  |
| NeonDBAgent       | 14-table schema, endpoint quirk (us-east-1), UUID PKs, migrations |
| StripeAgent       | Async billing, $4.99 Pro / $14.99 Business, webhook flow     |
| MLPipelineAgent   | Ensemble predictor, HNSW vector store, observation loop, nightly learning |

---

## Skill Symlinks

The Loki Mode skill source lives at `~/.claude/skills/loki-mode/`. Shared skill
libraries are symlinked from two sources into the global Claude configuration:

- `~/Documents/GitHub/awesome-claude-skills/` -- community skills
- `~/Documents/GitHub/investment-analysis-platform/` -- investment analysis skills

---

## PRD Templates

| File                   | Purpose                                                    |
|------------------------|------------------------------------------------------------|
| `.loki/prd-template.md`| Pre-filled template with tech stack, constraints, criteria |
| `.loki/test-prd.md`    | Example PRD (`GET /api/v1/health`) showing expected format |

The template includes sections for Context, Technical Constraints, Requirements,
and Acceptance Criteria (test counts, coverage, board sync, docs updates).

---

## Hook Pipeline

### Full Session Start Chain

```
Claude Code launches
  --> PreToolUse event fires
  --> session-init-check.sh (global, reminds to run init if marker absent)
  --> activate-orchestration.sh (project, marker-guarded)
        1. Claude Flow daemon start + memory verify
        2. Loki memory index rebuild (PYTHONPATH fix)
        3. Pending event drain via loki-event-sync.sh
        4. Board sync health check
        5. Summary log
```

### Full Session End Chain

```
Claude Code session ends
  --> Stop event fires
  --> session-end-orchestration.sh (project)
        1. Loki memory consolidate
        2. Event bus drain (loki-event-sync.sh)
        3. Claude Flow session-end (persist + metrics)
        4. Board sync drain (sync-boards.sh --force)
        5. Cross-system memory sync (learning signals)
        6. Marker cleanup
  --> evaluate-session.sh (global, pattern extraction)
  --> session-end-persist.sh (global, state persist + marker cleanup)
```

### Board Sync Sub-Hooks

In `.claude/hooks/board-sync/`, additional hooks trigger `sync-boards.sh` from
various git and edit events:

| Hook                   | Trigger                |
|------------------------|------------------------|
| git-post-commit.sh     | After git commit       |
| git-post-merge.sh      | After git merge        |
| git-post-checkout.sh   | After git checkout     |
| post-edit-sync.sh      | After file edits       |
| post-task-sync.sh      | After task completion  |
| session-end-sync.sh    | On session end         |

---

## Configuration

### Environment Variables

All MCP server env vars are defined in `.mcp.json` (see Architecture section).
Key variables beyond those:

- `PYTHONPATH` -- must include `~/.claude/skills/loki-mode` for memory CLI
- `OP_SERVICE_ACCOUNT_TOKEN` -- 1Password vault access for secrets

### PYTHONPATH Requirement

All `loki memory` CLI commands require the skill source on `PYTHONPATH`:
```bash
PYTHONPATH="$HOME/.claude/skills/loki-mode" loki memory <command>
```

### Provider State

Stored in `.loki/state/provider` (plaintext, currently `claude`). Change with
`loki provider set <name>`.

### Human Directives

Edit `.loki/HUMAN_INPUT.md` to inject constraints into RARV cycles. Loki reads
this file before each cycle iteration. Current active directives:

- Use Opus 4.6 for all development work
- Always run backend tests with `.venv/bin/python -m pytest`
- DB endpoint is `ep-withered-morning-aix83cfw-pooler` (us-east-1)
- Add new model fields to conftest.py `mock_sqlalchemy_select` patch list
- All PKs use UUID type; GRANTs use `neondb_owner` role

### Continuity State

`.loki/CONTINUITY.md` tracks the current RARV phase, cycle number, and merge
sequence. The `phase_change` event handler in `loki-event-sync.sh` automatically
updates this file.

### Dashboard

Start manually with `loki dashboard` (port 57374). Provides a web view of RARV
cycle status, memory contents, and event history.

---

## Troubleshooting

**PYTHONPATH fix** -- `ModuleNotFoundError: No module named 'memory'` on any
`loki memory` command. Always prefix with
`PYTHONPATH="$HOME/.claude/skills/loki-mode"`. The activation script does this
automatically; manual invocations must include it.

**Memory index rebuild** -- stale or missing semantic search results:
```bash
PYTHONPATH="$HOME/.claude/skills/loki-mode" python3 -c "
from memory.layers import IndexLayer
layer = IndexLayer('$(pwd)/.loki/memory'); layer.update([]); print('OK')
"
```

**Event bus drain** -- stale events stuck in pending:
```bash
ls .loki/events/pending/*.json 2>/dev/null | wc -l   # check count
.claude/hooks/board-sync/loki-event-sync.sh            # manual drain
.claude/hooks/board-sync/loki-event-sync.sh --dry-run  # inspect only
```

**Orchestration not activating** -- 0/3 systems online at session start:
1. Remove stale marker: `rm -f /tmp/claude-orchestration-active`
2. Check log: `.claude/logs/orchestration-init.log`
3. Verify: `loki --version` (expect v5.53.0+) and `npx claude-flow daemon status`

**Cross-system sync failure** -- `memory_search query="loki"` returns nothing
after completed cycles. Check `.loki/learning/signals/` for JSON files, then
manually store via `npx claude-flow memory store -k "loki_manual_sync" -v "..." --namespace project`.

**Board sync not triggering** -- GitHub/Notion not updated:
1. Check executable: `ls -la .claude/hooks/board-sync/sync-boards.sh`
2. Check log: `.claude/logs/loki-board-sync.log`
3. Verify auth: `gh auth status` and `cat ~/.config/notion/api_key`
