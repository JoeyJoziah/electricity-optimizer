#!/usr/bin/env bash
# activate-orchestration.sh — Full orchestration ecosystem activation
# Runs ONCE per session (marker-guarded). Initializes:
#   1. Claude Flow daemon + memory
#   2. Loki Mode memory index + event bus
#   3. Board sync health check
#   4. Cross-system memory verification
#
# Called by PreToolUse hook on first tool use of each session.
# Exit 0 always (never block tool execution).

set -uo pipefail

MARKER="/tmp/claude-orchestration-init-$$"
GLOBAL_MARKER="/tmp/claude-orchestration-active"
LOG_DIR="/Users/devinmcgrath/projects/electricity-optimizer/.claude/logs"
LOG_FILE="$LOG_DIR/orchestration-init.log"
REPO_ROOT="/Users/devinmcgrath/projects/electricity-optimizer"

mkdir -p "$LOG_DIR"

# Only run once per session (check both PID-specific and global markers)
if [[ -f "$GLOBAL_MARKER" ]]; then
    exit 0
fi

touch "$GLOBAL_MARKER"

log() {
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] $*" >> "$LOG_FILE"
    echo "[Orchestration] $*" >&2
}

log "=== Session activation starting ==="

# ---------------------------------------------------------------------------
# 1. Claude Flow daemon + memory
# ---------------------------------------------------------------------------
activate_claude_flow() {
    if ! command -v npx &>/dev/null; then
        log "WARN: npx not found, skipping Claude Flow"
        return 0
    fi

    # If MCP server is registered and handling things, skip CLI daemon startup.
    # The MCP server provides the same memory/hooks via tool calls, so a
    # separate daemon process is redundant.
    if npx claude-flow mcp status &>/dev/null 2>&1; then
        log "Claude Flow MCP server active, skipping CLI daemon"
    else
        # Fallback: start daemon via CLI if MCP server isn't running
        npx claude-flow daemon status &>/dev/null || {
            npx claude-flow hooks session-start --startDaemon true --restoreLatest true &>/dev/null || true
            log "Claude Flow daemon started (CLI fallback)"
        }
    fi

    # Verify memory (works via both MCP and CLI paths)
    local entry_count
    entry_count=$(npx claude-flow memory stats 2>/dev/null | grep "Total Entries" | grep -oE "[0-9]+" || echo "0")
    if (( entry_count > 0 )); then
        log "Claude Flow memory: OK ($entry_count entries)"
    else
        log "WARN: Claude Flow memory empty or unavailable"
    fi
}

# ---------------------------------------------------------------------------
# 2. Loki Mode memory + event bus
# ---------------------------------------------------------------------------
activate_loki() {
    local loki_dir="$REPO_ROOT/.loki"

    # Check Loki is installed
    if ! command -v loki &>/dev/null; then
        log "WARN: loki CLI not found"
        return 0
    fi

    local version
    version=$(loki --version 2>/dev/null || echo "unknown")
    log "Loki Mode: $version"

    # Ensure .loki directory exists
    if [[ ! -d "$loki_dir" ]]; then
        log "WARN: .loki/ not found, run 'loki start' to initialize"
        return 0
    fi

    # Rebuild memory index (fast operation)
    if [[ -d "$loki_dir/memory" ]]; then
        PYTHONPATH="$HOME/.claude/skills/loki-mode" python3 -c "
from memory.layers import IndexLayer
layer = IndexLayer('$loki_dir/memory')
layer.update([])
" &>/dev/null && log "Loki memory index: OK" || log "WARN: Loki memory index rebuild failed"
    fi

    # Process any stale pending events from previous sessions
    local event_sync="$REPO_ROOT/.claude/hooks/board-sync/loki-event-sync.sh"
    if [[ -x "$event_sync" ]]; then
        local pending_count
        pending_count=$(ls "$loki_dir/events/pending/"*.json 2>/dev/null | wc -l | tr -d ' ')
        if (( pending_count > 0 )); then
            "$event_sync" &>/dev/null || true
            log "Processed $pending_count stale Loki events"
        else
            log "Loki event bus: clean (no pending events)"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 3. Hooks intelligence bootstrap (one-time per repo)
# ---------------------------------------------------------------------------
bootstrap_hooks_intelligence() {
    if ! command -v npx &>/dev/null; then
        return 0
    fi

    local pretrain_marker="$REPO_ROOT/.claude-flow/.hooks-pretrained"
    if [[ -f "$pretrain_marker" ]]; then
        log "Hooks intelligence: already bootstrapped"
        return 0
    fi

    # One-time pretrain to populate the ReasoningBank from repo history
    npx claude-flow hooks pretrain --directory "$REPO_ROOT" &>/dev/null && {
        mkdir -p "$REPO_ROOT/.claude-flow"
        touch "$pretrain_marker"
        log "Hooks intelligence: bootstrapped (pretrain complete)"
    } || log "WARN: Hooks pretrain failed (non-critical)"
}

# ---------------------------------------------------------------------------
# 4. Board sync health check
# ---------------------------------------------------------------------------
check_board_sync() {
    local sync_script="$REPO_ROOT/.claude/hooks/board-sync/sync-boards.sh"
    if [[ -x "$sync_script" ]]; then
        log "Board sync: operational"
    else
        log "WARN: Board sync script not found or not executable"
    fi
}

# ---------------------------------------------------------------------------
# 5. Report summary
# ---------------------------------------------------------------------------
report_summary() {
    local systems_ok=0
    local systems_total=4

    command -v npx &>/dev/null && npx claude-flow memory stats &>/dev/null && systems_ok=$((systems_ok + 1))
    command -v loki &>/dev/null && systems_ok=$((systems_ok + 1))
    [[ -x "$REPO_ROOT/.claude/hooks/board-sync/sync-boards.sh" ]] && systems_ok=$((systems_ok + 1))
    [[ -f "$REPO_ROOT/.claude-flow/.hooks-pretrained" ]] && systems_ok=$((systems_ok + 1))

    log "=== Activation complete: $systems_ok/$systems_total systems online ==="
}

# Run all activations (background to not block tool execution)
{
    activate_claude_flow
    activate_loki
    bootstrap_hooks_intelligence
    check_board_sync
    report_summary
} &

exit 0
