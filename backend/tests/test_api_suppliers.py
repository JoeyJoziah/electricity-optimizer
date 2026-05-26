"""Tests for the Supplier API (backend/api/v1/suppliers.py).

Mounted at: /api/v1/suppliers  (public, uses Redis cache mock)

Covers:
- GET /suppliers/               (list; pagination; utility_type filter)
- GET /suppliers/region/{region}  (valid region; invalid region code 422)
- GET /suppliers/compare/{region} (returns comparison list sorted by rate)
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session, get_redis
from models.supplier_offer import SupplierOffer

_OFFER_REPO = (
    "repositories.supplier_offer_repository.SupplierOfferRepository.cheapest_available_by_supplier"
)

_BASE = "/api/v1/suppliers"

_SUPPLIER_ROW = {
    "id": "sup-001",
    "name": "Eversource",
    "utility_types": ["electricity"],
    "regions": ["us_ct"],
    "tariff_types": ["variable", "fixed"],
    "api_available": True,
    "rating": 4.2,
    "green_energy_provider": False,
    "is_active": True,
}


@pytest.fixture
def client():
    from main import app

    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    app.dependency_overrides[get_redis] = lambda: AsyncMock()
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# GET /suppliers/
# ---------------------------------------------------------------------------


class TestListSuppliers:
    def test_returns_suppliers_list(self, client):
        with patch(
            "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
            new=AsyncMock(return_value=([_SUPPLIER_ROW], 1)),
        ):
            resp = client.get(f"{_BASE}/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["suppliers"]) == 1

    def test_empty_suppliers_returns_200(self, client):
        with patch(
            "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
            new=AsyncMock(return_value=([], 0)),
        ):
            resp = client.get(f"{_BASE}/")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_utility_type_filter_accepted(self, client):
        with patch(
            "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
            new=AsyncMock(return_value=([_SUPPLIER_ROW], 1)),
        ) as mock_repo:
            resp = client.get(f"{_BASE}/?utility_type=electricity")
        assert resp.status_code == 200
        call_kwargs = mock_repo.call_args.kwargs
        assert call_kwargs["utility_type"] == "electricity"

    def test_page_size_over_max_returns_422(self, client):
        resp = client.get(f"{_BASE}/?page_size=101")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /suppliers/region/{region}
# ---------------------------------------------------------------------------


class TestGetSuppliersByRegion:
    def test_valid_region_returns_suppliers(self, client):
        with patch(
            "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
            new=AsyncMock(return_value=([_SUPPLIER_ROW], 1)),
        ):
            resp = client.get(f"{_BASE}/region/us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["region"] == "us_ct"
        assert body["total"] == 1

    def test_invalid_region_code_returns_422(self, client):
        resp = client.get(f"{_BASE}/region/INVALID_REGION")
        assert resp.status_code == 422

    def test_utility_type_filter_passed_through(self, client):
        with patch(
            "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
            new=AsyncMock(return_value=([], 0)),
        ) as mock_repo:
            resp = client.get(f"{_BASE}/region/us_ct?utility_type=natural_gas")
        assert resp.status_code == 200
        assert mock_repo.call_args.kwargs["utility_type"] == "natural_gas"


# ---------------------------------------------------------------------------
# GET /suppliers/compare/{region}
# ---------------------------------------------------------------------------


class TestCompareSuppliers:
    def test_returns_comparison_sorted_by_rate(self, client):
        two_suppliers = [
            {**_SUPPLIER_ROW, "id": "s1", "name": "SupplierA"},
            {**_SUPPLIER_ROW, "id": "s2", "name": "SupplierB"},
        ]
        with patch(
            "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
            new=AsyncMock(return_value=(two_suppliers, 2)),
        ):
            resp = client.get(f"{_BASE}/compare/us_ct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["region"] == "us_ct"
        assert body["total"] == 2
        assert "generated_at" in body

    def test_empty_suppliers_comparison_returns_200(self, client):
        with patch(
            "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
            new=AsyncMock(return_value=([], 0)),
        ):
            resp = client.get(f"{_BASE}/compare/us_ct")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# POST /suppliers/recommend  (audit 2026-05-21: was 405)
# ---------------------------------------------------------------------------


class TestRecommendEndpoint:
    def test_post_recommend_returns_200_not_405(self, client):
        """Regression: the route exists, so POST is no longer 405 (it used to
        fall through to GET /{supplier_id})."""
        with patch(_OFFER_REPO, new=AsyncMock(return_value={})):
            resp = client.post(
                f"{_BASE}/recommend",
                json={
                    "currentSupplierId": "sup-001",
                    "annualUsage": 10500,
                    "region": "us_ct",
                },
            )
        assert resp.status_code == 200
        assert "recommendation" in resp.json()

    def test_post_recommend_accepts_empty_body(self, client):
        resp = client.post(f"{_BASE}/recommend", json={})
        assert resp.status_code == 200
        assert resp.json()["recommendation"] is None

    def test_null_when_only_estimates(self, client):
        """Estimates are not an actionable switch basis → recommendation is null."""
        offers = {
            "sup-001": SupplierOffer(
                supplier_name="Eversource",
                supplier_id="sup-001",
                rate_per_kwh=0.30,
                source="regional_estimate",
                is_estimate=True,
            ),
            "sup-002": SupplierOffer(
                supplier_name="Cheap Co",
                supplier_id="sup-002",
                rate_per_kwh=0.20,
                source="regional_estimate",
                is_estimate=True,
            ),
        }
        with patch(_OFFER_REPO, new=AsyncMock(return_value=offers)):
            resp = client.post(
                f"{_BASE}/recommend",
                json={"currentSupplierId": "sup-001", "region": "us_ct"},
            )
        assert resp.status_code == 200
        assert resp.json()["recommendation"] is None

    def test_recommendation_from_real_offers(self, client):
        """A cheaper real offer than the current supplier yields a recommendation."""
        offers = {
            "sup-001": SupplierOffer(
                supplier_name="Eversource",
                supplier_id="sup-001",
                rate_per_kwh=0.30,
                source="ct_rate_board",
                is_estimate=False,
            ),
            "sup-002": SupplierOffer(
                supplier_name="Cheap Co",
                supplier_id="sup-002",
                rate_per_kwh=0.20,
                source="ct_rate_board",
                is_estimate=False,
                enroll_url="https://cheap.example/enroll",
            ),
        }
        with patch(_OFFER_REPO, new=AsyncMock(return_value=offers)):
            resp = client.post(
                f"{_BASE}/recommend",
                json={
                    "currentSupplierId": "sup-001",
                    "annualUsage": 10000,
                    "region": "us_ct",
                },
            )
        assert resp.status_code == 200
        rec = resp.json()["recommendation"]
        assert rec is not None
        assert rec["supplier"]["name"] == "Cheap Co"
        # (0.30 - 0.20) * 10000 = 1000.0
        assert rec["estimatedSavings"] == 1000.0
        assert rec["pricingSource"] == "ct_rate_board"
        assert rec["supplier"]["enrollUrl"] == "https://cheap.example/enroll"

    def test_null_when_current_already_cheapest(self, client):
        offers = {
            "sup-002": SupplierOffer(
                supplier_name="Cheap Co",
                supplier_id="sup-002",
                rate_per_kwh=0.20,
                source="ct_rate_board",
                is_estimate=False,
            ),
        }
        with patch(_OFFER_REPO, new=AsyncMock(return_value=offers)):
            resp = client.post(
                f"{_BASE}/recommend",
                json={"currentSupplierId": "sup-002", "region": "us_ct"},
            )
        assert resp.status_code == 200
        assert resp.json()["recommendation"] is None


# ---------------------------------------------------------------------------
# GET /suppliers/ pricing via supplier_offers (audit 2026-05-21: prices were $0.00)
# ---------------------------------------------------------------------------


class TestSupplierPricing:
    def test_offer_pricing_applied_with_source_and_estimate_flag(self, client):
        offers = {
            "sup-001": SupplierOffer(
                supplier_name="Eversource",
                supplier_id="sup-001",
                rate_per_kwh=0.25,
                source="regional_estimate",
                is_estimate=True,
            )
        }
        with (
            patch(
                "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
                new=AsyncMock(return_value=([dict(_SUPPLIER_ROW)], 1)),
            ),
            patch(_OFFER_REPO, new=AsyncMock(return_value=offers)),
        ):
            resp = client.get(f"{_BASE}/?region=us_ct&annual_usage=10500")
        assert resp.status_code == 200
        supplier = resp.json()["suppliers"][0]
        assert supplier["avg_price_per_kwh"] == 0.25
        assert supplier["estimated_annual_cost"] == 2625.0  # 0.25 * 10500
        assert supplier["pricing_source"] == "regional_estimate"
        assert supplier["is_estimate"] is True

    def test_price_null_when_no_offer(self, client):
        with (
            patch(
                "repositories.supplier_repository.SupplierRegistryRepository.list_suppliers",
                new=AsyncMock(return_value=([dict(_SUPPLIER_ROW)], 1)),
            ),
            patch(_OFFER_REPO, new=AsyncMock(return_value={})),
        ):
            resp = client.get(f"{_BASE}/?region=us_ct&annual_usage=10500")
        assert resp.status_code == 200
        supplier = resp.json()["suppliers"][0]
        assert supplier["avg_price_per_kwh"] is None
        assert supplier["estimated_annual_cost"] is None
        assert supplier["pricing_source"] is None
        assert supplier["is_estimate"] is False
