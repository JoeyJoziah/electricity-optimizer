"""
Tests for Referral System — service logic and API endpoints.

Tests cover:
- Code generation: format, uniqueness
- Apply flow: valid, already-used, self-referral blocked, nonexistent
- Complete flow: status transition, reward_applied, completed_at
- Stats: correct counts
- API: auth, validation, responses
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_ID = "test-user-123"
OTHER_USER_ID = "other-user-456"
REFERRAL_CODE = "AB12CD34"

NOW = datetime(2026, 3, 11, 12, 0, 0, tzinfo=UTC)


def _make_session_data(user_id=USER_ID, email="test@example.com"):
    from auth.neon_auth import SessionData

    return SessionData(user_id=user_id, email=email, name="Test User", email_verified=True)


def _mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _referral_row(
    referrer_id=USER_ID,
    referee_id=None,
    code=REFERRAL_CODE,
    status_val="pending",
    reward_applied=False,
):
    return {
        "id": "ref-id-001",
        "referrer_id": referrer_id,
        "referee_id": referee_id,
        "referral_code": code,
        "status": status_val,
        "reward_applied": reward_applied,
        "created_at": NOW,
        "completed_at": None,
    }


# ---------------------------------------------------------------------------
# Unit Tests: ReferralService
# ---------------------------------------------------------------------------


class TestReferralServiceUnit:
    """Unit tests for ReferralService methods."""

    async def test_generate_code_format(self):
        """Generated code is 8 chars alphanumeric."""
        from services.referral_service import ReferralService

        db = _mock_db()
        svc = ReferralService(db)

        code = svc._generate_code()
        assert len(code) == 8
        assert code.isalnum()
        assert code == code.upper()

    async def test_generate_code_stores_in_db(self):
        """generate_code() INSERTs and commits."""
        from services.referral_service import ReferralService

        db = _mock_db()
        svc = ReferralService(db)

        code = await svc.generate_code(USER_ID)
        assert len(code) == 8
        db.execute.assert_called_once()
        db.commit.assert_called_once()

    async def test_get_or_create_returns_existing(self):
        """If user already has a pending code, return it."""
        from services.referral_service import ReferralService

        db = _mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = REFERRAL_CODE
        db.execute.return_value = result

        svc = ReferralService(db)
        code = await svc.get_or_create_code(USER_ID)
        assert code == REFERRAL_CODE

    async def test_apply_referral_success(self):
        """Valid code + different user = success."""
        from services.referral_service import ReferralService

        db = _mock_db()

        # get_referral_by_code returns a valid pending referral
        lookup_result = MagicMock()
        lookup_result.mappings.return_value.first.return_value = _referral_row()

        # apply UPDATE
        update_result = MagicMock()

        db.execute.side_effect = [lookup_result, update_result]

        svc = ReferralService(db)
        result = await svc.apply_referral(OTHER_USER_ID, REFERRAL_CODE)
        assert result["referee_id"] == OTHER_USER_ID

    async def test_apply_referral_self_referral_blocked(self):
        """Cannot use your own referral code."""
        from services.referral_service import ReferralError, ReferralService

        db = _mock_db()
        lookup_result = MagicMock()
        lookup_result.mappings.return_value.first.return_value = _referral_row(referrer_id=USER_ID)
        db.execute.return_value = lookup_result

        svc = ReferralService(db)
        with pytest.raises(ReferralError, match="Cannot use your own referral code"):
            await svc.apply_referral(USER_ID, REFERRAL_CODE)

    async def test_apply_referral_nonexistent_code(self):
        """Nonexistent code raises error."""
        from services.referral_service import ReferralError, ReferralService

        db = _mock_db()
        lookup_result = MagicMock()
        lookup_result.mappings.return_value.first.return_value = None
        db.execute.return_value = lookup_result

        svc = ReferralService(db)
        with pytest.raises(ReferralError, match="Invalid referral code"):
            await svc.apply_referral(OTHER_USER_ID, "BADCODE1")

    async def test_apply_referral_already_used(self):
        """Already-completed code raises error."""
        from services.referral_service import ReferralError, ReferralService

        db = _mock_db()
        lookup_result = MagicMock()
        lookup_result.mappings.return_value.first.return_value = _referral_row(
            status_val="completed"
        )
        db.execute.return_value = lookup_result

        svc = ReferralService(db)
        with pytest.raises(ReferralError, match="already used or expired"):
            await svc.apply_referral(OTHER_USER_ID, REFERRAL_CODE)

    async def test_apply_referral_already_claimed(self):
        """Code with referee_id already set raises error."""
        from services.referral_service import ReferralError, ReferralService

        db = _mock_db()
        lookup_result = MagicMock()
        lookup_result.mappings.return_value.first.return_value = _referral_row(
            referee_id="someone-else"
        )
        db.execute.return_value = lookup_result

        svc = ReferralService(db)
        with pytest.raises(ReferralError, match="already claimed"):
            await svc.apply_referral(OTHER_USER_ID, REFERRAL_CODE)

    async def test_complete_referral(self):
        """Completing a referral sets status, reward, completed_at."""
        from services.referral_service import ReferralService

        db = _mock_db()
        completed_row = {
            **_referral_row(referee_id=OTHER_USER_ID, status_val="completed", reward_applied=True),
            "completed_at": NOW,
        }
        result = MagicMock()
        result.mappings.return_value.first.return_value = completed_row
        db.execute.return_value = result

        svc = ReferralService(db)
        result_data = await svc.complete_referral(OTHER_USER_ID)
        assert result_data["status"] == "completed"
        assert result_data["reward_applied"] is True
        assert result_data["completed_at"] is not None

    async def test_get_stats(self):
        """Stats aggregation returns correct counts."""
        from services.referral_service import ReferralService

        db = _mock_db()
        result = MagicMock()
        result.mappings.return_value.first.return_value = {
            "total": 5,
            "pending": 3,
            "completed": 2,
            "reward_credits": 2,
        }
        db.execute.return_value = result

        svc = ReferralService(db)
        stats = await svc.get_stats(USER_ID)
        assert stats["total"] == 5
        assert stats["pending"] == 3
        assert stats["completed"] == 2
        assert stats["reward_credits"] == 2


# ---------------------------------------------------------------------------
# API Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _override_deps(request):
    from api.dependencies import get_current_user, get_db_session
    from main import app

    db = _mock_db()
    session_data = _make_session_data()

    app.dependency_overrides[get_current_user] = lambda: session_data
    app.dependency_overrides[get_db_session] = lambda: db

    if request.instance is not None:
        request.instance._db = db

    yield

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


class TestReferralAPI:
    def test_get_code_generates_new(self, client):
        """GET /referrals/code returns a code."""
        # First query: no existing code
        no_code_result = MagicMock()
        no_code_result.scalar_one_or_none.return_value = None

        # Second query: INSERT succeeds (generate_code)
        insert_result = MagicMock()

        self._db.execute.side_effect = [no_code_result, insert_result]

        resp = client.get("/api/v1/referrals/code")
        assert resp.status_code == 200
        data = resp.json()
        assert "referral_code" in data
        assert len(data["referral_code"]) == 8

    def test_get_code_returns_existing(self, client):
        """GET /referrals/code returns existing code if one exists."""
        result = MagicMock()
        result.scalar_one_or_none.return_value = REFERRAL_CODE
        self._db.execute.return_value = result

        resp = client.get("/api/v1/referrals/code")
        assert resp.status_code == 200
        assert resp.json()["referral_code"] == REFERRAL_CODE

    def test_apply_referral_bad_code(self, client):
        """POST /referrals/apply with nonexistent code returns 400."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        self._db.execute.return_value = result

        resp = client.post("/api/v1/referrals/apply", json={"code": "BADCODE1"})
        assert resp.status_code == 400
        assert "Invalid" in resp.json()["detail"]

    def test_get_stats(self, client):
        """GET /referrals/stats returns counts."""
        result = MagicMock()
        result.mappings.return_value.first.return_value = {
            "total": 3,
            "pending": 1,
            "completed": 2,
            "reward_credits": 2,
        }
        self._db.execute.return_value = result

        resp = client.get("/api/v1/referrals/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["completed"] == 2

    def test_apply_missing_code_field(self, client):
        """POST /referrals/apply without code returns 422."""
        resp = client.post("/api/v1/referrals/apply", json={})
        assert resp.status_code == 422
