#!/usr/bin/env bash
# continuous-verify.sh — PostToolUse hook for Edit|Write|MultiEdit
#
# Smart continuous verification trigger. Runs verification during development
# using thresholds to avoid test-spam. NEVER blocks — always exits 0.

set -uo pipefail

FILE_PATH="${1:-}"
REPO_ROOT="/Users/devinmcgrath/projects/electricity-optimizer"
STATE_DIR="$REPO_ROOT/.claude/state"
COUNTER_FILE="$STATE_DIR/edit-counter"
COOLDOWN_FILE="$STATE_DIR/post-task-cooldown"
LOG_FILE="$REPO_ROOT/.claude/logs/orchestration-hooks.log"
PI_FAILURES="$REPO_ROOT/.project-intelligence/signals/QUALITY_GATE_FAILURES.log"
VERIFY_SCRIPT="$REPO_ROOT/scripts/loki-verify.sh"
SUMMARY_LOG="$REPO_ROOT/.claude/logs/verification-summary.log"
MIN_EDITS=3
MIN_SECONDS=60

mkdir -p "$STATE_DIR" "$(dirname "$LOG_FILE")" "$(dirname "$SUMMARY_LOG")"

log() { echo "[$(date '+%H:%M:%S')] [continuous-verify] $*" >> "$LOG_FILE"; }

# ── 1. Increment edit counter ─────────────────────────────────────────
current_count=0
[[ -f "$COUNTER_FILE" ]] && current_count=$(cat "$COUNTER_FILE" 2>/dev/null || echo "0")
current_count=$((current_count + 1))
echo "$current_count" > "$COUNTER_FILE"

# Track edit categories (for logging, no longer gates verification)
CATEGORY_FILE="$STATE_DIR/edit-categories"
if [[ -n "$FILE_PATH" ]]; then
    if echo "$FILE_PATH" | grep -q "backend/"; then
        echo "backend" >> "$CATEGORY_FILE"
    elif echo "$FILE_PATH" | grep -q "frontend/"; then
        echo "frontend" >> "$CATEGORY_FILE"
    elif echo "$FILE_PATH" | grep -q "ml/"; then
        echo "ml" >> "$CATEGORY_FILE"
    fi
fi

# ── 2. Check edit threshold ──────────────────────────────────────────
if (( current_count < MIN_EDITS )); then
    exit 0
fi

# ── 3. Check cooldown ────────────────────────────────────────────────
if [[ -f "$COOLDOWN_FILE" ]]; then
    last_run=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo "0")
    now=$(date +%s)
    elapsed=$((now - last_run))
    if (( elapsed < MIN_SECONDS )); then
        exit 0
    fi
fi

# ── 4. Cross-category no longer required — any 3 edits trigger verification

# ── 5. Threshold met — run quick verification in background ──────────
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"

run_fallback_verify() {
    local failures=0
    if ! "$VENV_PYTHON" -m pytest "$REPO_ROOT/backend/tests/" -q --tb=short --timeout=60 2>&1; then
        failures=$((failures + 1))
    fi
    if ! (cd "$REPO_ROOT/frontend" && npx jest --silent 2>&1); then
        failures=$((failures + 1))
    fi
    return $failures
}

log "Threshold met ($current_count edits) — triggering quick verification"

{
    verify_result=0
    if [[ -x "$VERIFY_SCRIPT" ]]; then
        if ! "$VERIFY_SCRIPT" --quick 2>&1; then
            verify_result=1
        fi
    else
        log "loki-verify.sh not found, falling back to direct test execution"
        if ! run_fallback_verify 2>&1; then
            verify_result=1
        fi
    fi

    if [[ $verify_result -eq 0 ]]; then
        log "Continuous verification PASSED"
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] PASS ($current_count edits)" >> "$SUMMARY_LOG" 2>/dev/null || true
    else
        log "Continuous verification FAILED"
        echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] FAIL ($current_count edits)" >> "$SUMMARY_LOG" 2>/dev/null || true
        if [[ -d "$(dirname "$PI_FAILURES")" ]]; then
            echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] QUALITY_GATE_FAILURE: continuous verify failed after $current_count edits" >> "$PI_FAILURES" 2>/dev/null || true
        fi
    fi
} &

# ── 6. Reset counter + cooldown ──────────────────────────────────────
echo "0" > "$COUNTER_FILE"
date +%s > "$COOLDOWN_FILE"
: > "$CATEGORY_FILE" 2>/dev/null || true

exit 0
