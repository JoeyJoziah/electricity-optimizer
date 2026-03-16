# Contributing to RateShift

Thank you for your interest in contributing to RateShift. This document provides guidelines and instructions for developers.

## Getting Started

### Clone the Repository

```bash
git clone https://github.com/JoeyJoziah/electricity-optimizer.git
cd electricity-optimizer
```

### Backend Setup (Python 3.12)

```bash
# Create and activate virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Neon credentials (DATABASE_URL)

# Run migrations (raw SQL files in backend/migrations/, apply sequentially)
# Use psql or your preferred migration tool against DATABASE_URL

# Start server
.venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

### Frontend Setup (Node 18+)

```bash
cd frontend

# Install dependencies (note: .npmrc has legacy-peer-deps=true for ESLint compatibility)
npm install

# Configure environment
cp .env.example .env.local
# Edit .env.local with backend URL: NEXT_PUBLIC_API_URL=/api/v1

# Start dev server
npm run dev
```

### Database Setup

RateShift uses **Neon PostgreSQL** (project `cold-rice-23455092`).

For local development:
- Option A: Connect to Neon production/preview branch (requires access)
- Option B: Run local PostgreSQL 15+ and apply migrations via `.venv/bin/python -m alembic upgrade head`

## Development Workflow

### Branching

- Create feature branches from `main`: `git checkout -b feat/description`
- Use conventional commit format (see below)
- Ensure all tests pass before pushing

### Conventional Commits

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `refactor:` Code restructuring without feature change
- `test:` Test additions/modifications
- `chore:` Tooling, CI/CD, dependency updates
- `perf:` Performance improvements

Example: `feat: add AI agent query streaming endpoint`

### Running Tests Before Push

```bash
# Backend (always use .venv Python, run from project root)
.venv/bin/python -m pytest backend/tests/ --cov=backend --cov-report=term-missing

# Frontend (run from frontend/)
cd frontend && npm test -- --coverage

