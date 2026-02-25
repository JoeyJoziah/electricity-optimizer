#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# loki-verify.sh — Verification orchestrator for Loki RARV cycles
#
# Runs the full test/lint/coverage gate and emits pass/fail events.
# Called by loki-feature.sh after each task, or standalone.
#
# Usage:
#   scripts/loki-verify.sh                  # Full verification
#   scripts/loki-verify.sh --quick          # Backend + frontend tests only
#   scripts/loki-verify.sh --backend-only   # Backend tests only
#   scripts/loki-verify.sh --dry-run        # Show what would run
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOKI_DIR="$PROJECT_DIR/.loki"
EVENTS_DIR="$LOKI_DIR/events/pending"
LOG_FILE="$PROJECT_DIR/.claude/logs/loki-verify.log"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

# Parse args
MODE="full"
DRY_RUN=false
TASK_ID=""
for arg in "$@"; do
    case "$arg" in
        --quick)        MODE="quick" ;;
        --backend-only) MODE="backend" ;;
        --dry-run)      DRY_RUN=true ;;
        --task=*)       TASK_ID="${arg#--task=}" ;;
    esac
done

# Ensure dirs exist
mkdir -p "$EVENTS_DIR" "$(dirname "$LOG_FILE")"

log() {
    local msg="[$(date +%H:%M:%S)] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

emit_event() {
    local event_type="$1"
    local payload="$2"
    local event_id="verify-$(date +%s)-$$"
    local event_file="$EVENTS_DIR/${event_id}.json"

    cat > "$event_file" <<EVTJSON
{
  "id": "$event_id",
  "type": "$event_type",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "payload": $payload
}
EVTJSON
    log "Emitted event: $event_type -> $(basename "$event_file")"
}

# ─── Test runners ───────────────────────────────────────────────────

run_backend_tests() {
    log "Running backend tests..."
    if $DRY_RUN; then
        log "  [dry-run] $VENV_PYTHON -m pytest backend/tests/ -q --tb=short"
        return 0
    fi

    local output
    if output=$("$VENV_PYTHON" -m pytest backend/tests/ -q --tb=short 2>&1); then
        local count
        count=$(echo "$output" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo "0")
        log "Backend tests PASSED ($count tests)"
        echo "$count"
        return 0
    else
        log "Backend tests FAILED"
        echo "$output" | tail -20 >> "$LOG_FILE"
        return 1
    fi
}

run_frontend_tests() {
    log "Running frontend tests..."
    if $DRY_RUN; then
        log "  [dry-run] npx jest --silent (in frontend/)"
        return 0
    fi

    local output
    if output=$(cd "$PROJECT_DIR/frontend" && npx jest --silent 2>&1); then
        local count
        count=$(echo "$output" | grep -oE '[0-9]+ passed' | head -1 | grep -oE '[0-9]+' || echo "0")
        local suites
        suites=$(echo "$output" | grep -oE '[0-9]+ passed' | tail -1 | grep -oE '[0-9]+' || echo "0")
        log "Frontend tests PASSED ($count tests, $suites suites)"
        echo "$count"
        return 0
    else
        log "Frontend tests FAILED"
        echo "$output" | tail -20 >> "$LOG_FILE"
        return 1
    fi
}

run_ml_tests() {
    log "Running ML tests..."
    if $DRY_RUN; then
        log "  [dry-run] python3 -m pytest ml/tests/ -q --tb=short"
        return 0
    fi

    local output
    if output=$(cd "$PROJECT_DIR" && python3 -m pytest ml/tests/ -q --tb=short 2>&1); then
        local count
        count=$(echo "$output" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo "0")
        log "ML tests PASSED ($count tests)"
        echo "$count"
        return 0
    else
        log "ML tests FAILED"
        echo "$output" | tail -20 >> "$LOG_FILE"
        return 1
    fi
}

run_lint_check() {
    log "Running lint checks..."
    if $DRY_RUN; then
        log "  [dry-run] frontend lint + backend type check"
        return 0
    fi

    local failed=false

    # Frontend lint
    if ! (cd "$PROJECT_DIR/frontend" && npx next lint --quiet 2>/dev/null); then
        log "Frontend lint FAILED"
        failed=true
    fi

    # Backend type check (best-effort, don't fail on mypy)
    if command -v mypy &>/dev/null; then
        if ! ("$VENV_PYTHON" -m mypy backend/ --ignore-missing-imports --no-error-summary 2>/dev/null); then
            log "Backend mypy warnings found (non-blocking)"
        fi
    fi

    if $failed; then
        return 1
    fi
    return 0
}

# ─── Main orchestration ────────────────────────────────────────────

main() {
    log "═══ Loki Verification ($MODE mode) ═══"

    local backend_count=0
    local frontend_count=0
    local ml_count=0
    local failures=0

    # Backend tests (always)
    if ! backend_count=$(run_backend_tests); then
        failures=$((failures + 1))
    fi

    # Frontend tests (full or quick)
    if [[ "$MODE" != "backend" ]]; then
        if ! frontend_count=$(run_frontend_tests); then
            failures=$((failures + 1))
        fi
    fi

    # ML tests + lint (full only)
    if [[ "$MODE" == "full" ]]; then
        if ! ml_count=$(run_ml_tests); then
            failures=$((failures + 1))
        fi

        if ! run_lint_check; then
            failures=$((failures + 1))
        fi
    fi

    # Emit result event
    local task_field=""
    if [[ -n "$TASK_ID" ]]; then
        task_field="\"task\": \"$TASK_ID\","
    fi

    if [[ $failures -eq 0 ]]; then
        log "═══ VERIFICATION PASSED ═══"
        emit_event "verification_pass" "{
            ${task_field}
            \"outcome\": \"pass\",
            \"mode\": \"$MODE\",
            \"backend_tests\": $backend_count,
            \"frontend_tests\": $frontend_count,
            \"ml_tests\": $ml_count
        }"
        return 0
    else
        log "═══ VERIFICATION FAILED ($failures failure(s)) ═══"
        emit_event "verification_fail" "{
            ${task_field}
            \"outcome\": \"fail\",
            \"mode\": \"$MODE\",
            \"failures\": $failures,
            \"details\": \"See $LOG_FILE for details\"
        }"
        return 1
    fi
}

main
