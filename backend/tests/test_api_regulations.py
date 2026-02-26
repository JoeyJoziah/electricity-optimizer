"""
Tests for the State Regulations API (backend/api/v1/regulations.py)

Tests cover:
- GET /regulations - list state regulations with optional filters
- GET /regulations/{state_code} - get single state regulation
- Response schema validation
- 404 for unknown state codes
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session


BASE_URL = "/api/v1/regulations"


# =============================================================================
# Mock Data
# =============================================================================


def _make_ct_regulation():
    """Connecticut regulation data (fully deregulated)."""
    return {
        "state_code": "CT",
        "state_name": "Connecticut",
        "electricity_deregulated": True,
        "gas_deregulated": True,
        "oil_competitive": True,
        "community_solar_enabled": True,
        "licensing_required": True,
        "bond_required": True,
        "bond_amount": 50000.0,
        "puc_name": "Connecticut PURA",
        "puc_website": "https://portal.ct.gov/pura",
        "comparison_tool_url": "https://energizect.com",
        "notes": "Full retail choice since 2000",
    }


def _make_tx_regulation():
    """Texas regulation data (electricity only)."""
    return {
        "state_code": "TX",
        "state_name": "Texas",
        "electricity_deregulated": True,
        "gas_deregulated": False,
        "oil_competitive": True,
        "community_solar_enabled": False,
        "licensing_required": True,
        "bond_required": True,
        "bond_amount": 25000.0,
        "puc_name": "Public Utility Commission of Texas",
        "puc_website": "https://www.puc.texas.gov",
        "comparison_tool_url": "https://powertochoose.org",
        "notes": "Deregulated since 2002, ERCOT grid",
    }


def _make_fl_regulation():
    """Florida regulation data (regulated market)."""
    return {
        "state_code": "FL",
        "state_name": "Florida",
        "electricity_deregulated": False,
        "gas_deregulated": False,
        "oil_competitive": True,
        "community_solar_enabled": True,
        "licensing_required": False,
        "bond_required": False,
        "bond_amount": None,
        "puc_name": "Florida Public Service Commission",
        "puc_website": "https://www.psc.state.fl.us",
        "comparison_tool_url": None,
        "notes": "Regulated market, limited competition",
    }


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def client(mock_db):
    """TestClient with mocked DB session (no auth required for regulations)."""
    from main import app

    app.dependency_overrides[get_db_session] = lambda: mock_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_db_session, None)


# =============================================================================
# GET /regulations (list)
# =============================================================================


class TestListRegulations:
    """Tests for the GET /api/v1/regulations endpoint."""

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_list_no_filters_returns_all(self, mock_repo_cls, client):
        """Listing without filters should return all states."""
        all_states = [_make_ct_regulation(), _make_tx_regulation(), _make_fl_regulation()]

        mock_repo = MagicMock()
        mock_repo.list_deregulated = AsyncMock(return_value=all_states)
        mock_repo_cls.return_value = mock_repo

        response = client.get(BASE_URL)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["states"]) == 3

        state_codes = [s["state_code"] for s in data["states"]]
        assert "CT" in state_codes
        assert "TX" in state_codes
        assert "FL" in state_codes

        # Verify repository was called with no filters
        mock_repo.list_deregulated.assert_awaited_once_with(
            electricity=None,
            gas=None,
            oil=None,
            community_solar=None,
        )

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_list_electricity_filter(self, mock_repo_cls, client):
        """Filtering by electricity=true should pass the filter to the repo."""
        deregulated = [_make_ct_regulation(), _make_tx_regulation()]

        mock_repo = MagicMock()
        mock_repo.list_deregulated = AsyncMock(return_value=deregulated)
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}?electricity=true")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(s["electricity_deregulated"] for s in data["states"])

        mock_repo.list_deregulated.assert_awaited_once_with(
            electricity=True,
            gas=None,
            oil=None,
            community_solar=None,
        )

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_list_gas_filter(self, mock_repo_cls, client):
        """Filtering by gas=true should return only gas-deregulated states."""
        mock_repo = MagicMock()
        mock_repo.list_deregulated = AsyncMock(return_value=[_make_ct_regulation()])
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}?gas=true")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["states"][0]["state_code"] == "CT"

        mock_repo.list_deregulated.assert_awaited_once_with(
            electricity=None,
            gas=True,
            oil=None,
            community_solar=None,
        )

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_list_multiple_filters(self, mock_repo_cls, client):
        """Multiple filters should all be passed to the repository."""
        mock_repo = MagicMock()
        mock_repo.list_deregulated = AsyncMock(return_value=[_make_ct_regulation()])
        mock_repo_cls.return_value = mock_repo

        response = client.get(
            f"{BASE_URL}?electricity=true&gas=true&community_solar=true"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

        mock_repo.list_deregulated.assert_awaited_once_with(
            electricity=True,
            gas=True,
            oil=None,
            community_solar=True,
        )

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_list_empty_result(self, mock_repo_cls, client):
        """When no states match the filters, should return empty list with total=0."""
        mock_repo = MagicMock()
        mock_repo.list_deregulated = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}?electricity=true&gas=true&oil=true&community_solar=true")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["states"] == []

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_list_false_filter(self, mock_repo_cls, client):
        """Filtering by electricity=false should find regulated states."""
        mock_repo = MagicMock()
        mock_repo.list_deregulated = AsyncMock(return_value=[_make_fl_regulation()])
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}?electricity=false")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["states"][0]["electricity_deregulated"] is False

        mock_repo.list_deregulated.assert_awaited_once_with(
            electricity=False,
            gas=None,
            oil=None,
            community_solar=None,
        )


# =============================================================================
# GET /regulations/{state_code}
# =============================================================================


class TestGetStateRegulation:
    """Tests for the GET /api/v1/regulations/{state_code} endpoint."""

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_get_state_ct(self, mock_repo_cls, client):
        """Should return Connecticut regulation data."""
        ct = _make_ct_regulation()

        mock_repo = MagicMock()
        mock_repo.get_by_state = AsyncMock(return_value=ct)
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}/CT")

        assert response.status_code == 200
        data = response.json()
        assert data["state_code"] == "CT"
        assert data["state_name"] == "Connecticut"
        assert data["electricity_deregulated"] is True
        assert data["gas_deregulated"] is True
        assert data["puc_name"] == "Connecticut PURA"
        assert data["bond_amount"] == 50000.0

        mock_repo.get_by_state.assert_awaited_once_with("CT")

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_get_state_tx(self, mock_repo_cls, client):
        """Should return Texas regulation data."""
        tx = _make_tx_regulation()

        mock_repo = MagicMock()
        mock_repo.get_by_state = AsyncMock(return_value=tx)
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}/TX")

        assert response.status_code == 200
        data = response.json()
        assert data["state_code"] == "TX"
        assert data["state_name"] == "Texas"
        assert data["electricity_deregulated"] is True
        assert data["gas_deregulated"] is False
        assert data["comparison_tool_url"] == "https://powertochoose.org"

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_get_state_not_found(self, mock_repo_cls, client):
        """Unknown state code should return 404."""
        mock_repo = MagicMock()
        mock_repo.get_by_state = AsyncMock(return_value=None)
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}/ZZ")

        assert response.status_code == 404
        assert "ZZ" in response.json()["detail"]

    def test_get_state_lowercase_returns_422(self, client):
        """Lowercase state code fails pattern validation before reaching the repo."""
        response = client.get(f"{BASE_URL}/xx")
        assert response.status_code == 422

    def test_get_state_too_long_returns_422(self, client):
        """State code longer than 2 uppercase letters should fail pattern validation."""
        response = client.get(f"{BASE_URL}/USA")
        assert response.status_code == 422

    def test_get_state_numeric_returns_422(self, client):
        """Numeric state code should fail pattern validation."""
        response = client.get(f"{BASE_URL}/12")
        assert response.status_code == 422

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_get_state_with_null_optional_fields(self, mock_repo_cls, client):
        """State with null optional fields should return nulls in response."""
        state = {
            "state_code": "WV",
            "state_name": "West Virginia",
            "electricity_deregulated": False,
            "gas_deregulated": False,
            "oil_competitive": False,
            "community_solar_enabled": False,
            "licensing_required": False,
            "bond_required": False,
            "bond_amount": None,
            "puc_name": None,
            "puc_website": None,
            "comparison_tool_url": None,
            "notes": None,
        }

        mock_repo = MagicMock()
        mock_repo.get_by_state = AsyncMock(return_value=state)
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}/WV")

        assert response.status_code == 200
        data = response.json()
        assert data["bond_amount"] is None
        assert data["puc_name"] is None
        assert data["puc_website"] is None
        assert data["comparison_tool_url"] is None
        assert data["notes"] is None


# =============================================================================
# Response Schema Validation
# =============================================================================


class TestResponseSchema:
    """Verify response objects conform to the StateRegulationResponse schema."""

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_list_response_has_all_fields(self, mock_repo_cls, client):
        """Each item in list response should have all StateRegulationResponse fields."""
        mock_repo = MagicMock()
        mock_repo.list_deregulated = AsyncMock(return_value=[_make_ct_regulation()])
        mock_repo_cls.return_value = mock_repo

        response = client.get(BASE_URL)

        assert response.status_code == 200
        data = response.json()
        assert "states" in data
        assert "total" in data

        state = data["states"][0]
        expected_fields = [
            "state_code", "state_name",
            "electricity_deregulated", "gas_deregulated",
            "oil_competitive", "community_solar_enabled",
            "licensing_required", "bond_required", "bond_amount",
            "puc_name", "puc_website", "comparison_tool_url", "notes",
        ]
        for field in expected_fields:
            assert field in state, f"Missing field: {field}"

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_single_response_has_all_fields(self, mock_repo_cls, client):
        """Single state response should have all StateRegulationResponse fields."""
        mock_repo = MagicMock()
        mock_repo.get_by_state = AsyncMock(return_value=_make_tx_regulation())
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}/TX")

        assert response.status_code == 200
        data = response.json()
        expected_fields = [
            "state_code", "state_name",
            "electricity_deregulated", "gas_deregulated",
            "oil_competitive", "community_solar_enabled",
            "licensing_required", "bond_required", "bond_amount",
            "puc_name", "puc_website", "comparison_tool_url", "notes",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    @patch("api.v1.regulations.StateRegulationRepository")
    def test_boolean_fields_are_booleans(self, mock_repo_cls, client):
        """Boolean fields should be actual booleans in JSON response."""
        mock_repo = MagicMock()
        mock_repo.get_by_state = AsyncMock(return_value=_make_ct_regulation())
        mock_repo_cls.return_value = mock_repo

        response = client.get(f"{BASE_URL}/CT")

        assert response.status_code == 200
        data = response.json()
        bool_fields = [
            "electricity_deregulated", "gas_deregulated",
            "oil_competitive", "community_solar_enabled",
            "licensing_required", "bond_required",
        ]
        for field in bool_fields:
            assert isinstance(data[field], bool), f"{field} should be bool, got {type(data[field])}"
