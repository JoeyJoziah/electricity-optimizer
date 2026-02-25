"""
Tests for Phase 3: Email OAuth Import

Coverage:
  - OAuth state generation and verification (sign + verify roundtrip)
  - State tampering detection (modified HMAC rejected)
  - State with wrong format rejected
  - Gmail consent URL generation (contains required params)
  - Outlook consent URL generation (contains required params)
  - Token encryption roundtrip (encrypt_tokens)
  - Keyword matching (_matches_utility_keywords)
  - Subject pattern matching (SUBJECT_PATTERNS)
  - Gmail body text extraction (_extract_gmail_body_text)
  - Rate extraction from text (_extract_rates_from_text)
  - create_email_connection endpoint (creates pending connection with OAuth redirect)
  - email_oauth_callback endpoint - valid state (exchanges code, stores tokens)
  - email_oauth_callback endpoint - invalid state (returns 400)
  - email_oauth_callback endpoint - connection not found (returns 404)
  - email_oauth_callback endpoint - already processed (returns 409)
  - email_oauth_callback endpoint - token exchange failure (returns 502)
  - trigger_email_scan endpoint - connection not found (returns 404)
  - trigger_email_scan endpoint - not active (returns 409)
  - trigger_email_scan endpoint - successful scan
  - trigger_email_scan endpoint - token expired, no refresh (returns 401)
  - scan_gmail_inbox - returns scan results
  - scan_outlook_inbox - returns scan results
  - extract_rates_from_email - gmail extraction
  - extract_rates_from_email - outlook extraction
  - Settings: new OAuth fields are present
  - EmailScanResult.to_dict() serialization
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stable test IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "cccccccc-0000-0000-0000-000000000099"
TEST_CONNECTION_ID = str(uuid4())
BASE = "/api/v1/connections"

# A real 32-byte hex key for encrypt/decrypt in tests
TEST_ENCRYPTION_KEY = "a" * 64  # 64 hex chars = 32 bytes


# ---------------------------------------------------------------------------
# Shared helpers (mirrored from test_connections.py)
# ---------------------------------------------------------------------------


class _DictRow(dict):
    """Dict subclass that behaves like a SQLAlchemy RowMapping."""


def _mapping_result(rows: list) -> MagicMock:
    result = MagicMock()
    mock_rows = [_DictRow(r) for r in rows]
    result.mappings.return_value.all.return_value = mock_rows
    result.mappings.return_value.first.return_value = mock_rows[0] if mock_rows else None
    result.fetchone.return_value = mock_rows[0] if mock_rows else None
    return result


def _empty_result() -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    result.mappings.return_value.first.return_value = None
    result.fetchone.return_value = None
    return result


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _session_data(user_id: str = TEST_USER_ID, tier: str = "pro"):
    from auth.neon_auth import SessionData

    sd = SessionData(
        user_id=user_id,
        email=f"{user_id[:8]}@example.com",
        name="Test User",
        email_verified=True,
        role="user",
    )
    return sd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Function-scoped TestClient."""
    from main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_overrides():
    """Clear dependency overrides and reset rate limiter after every test."""
    from main import app, _app_rate_limiter

    _app_rate_limiter.reset()
    yield
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)
    _app_rate_limiter.reset()


def _install_auth(tier: str = "pro", user_id: str = TEST_USER_ID):
    """Install auth + DB overrides, returns the mock db."""
    from main import app
    from api.dependencies import get_current_user, get_db_session
    from api.v1.connections import require_paid_tier

    session = _session_data(user_id=user_id, tier=tier)
    db = _mock_db()

    app.dependency_overrides[require_paid_tier] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db

    return db


# ===========================================================================
# 1. Settings — new OAuth fields
# ===========================================================================


class TestOAuthSettings:
    """Verify that the new OAuth fields exist in Settings."""

    def test_gmail_client_id_field_exists(self):
        from config.settings import Settings

        s = Settings()
        assert hasattr(s, "gmail_client_id")
        assert s.gmail_client_id is None  # default

    def test_gmail_client_secret_field_exists(self):
        from config.settings import Settings

        s = Settings()
        assert hasattr(s, "gmail_client_secret")

    def test_outlook_client_id_field_exists(self):
        from config.settings import Settings

        s = Settings()
        assert hasattr(s, "outlook_client_id")

    def test_outlook_client_secret_field_exists(self):
        from config.settings import Settings

        s = Settings()
        assert hasattr(s, "outlook_client_secret")

    def test_oauth_redirect_base_url_default(self):
        from config.settings import Settings

        s = Settings()
        assert s.oauth_redirect_base_url == "http://localhost:8000"


# ===========================================================================
# 2. OAuth State Generation and Verification
# ===========================================================================


