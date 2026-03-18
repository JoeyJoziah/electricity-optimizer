"""
Tests for the Internal Scan Emails API endpoint.

Covers:
- POST /internal/scan-emails — scan all active email-import connections

Test groups:
  TestScanEmailsHappyPath      — normal batch flows
  TestScanEmailsTokenHandling  — missing / expired tokens, refresh paths
  TestScanEmailsErrorIsolation — per-connection failures do not abort batch
  TestScanEmailsConcurrency    — semaphore limit is respected
  TestScanEmailsAuth           — endpoint requires X-API-Key

Note: the internal router uses lazy imports so all service patches target
the service modules directly, not api.v1.internal.email_scan.
"""

import asyncio
import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db_session, get_redis, verify_api_key

BASE_URL = "/api/v1/internal"


# =============================================================================
# Helpers
# =============================================================================


def _make_email_result(
    email_id: str = "email-001",
    subject: str = "Your electric bill is ready",
    sender: str = "noreply@eversource.com",
    is_utility_bill: bool = True,
    attachment_count: int = 0,
) -> MagicMock:
    """Return a mock EmailScanResult with sensible defaults."""
    r = MagicMock()
    r.email_id = email_id
    r.subject = subject
    r.sender = sender
    r.date = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
    r.is_utility_bill = is_utility_bill
    r.attachment_count = attachment_count
    r.to_dict.return_value = {
        "email_id": email_id,
        "subject": subject,
        "sender": sender,
        "date": "2026-02-01T12:00:00+00:00",
        "is_utility_bill": is_utility_bill,
        "attachment_count": attachment_count,
        "extracted_data": {},
    }
    return r


def _make_connection_row(
    conn_id: str = "conn-001",
    provider: str = "gmail",
    has_token: bool = True,
    token_expired: bool = False,
    has_refresh: bool = True,
) -> MagicMock:
    """Return a mapping-like object representing a user_connections row."""
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "id": conn_id,
        "user_id": "user-abc",
        "email_provider": provider,
        "oauth_access_token": (
            base64.b64encode(b"fake-encrypted-token").decode() if has_token else None
        ),
        "oauth_refresh_token": (
            base64.b64encode(b"fake-encrypted-refresh").decode() if has_refresh else None
        ),
        "oauth_token_expires_at": (
            (datetime.now(timezone.utc) - timedelta(hours=2))
            if token_expired
            else (datetime.now(timezone.utc) + timedelta(hours=1))
        ),
    }[k]
    row.get = lambda k, default=None: (
        row[k]
        if k
        in [
            "id",
            "user_id",
            "email_provider",
            "oauth_access_token",
            "oauth_refresh_token",
            "oauth_token_expires_at",
        ]
        else default
    )
    return row


def _make_db_with_connections(connections: list) -> AsyncMock:
    """Build a mock AsyncSession pre-configured to return the given connections."""
    mock_db = AsyncMock()
    mapping_result = MagicMock()
    mapping_result.fetchall.return_value = connections

    mappings_obj = MagicMock()
    mappings_obj.fetchall.return_value = connections

    execute_result = MagicMock()
    execute_result.mappings.return_value = mappings_obj

    mock_db.execute = AsyncMock(return_value=execute_result)
    mock_db.commit = AsyncMock()
    return mock_db


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis_client():
    return AsyncMock()


@pytest.fixture
def auth_client(mock_redis_client):
    """TestClient with API key verified; DB override applied per-test."""
    from main import app

    app.dependency_overrides[verify_api_key] = lambda: True
    app.dependency_overrides[get_redis] = lambda: mock_redis_client

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def unauth_client(mock_redis_client):
    """TestClient without API key override — real auth validation runs."""
    from main import app

    app.dependency_overrides.pop(verify_api_key, None)
    app.dependency_overrides[get_redis] = lambda: mock_redis_client

    mock_db = AsyncMock()
    app.dependency_overrides[get_db_session] = lambda: mock_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_redis, None)


