#!/usr/bin/env bash
# git-post-commit.sh — Git post-commit hook template
# Triggers a background board sync after each commit
# Template lives in .claude/hooks/board-sync/ (tracked)
# Copied to .git/hooks/post-commit (not tracked)

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[ -z "$REPO_ROOT" ] && exit 0

SYNC_SCRIPT="$REPO_ROOT/.claude/hooks/board-sync/sync-boards.sh"
[ -x "$SYNC_SCRIPT" ] && "$SYNC_SCRIPT" all --bg 2>/dev/null || true

exit 0
