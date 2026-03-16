# Specification: Dependency Upgrade

## Problem

- 13 npm vulnerabilities (3 HIGH: minimatch ReDoS, flatted DoS, immutable prototype pollution)
- 73 outdated Python packages (some 7+ major versions behind: stripe 7→14, sentry 1→2)
- 16 outdated npm packages (6 with major version jumps: tailwind, zustand, recharts, eslint, date-fns)
- Version caps blocking updates: `httpx<0.28`, `stripe<8.0`

## Scope

### In Scope
- All packages in `backend/requirements.txt` (66 packages)
- All packages in `backend/requirements-dev.txt` (dev/test tools)
- All packages in `frontend/package.json` (17 deps + 21 devDeps)
- Version cap updates where blocking
- Dependabot config validation

### Out of Scope
- Tailwind v3→v4 (massive CSS-first migration, separate track)
- ESLint v8→v10 (blocked by eslint-config-next compatibility)
- New dependency additions
- ML model retraining (only package compatibility)

## Success Criteria
1. npm audit: 6 or fewer vulnerabilities (all @excalidraw devDep transitive)
2. pip-audit: clean
3. Backend tests: 2,663+ passing
4. Frontend tests: 2,024+ passing
5. ML tests: 611+ passing
6. Frontend builds and type-checks cleanly
7. No Sentry error rate increase post-deploy
8. Stripe webhooks functional post-deploy

## Risks
- Stripe v14 may change webhook payload shapes → mitigated by focused testing
- Sentry v2 drops Hub API → mitigated by grep + migrate pattern
- numpy v2 removes type aliases → mitigated by codemod search
- pandas v3 CoW default → mitigated by test coverage
- redis v7 API stable but connection pool internals changed → mitigated by Lua script tests