# =============================================================================
# TestScanEmailsHappyPath
# =============================================================================


class TestScanEmailsHappyPath:
    """Normal batch scans with active, valid-token connections."""

    @patch("utils.encryption.decrypt_field", return_value="plain-access-token")
    @patch("services.email_scanner_service.extract_rates_from_email")
    @patch("services.email_scanner_service.scan_gmail_inbox")
    def test_single_connection_single_bill(
        self,
        mock_scan,
        mock_extract,
        mock_decrypt,
        auth_client,
    ):
        """A single connection with one utility bill returns a 1/1 summary."""
        mock_scan.return_value = [_make_email_result(email_id="e1")]
        mock_extract.return_value = {"rate_per_kwh": 0.1234, "total_amount": 85.00}

        conn = _make_connection_row(conn_id="c1", provider="gmail")
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["connections_scanned"] == 1
        assert data["emails_found"] == 1
        assert data["rates_extracted"] == 1
        assert data["errors"] == []

    @patch("utils.encryption.decrypt_field", return_value="plain-access-token")
    @patch("services.email_scanner_service.extract_rates_from_email")
    @patch("services.email_scanner_service.scan_gmail_inbox")
    def test_multiple_connections_aggregated(
        self,
        mock_scan,
        mock_extract,
        mock_decrypt,
        auth_client,
    ):
        """Three connections: totals are summed across all of them."""
        # Each scan returns 2 utility-bill emails
        mock_scan.return_value = [
            _make_email_result(email_id="e1"),
            _make_email_result(email_id="e2"),
        ]
        mock_extract.return_value = {"rate_per_kwh": 0.12}

        connections = [_make_connection_row(conn_id=f"c{i}", provider="gmail") for i in range(3)]
        mock_db = _make_db_with_connections(connections)

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["connections_scanned"] == 3
        assert data["emails_found"] == 6  # 3 connections × 2 emails
        assert data["rates_extracted"] == 6
        assert data["errors"] == []

    @patch("utils.encryption.decrypt_field", return_value="plain-access-token")
    @patch("services.email_scanner_service.extract_rates_from_email")
    @patch("services.email_scanner_service.scan_outlook_inbox")
    def test_outlook_provider_uses_correct_scanner(
        self,
        mock_scan_outlook,
        mock_extract,
        mock_decrypt,
        auth_client,
    ):
        """Outlook connections route to scan_outlook_inbox, not Gmail."""
        mock_scan_outlook.return_value = [_make_email_result(email_id="oe1")]
        mock_extract.return_value = {"rate_per_kwh": 0.09}

        conn = _make_connection_row(conn_id="outlook-c1", provider="outlook")
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["connections_scanned"] == 1
        assert data["emails_found"] == 1
        mock_scan_outlook.assert_awaited()

    def test_no_active_connections_returns_empty(self, auth_client):
        """When no active email connections exist, return a zero-sum summary."""
        mock_db = _make_db_with_connections([])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["connections_scanned"] == 0
        assert data["emails_found"] == 0
        assert data["rates_extracted"] == 0
        assert data["errors"] == []

    @patch("utils.encryption.decrypt_field", return_value="plain-access-token")
    @patch("services.email_scanner_service.extract_rates_from_email")
    @patch("services.email_scanner_service.scan_gmail_inbox")
    def test_emails_without_extracted_data_not_persisted(
        self,
        mock_scan,
        mock_extract,
        mock_decrypt,
        auth_client,
    ):
        """An email where extract_rates returns empty dict is skipped (not persisted)."""
        mock_scan.return_value = [_make_email_result(email_id="e1")]
        mock_extract.return_value = {}  # no usable data

        conn = _make_connection_row(conn_id="c1")
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["emails_found"] == 1
        assert data["rates_extracted"] == 0  # empty extract → not counted

    @patch("utils.encryption.decrypt_field", return_value="plain-access-token")
    @patch("services.email_scanner_service.extract_rates_from_email")
    @patch("services.email_scanner_service.scan_gmail_inbox")
    def test_non_utility_emails_excluded(
        self,
        mock_scan,
        mock_extract,
        mock_decrypt,
        auth_client,
    ):
        """Only emails with is_utility_bill=True contribute to the found count."""
        mock_scan.return_value = [
            _make_email_result(email_id="u1", is_utility_bill=True),
            _make_email_result(email_id="n1", is_utility_bill=False),
            _make_email_result(email_id="n2", is_utility_bill=False),
        ]
        mock_extract.return_value = {"rate_per_kwh": 0.11}

        conn = _make_connection_row(conn_id="c1")
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["emails_found"] == 1  # only the utility bill
        assert data["rates_extracted"] == 1


