#!/usr/bin/env bash
# project-intelligence-sync.sh — Create/sync .project-intelligence bridge
#
# Creates the .project-intelligence/ directory structure as a compatibility
# layer for the verification-loop skill. Uses symlinks to existing .loki/ state.
# Idempotent — safe to run repeatedly.

set -euo pipefail

REPO_ROOT="/Users/devinmcgrath/projects/electricity-optimizer"
PI_DIR="$REPO_ROOT/.project-intelligence"
LOKI_DIR="$REPO_ROOT/.loki"

log() { echo "[project-intelligence-sync] $*"; }

# ── Create directory structure ──────────────────────────────────────────
mkdir -p "$PI_DIR/state" "$PI_DIR/queue" "$PI_DIR/signals" "$PI_DIR/archives"

# ── Symlink CONTINUITY.md ───────────────────────────────────────────────
if [[ -f "$LOKI_DIR/CONTINUITY.md" ]]; then
    if [[ ! -L "$PI_DIR/CONTINUITY.md" ]]; then
        rm -f "$PI_DIR/CONTINUITY.md" 2>/dev/null || true
        ln -s "$LOKI_DIR/CONTINUITY.md" "$PI_DIR/CONTINUITY.md"
        log "Symlinked CONTINUITY.md -> .loki/CONTINUITY.md"
    fi
else
    log "WARN: .loki/CONTINUITY.md not found, skipping symlink"
fi

# ── Symlink orchestrator.json ───────────────────────────────────────────
if [[ -f "$LOKI_DIR/state/orchestrator.json" ]]; then
    if [[ ! -L "$PI_DIR/state/orchestrator.json" ]]; then
        rm -f "$PI_DIR/state/orchestrator.json" 2>/dev/null || true
        ln -s "$LOKI_DIR/state/orchestrator.json" "$PI_DIR/state/orchestrator.json"
        log "Symlinked state/orchestrator.json -> .loki/state/orchestrator.json"
    fi
else
    log "WARN: .loki/state/orchestrator.json not found, skipping symlink"
fi

# ── Initialize queue files (empty arrays if missing) ────────────────────
for queue_file in pending.json in-progress.json completed.json blocked.json; do
    target="$PI_DIR/queue/$queue_file"
    if [[ ! -f "$target" ]]; then
        echo "[]" > "$target"
        log "Created queue/$queue_file"
    fi
done

# ── Initialize signal files (empty if missing) ─────────────────────────
for signal_file in QUALITY_GATE_FAILURES.log ESCALATIONS.log; do
    target="$PI_DIR/signals/$signal_file"
    if [[ ! -f "$target" ]]; then
        touch "$target"
        log "Created signals/$signal_file"
    fi
done

log "Project intelligence bridge ready at $PI_DIR"
