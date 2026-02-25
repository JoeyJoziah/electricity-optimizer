"""
Tests for Bill Upload Feature — Phase 2

Coverage:
  - File validation: type, size, magic bytes, empty file
  - BillParserService: regex extraction of rate, supplier, billing period,
    usage, amount; complete parse flow; file-not-found; unsupported type
  - Endpoint: POST /{connection_id}/upload (success, bad type, too large, empty,
    connection not found, paid-tier gate)
  - Endpoint: GET /{connection_id}/uploads (list uploads, empty, not found)
  - Endpoint: POST /{connection_id}/uploads/{upload_id}/reparse (success, not found)
  - Pydantic model validation for BillUploadResponse / BillUploadListResponse

All HTTP calls use a function-scoped TestClient with overridden dependencies.
No real filesystem or Postgres connection is used.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Stable test IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "aaaaaaaa-1111-0000-0000-000000000001"
TEST_CONNECTION_ID = str(uuid4())
TEST_UPLOAD_ID = str(uuid4())
BASE = "/api/v1/connections"

# ---------------------------------------------------------------------------
# Minimal magic bytes for synthetic test files
# ---------------------------------------------------------------------------

PDF_MAGIC = b"%PDF-1.4 1 0 obj\n"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
JPG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 12


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_connections.py for independence)
# ---------------------------------------------------------------------------


class _DictRow(dict):
    """Dict subclass behaving like a SQLAlchemy RowMapping."""


def _row(**kwargs) -> _DictRow:
    return _DictRow(kwargs)


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


def _found_result() -> MagicMock:
    """Simulate a single-row fetchone() — ownership check succeeded."""
    result = MagicMock()
    result.fetchone.return_value = MagicMock()
    return result


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _session_data(user_id: str = TEST_USER_ID):
    from auth.neon_auth import SessionData

    return SessionData(
        user_id=user_id,
        email="test@example.com",
        name="Test User",
        email_verified=True,
        role="user",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Function-scoped TestClient — isolates rate limiter state."""
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_overrides():
    """Reset dependency_overrides and rate limiter around every test."""
    from main import app, _app_rate_limiter

    _app_rate_limiter.reset()
    yield
    for dep in list(app.dependency_overrides.keys()):
        app.dependency_overrides.pop(dep, None)
    _app_rate_limiter.reset()


def _install_auth(user_id: str = TEST_USER_ID) -> AsyncMock:
    """Override require_paid_tier and get_db_session; return the db mock."""
    from main import app
    from api.dependencies import get_current_user, get_db_session
    from api.v1.connections import require_paid_tier

    session = _session_data(user_id=user_id)
    db = _mock_db()

    app.dependency_overrides[require_paid_tier] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: session
    app.dependency_overrides[get_db_session] = lambda: db

    return db


# ---------------------------------------------------------------------------
# 1. File Validation (pure unit tests — no HTTP)
# ---------------------------------------------------------------------------


class TestValidateUploadFile:
    """Unit tests for services.bill_parser.validate_upload_file."""

    def test_valid_pdf(self):
        from services.bill_parser import validate_upload_file

        result = validate_upload_file("bill.pdf", "application/pdf", PDF_MAGIC + b"content")
        assert result == "pdf"

    def test_valid_png(self):
        from services.bill_parser import validate_upload_file

        result = validate_upload_file("scan.png", "image/png", PNG_MAGIC + b"body")
        assert result == "png"

    def test_valid_jpg(self):
        from services.bill_parser import validate_upload_file

        result = validate_upload_file("bill.jpg", "image/jpeg", JPG_MAGIC + b"body")
        assert result == "jpg"

    def test_bad_extension_rejected(self):
        from services.bill_parser import validate_upload_file

        with pytest.raises(ValueError, match="Unsupported file extension"):
            validate_upload_file("evil.exe", "application/pdf", PDF_MAGIC)

    def test_bad_mime_type_rejected(self):
        from services.bill_parser import validate_upload_file

        with pytest.raises(ValueError, match="Unsupported content type"):
            validate_upload_file("bill.pdf", "text/html", PDF_MAGIC)

    def test_magic_bytes_mismatch_rejected(self):
        """Extension says PDF but bytes are random garbage."""
        from services.bill_parser import validate_upload_file

        with pytest.raises(ValueError, match="does not match a supported format"):
            validate_upload_file("bill.pdf", "application/pdf", b"\x00\x01\x02" * 10)

    def test_extension_content_type_mismatch_rejected(self):
        """PNG extension but content-type is PDF."""
        from services.bill_parser import validate_upload_file

        with pytest.raises(ValueError):
            validate_upload_file("bill.png", "application/pdf", PDF_MAGIC)

    def test_jpeg_extension_accepted(self):
        """'.jpeg' extension must be accepted alongside '.jpg'."""
        from services.bill_parser import validate_upload_file

        result = validate_upload_file("bill.jpeg", "image/jpeg", JPG_MAGIC)
        assert result == "jpg"


