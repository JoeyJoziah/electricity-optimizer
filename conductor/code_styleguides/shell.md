# Shell/Bash Style Guide

Conventions for CI/CD workflows, automation scripts, and hooks.

## General

- Use `#!/bin/bash` shebang (or `#!/usr/bin/env bash` for portability)
- `set -euo pipefail` at the top of every script
- Quote all variable expansions: `"$VAR"`, `"${ARRAY[@]}"`

```bash
#!/bin/bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
```

## Naming

| Entity | Convention | Example |
|--------|-----------|---------|
| Scripts | kebab-case | `sync-boards.sh`, `retry-curl.sh` |
| Variables | UPPER_SNAKE_CASE | `BACKEND_URL`, `MAX_RETRIES` |
| Functions | snake_case | `check_health()`, `notify_slack()` |
| Constants | `readonly` keyword | `readonly TIMEOUT=30` |

## GitHub Actions

### Composite Actions

Located in `.github/actions/{name}/action.yml`. Follow existing patterns:

- **retry-curl**: Exponential backoff, 4xx fail-fast (except 429/408), 5xx/429/408/000 retries
- **notify-slack**: Color-coded severity (critical=danger, warning=warning, info=blue)
- **validate-migrations**: Convention checks (sequential numbering, IF NOT EXISTS, neondb_owner, no SERIAL)

### Workflow Conventions

```yaml
name: Descriptive Name
on:
  schedule:
    - cron: '0 6 * * *'  # Daily 6am UTC
  workflow_dispatch: {}   # Always allow manual trigger

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

### Secrets

- Never echo secrets, even in debug mode
- Use `${{ secrets.NAME }}` in workflows
- Store in both GitHub Secrets and 1Password vault

### Error Handling

- Use `retry-curl` composite action for all HTTP calls to internal endpoints
- Add `notify-slack` failure job to all cron workflows
- Sparse checkout when only `.github/actions/` is needed

```yaml
- uses: ./.github/actions/retry-curl
  with:
    url: ${{ secrets.BACKEND_URL }}/api/v1/internal/endpoint
    method: POST
    api-key: ${{ secrets.INTERNAL_API_KEY }}
    max-retries: '3'
```

## Hook Scripts

Located in `.claude/hooks/`. Must be executable (`chmod +x`).

- Keep hooks lightweight (< 5s execution)
- Log to stderr, output to stdout
- Exit 0 on success, non-zero on failure