# E2E (run from frontend/)
cd frontend && npx playwright test
```

## Code Standards

### Python (Backend)

- **Formatter**: Black (automatic on PRs, must pass on main)
- **Import Sort**: isort (automatic on PRs)
- **Linter**: Ruff (checked in CI)
- **Type Hints**: Required for all functions
- **Region Enum**: Never use raw state strings. Import and use `Region` from `backend/models/region.py`
- **UUID Primary Keys**: All new tables must use UUID type for PKs
- **Database Grants**: All migrations must include `GRANT ... TO neondb_owner`

Example migration pattern:
```sql
CREATE TABLE IF NOT EXISTS new_table (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON new_table TO neondb_owner;
```

### TypeScript/JavaScript (Frontend)

- **Formatter**: Prettier (integrated with ESLint)
- **Linter**: ESLint with next/recommended config
- **Type Safety**: Use `satisfies` and generics liberally
- **Testing Library**: Use React Testing Library + jest-axe for A11y
- **Import Order**: Standard library, third-party, local

### Test Updates

When adding new database columns:

1. Update `backend/conftest.py` `mock_sqlalchemy_select` fixture with the new field
2. Example: If adding `error_message VARCHAR(500)` to notifications, add to mock attributes

## Testing Requirements

### Coverage Thresholds

- Backend: 80% (enforced via `pyproject.toml`)
- Frontend: 80% branches/functions/lines/statements (enforced via `jest.config.js`)

### Running Tests

```bash
# Backend (requires .venv, run from project root)
.venv/bin/python -m pytest backend/tests/
.venv/bin/python -m pytest backend/tests/test_services/ -v
.venv/bin/python -m pytest backend/tests/ --cov=backend

# Frontend (run from frontend/)
cd frontend && npm test
cd frontend && npm test -- --coverage
cd frontend && npm test -- --watch

# E2E (run from frontend/)
cd frontend && npx playwright test
cd frontend && npx playwright test --debug
```

### Critical Test Patterns

- Connection tests: use function-scoped client fixture
- Auth tests: use `helper/auth.ts` mocking (frontend E2E)
- Database tests: use Neon test branch or local PG

## Migration Guidelines

Migrations are sequential SQL files in `backend/migrations/`. Current count: 50 (init_neon through 050). Next migration number: **051**.

### Rules

1. **Sequential numbering**: `050_community_posts_indexes.sql`, `051_your_feature.sql`, etc.
2. **IF NOT EXISTS**: Always use on CREATE TABLE/INDEX
3. **No SERIAL/BIGSERIAL**: Use `UUID DEFAULT gen_random_uuid()` instead
4. **Grant permissions**: `GRANT SELECT, INSERT, UPDATE, DELETE ON table TO neondb_owner`
5. **Test before production**: Apply on Neon `vercel-dev` branch first
6. **Idempotent**: All operations must be safe to re-run

Example:
```sql
-- migrations/051_my_feature.sql
CREATE TABLE IF NOT EXISTS my_table (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_my_table_user_id ON my_table(user_id);
GRANT SELECT, INSERT, UPDATE, DELETE ON my_table TO neondb_owner;
```

## PR Process

### Before Submitting

1. Run all tests and verify coverage
2. Ensure linters pass: Black, isort, ESLint, Ruff
3. Update relevant docs if behavior changed
4. If adding migration: verify on Neon dev branch

### CI Checks (Automated)

- Auto-format on PR (Black, isort) with auto-commit to PR branch
- Tests must pass (backend + frontend + E2E)
- Code analysis for security issues (fails on high/critical)
- Migration validation (sequential numbering, IF NOT EXISTS, GRANT patterns)
- Container scan (Trivy) for vulnerabilities
- Secret scan (Gitleaks)

### Self-Healing Monitor

The project tracks workflow failures:
- 3+ consecutive failures auto-create GitHub issue with `self-healing` label
- 3+ consecutive successes auto-close the issue
- Check `.github/workflows/self-healing-monitor.yml` for status

## Project Structure

```
electricity-optimizer/
├── backend/              # FastAPI application
│   ├── api/             # API routes (/api/v1/*)
│   ├── services/        # Business logic
│   ├── models/          # SQLAlchemy ORM + Pydantic
│   ├── migrations/      # Alembic SQL migrations
│   ├── tests/           # pytest test suite
│   └── requirements.txt
├── frontend/            # Next.js 16 application
│   ├── app/             # App Router pages
│   ├── components/      # React components
│   ├── lib/             # Utilities + hooks
│   ├── __tests__/       # Jest test suite
│   └── package.json
├── ml/                  # ML pipeline
│   ├── ensemble/        # Ensemble predictor
│   ├── hnsw/           # Vector search
│   └── tests/          # ML tests
├── workers/             # Cloudflare Workers
│   └── api-gateway/    # Edge caching + rate limiting
├── docs/               # Documentation
├── .github/workflows/  # GitHub Actions
└── .dsp/              # Codebase graph (DSP)
```

## Key Documentation

- **Architecture**: `docs/ARCHITECTURE.md`
- **Developer Guide**: `docs/DEVELOPER_GUIDE.md`
- **Database Schema**: `docs/DATABASE_SCHEMA.md`
- **API Reference**: `docs/API_REFERENCE.md`
- **Deployment Guide**: `docs/DEPLOYMENT.md`
- **Testing**: `docs/TESTING.md`
- **Observability**: `docs/OBSERVABILITY.md`
- **Infrastructure**: `docs/INFRASTRUCTURE.md`
- **Security**: `docs/SECURITY_AUDIT.md`
- **Automation**: `docs/AUTOMATION_PLAN.md`
- **Redeployment Runbook**: `docs/REDEPLOYMENT_RUNBOOK.md`
- **ADRs**: `docs/adr/001-005` (5 Architecture Decision Records)

## Questions?

- Create an issue with `question` label
- Check existing docs first: `docs/` directory
- Review CLAUDE.md for project-specific conventions