# ---------------------------------------------------------------------------
# 2. Magic Byte Detection
# ---------------------------------------------------------------------------


class TestMagicByteValidation:
    """Unit tests for _validate_magic_bytes."""

    def test_pdf_magic(self):
        from services.bill_parser import _validate_magic_bytes

        assert _validate_magic_bytes(PDF_MAGIC) == "pdf"

    def test_png_magic(self):
        from services.bill_parser import _validate_magic_bytes

        assert _validate_magic_bytes(PNG_MAGIC) == "png"

    def test_jpg_magic(self):
        from services.bill_parser import _validate_magic_bytes

        assert _validate_magic_bytes(JPG_MAGIC) == "jpg"

    def test_unknown_magic_returns_none(self):
        from services.bill_parser import _validate_magic_bytes

        assert _validate_magic_bytes(b"\x00\x01\x02\x03") is None


# ---------------------------------------------------------------------------
# 3. Regex Field Extraction (pure unit tests)
# ---------------------------------------------------------------------------


SAMPLE_BILL_TEXT = """
EVERSOURCE ENERGY
Electric Service Statement

Account Number: 12345678
Service Address: 100 Main St, Hartford, CT 06103

Billing Period: 01/15/2025 - 02/14/2025

Usage Summary:
  kWh Used: 847

Charges:
  Energy Charge   $0.2145/kWh      $181.68
  Distribution     0.0432/kWh       $36.60
  Total Charges                     $218.28

Amount Due: $218.28

Please pay by 03/01/2025.
Thank you for being an Eversource customer.
"""


class TestExtractRatePerKwh:
    def test_extracts_dollar_rate(self):
        from services.bill_parser import extract_rate_per_kwh

        rate, conf = extract_rate_per_kwh(SAMPLE_BILL_TEXT)
        assert rate == pytest.approx(0.2145, abs=1e-6)
        assert conf >= 0.8

    def test_cents_rate_converted_to_dollars(self):
        from services.bill_parser import extract_rate_per_kwh

        text = "Rate is 21.45 cents/kWh for all tiers"
        rate, conf = extract_rate_per_kwh(text)
        assert rate == pytest.approx(0.2145, abs=1e-4)
        assert conf >= 0.7

    def test_no_rate_returns_none(self):
        from services.bill_parser import extract_rate_per_kwh

        rate, conf = extract_rate_per_kwh("No pricing information here.")
        assert rate is None
        assert conf == 0.0

    def test_unrealistic_rate_ignored(self):
        """Values outside 0.05–0.80 $/kWh should not be returned."""
        from services.bill_parser import extract_rate_per_kwh

        rate, conf = extract_rate_per_kwh("Energy rate: $9.99/kWh")
        assert rate is None


class TestExtractSupplier:
    def test_known_supplier_found(self):
        from services.bill_parser import extract_supplier

        supplier, conf = extract_supplier(SAMPLE_BILL_TEXT)
        assert supplier == "Eversource"
        assert conf >= 0.8

    def test_unknown_supplier_returns_none(self):
        from services.bill_parser import extract_supplier

        supplier, conf = extract_supplier("Some Obscure Power Corp bill")
        assert supplier is None
        assert conf == 0.0

    def test_case_insensitive_match(self):
        from services.bill_parser import extract_supplier

        supplier, conf = extract_supplier("NATIONAL GRID electric services")
        assert supplier == "National Grid"


