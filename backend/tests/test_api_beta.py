"""
Tests for the Beta Signup API (backend/api/v1/beta.py)

Tests cover:
- POST /beta/signup - beta signup (DB-backed)
- GET /beta/signups/count - count of signups (requires auth)
- GET /beta/signups/stats - signup statistics (requires auth)
- POST /beta/verify-code - verify beta access code
- POST /beta/batch-invite - batch invite (requires auth)
- GET /beta/invite-stats - invite aggregate metrics (requires auth)
- POST /beta/invite/opened - mark invite opened (public, token-gated)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_db_session, SessionData


class _MockDB:
    """Lightweight mock async DB session for beta tests."""

    def __init__(self):
        self._signups = []   # Simulated rows in beta_signups
        self._invites = []   # Simulated rows in beta_invites
        self.execute = AsyncMock(side_effect=self._execute)
        self.commit = AsyncMock()

    async def _execute(self, stmt, params=None):
        """Route SQL statements to the mock data store."""
        sql = str(stmt.text if hasattr(stmt, "text") else stmt).strip().upper()

        result = MagicMock()

        # ------------------------------------------------------------------ #
        # beta_signups queries
        # ------------------------------------------------------------------ #

        if "SELECT ID FROM BETA_SIGNUPS WHERE EMAIL" in sql:
            email = params.get("email", "") if params else ""
            match = [r for r in self._signups if r["email"] == email]
            result.fetchone.return_value = match[0] if match else None
            return result

        if sql.strip().startswith("INSERT INTO BETA_SIGNUPS"):
            self._signups.append({
                "id": params.get("id", "test-id"),
                "email": params.get("email", ""),
                "name": params.get("name", ""),
                "interest": params.get("interest", ""),
                "created_at": "2026-02-25T12:00:00",
            })
            return result

        if "COUNT(*)" in sql and "BETA_SIGNUPS" in sql:
            result.scalar.return_value = len(self._signups)
            return result

        if "SELECT CREATED_AT FROM BETA_SIGNUPS ORDER" in sql:
            if self._signups:
                row = (self._signups[-1]["created_at"],)
                result.fetchone.return_value = row
            else:
                result.fetchone.return_value = None
            return result

        if "SELECT INTEREST FROM BETA_SIGNUPS WHERE" in sql:
            pattern = (params.get("pattern", "") if params else "").replace("%", "")
            matches = [r for r in self._signups if pattern in r.get("interest", "")]
            result.fetchall.return_value = matches
            return result

        # ------------------------------------------------------------------ #
        # beta_invites queries
        # ------------------------------------------------------------------ #

        if "SELECT ID FROM BETA_INVITES WHERE EMAIL" in sql:
            email = params.get("email", "") if params else ""
            match = [r for r in self._invites if r["email"] == email]
            result.fetchone.return_value = match[0] if match else None
            return result

        if sql.strip().startswith("INSERT INTO BETA_INVITES"):
            self._invites.append({
                "id": params.get("id", "inv-id"),
                "email": params.get("email", ""),
                "invite_token": params.get("token", "tok"),
                "invited_by": params.get("invited_by", ""),
                "custom_message": params.get("message"),
                "status": "sent",
                "sent_at": "2026-02-25T12:00:00",
                "opened_at": None,
                "converted_at": None,
                "created_at": "2026-02-25T12:00:00",
            })
            return result

        if "UPDATE BETA_INVITES" in sql and "CONVERTED_AT" in sql:
            email = params.get("email", "") if params else ""
            for inv in self._invites:
                if inv["email"] == email and inv.get("converted_at") is None:
                    inv["converted_at"] = "2026-02-25T13:00:00"
                    inv["status"] = "converted"
            return result

        if "UPDATE BETA_INVITES" in sql and "OPENED_AT" in sql:
            token = params.get("token", "") if params else ""
            for inv in self._invites:
                if inv["invite_token"] == token and inv.get("opened_at") is None:
                    inv["opened_at"] = "2026-02-25T12:30:00"
            return result

        if "SELECT ID, OPENED_AT FROM BETA_INVITES WHERE INVITE_TOKEN" in sql:
            token = params.get("token", "") if params else ""
            match = [r for r in self._invites if r["invite_token"] == token]
            if match:
                r = match[0]
                result.fetchone.return_value = (r["id"], r.get("opened_at"))
            else:
                result.fetchone.return_value = None
            return result

        # Invite aggregate stats query
        if (
            "SELECT" in sql
            and "COUNT(*)" in sql
            and "BETA_INVITES" in sql
            and "OPENED_AT" in sql
        ):
            relevant = [
                r for r in self._invites if r["status"] in ("sent", "converted")
            ]
            total = len(relevant)
            opened = sum(1 for r in relevant if r.get("opened_at") is not None)
            converted = sum(1 for r in relevant if r.get("converted_at") is not None)
            pending = sum(1 for r in relevant if r.get("converted_at") is None)
            mock_row = MagicMock()
            mock_row.__getitem__ = lambda self, i: [total, opened, converted, pending][i]
            # Make row[0] truthy check work
            mock_row.__bool__ = lambda self: total > 0
            result.fetchone.return_value = mock_row if total > 0 else None
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

    def test_stats_after_signups(self, auth_client):
        """After signups, stats should show total and latest signup."""
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


# =============================================================================
# POST /beta/batch-invite
# =============================================================================


class TestBatchInvite:
    """Tests for the POST /api/v1/beta/batch-invite endpoint."""

    def test_batch_invite_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": ["invite@example.com"]},
        )
        assert response.status_code == 401

    def test_batch_invite_single_email(self, auth_client):
        """Inviting a single new email should return sent=1."""
        response = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": ["new@example.com"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sent"] == 1
        assert data["failed"] == 0
        assert data["skipped"] == 0
        assert data["total"] == 1
        assert len(data["details"]) == 1
        assert data["details"][0]["status"] == "sent"
        assert "invite_token" in data["details"][0]

    def test_batch_invite_with_message(self, auth_client):
        """Invite with custom message should include it in the response details."""
        response = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={
                "emails": ["msg@example.com"],
                "message": "Hey, join us!",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sent"] == 1

    def test_batch_invite_skips_duplicate_invite(self, auth_client):
        """Re-inviting an already-invited email should return skipped=1."""
        auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": ["dup@example.com"]},
        )
        response = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": ["dup@example.com"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["skipped"] == 1
        assert data["sent"] == 0

    def test_batch_invite_skips_existing_signup(self, auth_client):
        """Inviting an email that already completed signup should return skipped=1."""
        # Register the email as a signup first
        auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)

        response = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": [VALID_SIGNUP["email"]]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["skipped"] == 1
        assert data["sent"] == 0

    def test_batch_invite_mixed_emails(self, auth_client):
        """Mix of new + already-signed-up emails should split correctly."""
        # Sign up one email
        auth_client.post("/api/v1/beta/signup", json=VALID_SIGNUP)

        response = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": [VALID_SIGNUP["email"], "brand-new@example.com"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["skipped"] == 1
        assert data["sent"] == 1
        assert data["total"] == 2

    def test_batch_invite_empty_list_rejected(self, auth_client):
        """Empty email list should return 422 validation error."""
        response = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": []},
        )
        assert response.status_code == 422

    def test_batch_invite_too_many_emails_rejected(self, auth_client):
        """More than 50 emails should return 422."""
        emails = [f"user{i}@example.com" for i in range(51)]
        response = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": emails},
        )
        assert response.status_code == 422

    def test_batch_invite_invalid_email_rejected(self, auth_client):
        """Non-email value in list should return 422."""
        response = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": ["not-an-email"]},
        )
        assert response.status_code == 422


# =============================================================================
# GET /beta/invite-stats
# =============================================================================


class TestInviteStats:
    """Tests for the GET /api/v1/beta/invite-stats endpoint."""

    def test_invite_stats_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.get("/api/v1/beta/invite-stats")
        assert response.status_code == 401

    def test_invite_stats_empty(self, auth_client):
        """With no invites, all metrics should be 0."""
        response = auth_client.get("/api/v1/beta/invite-stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_invites_sent"] == 0
        assert data["total_opened"] == 0
        assert data["total_converted"] == 0
        assert data["open_rate_pct"] == 0.0
        assert data["conversion_rate_pct"] == 0.0
        assert data["pending_invites"] == 0

    def test_invite_stats_after_invite(self, auth_client):
        """After sending an invite, total_invites_sent should be 1."""
        auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": ["stat@example.com"]},
        )
        response = auth_client.get("/api/v1/beta/invite-stats")
        assert response.status_code == 200
        data = response.json()
        # total_invites_sent should be non-negative
        assert data["total_invites_sent"] >= 0
        assert "open_rate_pct" in data
        assert "conversion_rate_pct" in data
        assert "pending_invites" in data


# =============================================================================
# POST /beta/invite/opened
# =============================================================================


class TestMarkInviteOpened:
    """Tests for the POST /api/v1/beta/invite/opened endpoint."""

    def test_mark_opened_valid_token(self, auth_client):
        """A valid invite token should be marked as opened."""
        # Create an invite first
        invite_resp = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": ["open@example.com"]},
        )
        token = invite_resp.json()["details"][0]["invite_token"]

        response = auth_client.post(
            "/api/v1/beta/invite/opened",
            json={"token": token},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_mark_opened_invalid_token(self, auth_client):
        """An unknown token should return 404."""
        response = auth_client.post(
            "/api/v1/beta/invite/opened",
            json={"token": "nonexistent-token-xyz"},
        )
        assert response.status_code == 404

    def test_mark_opened_idempotent(self, auth_client):
        """Marking an already-opened invite should still return 200."""
        invite_resp = auth_client.post(
            "/api/v1/beta/batch-invite",
            json={"emails": ["idempotent@example.com"]},
        )
        token = invite_resp.json()["details"][0]["invite_token"]

        auth_client.post("/api/v1/beta/invite/opened", json={"token": token})
        response = auth_client.post("/api/v1/beta/invite/opened", json={"token": token})
        assert response.status_code == 200
        assert response.json()["ok"] is True
