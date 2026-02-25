#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# loki-feature.sh — Automated feature development from PRD specs
#
# Orchestrates the full pipeline:
#   1. Parse PRD → task list (loki-decompose.py)
#   2. Create feature branch
#   3. For each task: RARV cycle (Reason→Act→Reflect→Verify)
#   4. Run verification gate (loki-verify.sh)
#   5. Update CONTINUITY.md state
#   6. Emit events for board sync
#   7. Create draft PR on completion
#
# Usage:
#   scripts/loki-feature.sh <prd-file>              # Run full pipeline
#   scripts/loki-feature.sh <prd-file> --dry-run    # Show plan only
#   scripts/loki-feature.sh <prd-file> --resume     # Resume from last checkpoint
#   scripts/loki-feature.sh --status                 # Show current pipeline state
#
# PRD files live in .loki/prds/ and follow .loki/prd-template.md format.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOKI_DIR="$PROJECT_DIR/.loki"
EVENTS_DIR="$LOKI_DIR/events/pending"
STATE_DIR="$LOKI_DIR/state"
TASKS_FILE="$LOKI_DIR/state/current-tasks.json"
STATUS_FILE="$LOKI_DIR/STATUS.txt"
CONTINUITY_FILE="$LOKI_DIR/CONTINUITY.md"
LOG_FILE="$PROJECT_DIR/.claude/logs/loki-feature.log"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
SYNC_SCRIPT="$PROJECT_DIR/.claude/hooks/board-sync/sync-boards.sh"
EVENT_SYNC="$PROJECT_DIR/.claude/hooks/board-sync/loki-event-sync.sh"

DRY_RUN=false
RESUME=false

# Parse args
PRD_FILE=""
for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=true ;;
        --resume)   RESUME=true ;;
        --status)   show_status; exit 0 ;;
        -*)         ;; # skip unknown flags
        *)          PRD_FILE="$arg" ;;
    esac
done

# Ensure dirs exist
mkdir -p "$EVENTS_DIR" "$STATE_DIR" "$LOKI_DIR/prds" "$(dirname "$LOG_FILE")"

# ─── Utilities ──────────────────────────────────────────────────────

