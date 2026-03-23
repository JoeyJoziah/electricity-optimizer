"""
Tests for Combined Savings and Neighborhood Comparison API routes.

Covers:
- GET /savings/combined — combined savings across all utilities (auth)
- GET /neighborhood/compare — rate comparison vs. region peers (auth)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Mock DB
# ---------------------------------------------------------------------------


class _MockSavingsDB:
    """Lightweight mock DB for savings and neighborhood queries."""

    def __init__(self):
        self.commit = AsyncMock()

    async def execute(self, stmt, params=None):
        sql = str(stmt.text if hasattr(stmt, "text") else stmt).strip().upper()
        params = params or {}
        result = MagicMock()

        # --- Combined savings query (SUM + GROUP BY utility_type) ---
        # Aggregator now returns savings_rank_pct per row via LEFT JOIN ranked CTE (19-P2-8)
        if "SUM" in sql and "GROUP BY" in sql and "UTILITY_TYPE" in sql:
            result.mappings.return_value.fetchall.return_value = [
                {
                    "utility_type": "electricity",
                    "monthly_savings": Decimal("25.50"),
                    "savings_rank_pct": 0.72,
                },
                {
                    "utility_type": "natural_gas",
                    "monthly_savings": Decimal("12.00"),
                    "savings_rank_pct": 0.72,
                },
            ]
            return result

        # --- Neighborhood comparison (single CTE query with user_count, 19-P2-7) ---
        if "PERCENT_RANK" in sql and "USER_RATES" in sql:
            result.mappings.return_value.fetchone.return_value = {
                "user_count": 25,
                "user_rate": Decimal("0.1850"),
                "percentile": 0.65,
                "cheapest_supplier": "Town Square Energy",
                "cheapest_rate": Decimal("0.1200"),
                "avg_rate": Decimal("0.1750"),
            }
            return result

        # Fallback
        result.scalar.return_value = 0
        result.mappings.return_value.fetchone.return_value = None
        result.mappings.return_value.fetchall.return_value = []
        return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    return _MockSavingsDB()


@pytest.fixture
def auth_client(mock_db):
    """TestClient with authenticated user."""
    from main import app

    test_user = SessionData(user_id=TEST_USER_ID, email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db_session] = lambda: mock_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client():
    """TestClient without authentication."""
    from main import app

    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)
    yield client


# =============================================================================
# GET /savings/combined
# =============================================================================


class TestCombinedSavings:
    def test_combined_savings_authenticated(self, auth_client):
        """200 with combined savings data when authenticated."""
        resp = auth_client.get("/api/v1/savings/combined")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_monthly_savings" in data
        assert "breakdown" in data

    def test_combined_savings_unauthenticated(self, unauth_client):
        """401 when not authenticated."""
        resp = unauth_client.get("/api/v1/savings/combined")
        assert resp.status_code in (401, 403)

    def test_combined_savings_response_shape(self, auth_client):
        """Response has total, breakdown, and rank fields."""
        resp = auth_client.get("/api/v1/savings/combined")
        data = resp.json()
        assert "total_monthly_savings" in data
        assert "breakdown" in data
        assert isinstance(data["breakdown"], list)
        assert "savings_rank_pct" in data


# =============================================================================
# GET /neighborhood/compare
# =============================================================================


class TestNeighborhoodComparison:
    def test_neighborhood_comparison_authenticated(self, auth_client):
        """200 with comparison data when authenticated."""
        resp = auth_client.get(
            "/api/v1/neighborhood/compare",
            params={"region": "us_ct", "utility_type": "electricity"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "percentile" in data or "region" in data