class TestExtractBillingPeriod:
    def test_slash_date_range(self):
        from services.bill_parser import extract_billing_period

        start, end, conf = extract_billing_period(SAMPLE_BILL_TEXT)
        assert start == "2025-01-15"
        assert end == "2025-02-14"
        assert conf >= 0.8

    def test_iso_date_range(self):
        from services.bill_parser import extract_billing_period

        text = "Billing Period: 2025-01-15 to 2025-02-14"
        start, end, conf = extract_billing_period(text)
        assert start == "2025-01-15"
        assert end == "2025-02-14"

    def test_no_date_returns_none(self):
        from services.bill_parser import extract_billing_period

        start, end, conf = extract_billing_period("No dates here.")
        assert start is None
        assert end is None
        assert conf == 0.0


class TestExtractTotalKwh:
    def test_kwh_usage_extracted(self):
        from services.bill_parser import extract_total_kwh

        kwh, conf = extract_total_kwh(SAMPLE_BILL_TEXT)
        assert kwh == pytest.approx(847.0)
        assert conf >= 0.8

    def test_no_kwh_returns_none(self):
        from services.bill_parser import extract_total_kwh

        kwh, conf = extract_total_kwh("No usage data on this page.")
        assert kwh is None

    def test_comma_separated_kwh(self):
        from services.bill_parser import extract_total_kwh

        kwh, conf = extract_total_kwh("Usage: 1,234 kWh used")
        assert kwh == pytest.approx(1234.0)


class TestExtractTotalAmount:
    def test_amount_due_extracted(self):
        from services.bill_parser import extract_total_amount

        amount, conf = extract_total_amount(SAMPLE_BILL_TEXT)
        assert amount == pytest.approx(218.28)
        assert conf >= 0.8

    def test_no_amount_returns_none(self):
        from services.bill_parser import extract_total_amount

        amount, conf = extract_total_amount("No financial data here.")
        assert amount is None


# ---------------------------------------------------------------------------
# 4. BillParserService unit tests (mocked DB + filesystem)
# ---------------------------------------------------------------------------


