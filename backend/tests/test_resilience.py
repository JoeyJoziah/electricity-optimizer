"""
Resilience tests — verify the app degrades gracefully under failure conditions.

Covers:
  - Database errors return 500, not unhandled crashes (uses raise_server_exceptions=False)
  - asyncio.TimeoutError from DB returns 500
  - Rate limiter stays stable under rapid requests (200/429 only)
  - VectorStore initialises and searches correctly without hnswlib
  - HNSWVectorStore falls back to brute-force search when hnswlib is absent
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_db_session, TokenData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test_user(suffix: str = "1") -> TokenData:
    """Return a minimal TokenData for dependency injection."""
    return TokenData(
        user_id=f"resilience-user-{suffix}",
        email=f"resilience{suffix}@test.com",
    )


def _make_erroring_db(exc: Exception) -> AsyncMock:
    """Return a mock async DB session whose execute() always raises *exc*."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=exc)
    db.commit = AsyncMock()
    return db


def _empty_mock_db() -> AsyncMock:
    """Return a mock async DB session that returns empty results."""
    mock_db = AsyncMock()
    empty_result = MagicMock()
    mapping = MagicMock()
    mapping.first.return_value = None
    mapping.all.return_value = []
    empty_result.mappings.return_value = mapping
    empty_result.fetchall.return_value = []
    empty_result.scalar.return_value = 0
    mock_db.execute = AsyncMock(return_value=empty_result)
    mock_db.commit = AsyncMock()
    return mock_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def basic_auth_client():
    """
    Authenticated client with an empty mock DB — useful for rate-limiter tests.
    Uses raise_server_exceptions=False so 500 responses come through as HTTP
    responses rather than re-raised exceptions in the test process.
    """
    from main import app

    user = _make_test_user("rate")
    mock_db = _empty_mock_db()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: mock_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# Database resilience
# ---------------------------------------------------------------------------


class TestDatabaseResilience:
    """
    Verify graceful degradation when the database layer raises exceptions.

    The FastAPI app registers a global exception handler for all unhandled
    exceptions (see main.py @app.exception_handler(Exception)).  These tests
    confirm that handler converts DB exceptions into HTTP 500 responses instead
    of crashing the process.

    raise_server_exceptions=False is required so that Starlette's TestClient
    lets the exception bubble through FastAPI's exception handler rather than
    re-raising it inside the test coroutine.
    """

    def _client_with_erroring_db(self, exc: Exception, user_suffix: str) -> TestClient:
        """Build a TestClient that injects an always-erroring mock DB."""
        from main import app

        user = _make_test_user(user_suffix)
        db = _make_erroring_db(exc)

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db_session] = lambda: db

        return TestClient(app, raise_server_exceptions=False)

    def _cleanup(self) -> None:
        from main import app
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)

    def test_generic_db_error_returns_500(self):
        """
        A generic exception from db.execute() should be caught by the global
        exception handler and return HTTP 500 — not crash the process.
        """
        client = self._client_with_erroring_db(
            Exception("DB connection refused"), "db-err"
        )
        try:
            response = client.get("/api/v1/savings/summary")
            assert response.status_code == 500, (
                f"Expected 500, got {response.status_code}: {response.text}"
            )
        finally:
            self._cleanup()

    def test_db_timeout_returns_error_response(self):
        """
        asyncio.TimeoutError from db.execute() should return an HTTP error
        response.  The RequestTimeoutMiddleware intercepts TimeoutError and
        returns 504 Gateway Timeout; the global handler returns 500 for other
        exceptions.  Either status is acceptable — the key invariant is that
        the server returns a JSON error rather than crashing.
        """
        client = self._client_with_erroring_db(
            asyncio.TimeoutError(), "db-timeout"
        )
        try:
            response = client.get("/api/v1/savings/summary")
            # 504 = RequestTimeoutMiddleware caught it
            # 500 = global exception handler caught it
            assert response.status_code in (500, 504), (
                f"Expected 500 or 504, got {response.status_code}: {response.text}"
            )
            # Response body must be parseable JSON with a 'detail' key
            body = response.json()
            assert "detail" in body
        finally:
            self._cleanup()

    def test_db_error_response_body_is_valid_json(self):
        """
        The 500 error response must be valid JSON with a 'detail' key so that
        the frontend can display a sensible error message.
        """
        client = self._client_with_erroring_db(
            RuntimeError("connection pool exhausted"), "db-json"
        )
        try:
            response = client.get("/api/v1/savings/summary")
            assert response.status_code == 500
            body = response.json()
            assert "detail" in body, (
                f"Missing 'detail' key in error body: {body}"
            )
        finally:
            self._cleanup()

    def test_db_error_on_history_endpoint_returns_500(self):
        """
        DB failures on the savings history endpoint should also return 500,
        confirming the global handler covers all routes — not just /summary.
        """
        client = self._client_with_erroring_db(
            Exception("disk I/O error"), "db-hist"
        )
        try:
            response = client.get("/api/v1/savings/history")
            assert response.status_code == 500
        finally:
            self._cleanup()

    def test_value_error_in_service_returns_500(self):
        """
        A ValueError raised inside the service layer (e.g. from malformed data)
        should also produce HTTP 500 rather than a 422 or crash.
        """
        client = self._client_with_erroring_db(
            ValueError("unexpected DB value"), "db-val"
        )
        try:
            response = client.get("/api/v1/savings/summary")
            assert response.status_code == 500
        finally:
            self._cleanup()


