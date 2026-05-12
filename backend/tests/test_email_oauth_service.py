"""Tests for email_oauth_service — CSRF/HMAC state generation + verification."""

import time
from unittest.mock import MagicMock, patch

import pytest

import services.email_oauth_service as svc_module
from services.email_oauth_service import (
    _get_oauth_signing_key,
    generate_oauth_state,
    get_gmail_consent_url,
    get_outlook_consent_url,
    verify_oauth_state,
)

# ---------------------------------------------------------------------------
# Helpers — patch settings
# ---------------------------------------------------------------------------


def _settings(oauth_state_secret="secret-key-xyz", internal_api_key="internal-fallback"):
    s = MagicMock()
    s.oauth_state_secret = oauth_state_secret
    s.internal_api_key = internal_api_key
    s.oauth_redirect_base_url = "https://app.example.com"
    s.gmail_client_id = "gmail-cid"
    s.outlook_client_id = "outlook-cid"
    return s


# ---------------------------------------------------------------------------
# _get_oauth_signing_key
# ---------------------------------------------------------------------------


class TestGetOauthSigningKey:
    def test_prefers_oauth_state_secret(self):
        with patch.object(svc_module, "settings", _settings(oauth_state_secret="my-secret")):
            key = _get_oauth_signing_key()
        assert key == b"my-secret"

    def test_falls_back_to_internal_api_key_when_no_oauth_secret(self):
        with patch.object(
            svc_module,
            "settings",
            _settings(oauth_state_secret="", internal_api_key="fallback-key"),
        ):
            # Reset the warned flag so we can test the warning path
            svc_module._get_oauth_signing_key._warned = False
            key = _get_oauth_signing_key()
        assert key == b"fallback-key"

    def test_raises_when_both_secrets_missing(self):
        with patch.object(
            svc_module, "settings", _settings(oauth_state_secret="", internal_api_key="")
        ):
            with pytest.raises(RuntimeError, match="OAUTH_STATE_SECRET"):
                _get_oauth_signing_key()


# ---------------------------------------------------------------------------
# generate_oauth_state
# ---------------------------------------------------------------------------


class TestGenerateOauthState:
    def test_produces_5_part_colon_separated_token(self):
        with patch.object(svc_module, "settings", _settings()):
            state = generate_oauth_state("cid-1", "uid-1")
        assert state.count(":") == 4, f"Expected 4 colons, got: {state!r}"

    def test_embeds_connection_id_in_first_part(self):
        with patch.object(svc_module, "settings", _settings()):
            state = generate_oauth_state("conn-abc", "uid-1")
        assert state.split(":")[0] == "conn-abc"

    def test_embeds_user_id_in_second_part(self):
        with patch.object(svc_module, "settings", _settings()):
            state = generate_oauth_state("cid-1", "user-xyz")
        assert state.split(":")[1] == "user-xyz"

    def test_each_call_produces_unique_nonce(self):
        with patch.object(svc_module, "settings", _settings()):
            s1 = generate_oauth_state("cid-1")
            s2 = generate_oauth_state("cid-1")
        # nonces (part index 2) should differ
        assert s1.split(":")[2] != s2.split(":")[2]

    def test_timestamp_is_approximately_now(self):
        before = int(time.time())
        with patch.object(svc_module, "settings", _settings()):
            state = generate_oauth_state("cid-1")
        after = int(time.time())
        ts = int(state.split(":")[3])
        assert before <= ts <= after + 1


# ---------------------------------------------------------------------------
# verify_oauth_state
# ---------------------------------------------------------------------------


class TestVerifyOauthState:
    def _gen(self, connection_id="cid-1", user_id="uid-1"):
        return generate_oauth_state(connection_id, user_id)

    def test_roundtrip_returns_connection_and_user_id(self):
        with patch.object(svc_module, "settings", _settings()):
            state = self._gen("cid-1", "uid-1")
            cid, uid = verify_oauth_state(state)
        assert cid == "cid-1"
        assert uid == "uid-1"

    def test_returns_none_on_tampered_hmac(self):
        with patch.object(svc_module, "settings", _settings()):
            state = self._gen()
            parts = state.split(":")
            parts[-1] = "deadbeef" * 8  # replace HMAC
            tampered = ":".join(parts)
            cid, uid = verify_oauth_state(tampered)
        assert cid is None
        assert uid is None

    def test_returns_none_when_connection_id_tampered(self):
        with patch.object(svc_module, "settings", _settings()):
            state = self._gen("cid-legit", "uid-1")
            # Swap connection_id but leave HMAC from original
            tampered = "cid-evil:" + ":".join(state.split(":")[1:])
            cid, uid = verify_oauth_state(tampered)
        assert cid is None

    def test_returns_none_on_wrong_part_count(self):
        with patch.object(svc_module, "settings", _settings()):
            cid, uid = verify_oauth_state("only:four:parts:here")
        assert cid is None
        assert uid is None

    def test_returns_none_on_expired_state(self):
        # Generate a state with a timestamp 700s in the past (> max_age)
        old_time = int(time.time()) - 700
        with patch.object(svc_module, "settings", _settings()):
            with patch.object(svc_module.time, "time", return_value=float(old_time)):
                state = self._gen()
            cid, uid = verify_oauth_state(state, max_age_seconds=600)
        assert cid is None

    def test_returns_none_on_future_timestamp(self):
        # Timestamp far in the future → age < 0
        future_time = int(time.time()) + 3600
        with patch.object(svc_module, "settings", _settings()):
            with patch.object(svc_module.time, "time", return_value=float(future_time)):
                state = self._gen()
            cid, uid = verify_oauth_state(state, max_age_seconds=600)
        assert cid is None

    def test_accepts_state_with_empty_user_id(self):
        with patch.object(svc_module, "settings", _settings()):
            state = generate_oauth_state("cid-1")  # user_id defaults to ""
            cid, uid = verify_oauth_state(state)
        assert cid == "cid-1"
        assert uid == ""

    def test_returns_none_on_non_integer_timestamp(self):
        with patch.object(svc_module, "settings", _settings()):
            state = self._gen()
            parts = state.split(":")
            parts[3] = "notanint"
            # Recompute HMAC to ensure we test the timestamp parse, not HMAC path
            import hashlib
            import hmac as _hmac

            key = b"secret-key-xyz"
            payload = ":".join(parts[:4])
            mac = _hmac.HMAC(key, payload.encode(), hashlib.sha256).hexdigest()
            parts[4] = mac
            cid, uid = verify_oauth_state(":".join(parts))
        assert cid is None


# ---------------------------------------------------------------------------
# Consent URL helpers
# ---------------------------------------------------------------------------


def test_gmail_consent_url_contains_gmail_auth_endpoint():
    with patch.object(svc_module, "settings", _settings()):
        url = get_gmail_consent_url("cid-1")
    assert "accounts.google.com" in url


def test_gmail_consent_url_includes_state_param():
    with patch.object(svc_module, "settings", _settings()):
        url = get_gmail_consent_url("cid-1")
    assert "state=" in url


def test_outlook_consent_url_contains_microsoft_endpoint():
    with patch.object(svc_module, "settings", _settings()):
        url = get_outlook_consent_url("cid-1")
    assert "microsoftonline.com" in url


def test_outlook_consent_url_includes_state_param():
    with patch.object(svc_module, "settings", _settings()):
        url = get_outlook_consent_url("cid-1")
    assert "state=" in url
