#!/usr/bin/env bash
# post-bash-recovery.sh — PostToolUse hook for Bash tool
#
# Detects Bash failures, classifies errors, suggests recovery actions,
# and stores patterns for prevention. Advisory only — NEVER blocks.
# Always exits 0.

set -uo pipefail

EXIT_CODE="${1:-0}"
COMMAND="${2:-}"
REPO_ROOT="/Users/devinmcgrath/projects/electricity-optimizer"
STATE_DIR="$REPO_ROOT/.claude/state"
PATTERNS_FILE="$STATE_DIR/error-patterns.jsonl"
PI_ESCALATIONS="$REPO_ROOT/.project-intelligence/signals/ESCALATIONS.log"

# Fast exit on success
[[ "$EXIT_CODE" == "0" ]] && exit 0

mkdir -p "$STATE_DIR"

TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# ── Error classification ──────────────────────────────────────────────
classify_error() {
    local cmd="$1"
    local category="unknown"
    local suggestion=""

    case "$cmd" in
        *ModuleNotFoundError*|*"No module named"*|*"Cannot find module"*|*"MODULE_NOT_FOUND"*)
            category="missing-dependency"
            # Extract module name
            local module
            module=$(echo "$cmd" | grep -oE "'[^']+'" | head -1 | tr -d "'")
            if [[ "$cmd" == *python* ]] || [[ "$cmd" == *pytest* ]]; then
                suggestion=".venv/bin/pip install ${module:-<module>}"
            else
                suggestion="npm install ${module:-<module>}"
            fi
            ;;
        *SyntaxError*|*"Unexpected token"*|*"Parse error"*)
            category="syntax-error"
            suggestion="Check syntax at the indicated line"
            ;;
        *FAILED*|*AssertionError*|*"test.*failed"*)
            category="test-failure"
            suggestion="Run failing test in isolation with -v flag"
            ;;
        *"connection refused"*|*OperationalError*|*ECONNREFUSED*|*"Connection reset"*)
            category="infrastructure"
            suggestion="Check if the service/database is running"
            ;;
        *EACCES*|*"Permission denied"*|*"Operation not permitted"*)
            category="permissions"
            suggestion="Check file permissions or use sudo if appropriate"
            ;;
        *"command not found"*|*"not recognized"*)
            category="missing-command"
            local missing_cmd
            missing_cmd=$(echo "$cmd" | grep -oE "[^ ]+: command not found" | cut -d: -f1)
            suggestion="Install ${missing_cmd:-the missing command}"
            ;;
        *"No such file"*|*ENOENT*)
            category="missing-file"
            suggestion="Verify file path exists"
            ;;
    esac

    echo "$category|$suggestion"
}

RESULT=$(classify_error "$COMMAND")
CATEGORY="${RESULT%%|*}"
SUGGESTION="${RESULT#*|}"

# ── Advisory output (stderr, never blocks) ─────────────────────────────
if [[ "$CATEGORY" != "unknown" ]]; then
    echo "[SelfHealing] ERROR ($CATEGORY): exit=$EXIT_CODE" >&2
    if [[ -n "$SUGGESTION" ]]; then
        echo "[SelfHealing] Suggested: $SUGGESTION" >&2
    fi
fi

# ── Pattern storage (non-blocking) ────────────────────────────────────
SAFE_CMD="$(echo "$COMMAND" | tr -d '\n' | sed 's/"/\\"/g' | cut -c1-200)"
echo "{\"ts\":\"$TIMESTAMP\",\"exit\":$EXIT_CODE,\"category\":\"$CATEGORY\",\"command\":\"$SAFE_CMD\",\"suggestion\":\"$SUGGESTION\"}" >> "$PATTERNS_FILE"

# ── Escalation check: same category 3+ times this session ─────────────
if [[ -f "$PATTERNS_FILE" ]]; then
    count=$(grep -c "\"category\":\"$CATEGORY\"" "$PATTERNS_FILE" 2>/dev/null || echo "0")
    if (( count >= 3 )) && [[ -d "$(dirname "$PI_ESCALATIONS")" ]]; then
        echo "[$TIMESTAMP] ESCALATION: $CATEGORY occurred $count times. Last: $SAFE_CMD" >> "$PI_ESCALATIONS" 2>/dev/null || true
        echo "[SelfHealing] ESCALATION: '$CATEGORY' has occurred $count times this session" >&2
    fi
fi

# NOTE: Claude Flow memory persist removed — error patterns are already stored
# locally in $PATTERNS_FILE (error-patterns.jsonl). The CF memory writes were
# never read back (0 access count across 500+ entries) and just created noise.

exit 0
