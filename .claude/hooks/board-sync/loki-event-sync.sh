#!/usr/bin/env bash
# loki-event-sync.sh — Bridge Loki Mode events to the board sync system
# Watches .loki/events/pending/ for new event files and dispatches actions
# based on event type:
#   task_complete     -> trigger board sync (GitHub Projects + Notion)
#   phase_change      -> log phase transition
#   verification_fail -> create GitHub issue with labels
#   cycle_complete    -> trigger memory persist via claude-flow
#
# Usage:
#   loki-event-sync.sh              Process all pending events once
#   loki-event-sync.sh --watch      Poll for new events (2s interval)
#   loki-event-sync.sh --dry-run    Show what would happen without acting

set -uo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [[ -z "$REPO_ROOT" ]]; then
    echo "[loki-event-sync] Not inside a git repository, aborting." >&2
    exit 1
fi

LOKI_DIR="$REPO_ROOT/.loki"
PENDING_DIR="$LOKI_DIR/events/pending"
ARCHIVE_DIR="$LOKI_DIR/events/archive"
CLAUDE_DIR="$REPO_ROOT/.claude"
SYNC_SCRIPT="$CLAUDE_DIR/hooks/board-sync/sync-boards.sh"
LOG_FILE="$CLAUDE_DIR/logs/loki-board-sync.log"
CONFIG_FILE="$REPO_ROOT/.notion_sync_config.json"
POLL_INTERVAL=2

# Ensure required directories exist
mkdir -p "$(dirname "$LOG_FILE")" "$ARCHIVE_DIR"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] $*" >> "$LOG_FILE"
}

die() {
    echo "[loki-event-sync] $*" >&2
    log "ERROR: $*"
    exit 1
}

json_field() {
    local file="$1" field="$2"
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get(sys.argv[2],''))" "$file" "$field" 2>/dev/null || echo ""
}

json_payload_field() {
    local file="$1" field="$2"
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('payload',{}).get(sys.argv[2],''))" "$file" "$field" 2>/dev/null || echo ""
}

get_repo_name() {
    if [[ -f "$CONFIG_FILE" ]] && command -v python3 &>/dev/null; then
        python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('github',{}).get('repo_full_name',''))" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

