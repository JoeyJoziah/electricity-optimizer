"""
Tests for backend/auth/neon_auth.py — session validation and caching.

Zenith P0 H-15-01: Verify session cache TTL is 60s (not the original 300s)
to limit the stale-session window for banned users.

Security hardening: Verify AES-256-GCM encryption of session cache in Redis.
"""

import hashlib
import hmac as hmac_mod
import json
from base64 import b64encode
from unittest.mock import AsyncMock, MagicMock, patch

from auth.neon_auth import (_SESSION_CACHE_TTL, _decrypt_session_cache,
                            _encrypt_session_cache, _get_session_from_token,
                            _unsign_cookie_token, invalidate_session_cache)


class TestUnsignCookieToken:
    """Verify Better Auth signed cookie parsing in _unsign_cookie_token."""

    def _make_signed(self, token: str, secret: str) -> str:
        """Replicate Better Auth's signing: token.base64(HMAC-SHA256(token, secret))."""
        sig = hmac_mod.new(
            secret.encode("utf-8"),
            token.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return f"{token}.{b64encode(sig).decode('ascii')}"

    def test_unsigned_token_returned_as_is(self):
        """A token with no '.' separator is returned unchanged."""
        assert _unsign_cookie_token("plain-token-no-dots") == "plain-token-no-dots"

    def test_signed_token_extracts_raw(self):
        """A properly signed cookie value yields the raw token."""
        secret = "a" * 64
        raw = "ES4SabyB9mmzKHAXq12dr4Hx7eBfBtl1"
        signed = self._make_signed(raw, secret)

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.better_auth_secret = secret
            result = _unsign_cookie_token(signed)

        assert result == raw

    def test_bad_signature_returns_full_value(self):
        """If the HMAC doesn't match, the full signed value is returned (will fail DB lookup)."""
        secret = "a" * 64
        raw = "ES4SabyB9mmzKHAXq12dr4Hx7eBfBtl1"
        # Sign with wrong secret
        signed = self._make_signed(raw, "wrong-secret")

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.better_auth_secret = secret
            result = _unsign_cookie_token(signed)

        assert result == signed  # Returns full signed value

    def test_no_secret_still_extracts_raw(self):
        """Without BETTER_AUTH_SECRET, the raw token is extracted without verification."""
        signed = "some-token.c29tZS1zaWduYXR1cmU="

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.better_auth_secret = None
            result = _unsign_cookie_token(signed)

        assert result == "some-token"

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert _unsign_cookie_token("") == ""

    def test_token_with_dots_uses_rfind(self):
        """If token itself contains dots, rfind splits on the last one (the signature)."""
        secret = "b" * 64
        raw = "token.with.dots.in.it"
        signed = self._make_signed(raw, secret)

        with patch("auth.neon_auth.settings") as mock_settings:
            mock_settings.better_auth_secret = secret
            result = _unsign_cookie_token(signed)

        assert result == raw


class TestSessionCacheTTL:
    """Zenith H-15-01: session cache TTL must be 60 seconds."""

    def test_session_cache_ttl_is_60(self):
        assert (
            _SESSION_CACHE_TTL == 60
        ), f"Expected _SESSION_CACHE_TTL=60 (Zenith H-15-01), got {_SESSION_CACHE_TTL}"

    async def test_session_cached_with_correct_ttl(self):
        """Verify Redis setex is called with TTL=60 when caching a session."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # Cache miss
        mock_redis.setex = AsyncMock()

        mock_db = AsyncMock()
        # Simulate a valid session row
        mock_row = MagicMock()
        mock_row.user_id = "user-123"
        mock_row.email = "test@example.com"
        mock_row.name = "Test User"
        mock_row.email_verified = True
        mock_row.role = "user"

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        session = await _get_session_from_token(
            "test-session-token", mock_db, redis=mock_redis
        )

        assert session is not None
        assert session.user_id == "user-123"
        assert session.email == "test@example.com"

        # Verify setex was called with TTL=60
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 60, f"Expected setex TTL=60, got {call_args[0][1]}"

    async def test_session_returned_from_cache(self):
        """Verify cached sessions are returned without hitting DB (legacy plaintext)."""
        # Legacy unencrypted cache entry (starts with '{')
        cached_data = json.dumps(
            {
                "user_id": "cached-user",
                "email": "cached@example.com",
                "name": "Cached",
                "email_verified": True,
                "role": None,
            }
        )
        mock_redis = AsyncMock()

        # Return cached data for session key, None for banned_user marker
        async def _redis_get(key):
            if key.startswith("banned_user:"):
                return None
            return cached_data

        mock_redis.get = AsyncMock(side_effect=_redis_get)

        mock_db = AsyncMock()

        session = await _get_session_from_token(
            "cached-token", mock_db, redis=mock_redis
        )

        assert session is not None
        assert session.user_id == "cached-user"
        # DB should NOT have been called
        mock_db.execute.assert_not_called()

    async def test_invalidate_session_cache(self):
        """Verify cache invalidation deletes the correct key."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        result = await invalidate_session_cache("some-token", redis=mock_redis)

        assert result is True
        mock_redis.delete.assert_called_once()


class TestSessionCacheEncryption:
    """Verify AES-256-GCM encryption of session data in Redis."""

    def test_encrypt_decrypt_roundtrip_with_key(self):
        """Encrypted data decrypts back to the original plaintext."""
        plaintext = json.dumps(
            {
                "user_id": "u-123",
                "email": "test@example.com",
                "name": "Test",
                "email_verified": True,
                "role": "user",
            }
        )
        with patch("utils.encryption.settings") as mock_settings:
            import secrets

            mock_settings.field_encryption_key = secrets.token_hex(32)
            encrypted = _encrypt_session_cache(plaintext)
            # Encrypted output must be bytes and must NOT be the same as plaintext
            assert isinstance(encrypted, bytes)
            assert encrypted != plaintext.encode("utf-8")
            # Decrypt must recover original
            decrypted = _decrypt_session_cache(encrypted)
            assert decrypted == plaintext

    def test_encrypt_fallback_without_key(self):
        """Without FIELD_ENCRYPTION_KEY, encrypt falls back to plaintext bytes."""
        plaintext = '{"user_id": "u-no-key"}'
        with patch("utils.encryption.settings") as mock_settings:
            mock_settings.field_encryption_key = None
            result = _encrypt_session_cache(plaintext)
            assert result == plaintext.encode("utf-8")

    def test_decrypt_legacy_plaintext(self):
        """Legacy unencrypted JSON cache entries are handled gracefully."""
        legacy = b'{"user_id": "legacy-user", "email": "a@b.com"}'
        result = _decrypt_session_cache(legacy)
        data = json.loads(result)
        assert data["user_id"] == "legacy-user"

    def test_decrypt_handles_string_input(self):
        """Redis may return str instead of bytes in some drivers."""
        legacy_str = '{"user_id": "str-user"}'
        result = _decrypt_session_cache(legacy_str)
        data = json.loads(result)
        assert data["user_id"] == "str-user"

    async def test_encrypted_cache_stored_on_cache_miss(self):
        """On cache miss, session data is stored encrypted in Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # Cache miss
        mock_redis.setex = AsyncMock()

        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.user_id = "enc-user"
        mock_row.email = "enc@example.com"
        mock_row.name = "Encrypted User"
        mock_row.email_verified = True
        mock_row.role = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("utils.encryption.settings") as mock_settings:
            import secrets

            mock_settings.field_encryption_key = secrets.token_hex(32)

            session = await _get_session_from_token(
                "enc-test-token", mock_db, redis=mock_redis
            )

            assert session is not None
            assert session.user_id == "enc-user"

            # Verify setex was called and the stored value is encrypted (bytes, not JSON string)
            mock_redis.setex.assert_called_once()
            stored_value = mock_redis.setex.call_args[0][2]
            assert isinstance(stored_value, bytes)
            # Encrypted data should NOT start with '{' (which would indicate plaintext JSON)
            assert stored_value[0:1] != b"{"

    async def test_encrypted_cache_read_on_cache_hit(self):
        """Encrypted cache entries are decrypted and returned correctly."""
        import secrets

        test_key = secrets.token_hex(32)

        session_payload = json.dumps(
            {
                "user_id": "enc-cached",
                "email": "enc@cached.com",
                "name": "Enc Cached",
                "email_verified": True,
                "role": "admin",
            }
        )

        # Encrypt with the test key
        with patch("utils.encryption.settings") as mock_settings:
            mock_settings.field_encryption_key = test_key
            encrypted = _encrypt_session_cache(session_payload)

        mock_redis = AsyncMock()

        # Return encrypted data for session key, None for banned_user marker
        async def _redis_get(key):
            if key.startswith("banned_user:"):
                return None
            return encrypted

        mock_redis.get = AsyncMock(side_effect=_redis_get)
        mock_db = AsyncMock()

        with patch("utils.encryption.settings") as mock_settings:
            mock_settings.field_encryption_key = test_key

            session = await _get_session_from_token(
                "enc-hit-token", mock_db, redis=mock_redis
            )

        assert session is not None
        assert session.user_id == "enc-cached"
        assert session.email == "enc@cached.com"
        assert session.role == "admin"
        # DB should NOT have been called (cache hit)
        mock_db.execute.assert_not_called()
