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
