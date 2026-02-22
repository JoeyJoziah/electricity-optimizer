"""
Tests for the Beta Signup API (backend/api/v1/beta.py)

Tests cover:
- POST /beta/signup - beta signup
- GET /beta/signups/count - count of signups (requires auth)
- GET /beta/signups/stats - signup statistics (requires auth)
- POST /beta/verify-code - verify beta access code
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, TokenData


@pytest.fixture(autouse=True)
def clear_beta_signups():
    """Clear in-memory beta signups between tests to avoid cross-test contamination."""
    from api.v1.beta import beta_signups

    beta_signups.clear()
    yield
    beta_signups.clear()


@pytest.fixture
def auth_client():
    """Create a TestClient with authenticated user."""
    from main import app

    test_user = TokenData(user_id="admin-user-1", email="admin@test.com")
    app.dependency_overrides[get_current_user] = lambda: test_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauth_client():
    """Create a TestClient without authentication."""
    from main import app

    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)
    yield client


VALID_SIGNUP = {
    "email": "alice@example.com",
    "name": "Alice Smith",
    "postcode": "SW1A 1AA",
    "currentSupplier": "British Gas",
    "monthlyBill": "50-100",
    "hearAbout": "Google Search",
}


# =============================================================================
# POST /beta/signup
# =============================================================================


class TestBetaSignup:
    """Tests for the POST /api/v1/beta/signup endpoint."""

    def test_signup_success(self, auth_client):
        """Valid signup should succeed and return a beta code."""
        response = auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["betaCode"].startswith("BETA-2026-")
        assert "message" in data

    def test_signup_invalid_postcode(self, auth_client):
        """Invalid UK postcode should return 400."""
        payload = {**VALID_SIGNUP, "postcode": "12345"}
        response = auth_client.post("/api/v1/beta/signup", json=payload)
        assert response.status_code == 400
        assert "postcode" in response.json()["detail"].lower()

    def test_signup_duplicate_email(self, auth_client):
        """Signing up with the same email twice should return 400."""
        auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)
        response = auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    def test_signup_missing_name(self, auth_client):
        """Missing required name field should return 422."""
        payload = {k: v for k, v in VALID_SIGNUP.items() if k != "name"}
        response = auth_client.post("/api/v1/beta/signup", json=payload)
        assert response.status_code == 422

    def test_signup_email_validation(self, auth_client):
        """Invalid email format should return 422."""
        payload = {**VALID_SIGNUP, "email": "not-an-email"}
        response = auth_client.post("/api/v1/beta/signup", json=payload)
        assert response.status_code == 422

    def test_signup_name_too_short(self, auth_client):
        """Name shorter than 2 chars should return 422."""
        payload = {**VALID_SIGNUP, "email": "short@example.com", "name": "A"}
        response = auth_client.post("/api/v1/beta/signup", json=payload)
        assert response.status_code == 422


# =============================================================================
# GET /beta/signups/count
# =============================================================================


class TestBetaSignupsCount:
    """Tests for the GET /api/v1/beta/signups/count endpoint."""

    def test_count_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.get("/api/v1/beta/signups/count")
        assert response.status_code == 401

    def test_count_empty(self, auth_client):
        """With no signups, total should be 0."""
        response = auth_client.get("/api/v1/beta/signups/count")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["target"] == 50
        assert data["percentage"] == 0.0

    def test_count_after_signup(self, auth_client):
        """After one signup, total should be 1."""
        auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)
        response = auth_client.get("/api/v1/beta/signups/count")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["percentage"] == 2.0  # 1/50 * 100


# =============================================================================
# GET /beta/signups/stats
# =============================================================================


class TestBetaSignupsStats:
    """Tests for the GET /api/v1/beta/signups/stats endpoint."""

    def test_stats_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.get("/api/v1/beta/signups/stats")
        assert response.status_code == 401

    def test_stats_empty(self, auth_client):
        """With no signups, stats should be empty."""
        response = auth_client.get("/api/v1/beta/signups/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["bySupplier"] == {}
        assert data["bySource"] == {}

    def test_stats_after_signups(self, auth_client):
        """After signups, stats should aggregate by supplier and source."""
        auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)

        second_signup = {
            **VALID_SIGNUP,
            "email": "bob@example.com",
            "name": "Bob Jones",
            "currentSupplier": "EDF Energy",
            "hearAbout": "Friend",
        }
        auth_client.post("/api/v1/beta/signup", json=second_signup)

        response = auth_client.get("/api/v1/beta/signups/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["bySupplier"]["British Gas"] == 1
        assert data["bySupplier"]["EDF Energy"] == 1
        assert data["bySource"]["Google Search"] == 1
        assert data["bySource"]["Friend"] == 1
        assert data["latestSignup"] is not None


# =============================================================================
# POST /beta/verify-code
# =============================================================================


class TestVerifyBetaCode:
    """Tests for the POST /api/v1/beta/verify-code endpoint."""

    def test_verify_valid_code(self, auth_client):
        """A code generated during signup should verify successfully."""
        signup_resp = auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)
        beta_code = signup_resp.json()["betaCode"]

        response = auth_client.post(
            "/api/v1/beta/verify-code",
            json={"code": beta_code},
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_verify_invalid_code(self, auth_client):
        """An invalid beta code should return 404."""
        response = auth_client.post(
            "/api/v1/beta/verify-code",
            json={"code": "FAKE-CODE-12345"},
        )
        assert response.status_code == 404
        assert "Invalid beta code" in response.json()["detail"]

    def test_verify_empty_code(self, auth_client):
        """Empty code should return 404 (no match)."""
        response = auth_client.post(
            "/api/v1/beta/verify-code",
            json={"code": ""},
        )
        assert response.status_code == 404
