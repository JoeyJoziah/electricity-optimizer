#!/usr/bin/env bash
# git-post-checkout.sh — Git post-checkout hook template
# Triggers a background board sync on branch checkout (not file checkout)
# Template lives in .claude/hooks/board-sync/ (tracked)
# Copied to .git/hooks/post-checkout (not tracked)
#
# Args from git: $1=prev_ref $2=new_ref $3=branch_flag
# $3 == 1 means branch checkout, 0 means file checkout

BRANCH_FLAG="${3:-0}"
[ "$BRANCH_FLAG" != "1" ] && exit 0

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[ -z "$REPO_ROOT" ] && exit 0

SYNC_SCRIPT="$REPO_ROOT/.claude/hooks/board-sync/sync-boards.sh"
[ -x "$SYNC_SCRIPT" ] && "$SYNC_SCRIPT" all --bg 2>/dev/null || true

exit 0
