#!/usr/bin/env bash
# session-end-orchestration.sh — Full orchestration shutdown
# Runs on session Stop event. Handles:
#   1. Loki memory consolidation
#   2. Loki event bus drain
#   3. Claude Flow state persist + metrics export
#   4. Board sync final drain
#   5. Cross-system memory sync
#   6. Marker cleanup

set -uo pipefail

REPO_ROOT="/Users/devinmcgrath/projects/electricity-optimizer"
LOG_DIR="$REPO_ROOT/.claude/logs"
LOG_FILE="$LOG_DIR/orchestration-shutdown.log"
LOKI_DIR="$REPO_ROOT/.loki"

mkdir -p "$LOG_DIR"

log() {
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] $*" >> "$LOG_FILE"
}

log "=== Session shutdown starting ==="

# 1. Loki memory consolidation
if command -v loki &>/dev/null && [[ -d "$LOKI_DIR" ]]; then
    PYTHONPATH="$HOME/.claude/skills/loki-mode" loki memory consolidate 2>/dev/null && \
        log "Loki memory consolidated" || \
        log "WARN: Loki memory consolidation skipped"
fi

# 2. Drain Loki event bus
event_sync="$REPO_ROOT/.claude/hooks/board-sync/loki-event-sync.sh"
if [[ -x "$event_sync" ]]; then
    "$event_sync" 2>/dev/null && \
        log "Loki events drained" || \
        log "WARN: Loki event drain failed"
fi

# 3. Claude Flow state persist + SONA metrics export
if command -v npx &>/dev/null; then
    npx claude-flow hooks session-end --saveState true --exportMetrics true 2>/dev/null && \
        log "Claude Flow state persisted" || \
        log "WARN: Claude Flow persist failed"

    # Export hooks intelligence metrics (SONA: Self-Organizing Neural Architecture)
    metrics_dir="$REPO_ROOT/.claude-flow/logs"
    mkdir -p "$metrics_dir"
    npx claude-flow hooks metrics --format json > "$metrics_dir/sona-metrics-$(date +%Y%m%d_%H%M%S).json" 2>/dev/null && \
        log "SONA metrics exported" || \
        log "WARN: SONA metrics export failed (non-critical)"
fi

# 4. Board sync final drain
sync_script="$REPO_ROOT/.claude/hooks/board-sync/sync-boards.sh"
if [[ -x "$sync_script" ]]; then
    "$sync_script" drain --force 2>/dev/null && \
        log "Board sync drained" || \
        log "WARN: Board sync drain failed"
fi

# 5. Cross-system memory sync: push Loki learnings to Claude Flow
if command -v npx &>/dev/null && [[ -d "$LOKI_DIR/learning" ]]; then
    # Count learning signals
    local_signals=$(find "$LOKI_DIR/learning" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
    if (( local_signals > 0 )); then
        npx claude-flow memory store \
            -k "loki_session_learnings_$(date +%Y%m%d_%H%M%S)" \
            -v "Session ended with $local_signals learning signals in .loki/learning/" \
            --namespace project 2>/dev/null && \
            log "Loki learnings synced to Claude Flow ($local_signals signals)" || \
            log "WARN: Loki->Claude Flow sync failed"
    fi
fi

# 6. Cleanup markers
rm -f /tmp/claude-orchestration-active 2>/dev/null
rm -f /tmp/claude-session-init-marker 2>/dev/null

log "=== Session shutdown complete ==="
exit 0