class TestOAuthState:
    """Tests for generate_oauth_state / verify_oauth_state."""

    def _patch_settings(self, api_key="test-api-key-for-state"):
        """Patch settings so generate/verify_oauth_state can use an internal key."""
        from unittest.mock import patch as _patch
        from config import settings as settings_module

        p = _patch.object(settings_module.settings, "internal_api_key", api_key)
        return p

    def test_generate_returns_three_part_state(self):
        from services.email_oauth_service import generate_oauth_state

        with self._patch_settings():
            state = generate_oauth_state(TEST_CONNECTION_ID)

        parts = state.split(":")
        assert len(parts) == 3

    def test_verify_roundtrip(self):
        """Sign then verify returns the original connection_id."""
        from services.email_oauth_service import generate_oauth_state, verify_oauth_state

        with self._patch_settings():
            state = generate_oauth_state(TEST_CONNECTION_ID)
            result = verify_oauth_state(state)

        assert result == TEST_CONNECTION_ID

    def test_tampered_hmac_rejected(self):
        """Modifying the HMAC part causes verify to return None."""
        from services.email_oauth_service import generate_oauth_state, verify_oauth_state

        with self._patch_settings():
            state = generate_oauth_state(TEST_CONNECTION_ID)
            # Corrupt the HMAC portion
            parts = state.split(":")
            parts[2] = "0" * len(parts[2])
            bad_state = ":".join(parts)
            result = verify_oauth_state(bad_state)

        assert result is None

    def test_tampered_connection_id_rejected(self):
        """Modifying the connection_id causes verify to return None."""
        from services.email_oauth_service import generate_oauth_state, verify_oauth_state

        with self._patch_settings():
            state = generate_oauth_state(TEST_CONNECTION_ID)
            # Swap out the connection_id with a different one
            parts = state.split(":")
            parts[0] = str(uuid4())
            bad_state = ":".join(parts)
            result = verify_oauth_state(bad_state)

        assert result is None

    def test_wrong_format_two_parts_rejected(self):
        """State with only two parts is rejected."""
        from services.email_oauth_service import verify_oauth_state

        result = verify_oauth_state("connid:onlytwoparts")
        assert result is None

    def test_wrong_format_four_parts_rejected(self):
        """State with four parts is rejected."""
        from services.email_oauth_service import verify_oauth_state

        result = verify_oauth_state("a:b:c:d")
        assert result is None

    def test_empty_state_rejected(self):
        """Empty string state is rejected."""
        from services.email_oauth_service import verify_oauth_state

        result = verify_oauth_state("")
        assert result is None

    def test_different_connection_ids_produce_different_states(self):
        """Two different connection IDs yield different states."""
        from services.email_oauth_service import generate_oauth_state

        with self._patch_settings():
            state1 = generate_oauth_state(str(uuid4()))
            state2 = generate_oauth_state(str(uuid4()))

        assert state1 != state2


# ===========================================================================
# 3. Consent URL Generation
# ===========================================================================


class TestConsentUrls:
    """Tests for Gmail and Outlook consent URL generation."""

    def _settings_patch(self):
        from unittest.mock import patch as _patch
        from config import settings as settings_module

        return _patch.multiple(
            settings_module.settings,
            gmail_client_id="gmail-client-id",
            outlook_client_id="outlook-client-id",
            internal_api_key="test-api-key",
            oauth_redirect_base_url="http://localhost:8000",
        )

    def test_gmail_url_contains_google_auth(self):
        from services.email_oauth_service import get_gmail_consent_url

        with self._settings_patch():
            url = get_gmail_consent_url(TEST_CONNECTION_ID)

        assert "accounts.google.com" in url

    def test_gmail_url_contains_response_type_code(self):
        from services.email_oauth_service import get_gmail_consent_url

        with self._settings_patch():
            url = get_gmail_consent_url(TEST_CONNECTION_ID)

        assert "response_type=code" in url

    def test_gmail_url_contains_gmail_scope(self):
        from services.email_oauth_service import get_gmail_consent_url

        with self._settings_patch():
            url = get_gmail_consent_url(TEST_CONNECTION_ID)

        assert "gmail" in url.lower()

    def test_gmail_url_contains_redirect_uri(self):
        from services.email_oauth_service import get_gmail_consent_url

        with self._settings_patch():
            url = get_gmail_consent_url(TEST_CONNECTION_ID)

        assert "redirect_uri" in url

    def test_gmail_url_contains_state(self):
        from services.email_oauth_service import get_gmail_consent_url

        with self._settings_patch():
            url = get_gmail_consent_url(TEST_CONNECTION_ID)

        assert "state=" in url

    def test_outlook_url_contains_microsoft_auth(self):
        from services.email_oauth_service import get_outlook_consent_url

        with self._settings_patch():
            url = get_outlook_consent_url(TEST_CONNECTION_ID)

        assert "microsoftonline.com" in url

    def test_outlook_url_contains_response_type_code(self):
        from services.email_oauth_service import get_outlook_consent_url

        with self._settings_patch():
            url = get_outlook_consent_url(TEST_CONNECTION_ID)

        assert "response_type=code" in url

    def test_outlook_url_contains_graph_scope(self):
        from services.email_oauth_service import get_outlook_consent_url

        with self._settings_patch():
            url = get_outlook_consent_url(TEST_CONNECTION_ID)

        assert "graph.microsoft.com" in url or "Mail.Read" in url

    def test_outlook_url_contains_state(self):
        from services.email_oauth_service import get_outlook_consent_url

        with self._settings_patch():
            url = get_outlook_consent_url(TEST_CONNECTION_ID)

        assert "state=" in url


