#!/usr/bin/env bash
# verify-track-completion.sh — Validate conductor track completion status
#
# Usage:
#   scripts/verify-track-completion.sh <track-id>
#   scripts/verify-track-completion.sh perf-optimization_20260316
#   scripts/verify-track-completion.sh --help
#   scripts/verify-track-completion.sh --dry-run perf-optimization_20260316
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONDUCTOR_DIR="$PROJECT_DIR/conductor/tracks"

# ── Parse args ────────────────────────────────────────────────────────
DRY_RUN=false
TRACK_ID=""

for arg in "$@"; do
    case "$arg" in
        --help|-h)
            echo "Usage: scripts/verify-track-completion.sh [--dry-run] <track-id>"
            echo ""
            echo "Validates conductor track completion by counting checkboxes in plan.md"
            echo "and comparing with metadata.json."
            echo ""
            echo "Options:"
            echo "  --dry-run   Show what files would be checked"
            echo "  --help      Show this help message"
            echo ""
            echo "Exit codes:"
            echo "  0 = all tasks complete, metadata matches"
            echo "  1 = incomplete tasks or metadata mismatch"
            echo "  2 = file not found"
            exit 0
            ;;
        --dry-run)
            DRY_RUN=true
            ;;
        *)
            TRACK_ID="$arg"
            ;;
    esac
done

if [[ -z "$TRACK_ID" ]]; then
    echo "Error: track ID required. Run with --help for usage."
    exit 2
fi

TRACK_DIR="$CONDUCTOR_DIR/$TRACK_ID"
PLAN_FILE="$TRACK_DIR/plan.md"
META_FILE="$TRACK_DIR/metadata.json"

# ── Validate files exist ─────────────────────────────────────────────
if [[ ! -d "$TRACK_DIR" ]]; then
    echo "Error: track directory not found: $TRACK_DIR"
    exit 2
fi

if [[ ! -f "$PLAN_FILE" ]]; then
    echo "Error: plan.md not found: $PLAN_FILE"
    exit 2
fi

# ── Dry run ───────────────────────────────────────────────────────────
if $DRY_RUN; then
    echo "[dry-run] Would check:"
    echo "  Plan: $PLAN_FILE"
    echo "  Metadata: $META_FILE"
    exit 0
fi

# ── Count checkboxes ─────────────────────────────────────────────────
total_complete=0
total_incomplete=0
total_in_progress=0
current_phase=""
phase_results=()

while IFS= read -r line; do
    # Detect phase headers
    if echo "$line" | grep -qE '^## Phase [0-9]+'; then
        if [[ -n "$current_phase" ]]; then
            phase_total=$((phase_complete + phase_incomplete + phase_in_progress))
            if (( phase_total > 0 )); then
                status_extra=""
                if (( phase_in_progress > 0 )); then
                    status_extra=" ($phase_in_progress in-progress)"
                fi
                phase_results+=("  $current_phase: $phase_complete/$phase_total tasks complete$status_extra")
            fi
        fi
        current_phase=$(echo "$line" | sed 's/^## //')
        phase_complete=0
        phase_incomplete=0
        phase_in_progress=0
    fi

    # Count checkboxes (task lines start with - [ ], - [x], or - [~])
    if echo "$line" | grep -qE '^\s*- \[x\]'; then
        total_complete=$((total_complete + 1))
        phase_complete=$((phase_complete + 1))
    elif echo "$line" | grep -qE '^\s*- \[~\]'; then
        total_in_progress=$((total_in_progress + 1))
        phase_in_progress=$((phase_in_progress + 1))
    elif echo "$line" | grep -qE '^\s*- \[ \]'; then
        total_incomplete=$((total_incomplete + 1))
        phase_incomplete=$((phase_incomplete + 1))
    fi
done < "$PLAN_FILE"

# Flush last phase
if [[ -n "$current_phase" ]]; then
    phase_total=$((phase_complete + phase_incomplete + phase_in_progress))
    if (( phase_total > 0 )); then
        status_extra=""
        if (( phase_in_progress > 0 )); then
            status_extra=" ($phase_in_progress in-progress)"
        fi
        phase_results+=("  $current_phase: $phase_complete/$phase_total tasks complete$status_extra")
    fi
fi

total=$((total_complete + total_incomplete + total_in_progress))

# ── Print results ────────────────────────────────────────────────────
echo "Track: $TRACK_ID"
echo ""

for result in "${phase_results[@]}"; do
    echo "$result"
done

echo ""
echo "Total: $total_complete/$total tasks complete"

if (( total_in_progress > 0 )); then
    echo "In progress: $total_in_progress"
fi
if (( total_incomplete > 0 )); then
    echo "Incomplete: $total_incomplete"
fi

# ── Validate metadata ───────────────────────────────────────────────
exit_code=0

if [[ -f "$META_FILE" ]]; then
    meta_completed=$(python3 -c "import json; d=json.load(open('$META_FILE')); print(d.get('tasks',{}).get('completed',0))" 2>/dev/null || echo "?")
    meta_total=$(python3 -c "import json; d=json.load(open('$META_FILE')); print(d.get('tasks',{}).get('total',0))" 2>/dev/null || echo "?")

    if [[ "$meta_completed" != "?" && "$meta_completed" != "$total_complete" ]]; then
        echo ""
        echo "WARNING: metadata.json says $meta_completed completed but plan.md has $total_complete checked"
        exit_code=1
    fi

    if [[ "$meta_total" != "?" && "$meta_total" != "$total" ]]; then
        echo "WARNING: metadata.json says $meta_total total but plan.md has $total tasks"
        exit_code=1
    fi
else
    echo ""
    echo "NOTE: metadata.json not found, skipping validation"
fi

if (( total_incomplete > 0 )); then
    exit_code=1
fi

exit $exit_code