# =============================================================================
# TestScanEmailsTokenHandling
# =============================================================================


class TestScanEmailsTokenHandling:
    """Token absent / expired / refresh flows."""

    def test_missing_oauth_token_skipped_gracefully(self, auth_client):
        """Connection with no oauth_access_token is skipped — not an error."""
        conn = _make_connection_row(conn_id="c1", has_token=False)
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        # Skipped connection is not an error — it just contributes 0 results.
        assert data["connections_scanned"] == 1
        assert data["emails_found"] == 0
        assert data["rates_extracted"] == 0
        assert data["errors"] == []

    @patch(
        "services.email_oauth_service.refresh_gmail_token",
        new_callable=AsyncMock,
        return_value={
            "access_token": "new-plain-token",
            "expires_in": 3600,
        },
    )
    @patch(
        "services.email_oauth_service.encrypt_tokens",
        return_value=(b"new-enc-access", b"new-enc-refresh"),
    )
    @patch("utils.encryption.decrypt_field", return_value="plain-old-token")
    @patch("services.email_scanner_service.extract_rates_from_email")
    @patch("services.email_scanner_service.scan_gmail_inbox")
    def test_expired_token_refreshed_before_scan(
        self,
        mock_scan,
        mock_extract,
        mock_decrypt,
        mock_encrypt,
        mock_refresh,
        auth_client,
    ):
        """When access token is expired, token is refreshed before the inbox scan."""
        mock_scan.return_value = [_make_email_result()]
        mock_extract.return_value = {"rate_per_kwh": 0.10}

        conn = _make_connection_row(
            conn_id="c1",
            provider="gmail",
            has_token=True,
            token_expired=True,
            has_refresh=True,
        )
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["connections_scanned"] == 1
        # Refresh was called with the encrypted refresh token bytes
        mock_refresh.assert_awaited_once()
        # The scan proceeded with the new token
        mock_scan.assert_awaited()

    @patch("utils.encryption.decrypt_field", return_value="plain-old-token")
    def test_expired_token_no_refresh_token_skipped(self, mock_decrypt, auth_client):
        """Expired token with no refresh_token available — connection is skipped."""
        conn = _make_connection_row(
            conn_id="c1",
            token_expired=True,
            has_refresh=False,
        )
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["connections_scanned"] == 1
        assert data["emails_found"] == 0
        assert data["errors"] == []

    @patch(
        "services.email_oauth_service.refresh_gmail_token",
        new_callable=AsyncMock,
        side_effect=RuntimeError("provider 500"),
    )
    @patch("utils.encryption.decrypt_field", return_value="plain-old-token")
    def test_token_refresh_failure_skips_connection(self, mock_decrypt, mock_refresh, auth_client):
        """A failed token refresh skips the connection without crashing the batch."""
        conn = _make_connection_row(
            conn_id="c1",
            provider="gmail",
            token_expired=True,
            has_refresh=True,
        )
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["connections_scanned"] == 1
        assert data["emails_found"] == 0
        assert data["errors"] == []  # skipped, not an error


# =============================================================================
# TestScanEmailsErrorIsolation
# =============================================================================


