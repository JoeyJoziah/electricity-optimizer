"""Tests for the Savings API (backend/api/v1/savings.py).

Covers:
- GET /savings/summary   (pro tier, with region filter, no region)
- GET /savings/history   (pro tier, pagination params, boundary values)
- GET /savings/combined  (free tier / any auth)
- Auth-wall: 401 when unauthenticated
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = str(uuid.uuid4())
_TEST_USER = SessionData(user_id=_USER_ID, email="savings@example.com")


def _pro_db_mock():
    """DB mock whose tier query returns 'pro' (satisfies require_tier guard)."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "pro"
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pro_client():
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: _pro_db_mock()
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def free_client():
    """Client authenticated but with no tier override (free = any auth user)."""
    from main import app

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client():
    from main import app

    client = TestClient(app, raise_server_exceptions=False)
    yield client


# ---------------------------------------------------------------------------
# GET /savings/summary
# ---------------------------------------------------------------------------

_SUMMARY_PAYLOAD = {
    "total": "123.45",
    "weekly": "10.00",
    "monthly": "45.00",
    "streak_days": 7,
    "currency": "USD",
}


class TestSavingsSummary:
    def test_returns_summary_for_pro_user(self, pro_client):
        with patch(
            "services.savings_service.SavingsService.get_savings_summary",
            new=AsyncMock(return_value=_SUMMARY_PAYLOAD),
        ):
            resp = pro_client.get("/api/v1/savings/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == "123.45"
        assert body["streak_days"] == 7
        assert body["currency"] == "USD"

    def test_filters_by_region_query_param(self, pro_client):
        with patch(
            "services.savings_service.SavingsService.get_savings_summary",
            new=AsyncMock(return_value=_SUMMARY_PAYLOAD),
        ) as mock_svc:
            resp = pro_client.get("/api/v1/savings/summary?region=US_CT")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(user_id=_USER_ID, region="US_CT")

    def test_summary_without_region_passes_none(self, pro_client):
        with patch(
            "services.savings_service.SavingsService.get_savings_summary",
            new=AsyncMock(return_value=_SUMMARY_PAYLOAD),
        ) as mock_svc:
            resp = pro_client.get("/api/v1/savings/summary")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(user_id=_USER_ID, region=None)

    def test_empty_summary_returns_200(self, pro_client):
        empty = {
            "total": "0.00",
            "weekly": "0.00",
            "monthly": "0.00",
            "streak_days": 0,
            "currency": "USD",
        }
        with patch(
            "services.savings_service.SavingsService.get_savings_summary",
            new=AsyncMock(return_value=empty),
        ):
            resp = pro_client.get("/api/v1/savings/summary")
        assert resp.status_code == 200
        assert resp.json()["streak_days"] == 0

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/savings/summary")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /savings/history
# ---------------------------------------------------------------------------

_HISTORY_PAYLOAD = {
    "items": [
        {
            "id": str(uuid.uuid4()),
            "amount": "12.50",
            "utility_type": "electricity",
            "saved_at": "2026-05-01",
        },
        {
            "id": str(uuid.uuid4()),
            "amount": "5.00",
            "utility_type": "natural_gas",
            "saved_at": "2026-05-02",
        },
    ],
    "total": 2,
    "page": 1,
    "page_size": 20,
    "pages": 1,
}


class TestSavingsHistory:
    def test_returns_paginated_history(self, pro_client):
        with patch(
            "services.savings_service.SavingsService.get_savings_history",
            new=AsyncMock(return_value=_HISTORY_PAYLOAD),
        ):
            resp = pro_client.get("/api/v1/savings/history")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 2
        assert body["pages"] == 1

    def test_passes_page_and_page_size_params(self, pro_client):
        with patch(
            "services.savings_service.SavingsService.get_savings_history",
            new=AsyncMock(return_value=_HISTORY_PAYLOAD),
        ) as mock_svc:
            resp = pro_client.get("/api/v1/savings/history?page=2&page_size=5")
        assert resp.status_code == 200
        mock_svc.assert_awaited_once_with(user_id=_USER_ID, page=2, page_size=5)

    def test_page_size_max_boundary_100(self, pro_client):
        with patch(
            "services.savings_service.SavingsService.get_savings_history",
            new=AsyncMock(return_value=_HISTORY_PAYLOAD),
        ):
            resp = pro_client.get("/api/v1/savings/history?page_size=100")
        assert resp.status_code == 200

    def test_page_size_over_max_returns_422(self, pro_client):
        with patch(
            "services.savings_service.SavingsService.get_savings_history",
            new=AsyncMock(return_value=_HISTORY_PAYLOAD),
        ):
            resp = pro_client.get("/api/v1/savings/history?page_size=101")
        assert resp.status_code == 422

    def test_page_zero_returns_422(self, pro_client):
        with patch(
            "services.savings_service.SavingsService.get_savings_history",
            new=AsyncMock(return_value=_HISTORY_PAYLOAD),
        ):
            resp = pro_client.get("/api/v1/savings/history?page=0")
        assert resp.status_code == 422

    def test_empty_history_returns_200(self, pro_client):
        empty = {"items": [], "total": 0, "page": 1, "page_size": 20, "pages": 0}
        with patch(
            "services.savings_service.SavingsService.get_savings_history",
            new=AsyncMock(return_value=empty),
        ):
            resp = pro_client.get("/api/v1/savings/history")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/savings/history")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /savings/combined
# ---------------------------------------------------------------------------

_COMBINED_PAYLOAD = {
    "electricity": {"total": "80.00", "currency": "USD"},
    "natural_gas": {"total": "30.00", "currency": "USD"},
    "heating_oil": {"total": "15.00", "currency": "USD"},
    "propane": {"total": "0.00", "currency": "USD"},
}


class TestSavingsCombined:
    def test_returns_combined_across_utility_types(self, free_client):
        with patch(
            "services.savings_aggregator.SavingsAggregator.get_combined_savings",
            new=AsyncMock(return_value=_COMBINED_PAYLOAD),
        ):
            resp = free_client.get("/api/v1/savings/combined")
        assert resp.status_code == 200
        body = resp.json()
        assert "electricity" in body
        assert "natural_gas" in body

    def test_passes_user_id_to_aggregator(self, free_client):
        with patch(
            "services.savings_aggregator.SavingsAggregator.get_combined_savings",
            new=AsyncMock(return_value=_COMBINED_PAYLOAD),
        ) as mock_agg:
            resp = free_client.get("/api/v1/savings/combined")
        assert resp.status_code == 200
        call_kwargs = mock_agg.call_args.kwargs
        assert call_kwargs["user_id"] == _USER_ID

    def test_empty_combined_returns_200(self, free_client):
        with patch(
            "services.savings_aggregator.SavingsAggregator.get_combined_savings",
            new=AsyncMock(return_value={}),
        ):
            resp = free_client.get("/api/v1/savings/combined")
        assert resp.status_code == 200

    def test_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/savings/combined")
        assert resp.status_code in (401, 403)