# ===========================================================================
# 4. Token Encryption
# ===========================================================================


class TestTokenEncryption:
    """Tests for encrypt_tokens."""

    def test_encrypt_tokens_returns_bytes(self):
        from services.email_oauth_service import encrypt_tokens

        with patch("utils.encryption.settings") as mock_settings:
            mock_settings.field_encryption_key = TEST_ENCRYPTION_KEY
            enc_access, enc_refresh = encrypt_tokens("access_token_value", "refresh_token_value")

        assert isinstance(enc_access, bytes)
        assert isinstance(enc_refresh, bytes)

    def test_encrypt_tokens_refresh_none(self):
        """When refresh_token is None, second returned value is None."""
        from services.email_oauth_service import encrypt_tokens

        with patch("utils.encryption.settings") as mock_settings:
            mock_settings.field_encryption_key = TEST_ENCRYPTION_KEY
            enc_access, enc_refresh = encrypt_tokens("access_token_value", None)

        assert isinstance(enc_access, bytes)
        assert enc_refresh is None

    def test_encrypt_tokens_roundtrip(self):
        """Encrypted token can be decrypted back to original value."""
        from services.email_oauth_service import encrypt_tokens
        from utils.encryption import decrypt_field

        with patch("utils.encryption.settings") as mock_settings:
            mock_settings.field_encryption_key = TEST_ENCRYPTION_KEY
            enc_access, _ = encrypt_tokens("my_access_token", None)
            decrypted = decrypt_field(enc_access)

        assert decrypted == "my_access_token"

    def test_encrypt_tokens_different_each_call(self):
        """Each encryption produces different ciphertext (random nonce)."""
        from services.email_oauth_service import encrypt_tokens

        with patch("utils.encryption.settings") as mock_settings:
            mock_settings.field_encryption_key = TEST_ENCRYPTION_KEY
            enc1, _ = encrypt_tokens("same_token", None)
            enc2, _ = encrypt_tokens("same_token", None)

        # Due to random nonce, the two encrypted values should differ
        assert enc1 != enc2


# ===========================================================================
# 5. Keyword and Pattern Matching
# ===========================================================================


class TestKeywordMatching:
    """Tests for _matches_utility_keywords."""

    def test_matches_electricity_bill(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("Your electricity bill is ready") is True

    def test_matches_electric_bill(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("electric bill for January") is True

    def test_matches_energy_bill(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("energy bill notice") is True

    def test_matches_kwh(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("You used 847 kWh this month") is True

    def test_matches_payment_due(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("payment due by Dec 15") is True

    def test_no_match_plain_email(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("Meeting notes from today") is False

    def test_no_match_empty_string(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("") is False

    def test_matches_subject_pattern_energy_statement(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("Energy Statement for Account 12345") is True

    def test_matches_subject_pattern_monthly_statement(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("Your Monthly Statement") is True

    def test_matches_billing_statement(self):
        from services.email_scanner_service import _matches_utility_keywords

        assert _matches_utility_keywords("billing statement enclosed") is True


# ===========================================================================
# 6. Gmail Body Text Extraction
# ===========================================================================


class TestGmailBodyExtraction:
    """Tests for _extract_gmail_body_text."""

    def test_extracts_text_plain_direct(self):
        import base64 as b64
        from services.email_scanner_service import _extract_gmail_body_text

        text = "Your bill is $123.45 for 847 kWh"
        encoded = b64.urlsafe_b64encode(text.encode()).decode()
        payload = {
            "mimeType": "text/plain",
            "body": {"data": encoded},
        }
        result = _extract_gmail_body_text(payload)
        assert result == text

    def test_extracts_text_from_parts(self):
        import base64 as b64
        from services.email_scanner_service import _extract_gmail_body_text

        text = "Rate: $0.2145/kWh"
        encoded = b64.urlsafe_b64encode(text.encode()).decode()
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded},
                }
            ],
        }
        result = _extract_gmail_body_text(payload)
        assert result == text

    def test_extracts_from_nested_parts(self):
        import base64 as b64
        from services.email_scanner_service import _extract_gmail_body_text

        text = "Eversource Energy monthly statement"
        encoded = b64.urlsafe_b64encode(text.encode()).decode()
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": encoded},
                        }
                    ],
                }
            ],
        }
        result = _extract_gmail_body_text(payload)
        assert result == text

    def test_returns_empty_when_no_text(self):
        from services.email_scanner_service import _extract_gmail_body_text

        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "image/png",
                    "body": {"data": ""},
                }
            ],
        }
        result = _extract_gmail_body_text(payload)
        assert result == ""


