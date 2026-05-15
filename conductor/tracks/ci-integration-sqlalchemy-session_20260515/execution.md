# Execution Log — ci-integration-sqlalchemy-session_20260515

## 2026-05-15 — Track created from latent-red split

Split off from `ci-red-triage_20260515` "Discovered Latent Reds" #9. 10+ integration tests in `backend/tests/integration/test_auto_switcher_db.py` fail at fixture setup with `AttributeError: 'Session' object has no attribute 'event'`. Suspect SQLAlchemy 1.x→2.0 API drift, possibly compounded by a lost skip-if-no-DATABASE_URL guard.

This failure re-surfaced in CI run `25932772064` after `ci-pydantic-import_20260515` cleared the pydantic-import blocker — confirms it's an independent latent red, not a downstream cascade.

Launch-blocker per "tests are sacred" — `ph-relaunch-jun2_20260515` depends on this closing.
