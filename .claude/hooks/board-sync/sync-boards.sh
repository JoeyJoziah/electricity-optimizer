#!/usr/bin/env bash
# sync-boards.sh — Central board-sync orchestrator
# Syncs GitHub Projects from git/Claude hooks
# (Notion sync removed 2026-03-06 — now via Rube recipe only)
#
# Usage:
#   sync-boards.sh [subcommand] [flags]
#
# Subcommands:
#   all       (default) Sync GitHub Projects
#   github    Sync GitHub Projects only
#   notion    (deprecated — prints notice)
#   status    Show last sync time and state
#   logs      Tail the sync log
#   queue     Show queued sync requests
#   drain     Process queued requests then sync
#
# Flags:
#   --force   Bypass 30-second debounce cooldown
#   --bg      Run sync in background (returns immediately)

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths (resolve relative to git repo root)
# ---------------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [[ -z "$REPO_ROOT" ]]; then
    echo "[board-sync] Not inside a git repository, aborting." >&2
    exit 1
fi

CLAUDE_DIR="$REPO_ROOT/.claude"
LOCK_FILE="$CLAUDE_DIR/.board-sync.lock"
LAST_FILE="$CLAUDE_DIR/.board-sync.last"
QUEUE_FILE="$CLAUDE_DIR/.board-sync-queue"
LOG_FILE="$CLAUDE_DIR/logs/board-sync.log"
CONFIG_FILE="$REPO_ROOT/.notion_sync_config.json"

DEBOUNCE_SECONDS=30

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] $*" >> "$LOG_FILE"
}

die() {
    echo "[board-sync] $*" >&2
    log "ERROR: $*"
    exit 1
}

# Acquire lock (PID-based, cleans stale locks)
acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local pid
        pid="$(cat "$LOCK_FILE" 2>/dev/null || echo "")"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            log "Sync already running (PID $pid), skipping"
            echo "[board-sync] Sync already running (PID $pid), skipping."
            return 1
        fi
        # Stale lock — remove it
        log "Removing stale lock (PID $pid)"
        rm -f "$LOCK_FILE"
    fi
    echo $$ > "$LOCK_FILE"
    return 0
}

release_lock() {
    rm -f "$LOCK_FILE"
}

# Check debounce cooldown
should_debounce() {
    if [[ ! -f "$LAST_FILE" ]]; then
        return 1  # No previous sync, don't debounce
    fi
    local last_sync now elapsed
    last_sync="$(cat "$LAST_FILE" 2>/dev/null || echo "0")"
    now="$(date +%s)"
    elapsed=$(( now - last_sync ))
    if (( elapsed < DEBOUNCE_SECONDS )); then
        log "Debounce: last sync ${elapsed}s ago (threshold ${DEBOUNCE_SECONDS}s)"
        echo "[board-sync] Debounce: synced ${elapsed}s ago, skipping (use --force to override)."
        return 0
    fi
    return 1
}

record_sync_time() {
    date +%s > "$LAST_FILE"
}

# ---------------------------------------------------------------------------
# GitHub Projects sync
# ---------------------------------------------------------------------------
sync_github() {
    log "Starting GitHub Projects sync"

    if ! command -v gh &>/dev/null; then
        log "WARN: gh CLI not found, skipping GitHub sync"
        echo "[board-sync] Warning: gh CLI not found, skipping GitHub Projects sync."
        return 0
    fi

    # Read project config
    local project_number project_owner
    if [[ -f "$CONFIG_FILE" ]] && command -v python3 &>/dev/null; then
        project_number="$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('github_project',{}).get('number',''))" 2>/dev/null || echo "")"
        project_owner="$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('github_project',{}).get('owner',''))" 2>/dev/null || echo "")"
    fi

    if [[ -z "$project_number" || -z "$project_owner" ]]; then
        log "WARN: github_project not configured in $CONFIG_FILE"
        echo "[board-sync] Warning: github_project not configured, skipping GitHub Projects sync."
        return 0
    fi

    local repo_full_name
    repo_full_name="$(python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('github',{}).get('repo_full_name',''))" 2>/dev/null || echo "")"
    if [[ -z "$repo_full_name" ]]; then
        log "WARN: github.repo_full_name not in config"
        return 0
    fi

    # Add open issues to the project
    local issue_count=0
    while IFS= read -r url; do
        [[ -z "$url" ]] && continue
        if gh project item-add "$project_number" --owner "$project_owner" --url "$url" &>/dev/null; then
            issue_count=$((issue_count + 1))
        fi
    done < <(gh issue list --repo "$repo_full_name" --state open --json url --jq '.[].url' 2>/dev/null || true)

    # Add open PRs to the project
    local pr_count=0
    while IFS= read -r url; do
        [[ -z "$url" ]] && continue
        if gh project item-add "$project_number" --owner "$project_owner" --url "$url" &>/dev/null; then
            pr_count=$((pr_count + 1))
        fi
    done < <(gh pr list --repo "$repo_full_name" --state open --json url --jq '.[].url' 2>/dev/null || true)

    log "GitHub sync complete: $issue_count issues, $pr_count PRs added/updated"
    echo "[board-sync] GitHub Projects: $issue_count issues, $pr_count PRs synced."
}