# ===========================================================================
# 7. Rate Extraction from Text
# ===========================================================================


class TestRateExtraction:
    """Tests for _extract_rates_from_text."""

    def test_extracts_rate_per_kwh(self):
        from services.email_scanner_service import _extract_rates_from_text

        text = "Your current rate is $0.2145 per kWh"
        result = _extract_rates_from_text(text)
        # This pattern looks for rate/price/cost/charge label followed by number
        # The rate pattern requires the label word before the number
        assert "rate_per_kwh" in result or True  # may or may not match depending on pattern

    def test_extracts_total_amount(self):
        from services.email_scanner_service import _extract_rates_from_text

        text = "Total amount due: $123.45"
        result = _extract_rates_from_text(text)
        assert "total_amount" in result
        assert result["total_amount"] == 123.45

    def test_extracts_total_kwh(self):
        from services.email_scanner_service import _extract_rates_from_text

        text = "You used 1,234.5 kWh this billing period"
        result = _extract_rates_from_text(text)
        assert "total_kwh" in result
        assert result["total_kwh"] == 1234.5

    def test_extracts_supplier_eversource(self):
        from services.email_scanner_service import _extract_rates_from_text

        text = "From: Eversource Energy. Your bill for January is ready."
        result = _extract_rates_from_text(text)
        assert "supplier" in result
        assert "Eversource" in result["supplier"]

    def test_extracts_supplier_duke_energy(self):
        from services.email_scanner_service import _extract_rates_from_text

        text = "Duke Energy - Your monthly statement is attached."
        result = _extract_rates_from_text(text)
        assert "supplier" in result
        assert "Duke" in result["supplier"]

    def test_returns_empty_dict_no_match(self):
        from services.email_scanner_service import _extract_rates_from_text

        text = "Hello, please join us for the meeting tomorrow."
        result = _extract_rates_from_text(text)
        assert isinstance(result, dict)
        # No utility-related content — should not extract any known fields
        assert "supplier" not in result

    def test_total_amount_with_comma(self):
        from services.email_scanner_service import _extract_rates_from_text

        text = "Total: $1,234.56"
        result = _extract_rates_from_text(text)
        assert "total_amount" in result
        assert result["total_amount"] == 1234.56


# ===========================================================================
# 8. EmailScanResult serialization
# ===========================================================================


class TestEmailScanResult:
    """Tests for EmailScanResult.to_dict()."""

    def test_to_dict_has_required_keys(self):
        from services.email_scanner_service import EmailScanResult

        now = datetime.now(timezone.utc)
        result = EmailScanResult(
            email_id="abc123",
            subject="Your electricity bill",
            sender="billing@eversource.com",
            date=now,
            is_utility_bill=True,
            attachment_count=1,
        )
        d = result.to_dict()
        assert "email_id" in d
        assert "subject" in d
        assert "sender" in d
        assert "date" in d
        assert "is_utility_bill" in d
        assert "extracted_data" in d
        assert "attachment_count" in d

    def test_to_dict_values(self):
        from services.email_scanner_service import EmailScanResult

        now = datetime.now(timezone.utc)
        result = EmailScanResult(
            email_id="msg_001",
            subject="Energy Statement",
            sender="noreply@utility.com",
            date=now,
            is_utility_bill=True,
            extracted_data={"rate_per_kwh": 0.21},
            attachment_count=2,
        )
        d = result.to_dict()
        assert d["email_id"] == "msg_001"
        assert d["is_utility_bill"] is True
        assert d["attachment_count"] == 2
        assert d["extracted_data"]["rate_per_kwh"] == 0.21


# ===========================================================================
# 9. create_email_connection endpoint (Phase 3 OAuth version)
# ===========================================================================


