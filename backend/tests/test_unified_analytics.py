"""
Tests for unified connection analytics — multi-source rate aggregation.

Coverage:
  - GET /connections/{id}/rates returns rates from all source types:
      - email_scan
      - email_attachment
      - api_pull
      - bill_parse
  - Different sources are correctly surfaced in response data_points
  - GET /connections/{id}/rates/current respects source field
  - ConnectionAnalyticsService.get_rate_history surfaces all source types
  - ConnectionAnalyticsService.get_rate_comparison works regardless of source
  - Source field is preserved verbatim in API responses (no normalisation)
  - Pagination works correctly with multi-source datasets

All DB calls are mocked; no real Postgres connection is required.
Auth is injected by overriding get_current_user / require_paid_tier.
"""

import math
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stable test IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "dddddddd-9999-0000-0000-000000000042"
TEST_CONNECTION_ID = str(uuid4())
TEST_CONNECTION_ID_2 = str(uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DictRow(dict):
    """Dict subclass that behaves like a SQLAlchemy RowMapping."""


def _row(**kwargs) -> "_DictRow":
    return _DictRow(kwargs)


def _mapping_result(rows: list) -> MagicMock:
    result = MagicMock()
    mock_rows = [_DictRow(r) for r in rows]
    result.mappings.return_value.all.return_value = mock_rows
    result.mappings.return_value.first.return_value = mock_rows[0] if mock_rows else None
    result.fetchone.return_value = mock_rows[0] if mock_rows else None
    result.scalar.return_value = len(mock_rows)
    result.scalar_one_or_none.return_value = None
    return result


def _empty_mapping_result() -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    result.mappings.return_value.first.return_value = None
    result.fetchone.return_value = None
    result.scalar.return_value = 0
    result.scalar_one_or_none.return_value = None
    return result


def _scalar_result(value) -> MagicMock:
    result = MagicMock()
    row = MagicMock()
    row.__getitem__ = lambda self, k: value
    result.fetchone.return_value = row
    result.scalar_one_or_none.return_value = value
    result.scalar.return_value = value
    return result


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _session_data(user_id: str = TEST_USER_ID, tier: str = "pro"):
    from auth.neon_auth import SessionData

    sd = SessionData(
        user_id=user_id,
        email=f"{user_id[:8]}@example.com",
        name="Analytics Tester",
        email_verified=True,
        role="user",
    )
    sd._tier = tier
    return sd


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_overrides():
    from main import app, _app_rate_limiter

    _app_rate_limiter.reset()
    yield
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)
    _app_rate_limiter.reset()


def _install_auth(tier: str = "pro", user_id: str = TEST_USER_ID):
    """Install auth + DB overrides; return the mock DB so callers can configure it."""
    from main import app
    from api.dependencies import get_current_user, get_db_session
    from api.v1.connections import require_paid_tier

    session = _session_data(user_id=user_id, tier=tier)
    db = _mock_db()

    if tier in ("pro", "business"):
        app.dependency_overrides[require_paid_tier] = lambda: session
    else:
        app.dependency_overrides[get_current_user] = lambda: session
        db.execute = AsyncMock(return_value=_scalar_result(tier))

    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db
    return db


BASE = "/api/v1/connections"

# All source types the platform supports
ALL_SOURCES = ["email_scan", "email_attachment", "api_pull", "bill_parse"]


# ===========================================================================
# 1. ConnectionAnalyticsService.get_rate_history — multi-source unit tests
# ===========================================================================


