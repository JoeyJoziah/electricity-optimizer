"""
Tests for the Savings API (backend/api/v1/savings.py) and SavingsService.

Coverage:
  - GET /api/v1/savings/summary  (empty user, user with data, auth guard)
  - GET /api/v1/savings/history  (empty list, pagination, auth guard)

The _MockDB class simulates the SQL layer entirely in-memory so no real
Postgres connection is needed. Auth is injected via dependency_overrides on
``get_current_user`` and ``get_db_session``.

Tests use function-scoped TestClient to avoid rate-limiter state accumulation.
"""

from __future__ import annotations

import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_db_session, TokenData

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "cccccccc-0000-0000-0000-000000000003"


# ---------------------------------------------------------------------------
# In-memory mock DB
# ---------------------------------------------------------------------------


class _MockDB:
    """
    Lightweight async DB session that keeps savings rows in a plain list and
    routes text() statements to the right in-memory operation.

    Supports:
      - aggregate SELECT (total / weekly / monthly)
      - streak SELECT (distinct dates)
      - count SELECT
      - paginated SELECT (LIMIT / OFFSET)
      - INSERT ... RETURNING
      - commit (no-op)
    """

    def __init__(self):
        self._rows: list[dict] = []
        self.commit = AsyncMock()

    # ------------------------------------------------------------------
    # Public execute entry-point
    # ------------------------------------------------------------------

    async def execute(self, stmt, params=None):
        sql = self._sql(stmt)
        params = params or {}
        return self._dispatch(sql, params)

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self, sql: str, params: dict) -> MagicMock:
        if sql.startswith("INSERT INTO USER_SAVINGS"):
            return self._handle_insert(params)
        if "COALESCE(SUM(AMOUNT)" in sql:
            return self._handle_aggregate(params)
        if "DISTINCT DATE(" in sql:
            return self._handle_streak(params)
        if "COUNT(*)" in sql:
            return self._handle_count(params)
        if "LIMIT" in sql and "OFFSET" in sql:
            return self._handle_paginated(params)
        # Fallback — empty result
        return self._empty_result()

    # ------------------------------------------------------------------
    # Handler: INSERT
    # ------------------------------------------------------------------

    def _handle_insert(self, params: dict) -> MagicMock:
        now = datetime.now(tz=timezone.utc)
        row = {
            "id": params.get("id", str(uuid4())),
            "user_id": params["user_id"],
            "savings_type": params["savings_type"],
            "amount": Decimal(str(params["amount"])),
            "currency": params.get("currency", "USD"),
            "description": params.get("description"),
            "region": params.get("region"),
            "period_start": params["period_start"],
            "period_end": params["period_end"],
            "created_at": now,
        }
        self._rows.append(row)
        return self._mapping_first(row)

    # ------------------------------------------------------------------
    # Handler: aggregate (total / weekly / monthly)
    # ------------------------------------------------------------------

    def _handle_aggregate(self, params: dict) -> MagicMock:
        uid = params["user_id"]
        region = params.get("region")
        user_rows = [r for r in self._rows if str(r["user_id"]) == str(uid)]
        if region:
            user_rows = [r for r in user_rows if r.get("region") == region]

        now = datetime.now(tz=timezone.utc)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        total = sum(float(r["amount"]) for r in user_rows)
        weekly = sum(
            float(r["amount"])
            for r in user_rows
            if r["created_at"] >= week_ago
        )
        monthly = sum(
            float(r["amount"])
            for r in user_rows
            if r["created_at"] >= month_ago
        )
        currency = user_rows[0]["currency"] if user_rows else "USD"

        agg = {
            "total": Decimal(str(total)),
            "weekly": Decimal(str(weekly)),
            "monthly": Decimal(str(monthly)),
            "currency": currency,
        }
        return self._mapping_first(agg)

    # ------------------------------------------------------------------
    # Handler: streak (distinct dates)
    # ------------------------------------------------------------------

    def _handle_streak(self, params: dict) -> MagicMock:
        uid = params["user_id"]
        user_rows = [r for r in self._rows if str(r["user_id"]) == str(uid)]
        dates = sorted(
            {r["created_at"].date() for r in user_rows},
            reverse=True,
        )
        # Return as fetchall() tuples — SavingsService reads row[0]
        mock_rows = [(d,) for d in dates]

        result = MagicMock()
        result.fetchall.return_value = mock_rows
        return result

    # ------------------------------------------------------------------
    # Handler: COUNT
    # ------------------------------------------------------------------

    def _handle_count(self, params: dict) -> MagicMock:
        uid = params["user_id"]
        count = sum(1 for r in self._rows if str(r["user_id"]) == str(uid))
        result = MagicMock()
        result.scalar.return_value = count
        return result

    # ------------------------------------------------------------------
    # Handler: paginated SELECT
    # ------------------------------------------------------------------

    def _handle_paginated(self, params: dict) -> MagicMock:
        uid = params["user_id"]
        limit = params.get("limit", 20)
        offset = params.get("offset", 0)

        user_rows = [
            r for r in self._rows if str(r["user_id"]) == str(uid)
        ]
        # Sort newest first (matches ORDER BY created_at DESC)
        user_rows = sorted(user_rows, key=lambda r: r["created_at"], reverse=True)
        page_rows = user_rows[offset: offset + limit]
        return self._mapping_all(page_rows)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sql(stmt) -> str:
        raw = str(stmt.text if hasattr(stmt, "text") else stmt)
        # Normalise whitespace, uppercase for routing
        return " ".join(raw.split()).upper()

    @staticmethod
    def _mapping_first(row: dict) -> MagicMock:
        result = MagicMock()
        mapping = MagicMock()
        mapping.first.return_value = row
        result.mappings.return_value = mapping
        return result

    @staticmethod
    def _mapping_all(rows: list) -> MagicMock:
        result = MagicMock()
        mapping = MagicMock()
        mapping.all.return_value = rows
        result.mappings.return_value = mapping
        return result

    @staticmethod
    def _empty_result() -> MagicMock:
        result = MagicMock()
        mapping = MagicMock()
        mapping.first.return_value = None
        mapping.all.return_value = []
        result.mappings.return_value = mapping
        result.fetchall.return_value = []
        result.scalar.return_value = 0
        return result

    # ------------------------------------------------------------------
    # Seed helper (used in tests to insert rows without going through the API)
    # ------------------------------------------------------------------

    def seed(
        self,
        user_id: str,
        amount: float = 5.0,
        savings_type: str = "switching",
        currency: str = "USD",
        region: str = "US_CT",
        days_ago: int = 0,
    ) -> dict:
        """Add a savings row directly to the in-memory store."""
        now = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
        row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "savings_type": savings_type,
            "amount": Decimal(str(amount)),
            "currency": currency,
            "description": f"Seeded record (days_ago={days_ago})",
            "region": region,
            "period_start": now - timedelta(days=30),
            "period_end": now,
            "created_at": now,
        }
        self._rows.append(row)
        return row


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    """Fresh mock DB for each test."""
    return _MockDB()


