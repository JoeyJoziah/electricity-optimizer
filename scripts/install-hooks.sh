#!/usr/bin/env bash
# install-hooks.sh — Install git hooks from board-sync templates
# Run after cloning the repo to set up git hook integration
#
# Usage: ./scripts/install-hooks.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [[ -z "$REPO_ROOT" ]]; then
    echo "Error: Not inside a git repository." >&2
    exit 1
fi

TEMPLATE_DIR="$REPO_ROOT/.claude/hooks/board-sync"
HOOK_DIR="$REPO_ROOT/.git/hooks"

if [[ ! -d "$TEMPLATE_DIR" ]]; then
    echo "Error: Template directory $TEMPLATE_DIR not found." >&2
    exit 1
fi

installed=0

for hook in post-commit post-merge post-checkout; do
    template="$TEMPLATE_DIR/git-${hook}.sh"
    target="$HOOK_DIR/$hook"

    if [[ ! -f "$template" ]]; then
        echo "Warning: Template $template not found, skipping $hook."
        continue
    fi

    if [[ -f "$target" ]]; then
        echo "Backing up existing $hook to ${hook}.bak"
        cp "$target" "${target}.bak"
    fi

    cp "$template" "$target"
    chmod +x "$target"
    echo "Installed: $hook"
    installed=$((installed + 1))
done

# Ensure the main sync script is executable
if [[ -f "$TEMPLATE_DIR/sync-boards.sh" ]]; then
    chmod +x "$TEMPLATE_DIR/sync-boards.sh"
fi

echo ""
echo "Done: $installed git hook(s) installed."
echo "Board sync will trigger on commits, merges, and branch switches."
