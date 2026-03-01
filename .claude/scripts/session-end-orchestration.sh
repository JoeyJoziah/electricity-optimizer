#!/usr/bin/env bash
# session-end-orchestration.sh — Full orchestration shutdown
# Runs on session Stop event. Handles:
#   1. Loki memory consolidation
#   2. Loki event bus drain
#   3. Claude Flow state persist + metrics export
#   4. Board sync final drain
#   5. Cross-system memory sync
#   6. SPARC Integration: full verification loop
#   7. SPARC Documenter: codemap staleness audit + session doc summary
#   8. GitHub Actions: trigger notion-sync workflow
#   9. Notion sync: full local sync (TODO.md + GitHub issues/PRs)
#  10. Session summary persist
#  11. Marker cleanup

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

# ---------------------------------------------------------------------------
# 6. SPARC Integration: full verification loop
# ---------------------------------------------------------------------------
verify_script="$REPO_ROOT/scripts/loki-verify.sh"
if [[ -x "$verify_script" ]]; then
    log "Running full verification (SPARC integration)..."
    if verify_output=$("$verify_script" 2>&1); then
        # Extract test counts from output
        backend_count=$(echo "$verify_output" | grep -oE 'Backend tests PASSED \([0-9]+' | grep -oE '[0-9]+' || echo "0")
        frontend_count=$(echo "$verify_output" | grep -oE 'Frontend tests PASSED \([0-9]+' | grep -oE '[0-9]+' || echo "0")
        ml_count=$(echo "$verify_output" | grep -oE 'ML tests PASSED \([0-9]+' | grep -oE '[0-9]+' || echo "0")
        log "SPARC Verification PASSED: backend=$backend_count frontend=$frontend_count ml=$ml_count"

        if command -v npx &>/dev/null; then
            npx claude-flow memory store \
                -k "session_verify_$(date +%Y%m%d_%H%M%S)" \
                -v "Session-end verification PASSED: backend=$backend_count frontend=$frontend_count ml=$ml_count" \
                --namespace project 2>/dev/null || true
        fi
    else
        log "WARN: SPARC Verification FAILED — check $REPO_ROOT/.claude/logs/loki-verify.log"
        if command -v npx &>/dev/null; then
            npx claude-flow memory store \
                -k "session_verify_fail_$(date +%Y%m%d_%H%M%S)" \
                -v "Session-end verification FAILED. Review loki-verify.log for details." \
                --namespace project 2>/dev/null || true
        fi
    fi
else
    log "WARN: loki-verify.sh not found, skipping verification"
fi

# ---------------------------------------------------------------------------
# 7. SPARC Documenter: codemap staleness audit + session doc summary
# ---------------------------------------------------------------------------
audit_docs() {
    log "Running docs staleness audit..."

    # Count current backend endpoints
    local endpoint_count
    endpoint_count=$(grep -r "@router\.\(get\|post\|put\|delete\|patch\)" "$REPO_ROOT/backend/api/" 2>/dev/null | wc -l | tr -d ' ')

    # Count current services
    local service_count
    service_count=$(find "$REPO_ROOT/backend/services" -name "*.py" -not -name "__init__*" -not -name "__pycache__" 2>/dev/null | wc -l | tr -d ' ')

    # Count frontend components
    local component_count
    component_count=$(find "$REPO_ROOT/frontend/components" -name "*.tsx" 2>/dev/null | wc -l | tr -d ' ')

    # Count test files
    local test_count_be
    test_count_be=$(find "$REPO_ROOT/backend/tests" -name "test_*.py" 2>/dev/null | wc -l | tr -d ' ')
    local test_count_fe
    test_count_fe=$(find "$REPO_ROOT/frontend/__tests__" -name "*.test.*" 2>/dev/null | wc -l | tr -d ' ')

    # Session change summary
    local session_edits=0
    local session_tasks=0
    local edits_log="$REPO_ROOT/.claude/logs/session-changes.jsonl"
    local tasks_log="$REPO_ROOT/.claude/logs/session-tasks.jsonl"
    [[ -f "$edits_log" ]] && session_edits=$(wc -l < "$edits_log" | tr -d ' ')
    [[ -f "$tasks_log" ]] && session_tasks=$(wc -l < "$tasks_log" | tr -d ' ')

    # Edited categories this session
    local categories=""
    if [[ -f "$edits_log" ]]; then
        categories=$(python3 -c "
import json, sys
cats = set()
for line in open('$edits_log'):
    try:
        cats.add(json.loads(line)['category'])
    except: pass
print(','.join(sorted(cats)))
" 2>/dev/null || echo "unknown")
    fi

    # Write audit report
    local audit_file="$REPO_ROOT/.claude/state/docs-audit.json"
    mkdir -p "$(dirname "$audit_file")"
    cat > "$audit_file" <<AUDITJSON
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "inventory": {
    "backend_endpoints": $endpoint_count,
    "backend_services": $service_count,
    "frontend_components": $component_count,
    "test_files_backend": $test_count_be,
    "test_files_frontend": $test_count_fe
  },
  "session": {
    "edits": $session_edits,
    "tasks": $session_tasks,
    "categories_touched": "$categories"
  }
}
AUDITJSON

    log "Docs audit: endpoints=$endpoint_count services=$service_count components=$component_count"
    log "Session summary: $session_edits edits, $session_tasks tasks, categories=[$categories]"

    # Persist to memory
    if command -v npx &>/dev/null; then
        npx claude-flow memory store \
            -k "session_docs_audit_$(date +%Y%m%d_%H%M%S)" \
            -v "Session docs audit: ${session_edits} edits, ${session_tasks} tasks. Categories: ${categories}. Inventory: ${endpoint_count} endpoints, ${service_count} services, ${component_count} components, ${test_count_be}+${test_count_fe} test files" \
            --namespace project 2>/dev/null || true
    fi
}

