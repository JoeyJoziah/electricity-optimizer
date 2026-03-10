# Python Style Guide

Based on existing config (`pyproject.toml`): Black, isort, Ruff, mypy, Bandit.

## Formatting

- **Black**: Line length 100, target Python 3.11+
- **isort**: Integrated via Ruff. Known first-party: `backend`, `config`, `models`, `repositories`, `services`, `api`, `routers`
- CI auto-formats on PRs (Black + isort fix mode with bot commit)

## Linting (Ruff)

Enabled rule sets: pycodestyle (E/W), Pyflakes (F), isort (I), flake8-bugbear (B), flake8-comprehensions (C4), pyupgrade (UP), unused-arguments (ARG), flake8-simplify (SIM).

### Ignored Rules

- `E501`: Line length (handled by Black)
- `B008`: Function calls in argument defaults (FastAPI `Depends()`)
- `B905`: `zip()` without `strict`
- `C901`: Complexity threshold

### Per-File Overrides

- `__init__.py`: Unused imports allowed (`F401`)
- `tests/*`: Unused arguments and `assert` allowed

## Type Checking (mypy)

- `strict_optional = true`
- `check_untyped_defs = true`
- Pydantic plugin enabled
- Missing import stubs ignored for: redis, asyncpg, prometheus_client, sentry_sdk, structlog, jose

## Naming Conventions

| Entity | Convention | Example |
|--------|-----------|---------|
| Modules | snake_case | `user_repository.py` |
| Classes | PascalCase | `DunningService`, `AlertConfig` |
| Functions | snake_case | `get_active_alert_configs()` |
| Constants | UPPER_SNAKE_CASE | `TIMEOUT_EXCLUDED_PREFIXES` |
| Pydantic models | PascalCase | `KPIReportResponse` |
| FastAPI routers | snake_case file, PascalCase class | `alerts.py`, `router = APIRouter()` |

## Async Patterns

- Use `async def` for all route handlers and database operations
- `asyncio.to_thread()` for blocking calls (Stripe SDK)
- `asyncio.gather()` + `Semaphore(N)` for parallel API calls
- Always `await db.commit()` after INSERT/UPDATE

```python
# Good: parallel with concurrency control
sem = asyncio.Semaphore(10)
async def fetch_one(region):
    async with sem:
        return await client.get(f"/weather/{region}")
results = await asyncio.gather(*[fetch_one(r) for r in regions])
```

## Testing

- Always run via `.venv/bin/python -m pytest`
- asyncio_mode = "auto"
- Markers: `@pytest.mark.asyncio`, `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.unit`
- Coverage threshold: 80% (`fail_under = 80`)

## Security (Bandit)

- Excludes: `tests/`, `alembic/`
- `B101` (assert_used) skipped
