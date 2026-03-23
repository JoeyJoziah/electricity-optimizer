"""
Neon Auth Hardening Tests (Sprint 1, Tasks 1.2 + 1.3)

Tests for audit remediation findings:
- 11-P1-2: Production-only __Secure- cookie enforcement
- 11-P1-4: Fail-hard on session cache encryption in production

These tests verify that security controls behave differently based on
the environment (production vs development/test).
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# =============================================================================
# 11-P1-2: Production-only __Secure- Cookie Enforcement
# =============================================================================


class TestSecureCookieEnforcement:
    """Task 1.2: In production, ONLY accept __Secure- prefixed cookies."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock async database session with a valid user row."""
        session = AsyncMock()
        mock_row = MagicMock()
        mock_row.user_id = "user-secure-test"
        mock_row.email = "secure@example.com"
        mock_row.name = "Secure Test User"
        mock_row.email_verified = True
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        session.execute.return_value = mock_result
        return session

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request with empty cookies."""
        request = MagicMock()
        request.cookies = {}
        return request

    # -------------------------------------------------------------------------
    # Production mode: reject non-__Secure- cookies
    # -------------------------------------------------------------------------

    async def test_production_rejects_plain_cookie(self, mock_db_session, mock_request):
        """In production, a plain 'better-auth.session_token' cookie is ignored."""
        from auth.neon_auth import SESSION_COOKIE_NAME, get_current_user

        mock_request.cookies = {SESSION_COOKIE_NAME: "plain-cookie-token"}

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            with pytest.raises(Exception) as exc_info:
                await get_current_user(mock_request, None, mock_db_session)

            # Should be a 401 because the plain cookie is not accepted
            assert exc_info.value.status_code == 401

    async def test_production_accepts_secure_cookie(self, mock_db_session, mock_request):
        """In production, the __Secure- prefixed cookie is accepted."""
        from auth.neon_auth import SESSION_COOKIE_NAME_SECURE, get_current_user

        mock_request.cookies = {SESSION_COOKIE_NAME_SECURE: "secure-cookie-token"}

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            result = await get_current_user(mock_request, None, mock_db_session)

        assert result.user_id == "user-secure-test"
        assert result.email == "secure@example.com"

    async def test_production_ignores_plain_when_both_present(self, mock_db_session, mock_request):
        """In production, when both cookies exist, only __Secure- is used.

        This verifies the plain cookie value is never read in production,
        even if an attacker manages to inject it alongside the secure one.
        """
        from auth.neon_auth import (
            SESSION_COOKIE_NAME,
            SESSION_COOKIE_NAME_SECURE,
            get_current_user,
        )

        # Set both cookies -- the plain one has a different (attacker) token
        mock_request.cookies = {
            SESSION_COOKIE_NAME: "attacker-injected-token",
            SESSION_COOKIE_NAME_SECURE: "legitimate-secure-token",
        }

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            result = await get_current_user(mock_request, None, mock_db_session)

        assert result.user_id == "user-secure-test"
        # Verify the DB was queried with the secure token, not the plain one
        call_args = mock_db_session.execute.call_args
        assert call_args[0][1]["token"] == "legitimate-secure-token"

    # -------------------------------------------------------------------------
    # Development/test mode: accept both cookie names
    # -------------------------------------------------------------------------

    async def test_development_accepts_plain_cookie(self, mock_db_session, mock_request):
        """In development, the plain cookie name is accepted."""
        from auth.neon_auth import SESSION_COOKIE_NAME, get_current_user

        mock_request.cookies = {SESSION_COOKIE_NAME: "dev-plain-token"}

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = False
            result = await get_current_user(mock_request, None, mock_db_session)

        assert result.user_id == "user-secure-test"

    async def test_development_accepts_secure_cookie(self, mock_db_session, mock_request):
        """In development, the __Secure- cookie is also accepted."""
        from auth.neon_auth import SESSION_COOKIE_NAME_SECURE, get_current_user

        mock_request.cookies = {SESSION_COOKIE_NAME_SECURE: "dev-secure-token"}

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = False
            result = await get_current_user(mock_request, None, mock_db_session)

        assert result.user_id == "user-secure-test"

    async def test_development_prefers_plain_cookie(self, mock_db_session, mock_request):
        """In development, when both cookies are present, the plain one is used first."""
        from auth.neon_auth import (
            SESSION_COOKIE_NAME,
            SESSION_COOKIE_NAME_SECURE,
            get_current_user,
        )

        mock_request.cookies = {
            SESSION_COOKIE_NAME: "dev-plain-token",
            SESSION_COOKIE_NAME_SECURE: "dev-secure-token",
        }

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = False
            result = await get_current_user(mock_request, None, mock_db_session)

        assert result.user_id == "user-secure-test"
        # Verify the plain cookie was used (it takes precedence via `or`)
        call_args = mock_db_session.execute.call_args
        assert call_args[0][1]["token"] == "dev-plain-token"

    # -------------------------------------------------------------------------
    # Bearer token works in all environments
    # -------------------------------------------------------------------------

    async def test_bearer_token_works_in_production(self, mock_db_session, mock_request):
        """Bearer token authentication works regardless of environment."""
        from fastapi.security import HTTPAuthorizationCredentials

        from auth.neon_auth import get_current_user

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bearer-prod-token")

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            result = await get_current_user(mock_request, credentials, mock_db_session)

        assert result.user_id == "user-secure-test"
        call_args = mock_db_session.execute.call_args
        assert call_args[0][1]["token"] == "bearer-prod-token"

    async def test_bearer_token_works_in_development(self, mock_db_session, mock_request):
        """Bearer token authentication works in development mode."""
        from fastapi.security import HTTPAuthorizationCredentials

        from auth.neon_auth import get_current_user

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bearer-dev-token")

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = False
            result = await get_current_user(mock_request, credentials, mock_db_session)

        assert result.user_id == "user-secure-test"
        call_args = mock_db_session.execute.call_args
        assert call_args[0][1]["token"] == "bearer-dev-token"

    async def test_bearer_token_takes_precedence_over_cookie(self, mock_db_session, mock_request):
        """Bearer token in header takes precedence over any cookie, in any environment."""
        from fastapi.security import HTTPAuthorizationCredentials

        from auth.neon_auth import SESSION_COOKIE_NAME_SECURE, get_current_user

        mock_request.cookies = {SESSION_COOKIE_NAME_SECURE: "cookie-token"}
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="header-bearer-token"
        )

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            result = await get_current_user(mock_request, credentials, mock_db_session)

        assert result.user_id == "user-secure-test"
        call_args = mock_db_session.execute.call_args
        assert call_args[0][1]["token"] == "header-bearer-token"

    # -------------------------------------------------------------------------
    # No credentials at all still raises 401
    # -------------------------------------------------------------------------

    async def test_no_credentials_raises_401_in_production(self, mock_db_session, mock_request):
        """No cookies and no Bearer token raises 401 in production."""
        from auth.neon_auth import get_current_user

        mock_request.cookies = {}

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            with pytest.raises(Exception) as exc_info:
                await get_current_user(mock_request, None, mock_db_session)
            assert exc_info.value.status_code == 401

    async def test_no_credentials_raises_401_in_development(self, mock_db_session, mock_request):
        """No cookies and no Bearer token raises 401 in development."""
        from auth.neon_auth import get_current_user

        mock_request.cookies = {}

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = False
            with pytest.raises(Exception) as exc_info:
                await get_current_user(mock_request, None, mock_db_session)
            assert exc_info.value.status_code == 401


# =============================================================================
# 11-P1-4: Fail-Hard on Session Cache Encryption in Production
# =============================================================================


class TestEncryptionFailHard:
    """Task 1.3: Production mode must fail hard when encryption is unavailable."""

    # -------------------------------------------------------------------------
    # Production: encryption failure raises RuntimeError
    # -------------------------------------------------------------------------

    def test_production_raises_on_encryption_failure(self):
        """In production, _encrypt_session_cache raises RuntimeError if key is missing."""
        from auth.neon_auth import _encrypt_session_cache

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            with patch(
                "utils.encryption.encrypt_field",
                side_effect=RuntimeError("FIELD_ENCRYPTION_KEY is not configured"),
            ):
                with pytest.raises(RuntimeError, match="FIELD_ENCRYPTION_KEY"):
                    _encrypt_session_cache('{"user_id": "test"}')

    def test_production_does_not_fallback_to_plaintext(self):
        """In production, encryption failure never returns plaintext bytes."""
        from auth.neon_auth import _encrypt_session_cache

        plaintext = '{"user_id": "secret-data", "email": "secret@example.com"}'

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            with patch(
                "utils.encryption.encrypt_field",
                side_effect=RuntimeError("FIELD_ENCRYPTION_KEY is not configured"),
            ):
                with pytest.raises(RuntimeError):
                    result = _encrypt_session_cache(plaintext)
                    # This assertion should never be reached, but if it is,
                    # it means plaintext was returned in production
                    assert result != plaintext.encode("utf-8")

    def test_production_succeeds_when_encryption_works(self):
        """In production, _encrypt_session_cache works normally when key is configured."""
        from auth.neon_auth import _encrypt_session_cache

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            with patch(
                "utils.encryption.encrypt_field",
                return_value=b"\x00\x01\x02encrypted-data",
            ):
                result = _encrypt_session_cache('{"user_id": "test"}')
                assert result == b"\x00\x01\x02encrypted-data"

    # -------------------------------------------------------------------------
    # Development/test: encryption failure falls back to plaintext
    # -------------------------------------------------------------------------

    def test_development_falls_back_to_plaintext(self):
        """In development, _encrypt_session_cache falls back to plaintext."""
        from auth.neon_auth import _encrypt_session_cache

        plaintext = '{"user_id": "dev-user", "email": "dev@example.com"}'

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = False
            with patch(
                "utils.encryption.encrypt_field",
                side_effect=RuntimeError("FIELD_ENCRYPTION_KEY is not configured"),
            ):
                result = _encrypt_session_cache(plaintext)
                # In development, should fall back to plaintext bytes
                assert result == plaintext.encode("utf-8")

    def test_development_uses_encryption_when_available(self):
        """In development, _encrypt_session_cache uses encryption if the key is available."""
        from auth.neon_auth import _encrypt_session_cache

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = False
            with patch(
                "utils.encryption.encrypt_field",
                return_value=b"\xaa\xbb\xccencrypted",
            ):
                result = _encrypt_session_cache('{"user_id": "test"}')
                assert result == b"\xaa\xbb\xccencrypted"

    def test_test_environment_falls_back_to_plaintext(self):
        """In test environment, encryption failure also falls back to plaintext."""
        from auth.neon_auth import _encrypt_session_cache

        plaintext = '{"user_id": "test-user"}'

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = False
            with patch(
                "utils.encryption.encrypt_field",
                side_effect=RuntimeError("FIELD_ENCRYPTION_KEY is not configured"),
            ):
                result = _encrypt_session_cache(plaintext)
                assert result == plaintext.encode("utf-8")

    # -------------------------------------------------------------------------
    # Integration: production encryption failure prevents Redis caching
    # -------------------------------------------------------------------------

    async def test_production_encryption_failure_prevents_cache_write(self):
        """In production, if encryption fails, session data is NOT cached in Redis.

        The _get_session_from_token function catches all exceptions during
        cache write, so a RuntimeError from _encrypt_session_cache means
        the session simply is not cached (next request re-queries the DB).
        """
        from auth.neon_auth import _get_session_from_token

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss
        mock_redis.setex = AsyncMock()

        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.user_id = "user-no-cache"
        mock_row.email = "nocache@example.com"
        mock_row.name = "No Cache"
        mock_row.email_verified = True
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.is_production = True
            with patch(
                "auth.neon_auth._encrypt_session_cache",
                side_effect=RuntimeError("FIELD_ENCRYPTION_KEY is not configured"),
            ):
                # Should still return session data from DB (caching is non-fatal)
                result = await _get_session_from_token("token-123", mock_db, redis=mock_redis)

        assert result is not None
        assert result.user_id == "user-no-cache"
        # setex should NOT have been called successfully (the exception
        # was raised inside _encrypt_session_cache and caught by the
        # outer try/except in _get_session_from_token)
        mock_redis.setex.assert_not_awaited()