log() {
    local msg="[$(date +%H:%M:%S)] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

emit_event() {
    local event_type="$1"
    local payload="$2"
    local event_id="feature-$(date +%s)-$$"
    local event_file="$EVENTS_DIR/${event_id}.json"

    cat > "$event_file" <<EVTJSON
{
  "id": "$event_id",
  "type": "$event_type",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "payload": $payload
}
EVTJSON
    log "Event: $event_type"
}

update_status() {
    local phase="$1"
    local task="$2"
    local progress="$3"
    cat > "$STATUS_FILE" <<STATUSEOF
Phase: $phase
Task: $task
Progress: $progress
Updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
STATUSEOF
}

update_continuity() {
    local phase="$1"
    local cycle="$2"
    local verification="$3"

    cat > "$CONTINUITY_FILE" <<CONTEOF
# Loki Mode Continuity State

## Project: Electricity Optimizer
## Provider: Claude (Opus 4.6 for planning + dev)
## Initialized: 2026-02-23

## Current Phase
- Phase: $phase
- RARV Cycle: $cycle
- Last verification: $verification

## Active Feature
$(if [[ -f "$TASKS_FILE" ]]; then
    echo "- PRD: $(python3 -c "import json,sys; d=json.load(open('$TASKS_FILE')); print(d.get('source','unknown'))")"
    echo "- Title: $(python3 -c "import json,sys; d=json.load(open('$TASKS_FILE')); print(d.get('title','unknown'))")"
    echo "- Tasks: $(python3 -c "import json,sys; d=json.load(open('$TASKS_FILE')); ts=d.get('tasks',[]); done=sum(1 for t in ts if t['status']=='done'); print(f'{done}/{len(ts)}')")"
else
    echo "- None"
fi)

## Merge Sequence
1. Feature branch → \`loki/session-*\`
2. Auto-commit on verification pass
3. Draft PR on push
4. Human review required for merge to main

## Integration Points
- Claude Flow: Active (memory sync on cycle_complete)
- AgentDB: HNSW vector search for semantic memory
- Board Sync: GitHub Projects #4 + Notion roadmap
- Continuous Learning: Pattern extraction on session end
- 1Password: Vault "Electricity Optimizer" for secrets
- Neon: PostgreSQL via app endpoint (us-east-1)
CONTEOF
}

show_status() {
    if [[ -f "$STATUS_FILE" ]]; then
        cat "$STATUS_FILE"
    else
        echo "No active pipeline."
    fi
    echo ""
    if [[ -f "$TASKS_FILE" ]]; then
        echo "Tasks:"
        python3 -c "
import json
d = json.load(open('$TASKS_FILE'))
for t in d.get('tasks', []):
    mark = '✓' if t['status'] == 'done' else '○' if t['status'] == 'pending' else '→'
    print(f\"  {mark} {t['id']}: {t['title']} [{t['phase']}] ({t['status']})\")
"
    fi
}

process_events() {
    if [[ -x "$EVENT_SYNC" ]]; then
        "$EVENT_SYNC" 2>/dev/null || true
    fi
}

trigger_board_sync() {
    if [[ -x "$SYNC_SCRIPT" ]]; then
        "$SYNC_SCRIPT" all --bg 2>/dev/null || true
    fi
}

# ─── Pipeline stages ───────────────────────────────────────────────

stage_decompose() {
    log "═══ Stage 1: Decompose PRD ═══"

    if [[ ! -f "$PRD_FILE" ]]; then
        log "Error: PRD file not found: $PRD_FILE"
        exit 1
    fi

    if $DRY_RUN; then
        log "[dry-run] Would decompose: $PRD_FILE"
        python3 "$SCRIPTS_DIR/loki-decompose.py" "$PRD_FILE"
        return 0
    fi

    python3 "$SCRIPTS_DIR/loki-decompose.py" "$PRD_FILE" --output "$TASKS_FILE"
    local task_count
    task_count=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['task_count'])")
    log "Decomposed into $task_count tasks"

    emit_event "phase_change" "{\"from\": \"idle\", \"to\": \"planning\", \"cycle\": 0, \"task_count\": $task_count}"
    update_continuity "Planning" "0" "N/A"
    update_status "Planning" "Decomposition complete" "$task_count tasks identified"
}

stage_branch() {
    log "═══ Stage 2: Create Feature Branch ═══"

    if $DRY_RUN; then
        log "[dry-run] Would create feature branch from PRD title"
        return 0
    fi

    local title
    title=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['title'])")
    local branch_name
    branch_name="loki/$(echo "$title" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd 'a-z0-9-' | head -c 50)"

    # Check if already on a feature branch (resume case)
    local current_branch
    current_branch=$(git -C "$PROJECT_DIR" branch --show-current)
    if [[ "$current_branch" == loki/* ]]; then
        log "Already on feature branch: $current_branch"
        return 0
    fi

    git -C "$PROJECT_DIR" checkout -b "$branch_name"
    log "Created branch: $branch_name"

    emit_event "phase_change" "{\"from\": \"planning\", \"to\": \"development\", \"cycle\": 1}"
    update_continuity "Development" "1" "N/A"
}

stage_execute_tasks() {
    log "═══ Stage 3: Execute Tasks (RARV) ═══"

    if $DRY_RUN; then
        log "[dry-run] Would execute tasks via Claude Code RARV cycles"
        return 0
    fi

    local task_count
    task_count=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(len(d['tasks']))")

    local cycle=1
    for i in $(seq 0 $((task_count - 1))); do
        local task_id task_title task_status task_phase task_desc
        task_id=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['tasks'][$i]['id'])")
        task_title=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['tasks'][$i]['title'])")
        task_status=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['tasks'][$i]['status'])")
        task_phase=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['tasks'][$i]['phase'])")
        task_desc=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['tasks'][$i]['description'])")

        # Skip completed tasks (resume support)
        if [[ "$task_status" == "done" ]]; then
            log "Skipping $task_id (already done): $task_title"
            continue
        fi

        log "── RARV Cycle $cycle: $task_id — $task_title [$task_phase] ──"
        update_status "Development" "$task_id: $task_title" "Cycle $cycle of $task_count"
        update_continuity "Development" "$cycle" "pending"

        # Mark task in-progress
        python3 -c "
import json
d = json.load(open('$TASKS_FILE'))
d['tasks'][$i]['status'] = 'in_progress'
json.dump(d, open('$TASKS_FILE', 'w'), indent=2)
"

        # ── REASON ──
        log "  [REASON] Analyzing: $task_desc"

        # ── ACT ──
        log "  [ACT] Executing task via Claude Code..."

        local prompt="Execute this development task for the electricity-optimizer project:

TASK: $task_title
DESCRIPTION: $task_desc
PHASE: $task_phase

CONSTRAINTS (from PRD):
$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(chr(10).join('- ' + c for c in d.get('constraints', [])))")

INSTRUCTIONS:
1. Implement the changes described above
2. Follow existing code patterns in the codebase
3. Add tests for any new code (>=80% coverage)
4. Commit with a descriptive message
5. Do NOT push — the orchestrator handles that

CRITICAL REMINDERS:
- Use .venv/bin/python -m pytest for backend tests
- DB endpoint is ep-withered-morning (us-east-1), NOT Neon MCP
- conftest.py mock_sqlalchemy_select: add new model fields to patch list
- All PKs use UUID type; GRANTs use neondb_owner role
- Region enum in backend/models/region.py (50 states + DC + intl)
"

        if command -v claude &>/dev/null; then
            echo "$prompt" | claude --dangerously-skip-permissions 2>>"$LOG_FILE" || {
                log "  [ACT] Claude Code execution returned non-zero (may be partial success)"
            }
        else
            log "  [ACT] ERROR: claude CLI not found — skipping execution"
            log "  [ACT] Manual action required for: $task_title"
        fi

        # ── REFLECT ──
        log "  [REFLECT] Checking git status..."
        local changes
        changes=$(git -C "$PROJECT_DIR" status --porcelain | wc -l | tr -d ' ')
        log "  [REFLECT] $changes file(s) changed"

        # ── VERIFY ──
        log "  [VERIFY] Running verification gate..."
        local verify_passed=true
        if ! "$SCRIPTS_DIR/loki-verify.sh" --quick --task="$task_id"; then
            verify_passed=false
            log "  [VERIFY] FAILED — will retry or flag for review"
        fi

        # Mark task done or failed
        if $verify_passed; then
            python3 -c "
import json
d = json.load(open('$TASKS_FILE'))
d['tasks'][$i]['status'] = 'done'
json.dump(d, open('$TASKS_FILE', 'w'), indent=2)
"
            emit_event "task_complete" "{\"task\": \"$task_id\", \"title\": \"$task_title\", \"cycle\": $cycle}"
            log "  ✓ $task_id COMPLETE"
        else
            python3 -c "
import json
d = json.load(open('$TASKS_FILE'))
d['tasks'][$i]['status'] = 'failed'
json.dump(d, open('$TASKS_FILE', 'w'), indent=2)
"
            emit_event "verification_fail" "{\"task\": \"$task_id\", \"title\": \"$task_title\", \"cycle\": $cycle, \"details\": \"Quick verification failed\"}"
            log "  ✗ $task_id FAILED — flagged for review"
        fi

        update_continuity "Development" "$cycle" "$(if $verify_passed; then echo "pass"; else echo "fail"; fi)"
        cycle=$((cycle + 1))

        # Process events + board sync between tasks
        process_events
    done
}

stage_final_verification() {
    log "═══ Stage 4: Final Verification ═══"

    if $DRY_RUN; then
        log "[dry-run] Would run full verification"
        return 0
    fi

    update_status "Verification" "Full test suite" "Running..."
    update_continuity "Verification" "final" "running"

    if "$SCRIPTS_DIR/loki-verify.sh" --task="final"; then
        log "Final verification PASSED"
        update_continuity "Verification" "final" "pass"
        return 0
    else
        log "Final verification FAILED"
        update_continuity "Verification" "final" "fail"
        return 1
    fi
}

stage_complete() {
    log "═══ Stage 5: Complete & PR ═══"

    if $DRY_RUN; then
        log "[dry-run] Would push branch and create draft PR"
        return 0
    fi

    local branch_name
    branch_name=$(git -C "$PROJECT_DIR" branch --show-current)
    local title
    title=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['title'])")

    # Push branch
    git -C "$PROJECT_DIR" push -u origin "$branch_name" 2>>"$LOG_FILE"
    log "Pushed branch: $branch_name"

    # Create draft PR
    if command -v gh &>/dev/null; then
        local task_summary
        task_summary=$(python3 -c "
import json
d = json.load(open('$TASKS_FILE'))
for t in d['tasks']:
    mark = '- [x]' if t['status'] == 'done' else '- [ ]'
    print(f\"{mark} {t['id']}: {t['title']}\")
")
        local pr_url
        pr_url=$(cd "$PROJECT_DIR" && gh pr create \
            --draft \
            --title "feat: $title" \
            --body "## Summary

Automated feature development via Loki Mode RARV orchestrator.

**PRD Source:** \`$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['source'])")\`

## Tasks

$task_summary

## Verification
- Full test suite: PASSED
- Board sync: Triggered

---
Generated by Loki Mode v5.53.0 (RARV Autonomous Orchestrator)" 2>>"$LOG_FILE")
        log "Draft PR created: $pr_url"
    else
        log "gh CLI not available — push succeeded, create PR manually"
    fi

    emit_event "cycle_complete" "{\"title\": \"$title\", \"branch\": \"$branch_name\", \"outcome\": \"success\"}"
    update_continuity "Complete" "final" "pass"
    update_status "Complete" "$title" "Draft PR created"

    # Final board sync
    trigger_board_sync

    log "═══ Pipeline complete ═══"
}

# ─── Main ───────────────────────────────────────────────────────────

main() {
    log ""
    log "╔═══════════════════════════════════════════════════════════╗"
    log "║  Loki Feature Pipeline — Automated Development from Spec ║"
    log "╚═══════════════════════════════════════════════════════════╝"
    log ""

    if [[ -z "$PRD_FILE" && "$RESUME" == false ]]; then
        echo "Usage: scripts/loki-feature.sh <prd-file> [--dry-run] [--resume]"
        echo ""
        echo "  <prd-file>    Path to PRD markdown file (.loki/prds/)"
        echo "  --dry-run     Show plan without executing"
        echo "  --resume      Resume from last checkpoint"
        echo "  --status      Show current pipeline state"
        echo ""
        echo "PRD template: .loki/prd-template.md"
        exit 1
    fi

    # Resume from checkpoint
    if $RESUME; then
        if [[ ! -f "$TASKS_FILE" ]]; then
            log "Error: No checkpoint found. Start a new pipeline with a PRD file."
            exit 1
        fi
        PRD_FILE=$(python3 -c "import json; d=json.load(open('$TASKS_FILE')); print(d['source'])")
        log "Resuming pipeline from checkpoint..."
        stage_execute_tasks
    else
        stage_decompose
        stage_branch
        stage_execute_tasks
    fi

    if stage_final_verification; then
        stage_complete
    else
        log "Pipeline stopped: final verification failed. Fix issues and run with --resume."
        exit 1
    fi
}

main
