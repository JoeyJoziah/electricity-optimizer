"""
Tests for GET /api/v1/public/unsubscribe (CAN-SPAM one-click unsubscribe).

Covers:
- Token generation and HMAC verification helpers
- Missing secret → 500
- Invalid token → 400
- Valid token, user state updated → 302 redirect
- Valid token, user already unsubscribed (noop) → 302 redirect
- Redirect target URL is correct
"""

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers (unit tests — no DB)
# ---------------------------------------------------------------------------


class TestUnsubscribeTokenHelpers:
    """Unit tests for _make_unsubscribe_token and _verify_token."""

    def _token(self, user_id: str, secret: str) -> str:
        from api.v1.public_unsubscribe import _make_unsubscribe_token

        return _make_unsubscribe_token(user_id, secret)

    def _verify(self, user_id: str, tok: str, secret: str) -> bool:
        from api.v1.public_unsubscribe import _verify_token

        return _verify_token(user_id, tok, secret)

    def test_token_is_32_hex_chars(self):
        tok = self._token("user-123", "mysecret")
        assert len(tok) == 32
        assert all(c in "0123456789abcdef" for c in tok)

    def test_token_is_deterministic(self):
        tok1 = self._token("user-abc", "s3cr3t")
        tok2 = self._token("user-abc", "s3cr3t")
        assert tok1 == tok2

    def test_different_users_produce_different_tokens(self):
        tok1 = self._token("user-1", "secret")
        tok2 = self._token("user-2", "secret")
        assert tok1 != tok2

    def test_different_secrets_produce_different_tokens(self):
        tok1 = self._token("user-1", "secret-a")
        tok2 = self._token("user-1", "secret-b")
        assert tok1 != tok2

    def test_verify_returns_true_for_correct_token(self):
        secret = "testsecret"
        user_id = "user-xyz"
        tok = self._token(user_id, secret)
        assert self._verify(user_id, tok, secret) is True

    def test_verify_returns_false_for_wrong_token(self):
        assert self._verify("user-xyz", "00000000000000000000000000000000", "secret") is False

    def test_verify_returns_false_for_wrong_user(self):
        tok = self._token("user-correct", "secret")
        assert self._verify("user-wrong", tok, "secret") is False

    def test_verify_returns_false_for_truncated_token(self):
        tok = self._token("user-1", "secret")[:16]
        assert self._verify("user-1", tok, "secret") is False

    def test_verify_uses_constant_time_compare(self):
        # hmac.compare_digest must be used (not ==) to prevent timing attacks.
        # We can't measure timing in a unit test, but we can assert the import
        # uses it by inspecting the source.
        import inspect

        from api.v1 import public_unsubscribe

        src = inspect.getsource(public_unsubscribe)
        assert "compare_digest" in src


# ---------------------------------------------------------------------------
# Endpoint integration tests (mocked DB)
# ---------------------------------------------------------------------------


class TestUnsubscribeEndpoint:
    """Tests for GET /api/v1/public/unsubscribe."""

    def _make_token(self, user_id: str, secret: str) -> str:
        return hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()[:32]

    def _make_app(self, mock_db: AsyncMock, secret: str | None) -> "TestClient":
        """Build a minimal FastAPI app with the unsubscribe router and mocked deps."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.dependencies import get_db_session
        from api.v1.public_unsubscribe import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        async def _override_db():
            yield mock_db

        app.dependency_overrides[get_db_session] = _override_db

        return TestClient(app, raise_server_exceptions=False), secret

    def _build_mock_db(self, row_found: bool = True) -> AsyncMock:
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock() if row_found else None
        db.execute.return_value = mock_result
        db.commit = AsyncMock()
        return db

    async def test_valid_token_returns_redirect(self):
        secret = "test-unsubscribe-secret"
        user_id = "user-test-123"
        tok = self._make_token(user_id, secret)
        mock_db = self._build_mock_db(row_found=True)

        client, _ = self._make_app(mock_db, secret)
        with patch("api.v1.public_unsubscribe._settings") as s:
            s.effective_unsubscribe_secret = secret
            response = client.get(
                f"/api/v1/public/unsubscribe?uid={user_id}&tok={tok}",
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "unsubscribed" in response.headers["location"]

    async def test_invalid_token_returns_400(self):
        mock_db = self._build_mock_db()
        client, _ = self._make_app(mock_db, "real-secret")

        with patch("api.v1.public_unsubscribe._settings") as s:
            s.effective_unsubscribe_secret = "real-secret"
            response = client.get(
                "/api/v1/public/unsubscribe?uid=user-1&tok=bad0bad0bad0bad0bad0bad0bad0bad0",
                follow_redirects=False,
            )

        assert response.status_code == 400

    async def test_missing_secret_returns_500(self):
        mock_db = self._build_mock_db()
        client, _ = self._make_app(mock_db, None)

        with patch("api.v1.public_unsubscribe._settings") as s:
            s.effective_unsubscribe_secret = None
            response = client.get(
                "/api/v1/public/unsubscribe?uid=user-1&tok=tok",
                follow_redirects=False,
            )

        assert response.status_code == 500

    async def test_already_unsubscribed_still_redirects(self):
        """fetchone returns None when user was already unsubscribed (noop path)."""
        secret = "noop-secret"
        user_id = "user-already-gone"
        tok = self._make_token(user_id, secret)
        mock_db = self._build_mock_db(row_found=False)

        client, _ = self._make_app(mock_db, secret)
        with patch("api.v1.public_unsubscribe._settings") as s:
            s.effective_unsubscribe_secret = secret
            response = client.get(
                f"/api/v1/public/unsubscribe?uid={user_id}&tok={tok}",
                follow_redirects=False,
            )

        # Noop path still redirects — user sees the same confirmation page
        assert response.status_code == 302

    async def test_db_commit_called_on_success(self):
        secret = "commit-test-secret"
        user_id = "user-commit-check"
        tok = self._make_token(user_id, secret)
        mock_db = self._build_mock_db(row_found=True)

        client, _ = self._make_app(mock_db, secret)
        with patch("api.v1.public_unsubscribe._settings") as s:
            s.effective_unsubscribe_secret = secret
            client.get(
                f"/api/v1/public/unsubscribe?uid={user_id}&tok={tok}",
                follow_redirects=False,
            )

        mock_db.commit.assert_called_once()