class TestRateHistoryMultiSource:
    """Unit tests verifying get_rate_history handles all source types."""

    def _make_rate_row(
        self,
        source: str,
        rate: float = 0.2000,
        days_ago: int = 0,
        connection_id: str = TEST_CONNECTION_ID,
    ) -> _DictRow:
        return _DictRow({
            "rate_per_kwh": rate,
            "supplier_name": "TestSupplier",
            "effective_date": _now() - timedelta(days=days_ago),
            "source": source,
            "connection_id": connection_id,
            "connection_type": "direct",
            "label": "Home",
        })

    @pytest.mark.asyncio
    async def test_history_returns_email_scan_rates(self):
        """Rates with source='email_scan' appear in the history output."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        rows = [self._make_rate_row("email_scan", rate=0.1800)]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        output = await svc.get_rate_history(TEST_USER_ID)

        assert output["total"] == 1
        assert output["data_points"][0]["source"] == "email_scan"
        assert output["data_points"][0]["rate"] == pytest.approx(0.1800, abs=1e-6)

    @pytest.mark.asyncio
    async def test_history_returns_email_attachment_rates(self):
        """Rates with source='email_attachment' appear in the history output."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        rows = [self._make_rate_row("email_attachment", rate=0.2100)]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        output = await svc.get_rate_history(TEST_USER_ID)

        assert output["total"] == 1
        assert output["data_points"][0]["source"] == "email_attachment"

    @pytest.mark.asyncio
    async def test_history_returns_api_pull_rates(self):
        """Rates with source='api_pull' appear in the history output."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        rows = [self._make_rate_row("api_pull", rate=0.1650)]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        output = await svc.get_rate_history(TEST_USER_ID)

        assert output["total"] == 1
        assert output["data_points"][0]["source"] == "api_pull"

    @pytest.mark.asyncio
    async def test_history_returns_bill_parse_rates(self):
        """Rates with source='bill_parse' appear in the history output."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        rows = [self._make_rate_row("bill_parse", rate=0.2250)]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        output = await svc.get_rate_history(TEST_USER_ID)

        assert output["total"] == 1
        assert output["data_points"][0]["source"] == "bill_parse"

    @pytest.mark.asyncio
    async def test_history_returns_all_sources_in_mixed_batch(self):
        """All four source types coexist correctly in a single result set."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        rows = [
            self._make_rate_row("email_scan", rate=0.1800, days_ago=30),
            self._make_rate_row("email_attachment", rate=0.2100, days_ago=20),
            self._make_rate_row("api_pull", rate=0.1650, days_ago=10),
            self._make_rate_row("bill_parse", rate=0.2250, days_ago=0),
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        output = await svc.get_rate_history(TEST_USER_ID)

        assert output["total"] == 4
        found_sources = {dp["source"] for dp in output["data_points"]}
        assert found_sources == {"email_scan", "email_attachment", "api_pull", "bill_parse"}

    @pytest.mark.asyncio
    async def test_history_sources_are_not_normalised(self):
        """Source strings are preserved verbatim — no remapping or normalisation."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        # Use the exact strings returned by the DB
        for source in ALL_SOURCES:
            rows = [self._make_rate_row(source)]
            result = MagicMock()
            result.mappings.return_value.all.return_value = rows
            db.execute = AsyncMock(return_value=result)

            svc = ConnectionAnalyticsService(db)
            output = await svc.get_rate_history(TEST_USER_ID)
            assert output["data_points"][0]["source"] == source, (
                f"Source '{source}' was altered during history serialisation"
            )

    @pytest.mark.asyncio
    async def test_history_multiple_connections_multi_source(self):
        """Multi-source rates across two connections are returned without filtering."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()
        rows = [
            self._make_rate_row("bill_parse", rate=0.22, days_ago=5, connection_id=TEST_CONNECTION_ID),
            self._make_rate_row("api_pull", rate=0.18, days_ago=3, connection_id=TEST_CONNECTION_ID_2),
        ]
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        svc = ConnectionAnalyticsService(db)
        output = await svc.get_rate_history(TEST_USER_ID)

        assert output["total"] == 2
        connection_ids = {dp["connection_id"] for dp in output["data_points"]}
        assert TEST_CONNECTION_ID in connection_ids
        assert TEST_CONNECTION_ID_2 in connection_ids


# ===========================================================================
# 2. ConnectionAnalyticsService.get_rate_comparison — multi-source
# ===========================================================================


class TestRateComparisonMultiSource:
    """Verify get_rate_comparison handles rate rows originating from any source."""

    def _make_rate_region_row(self, source: str, rate: float = 0.2500) -> _DictRow:
        return _DictRow({
            "rate_per_kwh": rate,
            "supplier_name": "MultiSourceSupplier",
            "effective_date": _now(),
            "connection_id": TEST_CONNECTION_ID,
            "connection_type": "direct",
            "user_region": "US_NY",
        })

    def _make_market_row(self) -> _DictRow:
        return _DictRow({
            "avg_price": 0.2000,
            "min_price": 0.1500,
            "max_price": 0.2800,
            "sample_count": 25,
        })

    @pytest.mark.asyncio
    @pytest.mark.parametrize("source", ALL_SOURCES)
    async def test_comparison_returns_has_data_for_each_source(self, source: str):
        """Comparison always returns has_data=True regardless of rate source."""
        from services.connection_analytics_service import ConnectionAnalyticsService

        db = _mock_db()

        rate_result = MagicMock()
        rate_result.mappings.return_value.first.return_value = self._make_rate_region_row(source)

        market_result = MagicMock()
        market_result.mappings.return_value.first.return_value = self._make_market_row()

        db.execute = AsyncMock(side_effect=[rate_result, market_result])

        svc = ConnectionAnalyticsService(db)
        result = await svc.get_rate_comparison(TEST_USER_ID)

        assert result["has_data"] is True, (
            f"Expected has_data=True for source='{source}'"
        )
        assert result["user_rate"] == pytest.approx(0.2500, abs=1e-6)


# ===========================================================================
# 3. GET /connections/{id}/rates — HTTP endpoint, multi-source
# ===========================================================================


class TestGetRatesEndpointMultiSource:
    """HTTP-level tests for GET /connections/{id}/rates with multi-source data."""

    def _make_extracted_rate_row(
        self,
        source: str,
        rate: float = 0.2000,
        days_ago: int = 0,
        rate_id: str | None = None,
    ) -> _DictRow:
        return _DictRow({
            "id": rate_id or str(uuid4()),
            "connection_id": TEST_CONNECTION_ID,
            "rate_per_kwh": rate,
            "effective_date": _now() - timedelta(days=days_ago),
            "source": source,
            "raw_label": None,
        })

    def test_get_rates_returns_email_scan_source(self, client):
        """API returns rates with source='email_scan'."""
        db = _install_auth()
        rate_row = self._make_extracted_rate_row("email_scan", rate=0.1800)

        # Simulate: COUNT=1, data=[rate_row]
        count_result = _scalar_result(1)
        data_result = _mapping_result([rate_row])

        db.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["rates"][0]["source"] == "email_scan"

    def test_get_rates_returns_email_attachment_source(self, client):
        """API returns rates with source='email_attachment'."""
        db = _install_auth()
        rate_row = self._make_extracted_rate_row("email_attachment", rate=0.2100)

        count_result = _scalar_result(1)
        data_result = _mapping_result([rate_row])
        db.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates")

        assert response.status_code == 200
        data = response.json()
        assert data["rates"][0]["source"] == "email_attachment"

    def test_get_rates_returns_api_pull_source(self, client):
        """API returns rates with source='api_pull'."""
        db = _install_auth()
        rate_row = self._make_extracted_rate_row("api_pull", rate=0.1650)

        count_result = _scalar_result(1)
        data_result = _mapping_result([rate_row])
        db.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates")

        assert response.status_code == 200
        data = response.json()
        assert data["rates"][0]["source"] == "api_pull"

    def test_get_rates_returns_bill_parse_source(self, client):
        """API returns rates with source='bill_parse'."""
        db = _install_auth()
        rate_row = self._make_extracted_rate_row("bill_parse", rate=0.2250)

        count_result = _scalar_result(1)
        data_result = _mapping_result([rate_row])
        db.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates")

        assert response.status_code == 200
        data = response.json()
        assert data["rates"][0]["source"] == "bill_parse"

    def test_get_rates_returns_all_four_sources_in_single_response(self, client):
        """Mixed batch of all four source types are all present in the response."""
        db = _install_auth()

        mixed_rows = [
            self._make_extracted_rate_row("email_scan", rate=0.1800, days_ago=30),
            self._make_extracted_rate_row("email_attachment", rate=0.2100, days_ago=20),
            self._make_extracted_rate_row("api_pull", rate=0.1650, days_ago=10),
            self._make_extracted_rate_row("bill_parse", rate=0.2250, days_ago=0),
        ]

        count_result = _scalar_result(4)
        data_result = _mapping_result(mixed_rows)
        db.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 4
        assert len(body["rates"]) == 4
        returned_sources = {r["source"] for r in body["rates"]}
        assert returned_sources == {"email_scan", "email_attachment", "api_pull", "bill_parse"}

    def test_get_rates_source_field_preserved_verbatim(self, client):
        """Source strings are never normalised or remapped in the API response."""
        db = _install_auth()

        for source in ALL_SOURCES:
            rate_row = self._make_extracted_rate_row(source)
            count_result = _scalar_result(1)
            data_result = _mapping_result([rate_row])
            db.execute = AsyncMock(side_effect=[count_result, data_result])

            response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates")

            assert response.status_code == 200
            returned_source = response.json()["rates"][0]["source"]
            assert returned_source == source, (
                f"Source '{source}' was changed to '{returned_source}' in the response"
            )

    def test_get_rates_sources_can_be_differentiated_by_field(self, client):
        """Each rate in the response carries a ``source`` field consumers can use."""
        db = _install_auth()

        rows = [
            self._make_extracted_rate_row("bill_parse", rate=0.22),
            self._make_extracted_rate_row("api_pull", rate=0.18),
        ]

        count_result = _scalar_result(2)
        data_result = _mapping_result(rows)
        db.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates")

        assert response.status_code == 200
        body = response.json()
        for rate in body["rates"]:
            assert "source" in rate, "source field missing from rate response"
            assert rate["source"] in ALL_SOURCES, (
                f"Unexpected source value '{rate['source']}'"
            )

    def test_get_rates_pagination_works_with_multi_source_data(self, client):
        """Pagination metadata is correct with a multi-source dataset of 4 rates."""
        db = _install_auth()

        # Request page_size=2, so 4 rows → 2 pages
        rows = [
            self._make_extracted_rate_row("email_scan", days_ago=3),
            self._make_extracted_rate_row("api_pull", days_ago=2),
        ]

        count_result = _scalar_result(4)
        data_result = _mapping_result(rows)
        db.execute = AsyncMock(side_effect=[count_result, data_result])

        response = client.get(
            f"{BASE}/{TEST_CONNECTION_ID}/rates",
            params={"page": 1, "page_size": 2},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 4
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert body["pages"] == 2
        assert len(body["rates"]) == 2


# ===========================================================================
# 4. GET /connections/{id}/rates/current — multi-source
# ===========================================================================


class TestGetCurrentRateMultiSource:
    """Tests for GET /connections/{id}/rates/current with various source types."""

    def _make_rate_row(self, source: str, rate: float = 0.2000) -> _DictRow:
        return _DictRow({
            "id": str(uuid4()),
            "connection_id": TEST_CONNECTION_ID,
            "rate_per_kwh": rate,
            "effective_date": _now(),
            "source": source,
            "raw_label": None,
        })

    @pytest.mark.parametrize("source", ALL_SOURCES)
    def test_current_rate_returns_correct_source(self, source: str, client):
        """Most recent rate has its source field preserved for all source types."""
        db = _install_auth()

        rate_row = self._make_rate_row(source)
        data_result = MagicMock()
        data_result.mappings.return_value.first.return_value = rate_row

        db.execute = AsyncMock(return_value=data_result)

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates/current")

        assert response.status_code == 200
        body = response.json()
        assert body is not None
        assert body["source"] == source, (
            f"Expected source='{source}', got '{body['source']}'"
        )

    def test_current_rate_prefers_most_recent_regardless_of_source(self, client):
        """The current-rate endpoint returns the latest row, whatever its source."""
        db = _install_auth()

        # The DB query returns only one row (LIMIT 1 ORDER BY effective_date DESC)
        rate_row = self._make_rate_row("api_pull", rate=0.1750)
        data_result = MagicMock()
        data_result.mappings.return_value.first.return_value = rate_row

        db.execute = AsyncMock(return_value=data_result)

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/rates/current")

        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "api_pull"
        assert body["rate_per_kwh"] == pytest.approx(0.1750, abs=1e-6)
