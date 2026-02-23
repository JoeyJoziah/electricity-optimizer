#!/usr/bin/env bash
# post-task-sync.sh — Claude PostToolUse hook for TaskUpdate
# Drains the queue and triggers a background sync

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[[ -z "$REPO_ROOT" ]] && exit 0

SYNC_SCRIPT="$REPO_ROOT/.claude/hooks/board-sync/sync-boards.sh"
[[ ! -x "$SYNC_SCRIPT" ]] && exit 0

# Drain queue and sync in background
"$SYNC_SCRIPT" drain --bg 2>/dev/null || true

exit 0
