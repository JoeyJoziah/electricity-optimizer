#!/usr/bin/env bash
# session-end-sync.sh — Claude Stop hook
# Drains the queue and runs a foreground forced sync on session end

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[[ -z "$REPO_ROOT" ]] && exit 0

SYNC_SCRIPT="$REPO_ROOT/.claude/hooks/board-sync/sync-boards.sh"
[[ ! -x "$SYNC_SCRIPT" ]] && exit 0

# Foreground forced sync to ensure everything is saved before exit
"$SYNC_SCRIPT" drain --force 2>/dev/null || true

exit 0
