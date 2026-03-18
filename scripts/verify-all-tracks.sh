#!/usr/bin/env bash
# verify-all-tracks.sh — Run track completion verification for all registered tracks
#
# Usage:
#   scripts/verify-all-tracks.sh           # Check all tracks
#   scripts/verify-all-tracks.sh --help    # Show usage
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TRACKS_FILE="$PROJECT_DIR/conductor/tracks.md"
VERIFY_SCRIPT="$PROJECT_DIR/scripts/verify-track-completion.sh"

# ── Parse args ────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --help|-h)
            echo "Usage: scripts/verify-all-tracks.sh [--help]"
            echo ""
            echo "Runs verify-track-completion.sh for every track in conductor/tracks.md."
            echo "Outputs a summary table."
            exit 0
            ;;
    esac
done

if [[ ! -f "$TRACKS_FILE" ]]; then
    echo "Error: tracks.md not found: $TRACKS_FILE"
    exit 2
fi

if [[ ! -x "$VERIFY_SCRIPT" ]]; then
    echo "Error: verify-track-completion.sh not found or not executable"
    exit 2
fi

# ── Parse tracks ─────────────────────────────────────────────────────
printf "%-45s %-12s %s\n" "Track ID" "Status" "Tasks"
printf "%-45s %-12s %s\n" "--------" "------" "-----"

any_issues=false

while IFS= read -r line; do
    # Match lines like: | [x] | track-id | Title | ...
    if echo "$line" | grep -qE '^\| \[(x|~| )\] \|'; then
        status_marker=$(echo "$line" | grep -oE '\[(x|~| )\]' | head -1)
        track_id=$(echo "$line" | awk -F'|' '{print $3}' | xargs)

        case "$status_marker" in
            "[x]") status="complete" ;;
            "[~]") status="active" ;;
            "[ ]") status="pending" ;;
            *)     status="unknown" ;;
        esac

        # Run verifier and capture output
        if output=$("$VERIFY_SCRIPT" "$track_id" 2>&1); then
            tasks=$(echo "$output" | grep "^Total:" | sed 's/Total: //')
            printf "%-45s %-12s %s\n" "$track_id" "$status" "$tasks"
        else
            tasks=$(echo "$output" | grep "^Total:" | sed 's/Total: //' || echo "error")
            printf "%-45s %-12s %s\n" "$track_id" "$status" "$tasks"
            if [[ "$status" == "active" ]]; then
                any_issues=true
            fi
        fi
    fi
done < "$TRACKS_FILE"

echo ""
if $any_issues; then
    echo "Some active tracks have issues."
    exit 1
else
    echo "All tracks OK."
    exit 0
fi