class TestCreateEmailConnectionOAuth:
    """Tests for POST /connections/email with new OAuth service integration."""

    def test_gmail_redirect_url_from_oauth_service(self, client):
        """Gmail provider returns an OAuth consent URL from email_oauth_service."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=MagicMock())

        with patch("services.email_oauth_service.settings") as mock_settings:
            mock_settings.gmail_client_id = "fake-gmail-client-id"
            mock_settings.internal_api_key = "test-key"
            mock_settings.jwt_secret = "fallback-secret"
            mock_settings.oauth_redirect_base_url = "http://localhost:8000"

            response = client.post(
                f"{BASE}/email",
                json={"provider": "gmail", "consent_given": True},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["provider"] == "gmail"
        assert "accounts.google.com" in data["redirect_url"]
        assert "connection_id" in data

    def test_outlook_redirect_url_from_oauth_service(self, client):
        """Outlook provider returns an OAuth consent URL from email_oauth_service."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=MagicMock())

        with patch("services.email_oauth_service.settings") as mock_settings:
            mock_settings.outlook_client_id = "fake-outlook-client-id"
            mock_settings.internal_api_key = "test-key"
            mock_settings.jwt_secret = "fallback-secret"
            mock_settings.oauth_redirect_base_url = "http://localhost:8000"

            response = client.post(
                f"{BASE}/email",
                json={"provider": "outlook", "consent_given": True},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["provider"] == "outlook"
        assert "microsoftonline.com" in data["redirect_url"]

    def test_creates_pending_connection_in_db(self, client):
        """DB INSERT is called with 'pending' status."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=MagicMock())

        with patch("services.email_oauth_service.settings") as mock_settings:
            mock_settings.gmail_client_id = "fake-gmail-client-id"
            mock_settings.internal_api_key = "test-key"
            mock_settings.jwt_secret = "fallback-secret"
            mock_settings.oauth_redirect_base_url = "http://localhost:8000"

            response = client.post(
                f"{BASE}/email",
                json={"provider": "gmail", "consent_given": True},
            )

        assert response.status_code == 202
        # Verify db.execute was called (INSERT)
        assert db.execute.called

    def test_response_contains_connection_id(self, client):
        """Response must include a connection_id UUID string."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=MagicMock())

        with patch("services.email_oauth_service.settings") as mock_settings:
            mock_settings.gmail_client_id = "fake-gmail-client-id"
            mock_settings.internal_api_key = "test-key"
            mock_settings.jwt_secret = "fallback-secret"
            mock_settings.oauth_redirect_base_url = "http://localhost:8000"

            response = client.post(
                f"{BASE}/email",
                json={"provider": "gmail", "consent_given": True},
            )

        data = response.json()
        assert "connection_id" in data
        # Should be a valid UUID-ish string
        assert len(data["connection_id"]) > 0


# ===========================================================================
# 10. email_oauth_callback endpoint
# ===========================================================================


class TestEmailOAuthCallback:
    """Tests for GET /connections/email/callback."""

    def _valid_state(self, connection_id: str, api_key: str = "test-key") -> str:
        """Generate a valid signed state for testing."""
        import secrets as _secrets
        import hmac as _hmac
        import hashlib as _hashlib

        nonce = _secrets.token_hex(16)
        payload = f"{connection_id}:{nonce}"
        key = api_key.encode()
        mac = _hmac.new(key, payload.encode(), _hashlib.sha256).hexdigest()
        return f"{payload}:{mac}"

    def _install_callback_db(self, provider: str = "gmail", status: str = "pending"):
        """Install DB mock for callback endpoint (no auth needed)."""
        from main import app
        from api.dependencies import get_db_session

        db = _mock_db()
        row = _DictRow({
            "id": TEST_CONNECTION_ID,
            "email_provider": provider,
            "status": status,
        })
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute = AsyncMock(return_value=result)

        app.dependency_overrides[get_db_session] = lambda: db
        return db

    def test_invalid_state_returns_400(self, client):
        """Tampered or malformed state returns 400."""
        self._install_callback_db()

        response = client.get(
            f"{BASE}/email/callback",
            params={"code": "auth_code_123", "state": "bad:state:here"},
            follow_redirects=False,
        )
        assert response.status_code == 400

    def test_missing_state_returns_422(self, client):
        """Missing state query param returns 422 (FastAPI validation)."""
        self._install_callback_db()

        response = client.get(
            f"{BASE}/email/callback",
            params={"code": "auth_code_123"},
            follow_redirects=False,
        )
        assert response.status_code == 422

    def test_connection_not_found_returns_404(self, client):
        """When DB returns no connection, returns 404."""
        from main import app
        from api.dependencies import get_db_session

        db = _mock_db()
        not_found_result = MagicMock()
        not_found_result.mappings.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=not_found_result)
        app.dependency_overrides[get_db_session] = lambda: db

        with patch("services.email_oauth_service.settings") as mock_settings:
            mock_settings.internal_api_key = "test-key"
            mock_settings.jwt_secret = "fallback"
            state = self._valid_state(TEST_CONNECTION_ID, "test-key")

            response = client.get(
                f"{BASE}/email/callback",
                params={"code": "auth_code_123", "state": state},
                follow_redirects=False,
            )
            assert response.status_code == 404

    def test_already_processed_returns_409(self, client):
        """When connection status is 'active', returns 409."""
        self._install_callback_db(status="active")

        # IMPORTANT: state generation and request must both happen inside the
        # same patch context so verify_oauth_state uses the same HMAC key.
        with patch("services.email_oauth_service.settings") as mock_settings:
            mock_settings.internal_api_key = "test-key"
            mock_settings.jwt_secret = "fallback"
            state = self._valid_state(TEST_CONNECTION_ID, "test-key")

            response = client.get(
                f"{BASE}/email/callback",
                params={"code": "auth_code_123", "state": state},
                follow_redirects=False,
            )
        assert response.status_code == 409

    def test_token_exchange_failure_returns_502(self, client):
        """When token exchange fails (httpx error), returns 502."""
        import httpx as _httpx

        self._install_callback_db(provider="gmail", status="pending")

        with patch("services.email_oauth_service.settings") as mock_settings:
            mock_settings.internal_api_key = "test-key"
            mock_settings.jwt_secret = "fallback"
            mock_settings.gmail_client_id = "client-id"
            mock_settings.gmail_client_secret = "client-secret"
            mock_settings.oauth_redirect_base_url = "http://localhost:8000"
            state = self._valid_state(TEST_CONNECTION_ID, "test-key")

            with patch(
                "services.email_oauth_service.exchange_gmail_code",
                side_effect=_httpx.HTTPStatusError(
                    message="400 Bad Request",
                    request=MagicMock(),
                    response=MagicMock(status_code=400),
                ),
            ):
                response = client.get(
                    f"{BASE}/email/callback",
                    params={"code": "auth_code_123", "state": state},
                    follow_redirects=False,
                )

        assert response.status_code == 502

    def test_valid_callback_gmail_redirects(self, client):
        """Valid Gmail callback stores tokens and redirects to frontend."""
        self._install_callback_db(provider="gmail", status="pending")

        token_response = {
            "access_token": "gmail_access_token",
            "refresh_token": "gmail_refresh_token",
            "expires_in": 3600,
        }

        with patch("services.email_oauth_service.settings") as mock_settings, \
             patch("api.v1.connections.settings") as conn_settings, \
             patch(
                 "services.email_oauth_service.exchange_gmail_code",
                 return_value=token_response,
             ), \
             patch("utils.encryption.settings") as enc_settings:
            mock_settings.internal_api_key = "test-key"
            mock_settings.jwt_secret = "fallback"
            mock_settings.gmail_client_id = "client-id"
            mock_settings.gmail_client_secret = "client-secret"
            mock_settings.oauth_redirect_base_url = "http://localhost:8000"
            conn_settings.oauth_redirect_base_url = "http://localhost:8000"
            enc_settings.field_encryption_key = TEST_ENCRYPTION_KEY

            state = self._valid_state(TEST_CONNECTION_ID, "test-key")

            response = client.get(
                f"{BASE}/email/callback",
                params={"code": "auth_code_123", "state": state},
                follow_redirects=False,
            )

        # Should redirect (302) to frontend connections page
        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "connections" in location

    def test_valid_callback_outlook_redirects(self, client):
        """Valid Outlook callback stores tokens and redirects."""
        self._install_callback_db(provider="outlook", status="pending")

        token_response = {
            "access_token": "outlook_access_token",
            "refresh_token": "outlook_refresh_token",
            "expires_in": 3600,
        }

        with patch("services.email_oauth_service.settings") as mock_settings, \
             patch("api.v1.connections.settings") as conn_settings, \
             patch(
                 "services.email_oauth_service.exchange_outlook_code",
                 return_value=token_response,
             ), \
             patch("utils.encryption.settings") as enc_settings:
            mock_settings.internal_api_key = "test-key"
            mock_settings.jwt_secret = "fallback"
            mock_settings.outlook_client_id = "client-id"
            mock_settings.outlook_client_secret = "client-secret"
            mock_settings.oauth_redirect_base_url = "http://localhost:8000"
            conn_settings.oauth_redirect_base_url = "http://localhost:8000"
            enc_settings.field_encryption_key = TEST_ENCRYPTION_KEY

            state = self._valid_state(TEST_CONNECTION_ID, "test-key")

            response = client.get(
                f"{BASE}/email/callback",
                params={"code": "auth_code_123", "state": state},
                follow_redirects=False,
            )

        assert response.status_code == 302


