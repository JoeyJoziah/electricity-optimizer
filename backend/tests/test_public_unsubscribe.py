"""
Tests for the public unsubscribe endpoint and token helpers.

Covers:
- _make_unsubscribe_token produces deterministic output
- _verify_token accepts valid token
- _verify_token rejects tampered token
- GET /public/unsubscribe with valid token stamps unsubscribed_at and redirects
- GET /public/unsubscribe with invalid token returns 400
- GET /public/unsubscribe is idempotent (second call is a no-op, still redirects)
- GET /public/unsubscribe when INTERNAL_API_KEY is not set returns 500
- DripService._make_unsubscribe_url produces URL containing uid and tok
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.public_unsubscribe import _make_unsubscribe_token, _verify_token, router

# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def test_token_deterministic():
    uid = str(uuid4())
    assert _make_unsubscribe_token(uid, "secret") == _make_unsubscribe_token(uid, "secret")


def test_token_different_for_different_uid():
    tok_a = _make_unsubscribe_token("uid-a", "secret")
    tok_b = _make_unsubscribe_token("uid-b", "secret")
    assert tok_a != tok_b


def test_token_different_for_different_secret():
    uid = str(uuid4())
    assert _make_unsubscribe_token(uid, "s1") != _make_unsubscribe_token(uid, "s2")


def test_token_length():
    tok = _make_unsubscribe_token("uid", "secret")
    assert len(tok) == 32


def test_verify_token_accepts_valid():
    uid = str(uuid4())
    tok = _make_unsubscribe_token(uid, "secret")
    assert _verify_token(uid, tok, "secret") is True


def test_verify_token_rejects_tampered():
    uid = str(uuid4())
    tok = _make_unsubscribe_token(uid, "secret")
    assert _verify_token(uid, tok[:-1] + "x", "secret") is False


def test_verify_token_rejects_wrong_uid():
    tok = _make_unsubscribe_token("uid-a", "secret")
    assert _verify_token("uid-b", tok, "secret") is False


# ---------------------------------------------------------------------------
# DripService URL helper
# ---------------------------------------------------------------------------


def test_drip_service_make_unsubscribe_url():
    from services.drip_service import _make_unsubscribe_url

    uid = str(uuid4())
    with patch("services.drip_service.get_settings") as mock_settings:
        mock_settings.return_value.internal_api_key = "test-secret"
        url = _make_unsubscribe_url(uid)

    assert f"uid={uid}" in url
    assert "tok=" in url
    assert url.startswith("https://rateshift.app/api/v1/public/unsubscribe")


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


def _make_app(db_mock):
    app = FastAPI()

    async def _override_db():
        yield db_mock

    from api.dependencies import get_db_session

    app.dependency_overrides[get_db_session] = _override_db
    app.include_router(router, prefix="/api/v1")
    return app


def _make_db(updated=True):
    db = AsyncMock()
    db.commit = AsyncMock()
    result = MagicMock()
    result.fetchone = MagicMock(return_value=("uid",) if updated else None)
    db.execute = AsyncMock(return_value=result)
    return db


class TestUnsubscribeEndpoint:
    def test_valid_token_redirects(self):
        uid = str(uuid4())
        tok = _make_unsubscribe_token(uid, "test-secret")
        db = _make_db(updated=True)
        app = _make_app(db)

        with patch("api.v1.public_unsubscribe._settings") as ms:
            ms.internal_api_key = "test-secret"
            client = TestClient(app, follow_redirects=False)
            resp = client.get(f"/api/v1/public/unsubscribe?uid={uid}&tok={tok}")

        assert resp.status_code == 302
        assert resp.headers["location"] == "https://rateshift.app/unsubscribed"
        db.commit.assert_awaited_once()

    def test_invalid_token_returns_400(self):
        uid = str(uuid4())
        db = _make_db()
        app = _make_app(db)

        with patch("api.v1.public_unsubscribe._settings") as ms:
            ms.internal_api_key = "test-secret"
            client = TestClient(app, follow_redirects=False)
            resp = client.get(
                f"/api/v1/public/unsubscribe?uid={uid}&tok=badtoken123456789012345678901234"
            )

        assert resp.status_code == 400

    def test_idempotent_still_redirects(self):
        uid = str(uuid4())
        tok = _make_unsubscribe_token(uid, "test-secret")
        db = _make_db(updated=False)  # already unsubscribed — UPDATE returns no row
        app = _make_app(db)

        with patch("api.v1.public_unsubscribe._settings") as ms:
            ms.internal_api_key = "test-secret"
            client = TestClient(app, follow_redirects=False)
            resp = client.get(f"/api/v1/public/unsubscribe?uid={uid}&tok={tok}")

        assert resp.status_code == 302

    def test_missing_secret_returns_500(self):
        uid = str(uuid4())
        tok = _make_unsubscribe_token(uid, "")
        db = _make_db()
        app = _make_app(db)

        with patch("api.v1.public_unsubscribe._settings") as ms:
            ms.internal_api_key = ""
            client = TestClient(app, follow_redirects=False)
            resp = client.get(f"/api/v1/public/unsubscribe?uid={uid}&tok={tok}")

        assert resp.status_code == 500