audit_docs

# ---------------------------------------------------------------------------
# 8. GitHub Actions: trigger notion-sync workflow
# ---------------------------------------------------------------------------
if command -v gh &>/dev/null; then
    remote_url=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || echo "")
    if [[ "$remote_url" == *"JoeyJoziah/electricity-optimizer"* ]]; then
        gh workflow run notion-sync.yml -R JoeyJoziah/electricity-optimizer 2>/dev/null && \
            log "Triggered notion-sync.yml GitHub Actions workflow" || \
            log "WARN: Failed to trigger notion-sync workflow"
    else
        log "Not on main repo remote, skipping GH Actions trigger"
    fi
else
    log "WARN: gh CLI not found, skipping GH Actions trigger"
fi

# ---------------------------------------------------------------------------
# 9. Notion sync: full local sync (TODO.md + GitHub issues/PRs)
# ---------------------------------------------------------------------------
run_full_notion_sync() {
    # Check API key
    local api_key_path
    api_key_path=$(python3 -c "
import json, os.path
config = json.load(open('$REPO_ROOT/.notion_sync_config.json'))
print(os.path.expanduser(config['notion']['api_key_path']))
" 2>/dev/null || echo "")

    if [[ -z "$api_key_path" ]] || [[ ! -f "$api_key_path" ]]; then
        log "WARN: Notion API key not found, skipping sync"
        return 0
    fi

    # TODO.md sync
    if [[ -f "$REPO_ROOT/scripts/notion_sync.py" ]]; then
        python3 "$REPO_ROOT/scripts/notion_sync.py" --once 2>/dev/null && \
            log "Notion TODO sync completed" || \
            log "WARN: Notion TODO sync failed"
    fi

    # GitHub → Notion full sync
    if [[ -f "$REPO_ROOT/scripts/github_notion_sync.py" ]]; then
        python3 "$REPO_ROOT/scripts/github_notion_sync.py" --mode full 2>/dev/null && \
            log "Notion GitHub sync completed" || \
            log "WARN: Notion GitHub sync failed"
    fi
}

run_full_notion_sync

# ---------------------------------------------------------------------------
# 10. Session summary persist
# ---------------------------------------------------------------------------
if command -v npx &>/dev/null; then
    session_edits=0
    session_tasks=0
    [[ -f "$REPO_ROOT/.claude/logs/session-changes.jsonl" ]] && \
        session_edits=$(wc -l < "$REPO_ROOT/.claude/logs/session-changes.jsonl" | tr -d ' ')
    [[ -f "$REPO_ROOT/.claude/logs/session-tasks.jsonl" ]] && \
        session_tasks=$(wc -l < "$REPO_ROOT/.claude/logs/session-tasks.jsonl" | tr -d ' ')

    npx claude-flow memory store \
        -k "session_end_$(date +%Y%m%d_%H%M%S)" \
        -v "Session ended: $session_edits edits, $session_tasks task events. Full verification + docs audit + Notion sync completed." \
        --namespace project 2>/dev/null || true
    log "Session summary persisted to Claude Flow memory"
fi

# ---------------------------------------------------------------------------
# 11. Cleanup markers + rotate session logs
# ---------------------------------------------------------------------------
rm -f /tmp/claude-orchestration-active 2>/dev/null
rm -f /tmp/claude-session-init-marker 2>/dev/null
rm -f "$REPO_ROOT/.claude/state/post-task-cooldown" 2>/dev/null

# Archive session logs (move to timestamped files, clear for next session)
archive_ts="$(date +%Y%m%d_%H%M%S)"
for logfile in session-changes.jsonl session-tasks.jsonl; do
    src="$REPO_ROOT/.claude/logs/$logfile"
    if [[ -f "$src" ]] && [[ -s "$src" ]]; then
        archive_dir="$REPO_ROOT/.claude/logs/archive"
        mkdir -p "$archive_dir"
        cp "$src" "$archive_dir/${logfile%.jsonl}-${archive_ts}.jsonl"
        : > "$src"  # truncate for next session
    fi
done

log "=== Session shutdown complete ==="
exit 0