@pytest.fixture()
def auth_client(mock_db):
    """TestClient with authenticated user and mock DB session."""
    from main import app

    test_user = TokenData(user_id=TEST_USER_ID, email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db_session] = lambda: mock_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture()
def unauth_client():
    """TestClient with no authentication installed."""
    from main import app

    app.dependency_overrides.pop(get_current_user, None)

    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _period():
    """Return (period_start, period_end) ISO strings suitable for record_savings."""
    now = datetime.now(tz=timezone.utc)
    return (now - timedelta(days=30)).isoformat(), now.isoformat()


# =============================================================================
# GET /api/v1/savings/summary
# =============================================================================


class TestSavingsSummary:
    """Tests for GET /api/v1/savings/summary."""

    def test_savings_summary_empty(self, auth_client):
        """A new user with no savings records should get all-zero totals."""
        response = auth_client.get("/api/v1/savings/summary")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0.0
        assert data["weekly"] == 0.0
        assert data["monthly"] == 0.0
        assert data["streak_days"] == 0
        assert data["currency"] == "USD"

    def test_savings_summary_with_data(self, auth_client, mock_db):
        """User with savings records should receive correct aggregated totals."""
        # Seed three records: two within the last 7 days, one older
        mock_db.seed(TEST_USER_ID, amount=10.0, days_ago=0)
        mock_db.seed(TEST_USER_ID, amount=5.0, days_ago=3)
        mock_db.seed(TEST_USER_ID, amount=20.0, days_ago=15)

        response = auth_client.get("/api/v1/savings/summary")
        assert response.status_code == 200

        data = response.json()
        # Total = 10 + 5 + 20 = 35
        assert data["total"] == pytest.approx(35.0, abs=0.01)
        # Weekly = 10 + 5 = 15 (within 7 days)
        assert data["weekly"] == pytest.approx(15.0, abs=0.01)
        # Monthly = 10 + 5 + 20 = 35 (all within 30 days)
        assert data["monthly"] == pytest.approx(35.0, abs=0.01)
        assert data["currency"] == "USD"

    def test_savings_summary_streak_consecutive(self, auth_client, mock_db):
        """Consecutive daily records should be counted as a streak."""
        # Three consecutive days ending today
        mock_db.seed(TEST_USER_ID, amount=1.0, days_ago=0)
        mock_db.seed(TEST_USER_ID, amount=1.0, days_ago=1)
        mock_db.seed(TEST_USER_ID, amount=1.0, days_ago=2)

        response = auth_client.get("/api/v1/savings/summary")
        assert response.status_code == 200

        data = response.json()
        assert data["streak_days"] == 3

    def test_savings_summary_streak_broken(self, auth_client, mock_db):
        """A gap in daily records should reset the streak count to the most recent run."""
        # Days 0 and 1 are present but day 2 is missing; days 3 and 4 are also present
        mock_db.seed(TEST_USER_ID, amount=1.0, days_ago=0)
        mock_db.seed(TEST_USER_ID, amount=1.0, days_ago=1)
        # day 2 missing — streak breaks here
        mock_db.seed(TEST_USER_ID, amount=1.0, days_ago=3)
        mock_db.seed(TEST_USER_ID, amount=1.0, days_ago=4)

        response = auth_client.get("/api/v1/savings/summary")
        assert response.status_code == 200

        data = response.json()
        # Streak is only the run ending today: days 0 and 1 = 2
        assert data["streak_days"] == 2

    def test_savings_summary_region_filter(self, auth_client, mock_db):
        """Passing a region query param should filter aggregate to that region only."""
        mock_db.seed(TEST_USER_ID, amount=10.0, region="US_CT")
        mock_db.seed(TEST_USER_ID, amount=50.0, region="US_NY")

        response = auth_client.get("/api/v1/savings/summary?region=US_CT")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == pytest.approx(10.0, abs=0.01)

    def test_savings_summary_requires_auth(self, unauth_client):
        """Unauthenticated request should return 401."""
        response = unauth_client.get("/api/v1/savings/summary")
        assert response.status_code in (401, 503)