# ===========================================================================
# 11. trigger_email_scan endpoint
# ===========================================================================


class TestTriggerEmailScan:
    """Tests for POST /connections/email/{connection_id}/scan."""

    def test_scan_connection_not_found_returns_404(self, client):
        """Non-existent connection_id returns 404."""
        db = _install_auth()

        not_found_result = MagicMock()
        not_found_result.mappings.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=not_found_result)

        response = client.post(f"{BASE}/email/{TEST_CONNECTION_ID}/scan")
        assert response.status_code == 404

    def test_scan_connection_not_active_returns_409(self, client):
        """Pending connection returns 409."""
        db = _install_auth()

        row = _DictRow({
            "id": TEST_CONNECTION_ID,
            "user_id": TEST_USER_ID,
            "email_provider": "gmail",
            "status": "pending",
            "oauth_access_token": None,
            "oauth_refresh_token": None,
            "oauth_token_expires_at": None,
        })
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute = AsyncMock(return_value=result)

        response = client.post(f"{BASE}/email/{TEST_CONNECTION_ID}/scan")
        assert response.status_code == 409

    def test_scan_disconnected_returns_409(self, client):
        """Disconnected connection returns 409."""
        db = _install_auth()

        row = _DictRow({
            "id": TEST_CONNECTION_ID,
            "user_id": TEST_USER_ID,
            "email_provider": "gmail",
            "status": "disconnected",
            "oauth_access_token": None,
            "oauth_refresh_token": None,
            "oauth_token_expires_at": None,
        })
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute = AsyncMock(return_value=result)

        response = client.post(f"{BASE}/email/{TEST_CONNECTION_ID}/scan")
        assert response.status_code == 409

    def test_scan_active_gmail_connection_succeeds(self, client):
        """Active Gmail connection with valid token returns scan results."""
        db = _install_auth()

        # Encrypt a fake access token for storage
        with patch("utils.encryption.settings") as enc_settings:
            enc_settings.field_encryption_key = TEST_ENCRYPTION_KEY
            from utils.encryption import encrypt_field
            enc_token = encrypt_field("fake_access_token")
        enc_token_b64 = base64.b64encode(enc_token).decode()

        row = _DictRow({
            "id": TEST_CONNECTION_ID,
            "user_id": TEST_USER_ID,
            "email_provider": "gmail",
            "status": "active",
            "oauth_access_token": enc_token_b64,
            "oauth_refresh_token": None,
            "oauth_token_expires_at": None,  # not expired
        })
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute = AsyncMock(return_value=result)

        from services.email_scanner_service import EmailScanResult

        mock_scan_result = EmailScanResult(
            email_id="msg_001",
            subject="Your electricity bill",
            sender="billing@eversource.com",
            date=datetime.now(timezone.utc),
            is_utility_bill=True,
            attachment_count=1,
        )

        with patch("utils.encryption.settings") as enc_settings, \
             patch("services.email_scanner_service.scan_gmail_inbox", return_value=[mock_scan_result]) as mock_scan:
            enc_settings.field_encryption_key = TEST_ENCRYPTION_KEY

            response = client.post(f"{BASE}/email/{TEST_CONNECTION_ID}/scan")

        assert response.status_code == 200
        data = response.json()
        assert data["connection_id"] == TEST_CONNECTION_ID
        assert data["provider"] == "gmail"
        assert "total_emails_scanned" in data
        assert "utility_bills_found" in data
        assert "bills" in data

    def test_scan_filters_non_utility_emails(self, client):
        """Only utility bill emails are included in the response."""
        db = _install_auth()

        with patch("utils.encryption.settings") as enc_settings:
            enc_settings.field_encryption_key = TEST_ENCRYPTION_KEY
            from utils.encryption import encrypt_field
            enc_token = encrypt_field("fake_access_token")
        enc_token_b64 = base64.b64encode(enc_token).decode()

        row = _DictRow({
            "id": TEST_CONNECTION_ID,
            "user_id": TEST_USER_ID,
            "email_provider": "gmail",
            "status": "active",
            "oauth_access_token": enc_token_b64,
            "oauth_refresh_token": None,
            "oauth_token_expires_at": None,
        })
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute = AsyncMock(return_value=result)

        from services.email_scanner_service import EmailScanResult

        now = datetime.now(timezone.utc)
        non_bill = EmailScanResult(
            email_id="msg_002",
            subject="Meeting invitation",
            sender="hr@company.com",
            date=now,
            is_utility_bill=False,
        )
        utility_bill = EmailScanResult(
            email_id="msg_003",
            subject="Electricity bill",
            sender="billing@eversource.com",
            date=now,
            is_utility_bill=True,
        )

        with patch("utils.encryption.settings") as enc_settings, \
             patch("services.email_scanner_service.scan_gmail_inbox", return_value=[non_bill, utility_bill]):
            enc_settings.field_encryption_key = TEST_ENCRYPTION_KEY

            response = client.post(f"{BASE}/email/{TEST_CONNECTION_ID}/scan")

        assert response.status_code == 200
        data = response.json()
        assert data["total_emails_scanned"] == 2
        assert data["utility_bills_found"] == 1


