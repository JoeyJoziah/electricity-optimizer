"""
Tests for the Beta Signup API (backend/api/v1/beta.py)

Tests cover:
- POST /beta/signup - early access signup (DB-backed)
- GET /beta/signups/count - count of signups (requires auth)
- GET /beta/signups/stats - signup statistics (requires auth)
- POST /beta/verify-code - verify access code
- validate_postcode() - US ZIP and UK postcode validation
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.dependencies import SessionData, get_current_user, get_db_session


class _MockDB:
    """Lightweight mock async DB session for beta tests."""

    def __init__(self):
        self._rows = []  # Simulated rows in beta_signups
        self.execute = AsyncMock(side_effect=self._execute)
        self.commit = AsyncMock()

    async def _execute(self, stmt, params=None):
        """Route SQL statements to the mock data store."""
        sql = str(stmt.text if hasattr(stmt, "text") else stmt).strip().upper()

        result = MagicMock()

        if sql.startswith("SELECT ID FROM BETA_SIGNUPS WHERE EMAIL"):
            # Duplicate email check
            email = params.get("email", "") if params else ""
            match = [r for r in self._rows if r["email"] == email]
            result.fetchone.return_value = match[0] if match else None
            return result

        if sql.startswith("INSERT INTO BETA_SIGNUPS"):
            self._rows.append(
                {
                    "id": params.get("id", "test-id"),
                    "email": params.get("email", ""),
                    "name": params.get("name", ""),
                    "interest": params.get("interest", ""),
                    "created_at": "2026-02-25T12:00:00",
                }
            )
            return result

        if "COUNT(*)" in sql:
            result.scalar.return_value = len(self._rows)
            return result

        if sql.startswith("SELECT CREATED_AT FROM BETA_SIGNUPS ORDER"):
            if self._rows:
                row = (self._rows[-1]["created_at"],)
                result.fetchone.return_value = row
            else:
                result.fetchone.return_value = None
            return result

        if sql.startswith("SELECT INTEREST FROM BETA_SIGNUPS WHERE"):
            pattern = (params.get("pattern", "") if params else "").replace("%", "")
            matches = [r for r in self._rows if pattern in r.get("interest", "")]
            result.fetchall.return_value = matches
            return result

        return result


@pytest.fixture
def mock_db():
    """Provide a fresh mock DB for each test."""
    return _MockDB()


@pytest.fixture
def auth_client(mock_db):
    """Create a TestClient with authenticated user and mock DB."""
    from main import app

    test_user = SessionData(user_id="admin-user-1", email="admin@test.com")
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db_session] = lambda: mock_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def unauth_client():
    """Create a TestClient without authentication."""
    from main import app

    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)
    yield client


@pytest.fixture
def unauth_client_with_db(mock_db):
    """Create a TestClient without authentication but with mock DB (for public endpoints)."""
    from main import app

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db_session] = lambda: mock_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_db_session, None)


VALID_SIGNUP = {
    "email": "alice@example.com",
    "name": "Alice Smith",
    "postcode": "06510",
    "currentSupplier": "Eversource Energy",
    "monthlyBill": "$75-$150",
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
        """Invalid postcode (non-US/UK) should return 400."""
        payload = {**VALID_SIGNUP, "postcode": "BADPC"}
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

    def test_signup_requires_no_invite_code(self, auth_client):
        """Signup should succeed without an invite field — signup is public."""
        payload = {**VALID_SIGNUP, "email": "noinvite@example.com"}
        # Ensure no invite/inviteCode field is present
        assert "invite" not in payload
        assert "inviteCode" not in payload
        response = auth_client.post("/api/v1/beta/signup", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_signup_unauthenticated_succeeds(self, unauth_client_with_db):
        """POST /beta/signup is a public endpoint — no auth required."""
        response = unauth_client_with_db.post("/api/v1/beta/signup", json=VALID_SIGNUP)
        # Public endpoint should not return 401/403
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_signup_us_zip_plus_four(self, auth_client):
        """ZIP+4 format (e.g. 12345-6789) should be accepted."""
        payload = {**VALID_SIGNUP, "email": "zipfour@example.com", "postcode": "06510-1234"}
        response = auth_client.post("/api/v1/beta/signup", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_signup_response_message_no_beta_language(self, auth_client):
        """Success response message should not contain the word 'beta'."""
        response = auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)
        assert response.status_code == 200
        message = response.json()["message"].lower()
        assert "beta" not in message, f"Response message still contains 'beta': {message!r}"


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

    def test_stats_after_signups(self, auth_client):
        """After signups, stats should show total and latest signup."""
        auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)

        second_signup = {
            **VALID_SIGNUP,
            "email": "bob@example.com",
            "name": "Bob Jones",
            "currentSupplier": "United Illuminating",
            "hearAbout": "Friend",
        }
        auth_client.post("/api/v1/beta/signup", json=second_signup)

        response = auth_client.get("/api/v1/beta/signups/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
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
        """An invalid access code should return 404."""
        response = auth_client.post(
            "/api/v1/beta/verify-code",
            json={"code": "FAKE-CODE-12345"},
        )
        assert response.status_code == 404
        assert "Invalid access code" in response.json()["detail"]

    def test_verify_empty_code(self, auth_client):
        """Empty code should return 404 (no match)."""
        response = auth_client.post(
            "/api/v1/beta/verify-code",
            json={"code": ""},
        )
        assert response.status_code == 404

    def test_verify_response_message_no_beta_language(self, auth_client):
        """Verify success message should use 'Access code verified', not 'Beta code verified'."""
        signup_resp = auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)
        beta_code = signup_resp.json()["betaCode"]

        response = auth_client.post(
            "/api/v1/beta/verify-code",
            json={"code": beta_code},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Access code verified"


# =============================================================================
# validate_postcode() unit tests
# =============================================================================


class TestValidatePostcode:
    """Unit tests for the validate_postcode() function."""

    def setup_method(self):
        from api.v1.beta import validate_postcode

        self.validate = validate_postcode

    def test_us_five_digit_zip(self):
        """Standard 5-digit US ZIP codes should be valid."""
        assert self.validate("06510") is True
        assert self.validate("10001") is True
        assert self.validate("99999") is True

    def test_us_zip_plus_four(self):
        """US ZIP+4 format should be valid."""
        assert self.validate("06510-1234") is True
        assert self.validate("12345-6789") is True
        assert self.validate("00000-0000") is True

    def test_uk_postcode_valid(self):
        """Standard UK postcodes should be valid."""
        assert self.validate("SW1A 1AA") is True
        assert self.validate("EC1A 1BB") is True
        assert self.validate("W1A 0AX") is True
        assert self.validate("M1 1AE") is True

    def test_uk_postcode_no_space(self):
        """UK postcodes without a space should be valid."""
        assert self.validate("SW1A1AA") is True

    def test_invalid_random_string(self):
        """Random strings should be invalid."""
        assert self.validate("BADPC") is False
        assert self.validate("HELLO") is False
        assert self.validate("12345678") is False

    def test_invalid_too_short(self):
        """Too-short values should be invalid."""
        assert self.validate("1234") is False

    def test_invalid_zip_wrong_separator(self):
        """ZIP with wrong separator should be invalid."""
        assert self.validate("06510_1234") is False
        assert self.validate("065101234") is False