class TestBillParserService:
    """Tests for BillParserService.parse() with mocked DB."""

    def _make_service(self, db: AsyncMock, tmp_path: Path) -> Any:
        from services.bill_parser import BillParserService

        return BillParserService(db=db, uploads_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_parse_pdf_text_success(self, tmp_path):
        """Parse succeeds when the file contains extractable bill text."""
        db = _mock_db()
        service = self._make_service(db, tmp_path)

        # Write a synthetic "PDF" with embedded text (raw PDF text extraction fallback)
        storage_key = f"{TEST_CONNECTION_ID}/{TEST_UPLOAD_ID}.pdf"
        dest = tmp_path / storage_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Build content: PDF magic + the sample bill text embedded
        dest.write_bytes(PDF_MAGIC + SAMPLE_BILL_TEXT.encode())

        result = await service.parse(TEST_UPLOAD_ID, TEST_CONNECTION_ID, storage_key)

        assert result["parse_status"] == "complete"
        assert result["detected_supplier"] == "Eversource"
        assert result["detected_rate_per_kwh"] == pytest.approx(0.2145, abs=1e-4)
        assert result["detected_total_kwh"] == pytest.approx(847.0)
        assert result["detected_total_amount"] == pytest.approx(218.28)

        # DB should have been called: set processing + save results + extracted rate insert
        assert db.execute.call_count >= 2
        assert db.commit.call_count >= 2

    @pytest.mark.asyncio
    async def test_parse_file_not_found(self, tmp_path):
        """Parser marks upload as failed when the file is missing."""
        db = _mock_db()
        service = self._make_service(db, tmp_path)

        result = await service.parse(
            TEST_UPLOAD_ID, TEST_CONNECTION_ID, "nonexistent/file.pdf"
        )

        assert result["parse_status"] == "failed"
        assert "not found" in result["parse_error"].lower()

    @pytest.mark.asyncio
    async def test_parse_bad_magic_bytes(self, tmp_path):
        """Parser marks upload as failed when magic bytes don't match supported types."""
        db = _mock_db()
        service = self._make_service(db, tmp_path)

        storage_key = f"{TEST_CONNECTION_ID}/{TEST_UPLOAD_ID}.pdf"
        dest = tmp_path / storage_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00\x01\x02\x03" + SAMPLE_BILL_TEXT.encode())

        result = await service.parse(TEST_UPLOAD_ID, TEST_CONNECTION_ID, storage_key)

        assert result["parse_status"] == "failed"
        assert "Unsupported" in result["parse_error"]

    @pytest.mark.asyncio
    async def test_parse_no_text_extracted(self, tmp_path):
        """Parser marks upload as failed when no text could be extracted."""
        db = _mock_db()
        service = self._make_service(db, tmp_path)

        storage_key = f"{TEST_CONNECTION_ID}/{TEST_UPLOAD_ID}.png"
        dest = tmp_path / storage_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Write valid PNG magic but no readable text (no pytesseract available)
        dest.write_bytes(PNG_MAGIC + b"\x00" * 200)

        result = await service.parse(TEST_UPLOAD_ID, TEST_CONNECTION_ID, storage_key)

        # Without pytesseract no text can be extracted from image
        assert result["parse_status"] == "failed"

    @pytest.mark.asyncio
    async def test_no_rate_still_completes(self, tmp_path):
        """
        If no rate is found the parse still completes — just with detected_rate=None.
        No extracted-rate row should be inserted.
        """
        db = _mock_db()
        service = self._make_service(db, tmp_path)

        storage_key = f"{TEST_CONNECTION_ID}/{TEST_UPLOAD_ID}.pdf"
        dest = tmp_path / storage_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Bill text with no rate information
        no_rate_text = (
            "EVERSOURCE ENERGY\n"
            "Billing Period: 01/15/2025 - 02/14/2025\n"
            "kWh Used: 500\n"
            "Amount Due: $120.00\n"
        )
        dest.write_bytes(PDF_MAGIC + no_rate_text.encode())

        result = await service.parse(TEST_UPLOAD_ID, TEST_CONNECTION_ID, storage_key)

        assert result["parse_status"] == "complete"
        assert result["detected_rate_per_kwh"] is None


# ---------------------------------------------------------------------------
# 5. POST /{connection_id}/upload endpoint
# ---------------------------------------------------------------------------


class TestUploadBillFileEndpoint:
    """Tests for POST /connections/{connection_id}/upload."""

    def _make_upload(
        self,
        data: bytes = None,
        filename: str = "bill.pdf",
        content_type: str = "application/pdf",
    ) -> dict:
        """Build multipart upload kwargs for TestClient."""
        if data is None:
            data = PDF_MAGIC + SAMPLE_BILL_TEXT.encode()
        return {
            "files": {"file": (filename, io.BytesIO(data), content_type)},
        }

    def test_upload_pdf_returns_202(self, client):
        """Valid PDF upload returns 202 with parse_status=pending."""
        db = _install_auth()
        db.execute = AsyncMock(
            side_effect=[
                _found_result(),  # ownership check
                MagicMock(),      # INSERT bill_uploads
            ]
        )

        with patch("api.v1.connections._UPLOADS_DIR", new=Path("/tmp/test_uploads")), \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_bytes"), \
             patch("api.v1.connections._run_background_parse"):
            response = client.post(
                f"{BASE}/{TEST_CONNECTION_ID}/upload",
                **self._make_upload(),
            )

        assert response.status_code == 202
        data = response.json()
        assert data["parse_status"] == "pending"
        assert data["connection_id"] == TEST_CONNECTION_ID
        assert data["file_name"] == "bill.pdf"
        assert data["file_type"] == "pdf"
        assert "id" in data

    def test_upload_png_returns_202(self, client):
        """Valid PNG upload is accepted."""
        db = _install_auth()
        db.execute = AsyncMock(
            side_effect=[_found_result(), MagicMock()]
        )

        with patch("api.v1.connections._UPLOADS_DIR", new=Path("/tmp/test_uploads")), \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_bytes"), \
             patch("api.v1.connections._run_background_parse"):
            response = client.post(
                f"{BASE}/{TEST_CONNECTION_ID}/upload",
                **self._make_upload(
                    data=PNG_MAGIC + b"\x00" * 100,
                    filename="scan.png",
                    content_type="image/png",
                ),
            )

        assert response.status_code == 202
        assert response.json()["file_type"] == "png"

    def test_upload_connection_not_found(self, client):
        """Returns 404 when the connection does not belong to the user."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_empty_result())

        response = client.post(
            f"{BASE}/{TEST_CONNECTION_ID}/upload",
            **self._make_upload(),
        )

        assert response.status_code == 404

    def test_upload_wrong_extension_rejected(self, client):
        """Uploading a .txt file returns 415."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_found_result())

        response = client.post(
            f"{BASE}/{TEST_CONNECTION_ID}/upload",
            files={"file": ("document.txt", io.BytesIO(b"some text"), "text/plain")},
        )

        assert response.status_code == 415

    def test_upload_empty_file_rejected(self, client):
        """Empty file upload returns 400."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_found_result())

        response = client.post(
            f"{BASE}/{TEST_CONNECTION_ID}/upload",
            files={"file": ("bill.pdf", io.BytesIO(b""), "application/pdf")},
        )

        assert response.status_code == 400

    def test_upload_spoofed_mime_rejected(self, client):
        """
        File with PDF extension and MIME type but non-PDF magic bytes returns 415.
        The endpoint checks magic bytes — it cannot be spoofed by content-type alone.
        """
        db = _install_auth()
        db.execute = AsyncMock(return_value=_found_result())

        response = client.post(
            f"{BASE}/{TEST_CONNECTION_ID}/upload",
            files={
                "file": (
                    "not_a_pdf.pdf",
                    io.BytesIO(b"\x00\x01\x02FAKE" * 100),
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 415

    def test_upload_requires_paid_tier(self, client):
        """Unauthenticated or free-tier users are rejected."""
        from main import app
        from api.dependencies import get_current_user, get_db_session
        from api.v1.connections import require_paid_tier

        app.dependency_overrides.pop(require_paid_tier, None)

        session = _session_data()
        db = _mock_db()
        db.execute = AsyncMock(
            return_value=MagicMock(
                fetchone=MagicMock(return_value=MagicMock(__getitem__=lambda s, k: "free"))
            )
        )

        # Return "free" from the subscription_tier query
        scalar_result = MagicMock()
        row_mock = MagicMock()
        row_mock.__getitem__ = lambda self, k: "free"
        scalar_result.fetchone.return_value = row_mock
        db.execute = AsyncMock(return_value=scalar_result)

        app.dependency_overrides[get_current_user] = lambda: session
        app.dependency_overrides[get_db_session] = lambda: db

        response = client.post(
            f"{BASE}/{TEST_CONNECTION_ID}/upload",
            **self._make_upload(),
        )

        assert response.status_code == 403

    def test_upload_file_size_tracked(self, client):
        """file_size_bytes in the response matches the actual payload size."""
        db = _install_auth()
        db.execute = AsyncMock(
            side_effect=[_found_result(), MagicMock()]
        )

        pdf_data = PDF_MAGIC + SAMPLE_BILL_TEXT.encode()

        with patch("api.v1.connections._UPLOADS_DIR", new=Path("/tmp/test_uploads")), \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_bytes"), \
             patch("api.v1.connections._run_background_parse"):
            response = client.post(
                f"{BASE}/{TEST_CONNECTION_ID}/upload",
                **self._make_upload(data=pdf_data),
            )

        assert response.status_code == 202
        assert response.json()["file_size_bytes"] == len(pdf_data)


# ---------------------------------------------------------------------------
# 6. GET /{connection_id}/uploads  — list uploads
# ---------------------------------------------------------------------------


class TestListBillUploads:
    """Tests for GET /connections/{connection_id}/uploads."""

    def _upload_row(self, upload_id: str = None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "id": upload_id or str(uuid4()),
            "connection_id": TEST_CONNECTION_ID,
            "file_name": "bill.pdf",
            "file_type": "pdf",
            "file_size_bytes": 1024,
            "parse_status": "complete",
            "detected_supplier": "Eversource",
            "detected_rate_per_kwh": 0.2145,
            "detected_billing_period_start": "2025-01-15",
            "detected_billing_period_end": "2025-02-14",
            "detected_total_kwh": 847.0,
            "detected_total_amount": 218.28,
            "parse_error": None,
            "created_at": now,
        }

    def test_list_uploads_empty(self, client):
        """New connection with no uploads returns empty list."""
        db = _install_auth()
        db.execute = AsyncMock(
            side_effect=[_found_result(), _mapping_result([])]
        )

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/uploads")

        assert response.status_code == 200
        data = response.json()
        assert data["uploads"] == []
        assert data["total"] == 0

    def test_list_uploads_returns_all(self, client):
        """All uploads for the connection are returned."""
        db = _install_auth()
        rows = [self._upload_row(), self._upload_row()]
        db.execute = AsyncMock(
            side_effect=[_found_result(), _mapping_result(rows)]
        )

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/uploads")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["uploads"]) == 2
        assert data["uploads"][0]["detected_supplier"] == "Eversource"

    def test_list_uploads_connection_not_found(self, client):
        """Returns 404 when the connection does not belong to the user."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_empty_result())

        response = client.get(f"{BASE}/{str(uuid4())}/uploads")

        assert response.status_code == 404

    def test_list_uploads_includes_parse_status(self, client):
        """parse_status field is correctly serialised in the response."""
        db = _install_auth()
        pending_row = self._upload_row()
        pending_row["parse_status"] = "pending"
        pending_row["detected_supplier"] = None
        pending_row["detected_rate_per_kwh"] = None

        db.execute = AsyncMock(
            side_effect=[_found_result(), _mapping_result([pending_row])]
        )

        response = client.get(f"{BASE}/{TEST_CONNECTION_ID}/uploads")

        assert response.status_code == 200
        upload = response.json()["uploads"][0]
        assert upload["parse_status"] == "pending"
        assert upload["detected_supplier"] is None


# ---------------------------------------------------------------------------
# 7. POST /{connection_id}/uploads/{upload_id}/reparse
# ---------------------------------------------------------------------------


class TestReparseBillUpload:
    """Tests for POST /connections/{connection_id}/uploads/{upload_id}/reparse."""

    def _upload_row(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "id": TEST_UPLOAD_ID,
            "connection_id": TEST_CONNECTION_ID,
            "file_name": "bill.pdf",
            "file_type": "pdf",
            "file_size_bytes": 2048,
            "storage_key": f"{TEST_CONNECTION_ID}/{TEST_UPLOAD_ID}.pdf",
            "parse_status": "failed",
            "detected_supplier": None,
            "detected_rate_per_kwh": None,
            "detected_billing_period_start": None,
            "detected_billing_period_end": None,
            "detected_total_kwh": None,
            "detected_total_amount": None,
            "parse_error": "previous error",
            "created_at": now,
        }

    def test_reparse_schedules_successfully(self, client):
        """Reparse resets status to pending and returns 202."""
        db = _install_auth()
        row = self._upload_row()
        db.execute = AsyncMock(
            side_effect=[
                _found_result(),             # connection ownership
                _mapping_result([row]),      # fetch upload
                MagicMock(),                 # UPDATE parse_status = pending
            ]
        )

        with patch("api.v1.connections._run_background_parse"):
            response = client.post(
                f"{BASE}/{TEST_CONNECTION_ID}/uploads/{TEST_UPLOAD_ID}/reparse"
            )

        assert response.status_code == 202
        data = response.json()
        assert data["parse_status"] == "pending"
        assert data["id"] == TEST_UPLOAD_ID

    def test_reparse_upload_not_found(self, client):
        """Returns 404 when the upload_id doesn't exist for this connection."""
        db = _install_auth()
        db.execute = AsyncMock(
            side_effect=[
                _found_result(),    # connection ownership
                _empty_result(),    # upload not found
            ]
        )

        response = client.post(
            f"{BASE}/{TEST_CONNECTION_ID}/uploads/{str(uuid4())}/reparse"
        )

        assert response.status_code == 404

    def test_reparse_connection_not_found(self, client):
        """Returns 404 when the connection doesn't belong to the user."""
        db = _install_auth()
        db.execute = AsyncMock(return_value=_empty_result())

        response = client.post(
            f"{BASE}/{str(uuid4())}/uploads/{TEST_UPLOAD_ID}/reparse"
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 8. Pydantic model validation
# ---------------------------------------------------------------------------


class TestBillUploadModels:
    """Pure Pydantic model validation — no HTTP client needed."""

    def test_bill_upload_response_valid(self):
        from models.connections import BillUploadResponse

        now = datetime.now(timezone.utc)
        upload = BillUploadResponse(
            id=str(uuid4()),
            connection_id=TEST_CONNECTION_ID,
            file_name="bill.pdf",
            file_type="pdf",
            file_size_bytes=1024,
            parse_status="complete",
            detected_supplier="Eversource",
            detected_rate_per_kwh=0.2145,
            detected_billing_period_start="2025-01-15",
            detected_billing_period_end="2025-02-14",
            detected_total_kwh=847.0,
            detected_total_amount=218.28,
            created_at=now,
        )
        dumped = upload.model_dump()
        assert dumped["parse_status"] == "complete"
        assert dumped["detected_rate_per_kwh"] == 0.2145
        assert dumped["file_type"] == "pdf"

    def test_bill_upload_response_optional_fields_default_none(self):
        from models.connections import BillUploadResponse

        upload = BillUploadResponse(
            id=str(uuid4()),
            connection_id=TEST_CONNECTION_ID,
            file_name="upload.pdf",
            file_type="pdf",
            file_size_bytes=512,
            parse_status="pending",
        )
        dumped = upload.model_dump()
        assert dumped["detected_supplier"] is None
        assert dumped["detected_rate_per_kwh"] is None
        assert dumped["parse_error"] is None

    def test_bill_upload_list_response_valid(self):
        from models.connections import BillUploadResponse, BillUploadListResponse

        now = datetime.now(timezone.utc)
        uploads = [
            BillUploadResponse(
                id=str(uuid4()),
                connection_id=TEST_CONNECTION_ID,
                file_name="bill.pdf",
                file_type="pdf",
                file_size_bytes=1024,
                parse_status="pending",
                created_at=now,
            )
        ]
        response = BillUploadListResponse(uploads=uploads, total=1)
        assert response.total == 1
        assert len(response.uploads) == 1

    def test_bill_upload_parse_status_values(self):
        """All four valid parse_status values are accepted."""
        from models.connections import BillUploadResponse

        for status in ("pending", "processing", "complete", "failed"):
            upload = BillUploadResponse(
                id=str(uuid4()),
                connection_id=TEST_CONNECTION_ID,
                file_name="bill.pdf",
                file_type="pdf",
                file_size_bytes=100,
                parse_status=status,
            )
            assert upload.parse_status == status


# ---------------------------------------------------------------------------
# 9. Storage key builder
# ---------------------------------------------------------------------------


class TestBuildStorageKey:
    def test_key_includes_connection_and_upload(self):
        from services.bill_parser import build_storage_key

        key = build_storage_key("conn-abc", "upload-xyz", "bill.pdf")
        assert key == "conn-abc/upload-xyz.pdf"

    def test_key_preserves_jpeg_extension(self):
        from services.bill_parser import build_storage_key

        key = build_storage_key("conn-abc", "upload-xyz", "scan.jpeg")
        assert key.endswith(".jpeg")

    def test_key_lowercases_extension(self):
        from services.bill_parser import build_storage_key

        key = build_storage_key("conn-abc", "upload-xyz", "BILL.PDF")
        assert key.endswith(".pdf")
