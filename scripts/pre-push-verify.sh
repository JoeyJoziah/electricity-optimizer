#!/usr/bin/env bash
# pre-push-verify.sh — Pre-push gate that blocks pushes when tests fail
#
# Usage:
#   scripts/pre-push-verify.sh              # Run quick verification
#   scripts/pre-push-verify.sh --dry-run    # Show what would run
#   scripts/pre-push-verify.sh --help       # Show usage
#   SKIP_VERIFY=1 git push                  # Bypass verification
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERIFY_SCRIPT="$PROJECT_DIR/scripts/loki-verify.sh"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

# ── Parse args ────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --help|-h)
            echo "Usage: scripts/pre-push-verify.sh [--dry-run] [--help]"
            echo ""
            echo "Pre-push gate that runs quick tests before allowing git push."
            echo "Set SKIP_VERIFY=1 to bypass."
            echo ""
            echo "Options:"
            echo "  --dry-run   Show what would run without running it"
            echo "  --help      Show this help message"
            exit 0
            ;;
        --dry-run)
            DRY_RUN=true
            ;;
    esac
done
DRY_RUN="${DRY_RUN:-false}"

# ── Skip check ────────────────────────────────────────────────────────
if [[ "${SKIP_VERIFY:-0}" == "1" ]]; then
    echo "Skipping pre-push verification (SKIP_VERIFY=1)"
    exit 0
fi

echo "Running pre-push verification..."

# ── Dry run ───────────────────────────────────────────────────────────
if $DRY_RUN; then
    if [[ -x "$VERIFY_SCRIPT" ]]; then
        echo "[dry-run] Would run: $VERIFY_SCRIPT --quick"
    else
        echo "[dry-run] loki-verify.sh not found, would run:"
        echo "  $VENV_PYTHON -m pytest backend/tests/ -q --tb=short"
        echo "  cd frontend && npx jest --silent"
    fi
    exit 0
fi

# ── Run verification ─────────────────────────────────────────────────
run_fallback() {
    local failures=0

    echo "Running backend tests..."
    if ! "$VENV_PYTHON" -m pytest "$PROJECT_DIR/backend/tests/" -q --tb=short 2>&1; then
        failures=$((failures + 1))
    fi

    echo "Running frontend tests..."
    if ! (cd "$PROJECT_DIR/frontend" && npx jest --silent 2>&1); then
        failures=$((failures + 1))
    fi

    return $failures
}

if [[ -x "$VERIFY_SCRIPT" ]]; then
    if "$VERIFY_SCRIPT" --quick; then
        echo "Pre-push verification passed"
        exit 0
    else
        echo ""
        echo "Push blocked — tests failing."
        echo "Fix the failing tests, or run: SKIP_VERIFY=1 git push"
        exit 1
    fi
else
    echo "loki-verify.sh not found, falling back to direct test execution..."
    if run_fallback; then
        echo "Pre-push verification passed"
        exit 0
    else
        echo ""
        echo "Push blocked — tests failing."
        echo "Fix the failing tests, or run: SKIP_VERIFY=1 git push"
        exit 1
    fi
fi
