#!/usr/bin/env bash
# project-routing.sh — PreToolUse hook for Task|TeamCreate
#
# Project-specific agent routing overlay for electricity-optimizer.
# Keyword-based routing that suggests domain-specific agents.
# Advisory only — NEVER blocks. Always exits 0.

set -uo pipefail

DESCRIPTION="${1:-}"
REPO_ROOT="/Users/devinmcgrath/projects/electricity-optimizer"
LOG_FILE="$REPO_ROOT/.claude/logs/orchestration-hooks.log"

# Fast exit if no description
[[ -z "$DESCRIPTION" ]] && exit 0

mkdir -p "$(dirname "$LOG_FILE")"

# Lowercase for matching
DESC_LOWER="$(echo "$DESCRIPTION" | tr '[:upper:]' '[:lower:]')"

# ── Keyword-based routing ─────────────────────────────────────────────
route_task() {
    local desc="$1"

    # EnergyDataAgent: energy domain, APIs, pricing, regions
    if echo "$desc" | grep -qE "(eia|nrel|energy|electricity|utility|utilit|price|rate|supplier|region|tariff|kwh|kilowatt)"; then
        echo "EnergyDataAgent"
        return
    fi

    # NeonDBAgent: database operations
    if echo "$desc" | grep -qE "(migrat|schema|database|neon|sql|table|column|endpoint|asyncpg|alembic)"; then
        echo "NeonDBAgent"
        return
    fi

    # StripeAgent: billing and payments
    if echo "$desc" | grep -qE "(billing|subscription|checkout|webhook|stripe|pro plan|business plan|payment|invoice)"; then
        echo "StripeAgent"
        return
    fi

    # MLPipelineAgent: machine learning
    if echo "$desc" | grep -qE "(ml|predictor|ensemble|hnsw|vector.store|forecast|bias|learning.service|adaptive|model.train)"; then
        echo "MLPipelineAgent"
        return
    fi

    echo ""
}

AGENT_OVERRIDE=$(route_task "$DESC_LOWER")

if [[ -n "$AGENT_OVERRIDE" ]]; then
    echo "[ProjectRouting] Agent override: $AGENT_OVERRIDE for: $(echo "$DESCRIPTION" | cut -c1-60)" >&2
    echo "[$(date '+%H:%M:%S')] [project-routing] Routed to $AGENT_OVERRIDE: $(echo "$DESCRIPTION" | cut -c1-80)" >> "$LOG_FILE"
fi

exit 0