# ---------------------------------------------------------------------------
# Rate limiter resilience
# ---------------------------------------------------------------------------


class TestRateLimiterResilience:
    """
    Verify rate-limiting behaviour under rapid requests.

    In the test environment the rate limiter's in-memory store is reset before
    and after each test by the autouse ``reset_rate_limiter`` fixture in
    conftest.py. These tests confirm that:
      - The app stays healthy regardless of request volume.
      - All responses are members of the expected set {200, 429, 500}.
    """

    def test_repeated_requests_dont_crash_app(self, basic_auth_client):
        """
        Sending 20 requests in rapid succession must not crash the server.
        Each response must be 200 (success), 429 (rate-limited), or 500 (DB error).
        """
        statuses: list[int] = []
        for _ in range(20):
            resp = basic_auth_client.get("/api/v1/savings/summary")
            statuses.append(resp.status_code)

        allowed = {200, 429, 500}
        unexpected = [s for s in statuses if s not in allowed]
        assert not unexpected, (
            f"Unexpected status codes in rapid-request test: {unexpected}"
        )

    def test_rate_limit_or_success_on_burst(self, basic_auth_client):
        """
        After a burst of requests either:
          (a) all succeed (rate limiter lenient / disabled in test mode), or
          (b) a 429 is returned once the limit is hit.
        Neither outcome is an error — we confirm the server stays healthy.
        """
        statuses: list[int] = []
        for _ in range(50):
            resp = basic_auth_client.get("/api/v1/savings/summary")
            statuses.append(resp.status_code)
            if resp.status_code == 429:
                break

        # Only 200, 429, or 500 are acceptable
        limiter_errors = [s for s in statuses if s not in {200, 429, 500}]
        assert not limiter_errors, (
            f"Unexpected codes during burst: {limiter_errors}"
        )


# ---------------------------------------------------------------------------
# HNSW / VectorStore fallback
# ---------------------------------------------------------------------------


class TestHNSWFallback:
    """
    Verify the vector store degrades gracefully when hnswlib is absent.

    The production VectorStore (SQLite-backed brute-force) is always the
    fallback layer.  HNSWVectorStore wraps it and skips HNSW index
    construction when HNSW_AVAILABLE is False.
    """

    def test_vector_store_initialises_without_hnswlib(self, tmp_path):
        """
        VectorStore must initialise and support search regardless of whether
        hnswlib is installed. This confirms the base brute-force layer works
        independently.
        """
        import numpy as np
        from services.vector_store import VectorStore

        db_path = str(tmp_path / "test.db")
        store = VectorStore(db_path=db_path, dimension=4)
        assert store is not None

        # Search on an empty store must return an empty list without error
        results = store.search(query_vector=np.zeros(4), domain="test", k=5)
        assert isinstance(results, list)
        assert results == []

    def test_hnsw_store_initialises_with_hnsw_unavailable(self, tmp_path):
        """
        HNSWVectorStore must initialise without error even when hnswlib
        cannot be imported. The HNSW index should remain None (skipped).
        """
        import services.hnsw_vector_store as hnsw_module

        db_path = str(tmp_path / "hnsw_test.db")

        original_available = hnsw_module.HNSW_AVAILABLE
        try:
            hnsw_module.HNSW_AVAILABLE = False
            store = hnsw_module.HNSWVectorStore(db_path=db_path, dimension=4)
            assert store is not None
            # With hnswlib unavailable, _build_index() is skipped
            assert store._index is None
        finally:
            hnsw_module.HNSW_AVAILABLE = original_available

    def test_hnsw_search_falls_back_to_brute_force(self, tmp_path):
        """
        When HNSW_AVAILABLE is False (or _index is None), HNSWVectorStore.search()
        must delegate to VectorStore brute-force search and return a list without
        raising an exception.
        """
        import numpy as np
        import services.hnsw_vector_store as hnsw_module

        db_path = str(tmp_path / "hnsw_search.db")
        original_available = hnsw_module.HNSW_AVAILABLE
        try:
            hnsw_module.HNSW_AVAILABLE = False
            store = hnsw_module.HNSWVectorStore(db_path=db_path, dimension=4)
            # _index is None — search must fall back to brute-force
            results = store.search(query_vector=np.zeros(4), domain="test", k=3)
            assert isinstance(results, list)
        finally:
            hnsw_module.HNSW_AVAILABLE = original_available

    def test_hnsw_search_with_index_present_falls_back_when_empty(self, tmp_path):
        """
        Even when the HNSW index object exists, an empty index (count=0) causes
        HNSWVectorStore to delegate to brute-force. Verify this still returns
        a list for an empty store.
        """
        import numpy as np
        from services.hnsw_vector_store import HNSWVectorStore

        db_path = str(tmp_path / "hnsw_empty.db")
        # Let the store initialise normally (with or without hnswlib)
        store = HNSWVectorStore(db_path=db_path, dimension=4)
        # Either brute-force (no hnswlib) or empty HNSW index — both return []
        results = store.search(query_vector=np.zeros(4), domain="test", k=3)
        assert isinstance(results, list)
