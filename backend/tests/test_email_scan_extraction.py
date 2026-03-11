"""
Tests for Phase 1 Utility Account Integration: Email Scan Rate Extraction

Coverage:
  - Email body text extraction produces rates from scan endpoint
  - Gmail attachment download and parsing
  - Outlook attachment download and parsing
  - Extracted rates are persisted to connection_extracted_rates
  - Scan response includes extraction summary (rates_extracted, attachments_parsed)
  - Multiple bills with different rates are all extracted
  - Bills with no extractable data don't crash (graceful fallback)
  - EmailScanResponse model validation
  - download_gmail_attachments filters non-PDF/image types
  - download_gmail_attachments caps at 5 attachments
  - download_outlook_attachments filters non-PDF/image types
  - download_outlook_attachments caps at 5 attachments
  - extract_rates_from_attachments uses bill_parser extractors
  - extract_rates_from_attachments ignores empty/corrupt data
  - Attachment download failure does not abort the scan
  - Body extraction failure does not abort the scan
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stable test identifiers
# ---------------------------------------------------------------------------

TEST_USER_ID = "dddddddd-1111-0000-0000-000000000088"
TEST_CONNECTION_ID = str(uuid4())
BASE = "/api/v1/connections"

# Minimal fake AES-256-GCM-compatible 64-hex-char key
TEST_ENCRYPTION_KEY = "b" * 64


# ---------------------------------------------------------------------------
# Shared helpers
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

    return SessionData(
        user_id=user_id,
        email=f"{user_id[:8]}@example.com",
        name="Test User",
        email_verified=True,
        role="user",
    )


def _active_connection_row(
    connection_id: str = TEST_CONNECTION_ID,
    provider: str = "gmail",
    attachment_count: int = 0,
) -> _DictRow:
    """Return a fake active connection DB row with encrypted token placeholder."""
    # Use a real encrypted token so decrypt_field won't be called with garbage.
    # We'll patch decrypt_field in tests that need it.
    return _DictRow({
        "id": connection_id,
        "user_id": TEST_USER_ID,
        "email_provider": provider,
        "status": "active",
        "oauth_access_token": base64.b64encode(b"encrypted_access").decode(),
        "oauth_refresh_token": None,
        "oauth_token_expires_at": None,
    })


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
    """Install auth + DB overrides; returns the mock db."""
    from main import app
    from api.dependencies import get_current_user, get_db_session
    from api.v1.connections import require_paid_tier

    session = _session_data(user_id=user_id, tier=tier)
    db = _mock_db()

    app.dependency_overrides[require_paid_tier] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db

    return db


def _make_scan_result(
    email_id: str = "msg123",
    subject: str = "Your electricity bill is ready",
    sender: str = "billing@eversource.com",
    is_utility_bill: bool = True,
    attachment_count: int = 0,
):
    from services.email_scanner_service import EmailScanResult

    return EmailScanResult(
        email_id=email_id,
        subject=subject,
        sender=sender,
        date=datetime.now(timezone.utc),
        is_utility_bill=is_utility_bill,
        attachment_count=attachment_count,
    )


# ===========================================================================
# 1. EmailScanResponse model
# ===========================================================================


class TestEmailScanResponseModel:
    """Validate the new EmailScanResponse Pydantic model."""

    def test_model_accepts_full_payload(self):
        from models.connections import EmailScanResponse

        resp = EmailScanResponse(
            connection_id=TEST_CONNECTION_ID,
            provider="gmail",
            total_emails_scanned=10,
            utility_bills_found=3,
            rates_extracted=2,
            attachments_parsed=1,
            bills=[{"email_id": "abc"}],
        )
        assert resp.connection_id == TEST_CONNECTION_ID
        assert resp.rates_extracted == 2
        assert resp.attachments_parsed == 1

    def test_model_defaults_extraction_counts_to_zero(self):
        from models.connections import EmailScanResponse

        resp = EmailScanResponse(
            connection_id="c1",
            provider="outlook",
            total_emails_scanned=5,
            utility_bills_found=1,
        )
        assert resp.rates_extracted == 0
        assert resp.attachments_parsed == 0
        assert resp.bills == []

    def test_model_bills_default_is_empty_list(self):
        from models.connections import EmailScanResponse

        resp = EmailScanResponse(
            connection_id="c2",
            provider="gmail",
            total_emails_scanned=0,
            utility_bills_found=0,
        )
        assert isinstance(resp.bills, list)
        assert len(resp.bills) == 0


# ===========================================================================
# 2. download_gmail_attachments
# ===========================================================================


class TestDownloadGmailAttachments:
    """Unit tests for the download_gmail_attachments helper."""

    @pytest.mark.asyncio
    async def test_downloads_pdf_attachment(self):
        """Should download and return a PDF attachment as bytes."""
        from services.email_scanner_service import download_gmail_attachments

        # Fake payload: one PDF part
        msg_payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "application/pdf",
                    "filename": "bill.pdf",
                    "body": {"attachmentId": "att-001", "size": 1024},
                    "parts": [],
                }
            ],
        }
        fake_att_data = base64.urlsafe_b64encode(b"%PDF-fake-content").decode()

        msg_response = MagicMock()
        msg_response.status_code = 200
        msg_response.raise_for_status = MagicMock()
        msg_response.json.return_value = {"payload": msg_payload}

        att_response = MagicMock()
        att_response.status_code = 200
        att_response.raise_for_status = MagicMock()
        att_response.json.return_value = {"data": fake_att_data}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=[msg_response, att_response])

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token123", "msg-001")

        assert len(results) == 1
        assert results[0]["filename"] == "bill.pdf"
        assert results[0]["mime_type"] == "application/pdf"
        assert isinstance(results[0]["data"], bytes)
        assert results[0]["data"].startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_skips_non_pdf_image_attachments(self):
        """ZIP and DOC attachments should be ignored."""
        from services.email_scanner_service import download_gmail_attachments

        msg_payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "application/zip",
                    "filename": "archive.zip",
                    "body": {"attachmentId": "att-zip", "size": 500},
                    "parts": [],
                },
                {
                    "mimeType": "application/msword",
                    "filename": "letter.doc",
                    "body": {"attachmentId": "att-doc", "size": 200},
                    "parts": [],
                },
            ],
        }

        msg_response = MagicMock()
        msg_response.raise_for_status = MagicMock()
        msg_response.json.return_value = {"payload": msg_payload}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=msg_response)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token123", "msg-002")

        assert results == []

    @pytest.mark.asyncio
    async def test_caps_at_five_attachments(self):
        """At most 5 attachments should be downloaded even when more exist."""
        from services.email_scanner_service import download_gmail_attachments

        # Build 8 PDF parts
        parts = [
            {
                "mimeType": "application/pdf",
                "filename": f"bill_{i}.pdf",
                "body": {"attachmentId": f"att-{i:03d}", "size": 100},
                "parts": [],
            }
            for i in range(8)
        ]
        msg_payload = {"mimeType": "multipart/mixed", "parts": parts}

        fake_att_data = base64.urlsafe_b64encode(b"%PDF").decode()

        msg_response = MagicMock()
        msg_response.raise_for_status = MagicMock()
        msg_response.json.return_value = {"payload": msg_payload}

        att_response = MagicMock()
        att_response.raise_for_status = MagicMock()
        att_response.json.return_value = {"data": fake_att_data}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        # First call = msg fetch, subsequent = attachment fetches
        mock_client.get = AsyncMock(side_effect=[msg_response] + [att_response] * 5)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token123", "msg-003")

        assert len(results) <= 5

    @pytest.mark.asyncio
    async def test_failed_attachment_download_is_skipped(self):
        """A failed individual attachment download should not abort the rest."""
        from services.email_scanner_service import download_gmail_attachments
        import httpx

        parts = [
            {
                "mimeType": "application/pdf",
                "filename": "bill_a.pdf",
                "body": {"attachmentId": "att-a", "size": 100},
                "parts": [],
            },
            {
                "mimeType": "application/pdf",
                "filename": "bill_b.pdf",
                "body": {"attachmentId": "att-b", "size": 100},
                "parts": [],
            },
        ]
        msg_payload = {"mimeType": "multipart/mixed", "parts": parts}

        fake_att_data = base64.urlsafe_b64encode(b"%PDF-good").decode()

        msg_response = MagicMock()
        msg_response.raise_for_status = MagicMock()
        msg_response.json.return_value = {"payload": msg_payload}

        # First attachment raises, second succeeds
        bad_att_response = MagicMock()
        bad_att_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock()
            )
        )

        good_att_response = MagicMock()
        good_att_response.raise_for_status = MagicMock()
        good_att_response.json.return_value = {"data": fake_att_data}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(
            side_effect=[msg_response, bad_att_response, good_att_response]
        )

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token123", "msg-004")

        # Only the successful attachment should be returned
        assert len(results) == 1
        assert results[0]["filename"] == "bill_b.pdf"

    @pytest.mark.asyncio
    async def test_handles_nested_parts(self):
        """Attachments nested inside multipart/alternative should be found."""
        from services.email_scanner_service import download_gmail_attachments

        msg_payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "application/pdf",
                            "filename": "nested.pdf",
                            "body": {"attachmentId": "att-nested", "size": 100},
                            "parts": [],
                        }
                    ],
                    "body": {},
                    "filename": "",
                }
            ],
        }
        fake_att_data = base64.urlsafe_b64encode(b"%PDF-nested").decode()

        msg_response = MagicMock()
        msg_response.raise_for_status = MagicMock()
        msg_response.json.return_value = {"payload": msg_payload}

        att_response = MagicMock()
        att_response.raise_for_status = MagicMock()
        att_response.json.return_value = {"data": fake_att_data}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=[msg_response, att_response])

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token123", "msg-005")

        assert len(results) == 1
        assert results[0]["filename"] == "nested.pdf"


# ===========================================================================
# 3. download_outlook_attachments
# ===========================================================================


class TestDownloadOutlookAttachments:
    """Unit tests for the download_outlook_attachments helper."""

    @pytest.mark.asyncio
    async def test_downloads_pdf_attachment(self):
        """Should decode and return a PDF attachment from contentBytes."""
        from services.email_scanner_service import download_outlook_attachments

        fake_content = base64.b64encode(b"%PDF-outlook-bill").decode()
        att_list = {
            "value": [
                {
                    "name": "energy_bill.pdf",
                    "contentType": "application/pdf",
                    "contentBytes": fake_content,
                }
            ]
        }

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = att_list

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token456", "outlook-msg-001")

        assert len(results) == 1
        assert results[0]["filename"] == "energy_bill.pdf"
        assert results[0]["data"].startswith(b"%PDF")
        assert results[0]["mime_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_skips_non_pdf_image_attachments(self):
        """Non-PDF/image content types should be filtered out."""
        from services.email_scanner_service import download_outlook_attachments

        att_list = {
            "value": [
                {
                    "name": "archive.zip",
                    "contentType": "application/zip",
                    "contentBytes": base64.b64encode(b"zip-data").decode(),
                },
                {
                    "name": "doc.docx",
                    "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "contentBytes": base64.b64encode(b"docx-data").decode(),
                },
            ]
        }

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = att_list

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token456", "outlook-msg-002")

        assert results == []

    @pytest.mark.asyncio
    async def test_caps_at_five_attachments(self):
        """At most 5 attachments should be returned even with 8 in the list."""
        from services.email_scanner_service import download_outlook_attachments

        fake_content = base64.b64encode(b"%PDF-page").decode()
        att_list = {
            "value": [
                {
                    "name": f"bill_{i}.pdf",
                    "contentType": "application/pdf",
                    "contentBytes": fake_content,
                }
                for i in range(8)
            ]
        }

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = att_list

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token456", "outlook-msg-003")

        assert len(results) <= 5

    @pytest.mark.asyncio
    async def test_skips_attachment_with_empty_content_bytes(self):
        """Attachment with empty or missing contentBytes should be skipped."""
        from services.email_scanner_service import download_outlook_attachments

        att_list = {
            "value": [
                {
                    "name": "empty.pdf",
                    "contentType": "application/pdf",
                    "contentBytes": "",
                }
            ]
        }

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = att_list

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token456", "outlook-msg-004")

        assert results == []

    @pytest.mark.asyncio
    async def test_handles_content_type_with_charset_param(self):
        """content-type 'application/pdf; charset=utf-8' should still match."""
        from services.email_scanner_service import download_outlook_attachments

        fake_content = base64.b64encode(b"%PDF-charset").decode()
        att_list = {
            "value": [
                {
                    "name": "bill.pdf",
                    "contentType": "application/pdf; charset=utf-8",
                    "contentBytes": fake_content,
                }
            ]
        }

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = att_list

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token456", "outlook-msg-005")

        assert len(results) == 1
        assert results[0]["filename"] == "bill.pdf"


# ===========================================================================
# 4. extract_rates_from_attachments
# ===========================================================================


class TestExtractRatesFromAttachments:
    """Unit tests for the extract_rates_from_attachments helper."""

    @pytest.mark.asyncio
    async def test_extracts_rate_from_pdf_attachment(self):
        """Should call bill_parser extractors and return rate data."""
        from services.email_scanner_service import extract_rates_from_attachments

        fake_pdf_data = b"%PDF-1.4 fake"
        attachments = [
            {"filename": "bill.pdf", "data": fake_pdf_data, "mime_type": "application/pdf"}
        ]

        with patch(
            "services.bill_parser.extract_text", return_value="Rate: $0.1850/kWh\nTotal: $95.00"
        ), patch(
            "services.bill_parser._validate_magic_bytes", return_value="pdf"
        ), patch(
            "services.bill_parser.extract_rate_per_kwh", return_value=(0.185, 1.0)
        ), patch(
            "services.bill_parser.extract_supplier", return_value=("Eversource", 0.9)
        ), patch(
            "services.bill_parser.extract_billing_period", return_value=("2025-01-01", "2025-01-31", 0.85)
        ), patch(
            "services.bill_parser.extract_total_kwh", return_value=(512.0, 0.85)
        ), patch(
            "services.bill_parser.extract_total_amount", return_value=(95.00, 0.9)
        ):
            results = await extract_rates_from_attachments(attachments)

        assert len(results) == 1
        assert results[0]["filename"] == "bill.pdf"
        assert results[0]["rate_per_kwh"] == 0.185
        assert results[0]["supplier"] == "Eversource"
        assert results[0]["total_kwh"] == 512.0

    @pytest.mark.asyncio
    async def test_skips_attachment_with_empty_data(self):
        """Empty data bytes should produce no results."""
        from services.email_scanner_service import extract_rates_from_attachments

        attachments = [
            {"filename": "empty.pdf", "data": b"", "mime_type": "application/pdf"}
        ]
        results = await extract_rates_from_attachments(attachments)
        assert results == []

    @pytest.mark.asyncio
    async def test_attachment_with_no_extractable_text_returns_partial_result(self):
        """An attachment whose text extraction yields blank should be skipped."""
        from services.email_scanner_service import extract_rates_from_attachments

        attachments = [
            {"filename": "scan.pdf", "data": b"%PDF-blank", "mime_type": "application/pdf"}
        ]

        with patch(
            "services.bill_parser._validate_magic_bytes", return_value="pdf"
        ), patch(
            "services.bill_parser.extract_text", return_value="   "
        ):
            results = await extract_rates_from_attachments(attachments)

        # No results because text is blank
        assert results == []

    @pytest.mark.asyncio
    async def test_rate_below_confidence_threshold_not_included(self):
        """Rates with confidence < 0.5 should be omitted from the result dict."""
        from services.email_scanner_service import extract_rates_from_attachments

        attachments = [
            {"filename": "bill.pdf", "data": b"%PDF-low-conf", "mime_type": "application/pdf"}
        ]

        with patch(
            "services.bill_parser._validate_magic_bytes", return_value="pdf"
        ), patch(
            "services.bill_parser.extract_text", return_value="kWh 500"
        ), patch(
            "services.bill_parser.extract_rate_per_kwh", return_value=(0.12, 0.3)  # low confidence
        ), patch(
            "services.bill_parser.extract_supplier", return_value=(None, 0.0)
        ), patch(
            "services.bill_parser.extract_billing_period", return_value=(None, None, 0.0)
        ), patch(
            "services.bill_parser.extract_total_kwh", return_value=(500.0, 0.85)
        ), patch(
            "services.bill_parser.extract_total_amount", return_value=(None, 0.0)
        ):
            results = await extract_rates_from_attachments(attachments)

        assert len(results) == 1
        assert "rate_per_kwh" not in results[0]
        assert results[0]["total_kwh"] == 500.0

    @pytest.mark.asyncio
    async def test_exception_in_extractor_returns_partial_result(self):
        """An exception in bill_parser should not crash — filename entry is returned."""
        from services.email_scanner_service import extract_rates_from_attachments

        attachments = [
            {"filename": "corrupt.pdf", "data": b"%PDF-corrupt", "mime_type": "application/pdf"}
        ]

        with patch(
            "services.bill_parser._validate_magic_bytes", return_value="pdf"
        ), patch(
            "services.bill_parser.extract_text", side_effect=RuntimeError("corrupt PDF")
        ):
            results = await extract_rates_from_attachments(attachments)

        assert len(results) == 1
        assert results[0]["filename"] == "corrupt.pdf"
        assert "rate_per_kwh" not in results[0]

    @pytest.mark.asyncio
    async def test_multiple_attachments_all_processed(self):
        """All qualifying attachments in the list should be processed."""
        from services.email_scanner_service import extract_rates_from_attachments

        attachments = [
            {"filename": "jan.pdf", "data": b"%PDF-jan", "mime_type": "application/pdf"},
            {"filename": "feb.pdf", "data": b"%PDF-feb", "mime_type": "application/pdf"},
        ]

        rates = [0.185, 0.190]
        call_count = [0]

        def _rate_side_effect(text):
            r = rates[call_count[0] % len(rates)]
            call_count[0] += 1
            return (r, 1.0)

        with patch(
            "services.bill_parser._validate_magic_bytes", return_value="pdf"
        ), patch(
            "services.bill_parser.extract_text", return_value="Rate: $0.185/kWh"
        ), patch(
            "services.bill_parser.extract_rate_per_kwh", side_effect=_rate_side_effect
        ), patch(
            "services.bill_parser.extract_supplier", return_value=(None, 0.0)
        ), patch(
            "services.bill_parser.extract_billing_period", return_value=(None, None, 0.0)
        ), patch(
            "services.bill_parser.extract_total_kwh", return_value=(None, 0.0)
        ), patch(
            "services.bill_parser.extract_total_amount", return_value=(None, 0.0)
        ):
            results = await extract_rates_from_attachments(attachments)

        assert len(results) == 2
        filenames = {r["filename"] for r in results}
        assert "jan.pdf" in filenames
        assert "feb.pdf" in filenames


# ===========================================================================
# 5. trigger_email_scan endpoint — body text extraction
# ===========================================================================


class TestTriggerEmailScanBodyExtraction:
    """Tests for email body rate extraction wired into the scan endpoint."""

    def _setup_scan(
        self,
        db: AsyncMock,
        connection_id: str,
        provider: str,
        bills: list,
        db_execute_results: list | None = None,
    ):
        """Wire db.execute to return different results per call."""
        # First call = connection lookup, subsequent = INSERT calls
        conn_row = _active_connection_row(connection_id, provider)
        conn_result = _mapping_result([conn_row])
        # Subsequent executes (INSERT) return a generic mock
        insert_result = MagicMock()
        insert_result.mappings.return_value.first.return_value = None

        side_effects = [conn_result] + [insert_result] * 20
        db.execute.side_effect = side_effects

    @pytest.mark.asyncio
    async def test_body_rate_extracted_and_persisted(self, client):
        """When body text contains a rate, it should be persisted and counted."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_scan(db, connection_id, "gmail", [])

        bill = _make_scan_result(email_id="msg-body-1", attachment_count=0)

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={"rate_per_kwh": 0.1750, "total_amount": 88.50},
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rates_extracted"] == 1
        assert data["utility_bills_found"] == 1
        assert data["attachments_parsed"] == 0

    @pytest.mark.asyncio
    async def test_no_rate_in_body_does_not_persist(self, client):
        """When body extraction returns no rate, nothing is inserted."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_scan(db, connection_id, "gmail", [])

        bill = _make_scan_result(email_id="msg-no-rate", attachment_count=0)

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={"total_amount": 55.00},  # no rate_per_kwh
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rates_extracted"] == 0

    @pytest.mark.asyncio
    async def test_body_extraction_failure_does_not_abort_scan(self, client):
        """If extract_rates_from_email raises, the scan still completes."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_scan(db, connection_id, "gmail", [])

        bill = _make_scan_result(email_id="msg-crash", attachment_count=0)

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            side_effect=Exception("API timeout"),
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rates_extracted"] == 0  # failed gracefully

    @pytest.mark.asyncio
    async def test_multiple_bills_all_extracted(self, client):
        """Rates from multiple utility bills should all be counted."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_scan(db, connection_id, "gmail", [])

        bills = [
            _make_scan_result(email_id=f"msg-multi-{i}", attachment_count=0)
            for i in range(3)
        ]

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=bills,
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={"rate_per_kwh": 0.2100},
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rates_extracted"] == 3
        assert data["utility_bills_found"] == 3

    @pytest.mark.asyncio
    async def test_non_utility_emails_not_processed(self, client):
        """Non-utility emails should not trigger any extraction."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_scan(db, connection_id, "gmail", [])

        non_bill = _make_scan_result(
            email_id="msg-newsletter",
            subject="Weekly Newsletter",
            sender="news@example.com",
            is_utility_bill=False,
        )
        bill = _make_scan_result(email_id="msg-bill", is_utility_bill=True)

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[non_bill, bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={"rate_per_kwh": 0.1500},
        ) as mock_extract:
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        # Only 1 utility bill was found
        assert data["utility_bills_found"] == 1
        assert data["total_emails_scanned"] == 2
        # extract_rates_from_email called once (for the one utility bill)
        mock_extract.assert_called_once()


