#!/usr/bin/env bash
# post-edit-sync.sh — Claude PostToolUse hook for Edit/Write/MultiEdit
# Queues a board sync request (non-blocking, never fails)

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[[ -z "$REPO_ROOT" ]] && exit 0

QUEUE_FILE="$REPO_ROOT/.claude/.board-sync-queue"
mkdir -p "$(dirname "$QUEUE_FILE")"

# Append a timestamped queue entry
echo "$(date '+%Y-%m-%d %H:%M:%S') edit" >> "$QUEUE_FILE"

exit 0