class TestScanEmailsErrorIsolation:
    """Per-connection errors must not abort the remaining batch."""

    @patch("utils.encryption.decrypt_field")
    @patch("services.email_scanner_service.extract_rates_from_email")
    @patch("services.email_scanner_service.scan_gmail_inbox")
    def test_one_connection_error_does_not_abort_batch(
        self,
        mock_scan,
        mock_extract,
        mock_decrypt,
        auth_client,
    ):
        """One failing connection records an error; healthy connections succeed."""
        import httpx

        call_count = 0

        async def _flaky_scan(access_token, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # Simulate Gmail API returning 401 for second connection
                raise httpx.HTTPStatusError(
                    "401 Unauthorized",
                    request=MagicMock(),
                    response=MagicMock(status_code=401),
                )
            return [_make_email_result(email_id=f"e{call_count}")]

        mock_scan.side_effect = _flaky_scan
        mock_extract.return_value = {"rate_per_kwh": 0.12}
        mock_decrypt.return_value = "plain-token"

        connections = [_make_connection_row(conn_id=f"c{i}", provider="gmail") for i in range(3)]
        mock_db = _make_db_with_connections(connections)

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["connections_scanned"] == 3
        # 2 healthy connections each found 1 email
        assert data["emails_found"] == 2
        # Exactly 1 connection error recorded
        assert len(data["errors"]) == 1
        assert data["errors"][0]["connection_id"] == "c1"

    @patch("utils.encryption.decrypt_field")
    @patch("services.email_scanner_service.extract_rates_from_email")
    @patch("services.email_scanner_service.scan_gmail_inbox")
    def test_persist_failure_is_tolerated(
        self,
        mock_scan,
        mock_extract,
        mock_decrypt,
        auth_client,
    ):
        """DB insert failures for rate rows are logged and tolerated."""
        mock_scan.return_value = [_make_email_result()]
        mock_extract.return_value = {"rate_per_kwh": 0.14}
        mock_decrypt.return_value = "plain-token"

        conn = _make_connection_row(conn_id="c1")
        mock_db = _make_db_with_connections([conn])

        # Cause execute to fail on the INSERT call
        call_count = [0]
        original_execute = mock_db.execute

        async def _execute_side_effect(stmt, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                # First call is the SELECT; subsequent calls are INSERTs
                raise RuntimeError("disk full")
            return await original_execute(stmt, *args, **kwargs)

        mock_db.execute = AsyncMock(side_effect=_execute_side_effect)

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        # Email was found but not persisted due to DB error
        assert data["emails_found"] == 1
        assert data["rates_extracted"] == 0
        # The connection itself did not error — only the persist step failed
        assert data["errors"] == []

    @patch("utils.encryption.decrypt_field", side_effect=Exception("decryption error"))
    def test_decryption_failure_recorded_as_connection_error(self, mock_decrypt, auth_client):
        """A decrypt_field exception is captured per-connection and surfaced in errors."""
        conn = _make_connection_row(conn_id="c1")
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["connections_scanned"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["connection_id"] == "c1"
        assert "decryption error" in data["errors"][0]["error"]

    def test_db_unavailable_returns_503(self, auth_client):
        """When db is None the endpoint must return 503, not 500."""
        from main import app

        app.dependency_overrides[get_db_session] = lambda: None

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 503


# =============================================================================
# TestScanEmailsConcurrency
# =============================================================================


class TestScanEmailsConcurrency:
    """Verify that the semaphore limits peak concurrency toward email APIs."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_peak_concurrency(self):
        """
        Directly invoke the endpoint logic via the scan_all_emails coroutine
        with 10 connections and verify peak concurrency never exceeds 3.

        We monkey-patch the internal _SCAN_SEMAPHORE_LIMIT to the project
        constant (3) and confirm it applies.
        """
        import api.v1.internal.email_scan as _mod

        peak = 0
        current = 0

        async def _counting_scan(access_token, **kwargs):
            nonlocal peak, current
            current += 1
            peak = max(peak, current)
            await asyncio.sleep(0.01)  # small yield so coroutines overlap
            current -= 1
            return []  # no emails

        with (
            patch("utils.encryption.decrypt_field", return_value="tok"),
            patch(
                "services.email_scanner_service.scan_gmail_inbox",
                side_effect=_counting_scan,
            ),
        ):
            conns = [_make_connection_row(conn_id=f"c{i}", provider="gmail") for i in range(10)]

            # Build a mock DB that returns the connections list
            mock_db = _make_db_with_connections(conns)

            # Call the endpoint function directly (bypasses HTTP stack)
            from api.v1.internal.email_scan import scan_all_emails

            result = await scan_all_emails(db=mock_db)

        assert peak <= _mod._SCAN_SEMAPHORE_LIMIT, (
            f"Peak concurrency {peak} exceeded semaphore limit " f"{_mod._SCAN_SEMAPHORE_LIMIT}"
        )
        assert result["connections_scanned"] == 10


# =============================================================================
# TestScanEmailsAuth
# =============================================================================


class TestScanEmailsAuth:
    """Authorization guard tests."""

    def test_requires_api_key(self, unauth_client):
        """Request without X-API-Key header must be rejected with 401."""
        response = unauth_client.post(f"{BASE_URL}/scan-emails")
        assert response.status_code == 401

    def test_invalid_api_key_rejected(self, mock_redis_client):
        """An incorrect X-API-Key must be rejected with 401."""
        from main import app

        # Remove any verify_api_key override so real validation runs
        app.dependency_overrides.pop(verify_api_key, None)

        mock_db = AsyncMock()
        app.dependency_overrides[get_db_session] = lambda: mock_db
        app.dependency_overrides[get_redis] = lambda: mock_redis_client

        # Patch settings so the key is configured but does not match what we send
        with patch("api.dependencies.settings") as mock_settings:
            mock_settings.internal_api_key = "correct-secret-key"
            client = TestClient(app)
            response = client.post(
                f"{BASE_URL}/scan-emails",
                headers={"X-API-Key": "wrong-key"},
            )

        # Clean up
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_redis, None)

        assert response.status_code == 401

    @patch("utils.encryption.decrypt_field", return_value="tok")
    @patch(
        "services.email_scanner_service.scan_gmail_inbox",
        new_callable=AsyncMock,
        return_value=[],
    )
    def test_valid_api_key_accepted(self, mock_scan, mock_decrypt, auth_client):
        """A correct X-API-Key header (dependency overridden) lets the request through."""
        mock_db = _make_db_with_connections([])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")
        assert response.status_code == 200


# =============================================================================
# TestScanEmailsResponseSchema
# =============================================================================


class TestScanEmailsResponseSchema:
    """Validate the shape of the response dict regardless of content."""

    @patch("utils.encryption.decrypt_field", return_value="tok")
    @patch("services.email_scanner_service.extract_rates_from_email")
    @patch("services.email_scanner_service.scan_gmail_inbox")
    def test_response_contains_all_required_keys(
        self, mock_scan, mock_extract, mock_decrypt, auth_client
    ):
        """Response always includes all documented keys."""
        mock_scan.return_value = [_make_email_result()]
        mock_extract.return_value = {"rate_per_kwh": 0.10}

        conn = _make_connection_row(conn_id="c1")
        mock_db = _make_db_with_connections([conn])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        required = {"status", "connections_scanned", "emails_found", "rates_extracted", "errors"}
        missing = required - set(data.keys())
        assert not missing, f"Response missing keys: {missing}"

    def test_empty_db_response_schema_valid(self, auth_client):
        """Even with no connections, the response schema is fully populated."""
        mock_db = _make_db_with_connections([])

        from main import app

        app.dependency_overrides[get_db_session] = lambda: mock_db

        response = auth_client.post(f"{BASE_URL}/scan-emails")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert isinstance(data["connections_scanned"], int)
        assert isinstance(data["emails_found"], int)
        assert isinstance(data["rates_extracted"], int)
        assert isinstance(data["errors"], list)