# ---------------------------------------------------------------------------
# Notion sync — REMOVED (2026-03-06)
# Notion sync is now handled exclusively by Rube recipe (every 6h).
# Local hooks no longer touch Notion to avoid deadlocks and 400 errors.
# See: Electricity Optimizer Hub in Notion
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
cmd_all() {
    sync_github
    record_sync_time
    log "Full sync complete"
}

cmd_github() {
    sync_github
    record_sync_time
    log "GitHub-only sync complete"
}

cmd_notion() {
    echo "[board-sync] Notion sync removed. Notion is now synced via Rube recipe (every 6h)."
    log "Notion sync skipped (removed — use Rube recipe)"
}

cmd_status() {
    echo "[board-sync] Status:"
    if [[ -f "$LAST_FILE" ]]; then
        local last_sync now elapsed
        last_sync="$(cat "$LAST_FILE")"
        now="$(date +%s)"
        elapsed=$(( now - last_sync ))
        local last_date
        last_date="$(date -r "$last_sync" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d "@$last_sync" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "unknown")"
        echo "  Last sync: $last_date (${elapsed}s ago)"
    else
        echo "  Last sync: never"
    fi
    if [[ -f "$LOCK_FILE" ]]; then
        local pid
        pid="$(cat "$LOCK_FILE")"
        if kill -0 "$pid" 2>/dev/null; then
            echo "  Lock: active (PID $pid)"
        else
            echo "  Lock: stale (PID $pid)"
        fi
    else
        echo "  Lock: none"
    fi
    if [[ -f "$QUEUE_FILE" ]]; then
        local qcount
        qcount="$(wc -l < "$QUEUE_FILE" | tr -d ' ')"
        echo "  Queue: $qcount pending request(s)"
    else
        echo "  Queue: empty"
    fi
}

cmd_logs() {
    if [[ -f "$LOG_FILE" ]]; then
        tail -30 "$LOG_FILE"
    else
        echo "[board-sync] No log file yet."
    fi
}

cmd_queue() {
    if [[ -f "$QUEUE_FILE" && -s "$QUEUE_FILE" ]]; then
        echo "[board-sync] Queued requests:"
        cat "$QUEUE_FILE"
    else
        echo "[board-sync] Queue is empty."
    fi
}

cmd_drain() {
    if [[ -f "$QUEUE_FILE" ]]; then
        local qcount
        qcount="$(wc -l < "$QUEUE_FILE" | tr -d ' ')"
        log "Draining queue ($qcount requests)"
        : > "$QUEUE_FILE"  # Truncate queue
    fi
    # Proceed with full sync
    cmd_all
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    local subcmd="all"
    local force=false
    local bg=false

    for arg in "$@"; do
        case "$arg" in
            --force) force=true ;;
            --bg)    bg=true ;;
            all|github|notion|status|logs|queue|drain) subcmd="$arg" ;;
            *) die "Unknown argument: $arg" ;;
        esac
    done

    # Status, logs, queue don't need lock/debounce
    case "$subcmd" in
        status) cmd_status; return 0 ;;
        logs)   cmd_logs;   return 0 ;;
        queue)  cmd_queue;  return 0 ;;
    esac

    # Background mode: re-exec in background
    if [[ "$bg" == true ]]; then
        log "Spawning background sync: $subcmd"
        nohup "$0" "$subcmd" $([ "$force" == true ] && echo "--force") >> "$LOG_FILE" 2>&1 &
        disown
        return 0
    fi

    # Debounce check (unless --force)
    if [[ "$force" != true ]] && should_debounce; then
        return 0
    fi

    # Acquire lock
    if ! acquire_lock; then
        return 0
    fi
    trap release_lock EXIT

    log "=== Sync started: $subcmd ==="

    case "$subcmd" in
        all)     cmd_all ;;
        github)  cmd_github ;;
        notion)  cmd_notion ;;
        drain)   cmd_drain ;;
        *)       die "Unknown subcommand: $subcmd" ;;
    esac

    log "=== Sync finished: $subcmd ==="
}

main "$@"