# =============================================================================
# GET /api/v1/savings/history
# =============================================================================


class TestSavingsHistory:
    """Tests for GET /api/v1/savings/history."""

    def test_savings_history_empty(self, auth_client):
        """A new user should receive an empty items list with correct metadata."""
        response = auth_client.get("/api/v1/savings/history")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["pages"] == 1  # at least 1 page even when empty

    def test_savings_history_returns_records(self, auth_client, mock_db):
        """User with savings records should see them in the history response."""
        mock_db.seed(TEST_USER_ID, amount=7.50, savings_type="usage")
        mock_db.seed(TEST_USER_ID, amount=12.00, savings_type="switching")

        response = auth_client.get("/api/v1/savings/history")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

        # Each item should have the expected shape
        item = data["items"][0]
        assert "id" in item
        assert "user_id" in item
        assert "savings_type" in item
        assert "amount" in item
        assert "currency" in item
        assert "created_at" in item

    def test_savings_history_paginated(self, auth_client, mock_db):
        """Pagination should correctly slice results and report page metadata."""
        # Seed 5 records
        for i in range(5):
            mock_db.seed(TEST_USER_ID, amount=float(i + 1), days_ago=i)

        # Request page 1 with page_size=2
        response = auth_client.get("/api/v1/savings/history?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["pages"] == 3  # ceil(5 / 2) = 3
        assert len(data["items"]) == 2

        # Request page 2 with page_size=2
        response2 = auth_client.get("/api/v1/savings/history?page=2&page_size=2")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["page"] == 2
        assert len(data2["items"]) == 2

        # Page 1 and page 2 items should not overlap
        ids_p1 = {item["id"] for item in data["items"]}
        ids_p2 = {item["id"] for item in data2["items"]}
        assert ids_p1.isdisjoint(ids_p2)

    def test_savings_history_last_page_partial(self, auth_client, mock_db):
        """The last page should contain only the remaining records."""
        for i in range(5):
            mock_db.seed(TEST_USER_ID, amount=float(i + 1), days_ago=i)

        response = auth_client.get("/api/v1/savings/history?page=3&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1  # 5 records, page 3 has only 1

    def test_savings_history_page_size_clamped(self, auth_client, mock_db):
        """page_size > 100 should be rejected (query param ge/le validation)."""
        response = auth_client.get("/api/v1/savings/history?page_size=9999")
        assert response.status_code == 422

    def test_savings_history_requires_auth(self, unauth_client):
        """Unauthenticated request should return 401."""
        response = unauth_client.get("/api/v1/savings/history")
        assert response.status_code in (401, 503)

    def test_savings_history_user_isolation(self, mock_db):
        """Records belonging to another user should not appear in the response."""
        other_user_id = "dddddddd-0000-0000-0000-000000000004"

        # Seed a record for the OTHER user only
        mock_db.seed(other_user_id, amount=99.0)

        from main import app

        my_user = TokenData(user_id=TEST_USER_ID, email="me@example.com")
        app.dependency_overrides[get_current_user] = lambda: my_user
        app.dependency_overrides[get_db_session] = lambda: mock_db

        try:
            with TestClient(app) as client:
                response = client.get("/api/v1/savings/history")
                assert response.status_code == 200
                data = response.json()
                # TEST_USER_ID has no records — should be empty
                assert data["total"] == 0
                assert data["items"] == []
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db_session, None)
