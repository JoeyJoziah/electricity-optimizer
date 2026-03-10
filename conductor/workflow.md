# Workflow

## TDD Policy: Strict

Tests are required **before** implementation. Follow the Red-Green-Refactor cycle:

1. **Red:** Write a failing test that describes the expected behavior
2. **Green:** Write the minimum code to make the test pass
3. **Refactor:** Clean up while keeping tests green

### Test Commands

```bash
# Backend
.venv/bin/python -m pytest                        # All backend tests
.venv/bin/python -m pytest tests/test_specific.py  # Single file
.venv/bin/python -m pytest -k "test_name"          # Single test

# Frontend
cd frontend && npm test                            # All frontend tests
cd frontend && npm test -- --testPathPattern=file   # Single file

# E2E
cd frontend && npx playwright test                 # All E2E tests
```

### Coverage Thresholds

- **Backend:** 80% (pyproject.toml)
- **Frontend:** 80% branches/functions/lines/statements (jest.config.js)

## Commit Strategy: Conventional Commits

Format: `<type>(<scope>): <description>`

### Types

| Type | Usage |
|------|-------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks, dependency updates |
| `perf` | Performance improvement |
| `ci` | CI/CD changes |

### Examples

```
feat(alerts): add optimal usage window notifications
fix(connections): resolve bill upload timeout on large files
refactor(auth): extract session validation to middleware
test(payments): add dunning cycle edge case coverage
ci(deploy): add migration gate before production deploy
```

### Co-Author

All AI-assisted commits include:
```
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

## Code Review

**Required for all changes.** Every pull request needs review before merge.

### PR Template

```markdown
## Summary
<1-3 bullet points>

## Test plan
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] E2E tests pass (if applicable)
- [ ] Manual verification complete
```

## Verification Checkpoints

Manual verification is required **after each phase completion** within a track.

### Phase Completion Checklist

- [ ] All phase tasks marked complete
- [ ] Tests pass (backend + frontend)
- [ ] No regressions in existing functionality
- [ ] Documentation updated if applicable
- [ ] Board sync triggered (GitHub Projects)
- [ ] Memory persisted to Claude Flow

## Task Lifecycle

```
PENDING -> IN_PROGRESS -> VERIFICATION -> COMPLETE
                |                |
                v                v
            BLOCKED          FAILED (reopens as IN_PROGRESS)
```