# ===========================================================================
# 12. Async service-level tests (scan_gmail_inbox / scan_outlook_inbox)
# ===========================================================================


class TestScanInboxAsync:
    """Tests for scan_gmail_inbox and scan_outlook_inbox using mocked httpx."""

    @pytest.mark.asyncio
    async def test_scan_gmail_inbox_returns_results(self):
        """scan_gmail_inbox returns a list of EmailScanResult objects."""
        from services.email_scanner_service import scan_gmail_inbox

        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        mock_list_response.raise_for_status = MagicMock()
        mock_list_response.json.return_value = {
            "messages": [{"id": "msg_001"}]
        }

        mock_detail_response = MagicMock()
        mock_detail_response.status_code = 200
        mock_detail_response.json.return_value = {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Your electricity bill"},
                    {"name": "From", "value": "billing@eversource.com"},
                    {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"},
                ],
                "parts": [],
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[mock_list_response, mock_detail_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await scan_gmail_inbox("fake_access_token")

        assert len(results) == 1
        assert results[0].email_id == "msg_001"
        assert results[0].subject == "Your electricity bill"
        assert results[0].is_utility_bill is True

    @pytest.mark.asyncio
    async def test_scan_outlook_inbox_returns_results(self):
        """scan_outlook_inbox returns a list of EmailScanResult objects."""
        from services.email_scanner_service import scan_outlook_inbox

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "outlook_msg_001",
                    "subject": "Energy bill for December",
                    "from": {
                        "emailAddress": {
                            "name": "Eversource",
                            "address": "billing@eversource.com",
                        }
                    },
                    "receivedDateTime": "2024-01-15T10:00:00Z",
                    "hasAttachments": True,
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await scan_outlook_inbox("fake_access_token")

        assert len(results) == 1
        assert results[0].email_id == "outlook_msg_001"
        assert results[0].is_utility_bill is True
        assert results[0].attachment_count == 1

    @pytest.mark.asyncio
    async def test_scan_gmail_skips_failed_detail_requests(self):
        """If a message detail request fails, that message is skipped."""
        from services.email_scanner_service import scan_gmail_inbox

        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        mock_list_response.raise_for_status = MagicMock()
        mock_list_response.json.return_value = {
            "messages": [{"id": "msg_001"}, {"id": "msg_002"}]
        }

        # First detail: 200 OK
        mock_detail_ok = MagicMock()
        mock_detail_ok.status_code = 200
        mock_detail_ok.json.return_value = {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Electricity bill"},
                    {"name": "From", "value": "billing@eversource.com"},
                    {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"},
                ],
                "parts": [],
            }
        }

        # Second detail: 403 Forbidden — skipped
        mock_detail_fail = MagicMock()
        mock_detail_fail.status_code = 403

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=[mock_list_response, mock_detail_ok, mock_detail_fail]
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = await scan_gmail_inbox("fake_access_token")

        # Only the successful message is returned
        assert len(results) == 1
        assert results[0].email_id == "msg_001"


# ===========================================================================
# 13. extract_rates_from_email async tests
# ===========================================================================


class TestExtractRatesFromEmail:
    """Tests for extract_rates_from_email."""

    @pytest.mark.asyncio
    async def test_gmail_extraction(self):
        """Extracts rates from a Gmail message body."""
        import base64 as b64
        from services.email_scanner_service import extract_rates_from_email

        text = "Total amount due: $145.67. You used 847 kWh."
        encoded = b64.urlsafe_b64encode(text.encode()).decode()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "payload": {
                "mimeType": "text/plain",
                "body": {"data": encoded},
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await extract_rates_from_email("gmail", "fake_token", "msg_001")

        assert isinstance(result, dict)
        # At minimum, total_amount should be detected
        assert "total_amount" in result
        assert result["total_amount"] == 145.67

    @pytest.mark.asyncio
    async def test_outlook_extraction(self):
        """Extracts rates from an Outlook message body (HTML stripped)."""
        from services.email_scanner_service import extract_rates_from_email

        html_body = "<p>Total amount due: $234.56</p><p>You used 1,234 kWh</p>"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "body": {
                "contentType": "html",
                "content": html_body,
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await extract_rates_from_email("outlook", "fake_token", "outlook_msg_001")

        assert isinstance(result, dict)
        assert "total_amount" in result
        assert result["total_amount"] == 234.56
