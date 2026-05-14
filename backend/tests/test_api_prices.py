"""Tests for the Prices API (backend/api/v1/prices.py).

Mounted at: /api/v1/prices

Covers:
- GET /prices/current          (all suppliers, specific supplier, 404, fallback)
- GET /prices/history          (default window, explicit dates, invalid range, pagination)
- GET /prices/forecast         (pro tier, free tier denied, 404 when missing)
- GET /prices/compare          (live, fallback)
- POST /prices/refresh         (api key, success, sync error → 503)
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import (
    SessionData,
    get_current_user,
    get_db_session,
    get_price_service,
    verify_api_key,
)
from models.price import Price, PriceForecast
from models.region import Region

_BASE = "/api/v1/prices"
_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="prices@example.com")


def _make_price(supplier: str = "Eversource Energy", price: str = "0.2600") -> Price:
    return Price(
        region=Region.US_CT,
        supplier=supplier,
        price_per_kwh=Decimal(price),
        timestamp=datetime.now(UTC),
        currency="USD",
        is_peak=False,
        carbon_intensity=180.0,
    )


def _pro_db_mock():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "pro"
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _free_db_mock():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "free"
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


async def _noop_verify_api_key():
    return True


@pytest.fixture
def price_service_mock():
    return AsyncMock()


@pytest.fixture
def client(price_service_mock):
    from main import app

    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    app.dependency_overrides[get_price_service] = lambda: price_service_mock
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_price_service, None)


@pytest.fixture
def pro_client(price_service_mock):
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _pro_db_mock()
    app.dependency_overrides[get_price_service] = lambda: price_service_mock
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_price_service, None)


@pytest.fixture
def free_client(price_service_mock):
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _free_db_mock()
    app.dependency_overrides[get_price_service] = lambda: price_service_mock
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_price_service, None)


@pytest.fixture
def api_key_client():
    from main import app

    db = AsyncMock()
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[verify_api_key] = _noop_verify_api_key
    c = TestClient(app)
    yield c, db
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(verify_api_key, None)


# ---------------------------------------------------------------------------
# GET /prices/current
# ---------------------------------------------------------------------------


class TestGetCurrentPrices:
    def test_returns_prices_for_region(self, client, price_service_mock):
        price_service_mock.get_current_prices = AsyncMock(
            return_value=[_make_price(), _make_price("UI", "0.2800")]
        )
        resp = client.get(f"{_BASE}/current?region=us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["region"] == "us_ct"
        assert body["source"] == "live"
        assert len(body["prices"]) == 2

    def test_filters_by_supplier_returns_single_price(self, client, price_service_mock):
        price_service_mock.get_current_price = AsyncMock(return_value=_make_price("UI", "0.30"))
        resp = client.get(f"{_BASE}/current?region=us_ct&supplier=UI")
        assert resp.status_code == 200
        body = resp.json()
        assert body["price"]["supplier"] == "UI"
        price_service_mock.get_current_price.assert_awaited_once()

    def test_supplier_not_found_returns_404(self, client, price_service_mock):
        price_service_mock.get_current_price = AsyncMock(return_value=None)
        resp = client.get(f"{_BASE}/current?region=us_ct&supplier=Nope")
        assert resp.status_code == 404
        assert "Nope" in resp.json()["detail"]

    def test_invalid_region_returns_422(self, client):
        resp = client.get(f"{_BASE}/current?region=mars")
        assert resp.status_code == 422

    def test_limit_out_of_range_returns_422(self, client):
        resp = client.get(f"{_BASE}/current?region=us_ct&limit=999")
        assert resp.status_code == 422

    def test_service_exception_returns_fallback_in_dev(self, client, price_service_mock):
        price_service_mock.get_current_prices = AsyncMock(side_effect=RuntimeError("db down"))
        with patch("api.v1.prices.settings.environment", "development"):
            resp = client.get(f"{_BASE}/current?region=us_ct")
        assert resp.status_code == 200
        assert resp.json()["source"] == "fallback"

    def test_service_exception_returns_503_in_production(self, client, price_service_mock):
        price_service_mock.get_current_prices = AsyncMock(side_effect=RuntimeError("db down"))
        with patch("api.v1.prices.settings.environment", "production"):
            resp = client.get(f"{_BASE}/current?region=us_ct")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /prices/history
# ---------------------------------------------------------------------------


class TestGetPriceHistory:
    def test_default_window_returns_paginated_history(self, client, price_service_mock):
        prices = [_make_price() for _ in range(5)]
        price_service_mock.get_historical_prices_paginated = AsyncMock(return_value=(prices, 5))
        resp = client.get(f"{_BASE}/history?region=us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["region"] == "us_ct"
        assert body["total"] == 5
        assert body["page"] == 1
        assert body["pages"] == 1
        assert body["source"] == "live"

    def test_invalid_date_range_returns_400(self, client, price_service_mock):
        start = "2026-05-10T00:00:00"
        end = "2026-05-01T00:00:00"
        resp = client.get(f"{_BASE}/history?region=us_ct&start_date={start}&end_date={end}")
        assert resp.status_code == 400
        assert "start_date" in resp.json()["detail"]

    def test_explicit_date_range_overrides_days(self, client, price_service_mock):
        price_service_mock.get_historical_prices_paginated = AsyncMock(return_value=([], 0))
        price_service_mock.get_price_statistics = AsyncMock(
            return_value={
                "avg_price": Decimal("0.25"),
                "min_price": Decimal("0.20"),
                "max_price": Decimal("0.30"),
            }
        )
        start = "2026-05-01T00:00:00"
        end = "2026-05-05T00:00:00"
        resp = client.get(f"{_BASE}/history?region=us_ct&days=30&start_date={start}&end_date={end}")
        assert resp.status_code == 200
        call_kwargs = price_service_mock.get_historical_prices_paginated.call_args.kwargs
        # explicit dates win over days=30
        assert call_kwargs["start_date"].isoformat().startswith("2026-05-01")
        assert call_kwargs["end_date"].isoformat().startswith("2026-05-05")

    def test_pagination_params_propagate(self, client, price_service_mock):
        price_service_mock.get_historical_prices_paginated = AsyncMock(return_value=([], 0))
        price_service_mock.get_price_statistics = AsyncMock(return_value={})
        resp = client.get(f"{_BASE}/history?region=us_ct&page=2&page_size=50")
        assert resp.status_code == 200
        call_kwargs = price_service_mock.get_historical_prices_paginated.call_args.kwargs
        assert call_kwargs["page"] == 2
        assert call_kwargs["page_size"] == 50

    def test_page_size_above_100_returns_422(self, client):
        resp = client.get(f"{_BASE}/history?region=us_ct&page_size=500")
        assert resp.status_code == 422

    def test_days_above_365_returns_422(self, client):
        resp = client.get(f"{_BASE}/history?region=us_ct&days=400")
        assert resp.status_code == 422

    def test_service_exception_returns_fallback_in_dev(self, client, price_service_mock):
        price_service_mock.get_historical_prices_paginated = AsyncMock(
            side_effect=RuntimeError("db down")
        )
        with patch("api.v1.prices.settings.environment", "development"):
            resp = client.get(f"{_BASE}/history?region=us_ct&days=2")
        assert resp.status_code == 200
        assert resp.json()["source"] == "fallback"

    def test_service_exception_returns_503_in_production(self, client, price_service_mock):
        price_service_mock.get_historical_prices_paginated = AsyncMock(
            side_effect=RuntimeError("db down")
        )
        with patch("api.v1.prices.settings.environment", "production"):
            resp = client.get(f"{_BASE}/history?region=us_ct")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /prices/forecast
# ---------------------------------------------------------------------------


def _make_forecast(hours: int = 24) -> PriceForecast:
    return PriceForecast(
        region=Region.US_CT,
        generated_at=datetime.now(UTC),
        horizon_hours=hours,
        prices=[_make_price() for _ in range(hours)],
        confidence=0.9,
        model_version="v1.0.0",
    )


class TestGetPriceForecast:
    def test_pro_user_gets_forecast(self, pro_client, price_service_mock):
        price_service_mock.get_price_forecast = AsyncMock(return_value=_make_forecast(24))
        resp = pro_client.get(f"{_BASE}/forecast?region=us_ct&hours=24")
        assert resp.status_code == 200
        body = resp.json()
        assert body["region"] == "us_ct"
        assert body["horizon_hours"] == 24
        assert body["source"] == "live"

    def test_free_user_denied_403(self, free_client, price_service_mock):
        price_service_mock.get_price_forecast = AsyncMock(return_value=_make_forecast())
        resp = free_client.get(f"{_BASE}/forecast?region=us_ct")
        assert resp.status_code == 403

    def test_no_forecast_returns_404(self, pro_client, price_service_mock):
        price_service_mock.get_price_forecast = AsyncMock(return_value=None)
        resp = pro_client.get(f"{_BASE}/forecast?region=us_ct")
        assert resp.status_code == 404

    def test_hours_above_168_returns_422(self, pro_client):
        resp = pro_client.get(f"{_BASE}/forecast?region=us_ct&hours=200")
        assert resp.status_code == 422

    def test_service_exception_returns_fallback_in_dev(self, pro_client, price_service_mock):
        price_service_mock.get_price_forecast = AsyncMock(side_effect=RuntimeError("ml down"))
        with patch("api.v1.prices.settings.environment", "development"):
            resp = pro_client.get(f"{_BASE}/forecast?region=us_ct&hours=12")
        assert resp.status_code == 200
        assert resp.json()["source"] == "fallback"
        assert resp.json()["horizon_hours"] == 12

    def test_service_exception_returns_503_in_production(self, pro_client, price_service_mock):
        price_service_mock.get_price_forecast = AsyncMock(side_effect=RuntimeError("ml down"))
        with patch("api.v1.prices.settings.environment", "production"):
            resp = pro_client.get(f"{_BASE}/forecast?region=us_ct")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /prices/compare
# ---------------------------------------------------------------------------


class TestComparePrices:
    def test_returns_sorted_comparison(self, client, price_service_mock):
        cheap = _make_price("Cheap Co", "0.20")
        mid = _make_price("Mid Co", "0.25")
        price_service_mock.get_price_comparison = AsyncMock(return_value=[cheap, mid])
        resp = client.get(f"{_BASE}/compare?region=us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cheapest_supplier"] == "Cheap Co"
        assert Decimal(str(body["cheapest_price"])) == Decimal("0.2000")
        assert body["source"] == "live"
        assert len(body["suppliers"]) == 2

    def test_empty_comparison_falls_back_in_dev(self, client, price_service_mock):
        price_service_mock.get_price_comparison = AsyncMock(return_value=[])
        with patch("api.v1.prices.settings.environment", "development"):
            resp = client.get(f"{_BASE}/compare?region=us_ct")
        assert resp.status_code == 200
        assert resp.json()["source"] == "fallback"

    def test_empty_comparison_returns_503_in_production(self, client, price_service_mock):
        price_service_mock.get_price_comparison = AsyncMock(return_value=[])
        with patch("api.v1.prices.settings.environment", "production"):
            resp = client.get(f"{_BASE}/compare?region=us_ct")
        assert resp.status_code == 503

    def test_invalid_region_returns_422(self, client):
        resp = client.get(f"{_BASE}/compare?region=atlantis")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /prices/refresh
# ---------------------------------------------------------------------------


class TestRefreshPrices:
    def test_refresh_success_returns_result(self, api_key_client):
        client, _db = api_key_client
        with patch(
            "services.price_sync_service.sync_prices",
            new=AsyncMock(return_value={"status": "ok", "synced": 12}),
        ):
            resp = client.post(f"{_BASE}/refresh")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["synced"] == 12

    def test_refresh_error_returns_503(self, api_key_client):
        client, _db = api_key_client
        with patch(
            "services.price_sync_service.sync_prices",
            new=AsyncMock(return_value={"status": "error", "reason": "upstream 500"}),
        ):
            resp = client.post(f"{_BASE}/refresh")
        assert resp.status_code == 503
        assert resp.json()["status"] == "error"

    def test_refresh_empty_returns_503(self, api_key_client):
        client, _db = api_key_client
        with patch(
            "services.price_sync_service.sync_prices",
            new=AsyncMock(return_value={"status": "empty", "synced": 0}),
        ):
            resp = client.post(f"{_BASE}/refresh")
        assert resp.status_code == 503