# ===========================================================================
# 6. trigger_email_scan endpoint — attachment extraction
# ===========================================================================


class TestTriggerEmailScanAttachmentExtraction:
    """Tests for attachment download and parsing wired into the scan endpoint."""

    def _setup_db(self, db: AsyncMock, connection_id: str, provider: str = "gmail"):
        conn_row = _active_connection_row(connection_id, provider)
        conn_result = _mapping_result([conn_row])
        insert_result = MagicMock()
        insert_result.mappings.return_value.first.return_value = None
        db.execute.side_effect = [conn_result] + [insert_result] * 30

    @pytest.mark.asyncio
    async def test_gmail_attachment_rate_persisted(self, client):
        """When a Gmail attachment contains a rate, it should be counted."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_db(db, connection_id, "gmail")

        bill = _make_scan_result(email_id="msg-att-gmail", attachment_count=1)
        fake_attachment = [
            {"filename": "bill.pdf", "data": b"%PDF-fake", "mime_type": "application/pdf"}
        ]
        parsed_result = [{"filename": "bill.pdf", "rate_per_kwh": 0.2150}]

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={},  # no rate from body
        ), patch(
            "services.email_scanner_service.download_gmail_attachments",
            new_callable=AsyncMock,
            return_value=fake_attachment,
        ), patch(
            "services.email_scanner_service.extract_rates_from_attachments",
            new_callable=AsyncMock,
            return_value=parsed_result,
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rates_extracted"] == 1
        assert data["attachments_parsed"] == 1

    @pytest.mark.asyncio
    async def test_outlook_attachment_rate_persisted(self, client):
        """When an Outlook attachment contains a rate, it should be counted."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_db(db, connection_id, "outlook")

        bill = _make_scan_result(email_id="msg-att-outlook", attachment_count=1)
        fake_attachment = [
            {"filename": "invoice.pdf", "data": b"%PDF-fake", "mime_type": "application/pdf"}
        ]
        parsed_result = [{"filename": "invoice.pdf", "rate_per_kwh": 0.1890}]

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_outlook_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "services.email_scanner_service.download_outlook_attachments",
            new_callable=AsyncMock,
            return_value=fake_attachment,
        ), patch(
            "services.email_scanner_service.extract_rates_from_attachments",
            new_callable=AsyncMock,
            return_value=parsed_result,
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rates_extracted"] == 1
        assert data["attachments_parsed"] == 1

    @pytest.mark.asyncio
    async def test_attachment_download_failure_does_not_abort_scan(self, client):
        """If attachment download fails, the scan completes with partial counts."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_db(db, connection_id, "gmail")

        bill = _make_scan_result(email_id="msg-att-crash", attachment_count=1)

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "services.email_scanner_service.download_gmail_attachments",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rates_extracted"] == 0
        assert data["attachments_parsed"] == 0

    @pytest.mark.asyncio
    async def test_no_attachments_skips_download(self, client):
        """When attachment_count is 0, the download functions should not be called."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_db(db, connection_id, "gmail")

        bill = _make_scan_result(email_id="msg-no-att", attachment_count=0)

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "services.email_scanner_service.download_gmail_attachments",
            new_callable=AsyncMock,
        ) as mock_download:
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        mock_download.assert_not_called()

    @pytest.mark.asyncio
    async def test_attachment_without_rate_increments_parsed_not_extracted(self, client):
        """Parsed attachments with no extractable rate should increment attachments_parsed only."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_db(db, connection_id, "gmail")

        bill = _make_scan_result(email_id="msg-no-rate-att", attachment_count=1)
        fake_attachment = [
            {"filename": "bill.pdf", "data": b"%PDF-fake", "mime_type": "application/pdf"}
        ]
        # Parsed but no rate found
        parsed_result = [{"filename": "bill.pdf", "supplier": "Eversource"}]

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "services.email_scanner_service.download_gmail_attachments",
            new_callable=AsyncMock,
            return_value=fake_attachment,
        ), patch(
            "services.email_scanner_service.extract_rates_from_attachments",
            new_callable=AsyncMock,
            return_value=parsed_result,
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["attachments_parsed"] == 1
        assert data["rates_extracted"] == 0

    @pytest.mark.asyncio
    async def test_combined_body_and_attachment_rates(self, client):
        """Rates from both body and attachment should both be counted."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_db(db, connection_id, "gmail")

        bill = _make_scan_result(email_id="msg-combined", attachment_count=1)
        fake_attachment = [
            {"filename": "bill.pdf", "data": b"%PDF-fake", "mime_type": "application/pdf"}
        ]
        parsed_result = [{"filename": "bill.pdf", "rate_per_kwh": 0.2200}]

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={"rate_per_kwh": 0.1950},  # from body
        ), patch(
            "services.email_scanner_service.download_gmail_attachments",
            new_callable=AsyncMock,
            return_value=fake_attachment,
        ), patch(
            "services.email_scanner_service.extract_rates_from_attachments",
            new_callable=AsyncMock,
            return_value=parsed_result,  # from attachment
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        # 1 from body + 1 from attachment = 2 total
        assert data["rates_extracted"] == 2
        assert data["attachments_parsed"] == 1


# ===========================================================================
# 7. trigger_email_scan endpoint — response structure
# ===========================================================================


class TestTriggerEmailScanResponse:
    """Verify the updated scan endpoint returns the correct response shape."""

    def _setup_db(self, db: AsyncMock, connection_id: str, provider: str = "gmail"):
        conn_row = _active_connection_row(connection_id, provider)
        conn_result = _mapping_result([conn_row])
        insert_result = MagicMock()
        insert_result.mappings.return_value.first.return_value = None
        db.execute.side_effect = [conn_result] + [insert_result] * 10

    @pytest.mark.asyncio
    async def test_response_includes_all_required_fields(self, client):
        """Response should include connection_id, provider, counts, and bills."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_db(db, connection_id)

        bill = _make_scan_result(email_id="msg-resp", attachment_count=0)

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[bill],
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={},
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()

        required_keys = {
            "connection_id", "provider", "total_emails_scanned",
            "utility_bills_found", "rates_extracted", "attachments_parsed", "bills",
        }
        assert required_keys.issubset(set(data.keys()))

    @pytest.mark.asyncio
    async def test_bills_capped_at_twenty(self, client):
        """Response bills list should contain at most 20 entries."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_db(db, connection_id)

        bills = [
            _make_scan_result(email_id=f"msg-cap-{i}", is_utility_bill=True, attachment_count=0)
            for i in range(25)
        ]

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=bills,
        ), patch(
            "services.email_scanner_service.extract_rates_from_email",
            new_callable=AsyncMock,
            return_value={},
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["bills"]) <= 20
        assert data["utility_bills_found"] == 25

    @pytest.mark.asyncio
    async def test_empty_inbox_returns_zero_counts(self, client):
        """A scan with no emails should return all zero counts."""
        db = _install_auth()
        connection_id = str(uuid4())
        self._setup_db(db, connection_id)

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_gmail_inbox",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_emails_scanned"] == 0
        assert data["utility_bills_found"] == 0
        assert data["rates_extracted"] == 0
        assert data["attachments_parsed"] == 0
        assert data["bills"] == []

    @pytest.mark.asyncio
    async def test_outlook_scan_uses_correct_provider_label(self, client):
        """Outlook scan should return provider='outlook' in the response."""
        db = _install_auth()
        connection_id = str(uuid4())

        conn_row = _active_connection_row(connection_id, "outlook")
        conn_result = _mapping_result([conn_row])
        insert_result = MagicMock()
        insert_result.mappings.return_value.first.return_value = None
        db.execute.side_effect = [conn_result] + [insert_result] * 10

        with patch(
            "utils.encryption.decrypt_field", return_value="fake_access_token"
        ), patch(
            "services.email_scanner_service.scan_outlook_inbox",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.post(f"{BASE}/email/{connection_id}/scan")

        assert resp.status_code == 200
        assert resp.json()["provider"] == "outlook"