archive_event() {
    local event_file="$1"
    local basename
    basename="$(basename "$event_file")"
    mv "$event_file" "$ARCHIVE_DIR/$basename" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

handle_task_complete() {
    local event_file="$1"
    local task_desc
    task_desc="$(json_payload_field "$event_file" "task")"
    [[ -z "$task_desc" ]] && task_desc="$(json_payload_field "$event_file" "description")"

    log "task_complete: $task_desc"

    if [[ -x "$SYNC_SCRIPT" ]]; then
        log "Triggering board sync (drain --bg)"
        "$SYNC_SCRIPT" drain --bg 2>/dev/null || true
    else
        log "WARN: sync-boards.sh not found or not executable, skipping board sync"
    fi
}

handle_phase_change() {
    local event_file="$1"
    local from_phase to_phase cycle
    from_phase="$(json_payload_field "$event_file" "from")"
    to_phase="$(json_payload_field "$event_file" "to")"
    cycle="$(json_payload_field "$event_file" "cycle")"

    log "phase_change: ${from_phase:-unknown} -> ${to_phase:-unknown} (cycle ${cycle:-?})"

    local continuity_file="$LOKI_DIR/CONTINUITY.md"
    if [[ -n "$to_phase" && -f "$continuity_file" ]] && command -v sed &>/dev/null; then
        sed -i '' "s/^- Phase: .*$/- Phase: $to_phase/" "$continuity_file" 2>/dev/null || true
        if [[ -n "$cycle" ]]; then
            sed -i '' "s/^- RARV Cycle: .*$/- RARV Cycle: $cycle/" "$continuity_file" 2>/dev/null || true
        fi
        log "Updated CONTINUITY.md with phase=$to_phase cycle=$cycle"
    fi
}

handle_verification_fail() {
    local event_file="$1"
    local summary phase details cycle
    summary="$(json_payload_field "$event_file" "summary")"
    phase="$(json_payload_field "$event_file" "phase")"
    details="$(json_payload_field "$event_file" "details")"
    cycle="$(json_payload_field "$event_file" "cycle")"

    [[ -z "$summary" ]] && summary="Loki verification failure"

    log "verification_fail: $summary (phase=${phase:-unknown}, cycle=${cycle:-?})"

    if ! command -v gh &>/dev/null; then
        log "WARN: gh CLI not found, cannot create GitHub issue"
        return 0
    fi

    local repo_name
    repo_name="$(get_repo_name)"
    if [[ -z "$repo_name" ]]; then
        log "WARN: repo_full_name not configured, cannot create GitHub issue"
        return 0
    fi

    local title="[Loki] Verification failure: $summary"
    local body
    body="$(cat <<BODY_EOF
## Loki Verification Failure

**Phase:** ${phase:-unknown}
**RARV Cycle:** ${cycle:-unknown}
**Timestamp:** $(json_field "$event_file" "timestamp")
**Event ID:** $(json_field "$event_file" "id")

### Summary
$summary

### Details
${details:-No additional details provided.}

---
*Auto-created by \`loki-event-sync.sh\` from Loki Mode event bus.*
BODY_EOF
)"

    local issue_url
    issue_url="$(gh issue create \
        --repo "$repo_name" \
        --title "$title" \
        --body "$body" \
        --label "bug,loki" 2>&1)" || true

    if [[ "$issue_url" == http* ]]; then
        log "Created GitHub issue: $issue_url"
    else
        log "WARN: Failed to create GitHub issue: $issue_url"
    fi
}

handle_cycle_complete() {
    local event_file="$1"
    local cycle outcome
    cycle="$(json_payload_field "$event_file" "cycle")"
    outcome="$(json_payload_field "$event_file" "outcome")"

    log "cycle_complete: cycle=${cycle:-?} outcome=${outcome:-unknown}"

    # Trigger memory persist via claude-flow if available
    if command -v npx &>/dev/null; then
        log "Triggering memory persist via claude-flow"
        npx claude-flow memory store \
            "loki/cycle/$cycle" \
            "{\"cycle\":\"$cycle\",\"outcome\":\"$outcome\",\"timestamp\":\"$(date -u '+%Y-%m-%dT%H:%M:%SZ')\"}" \
            --namespace coordination 2>>"$LOG_FILE" || {
            log "WARN: claude-flow memory persist failed"
        }
    fi

    # Trigger a full board sync since a cycle represents significant progress
    if [[ -x "$SYNC_SCRIPT" ]]; then
        log "Triggering full board sync after cycle complete"
        "$SYNC_SCRIPT" all --force --bg 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# Event dispatcher
# ---------------------------------------------------------------------------
process_event() {
    local event_file="$1"
    local dry_run="${2:-false}"

    if [[ ! -f "$event_file" ]]; then
        return 0
    fi

    local event_type
    event_type="$(json_field "$event_file" "type")"

    if [[ -z "$event_type" ]]; then
        log "WARN: Skipping event with no type: $(basename "$event_file")"
        archive_event "$event_file"
        return 0
    fi

    if [[ "$dry_run" == true ]]; then
        echo "[loki-event-sync] Would process: $(basename "$event_file") (type=$event_type)"
        return 0
    fi

    case "$event_type" in
        task_complete)
            handle_task_complete "$event_file"
            ;;
        phase_change)
            handle_phase_change "$event_file"
            ;;
        verification_fail)
            handle_verification_fail "$event_file"
            ;;
        cycle_complete)
            handle_cycle_complete "$event_file"
            ;;
        *)
            log "Ignoring unhandled event type: $event_type ($(basename "$event_file"))"
            ;;
    esac

    archive_event "$event_file"
}

# ---------------------------------------------------------------------------
# Process all pending events
# ---------------------------------------------------------------------------
process_all_pending() {
    local dry_run="${1:-false}"
    local count=0

    if [[ ! -d "$PENDING_DIR" ]]; then
        log "No pending directory found at $PENDING_DIR"
        return 0
    fi

    for event_file in "$PENDING_DIR"/*.json; do
        [[ -f "$event_file" ]] || continue
        process_event "$event_file" "$dry_run"
        count=$((count + 1))
    done

    if (( count > 0 )); then
        log "Processed $count pending event(s)"
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Watch mode (poll-based)
# ---------------------------------------------------------------------------
watch_events() {
    local dry_run="${1:-false}"
    log "Starting watch mode (poll interval: ${POLL_INTERVAL}s)"
    echo "[loki-event-sync] Watching $PENDING_DIR for events (Ctrl+C to stop)..."

    while true; do
        process_all_pending "$dry_run"
        sleep "$POLL_INTERVAL"
    done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local watch=false
    local dry_run=false

    for arg in "$@"; do
        case "$arg" in
            --watch)   watch=true ;;
            --dry-run) dry_run=true ;;
            -h|--help)
                echo "Usage: loki-event-sync.sh [--watch] [--dry-run]"
                echo ""
                echo "  --watch    Poll for new events continuously"
                echo "  --dry-run  Show what would happen without acting"
                return 0
                ;;
            *) die "Unknown argument: $arg" ;;
        esac
    done

    log "=== loki-event-sync started (watch=$watch, dry_run=$dry_run) ==="

    if [[ "$watch" == true ]]; then
        watch_events "$dry_run"
    else
        process_all_pending "$dry_run"
    fi

    log "=== loki-event-sync finished ==="
}

main "$@"
