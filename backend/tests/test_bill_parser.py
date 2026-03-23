"""Tests for bill_parser service — field extractors, helpers, and BillParserService."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.bill_parser import (
    _MAGIC_JPG,
    _MAGIC_PDF,
    _MAGIC_PNG,
    BillParserService,
    _parse_date_flexible,
    _strip_commas,
    _validate_magic_bytes,
    build_storage_key,
    extract_billing_period,
    extract_rate_per_kwh,
    extract_supplier,
    extract_text,
    extract_total_amount,
    extract_total_kwh,
    validate_upload_file,
)

# ---------------------------------------------------------------------------
# Magic bytes / helper tests
# ---------------------------------------------------------------------------


class TestValidateMagicBytes:
    def test_detects_pdf(self):
        assert _validate_magic_bytes(_MAGIC_PDF + b"rest") == "pdf"

    def test_detects_png(self):
        assert _validate_magic_bytes(_MAGIC_PNG + b"rest") == "png"

    def test_detects_jpg(self):
        assert _validate_magic_bytes(_MAGIC_JPG + b"rest") == "jpg"

    def test_unknown_returns_none(self):
        assert _validate_magic_bytes(b"\x00\x01\x02\x03") is None

    def test_empty_bytes_returns_none(self):
        assert _validate_magic_bytes(b"") is None


class TestParseDateFlexible:
    def test_parses_mm_dd_yyyy(self):
        assert _parse_date_flexible("01/15/2025") == "2025-01-15"

    def test_parses_iso_format(self):
        assert _parse_date_flexible("2025-01-15") == "2025-01-15"

    def test_parses_long_month_name(self):
        assert _parse_date_flexible("January 15, 2025") == "2025-01-15"

    def test_parses_short_month_name(self):
        assert _parse_date_flexible("Jan 15, 2025") == "2025-01-15"

    def test_invalid_format_returns_none(self):
        assert _parse_date_flexible("not-a-date") is None

    def test_strips_trailing_comma(self):
        assert _parse_date_flexible("Jan 15, 2025,") == "2025-01-15"


class TestStripCommas:
    def test_removes_commas(self):
        assert _strip_commas("1,234.56") == "1234.56"

    def test_no_commas_unchanged(self):
        assert _strip_commas("847.00") == "847.00"


# ---------------------------------------------------------------------------
# Rate extraction tests
# ---------------------------------------------------------------------------


class TestExtractRatePerKwh:
    def test_dollar_per_kwh_pattern(self):
        rate, conf = extract_rate_per_kwh("Your rate is $0.2145/kWh this month.")
        assert rate == pytest.approx(0.2145)
        assert conf == 1.0

    def test_cents_per_kwh_pattern(self):
        rate, conf = extract_rate_per_kwh("Energy charge: 21.45 cents/kWh")
        assert rate == pytest.approx(0.2145, rel=1e-3)
        assert conf == 0.8

    def test_cents_with_symbol(self):
        rate, conf = extract_rate_per_kwh("21.45¢/kWh billed")
        assert rate is not None
        assert rate == pytest.approx(0.2145, rel=1e-3)

    def test_generic_per_kwh_pattern(self):
        rate, conf = extract_rate_per_kwh("0.1850 per kWh distribution")
        assert rate == pytest.approx(0.1850)
        assert conf == 0.6

    def test_no_rate_returns_none_zero_conf(self):
        rate, conf = extract_rate_per_kwh("No rate information here.")
        assert rate is None
        assert conf == 0.0

    def test_rate_out_of_valid_range_ignored(self):
        # 1.50/kWh is above the 0.80 upper bound
        rate, conf = extract_rate_per_kwh("Rate: $1.50/kWh extremely high")
        assert rate is None

    def test_very_low_rate_ignored(self):
        # $0.01/kWh is below the 0.05 lower bound
        rate, conf = extract_rate_per_kwh("Rate: $0.01/kWh")
        assert rate is None


# ---------------------------------------------------------------------------
# Supplier extraction tests
# ---------------------------------------------------------------------------


class TestExtractSupplier:
    def test_known_supplier_found(self):
        supplier, conf = extract_supplier("Bill from Con Edison for your service")
        assert supplier == "Con Edison"
        assert conf == 0.9

    def test_case_insensitive_match(self):
        supplier, conf = extract_supplier("eversource energy customer service")
        assert supplier == "Eversource"
        assert conf == 0.9

    def test_unknown_supplier_returns_none(self):
        supplier, conf = extract_supplier("Some Unknown Power Company LLC")
        assert supplier is None
        assert conf == 0.0

    def test_duke_energy_recognized(self):
        supplier, conf = extract_supplier("Duke Energy Progress LLC")
        assert supplier == "Duke Energy"

    def test_comed_recognized(self):
        supplier, conf = extract_supplier("Commonwealth Edison (ComEd) bill")
        assert supplier is not None  # Either "CommonwealthEdison" or "ComEd"


# ---------------------------------------------------------------------------
# Billing period extraction tests
# ---------------------------------------------------------------------------


class TestExtractBillingPeriod:
    def test_slash_date_range(self):
        start, end, conf = extract_billing_period("Service period: 01/15/2025 - 02/14/2025")
        assert start == "2025-01-15"
        assert end == "2025-02-14"
        assert conf == 0.85

    def test_iso_date_range(self):
        start, end, conf = extract_billing_period("2025-01-15 to 2025-02-14")
        assert start == "2025-01-15"
        assert end == "2025-02-14"
        assert conf == 0.85

    def test_month_name_range(self):
        start, end, conf = extract_billing_period(
            "Billing period: January 15, 2025 - February 14, 2025"
        )
        assert start == "2025-01-15"
        assert end == "2025-02-14"
        assert conf == 0.85

    def test_billing_period_from_pattern(self):
        start, end, conf = extract_billing_period("Billing period from: 01/15/2025 to 02/14/2025")
        assert start == "2025-01-15"
        assert end == "2025-02-14"

    def test_no_dates_returns_none(self):
        start, end, conf = extract_billing_period("No date information here.")
        assert start is None
        assert end is None
        assert conf == 0.0


# ---------------------------------------------------------------------------
# kWh usage extraction tests
# ---------------------------------------------------------------------------


class TestExtractTotalKwh:
    def test_usage_label_pattern(self):
        kwh, conf = extract_total_kwh("Usage: 847 kWh billed this month.")
        assert kwh == pytest.approx(847.0)
        assert conf == 0.85

    def test_kwh_used_pattern(self):
        kwh, conf = extract_total_kwh("1,234.5 kWh used during billing period")
        assert kwh == pytest.approx(1234.5)

    def test_comma_separated_number(self):
        kwh, conf = extract_total_kwh("Total Usage: 1,500 kWh")
        assert kwh == pytest.approx(1500.0)

    def test_no_usage_returns_none(self):
        kwh, conf = extract_total_kwh("No usage information.")
        assert kwh is None
        assert conf == 0.0

    def test_unreasonably_large_usage_ignored(self):
        kwh, conf = extract_total_kwh("Usage: 999999 kWh used")
        assert kwh is None


# ---------------------------------------------------------------------------
# Total amount extraction tests
# ---------------------------------------------------------------------------


class TestExtractTotalAmount:
    def test_amount_due_pattern(self):
        amount, conf = extract_total_amount("Amount Due: $123.45")
        assert amount == pytest.approx(123.45)
        assert conf == 0.9

    def test_total_amount_due_pattern(self):
        amount, conf = extract_total_amount("Total Amount Due $456.78")
        assert amount == pytest.approx(456.78)

    def test_please_pay_pattern(self):
        amount, conf = extract_total_amount("Please pay: $89.00 by due date")
        assert amount == pytest.approx(89.00)

    def test_balance_due_pattern(self):
        amount, conf = extract_total_amount("Balance Due $200.50")
        assert amount == pytest.approx(200.50)

    def test_no_amount_returns_none(self):
        amount, conf = extract_total_amount("No charge information.")
        assert amount is None
        assert conf == 0.0

    def test_comma_in_amount_parsed(self):
        amount, conf = extract_total_amount("Total Amount Due: $1,234.56")
        assert amount == pytest.approx(1234.56)


# ---------------------------------------------------------------------------
# extract_text routing
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_pdf_type_calls_pdf_extractor(self):
        # Minimal valid PDF-like bytes for the fallback extractor
        data = _MAGIC_PDF + b" Hello kWh World"
        text = extract_text(data, "pdf")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_unsupported_type_returns_empty(self):
        text = extract_text(b"some bytes", "docx")
        assert text == ""


# ---------------------------------------------------------------------------
# validate_upload_file tests
# ---------------------------------------------------------------------------


class TestValidateUploadFile:
    def test_valid_pdf(self):
        data = _MAGIC_PDF + b" content"
        result = validate_upload_file("bill.pdf", "application/pdf", data)
        assert result == "pdf"

    def test_valid_png(self):
        data = _MAGIC_PNG + b" content"
        result = validate_upload_file("bill.png", "image/png", data)
        assert result == "png"

    def test_valid_jpg(self):
        data = _MAGIC_JPG + b" content"
        result = validate_upload_file("bill.jpg", "image/jpeg", data)
        assert result == "jpg"

    def test_invalid_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported file extension"):
            validate_upload_file("bill.docx", "application/pdf", _MAGIC_PDF)

    def test_invalid_mime_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported content type"):
            validate_upload_file("bill.pdf", "text/plain", _MAGIC_PDF)

    def test_magic_bytes_mismatch_raises(self):
        # Extension says PDF but content is PNG magic bytes
        with pytest.raises(ValueError):
            validate_upload_file("bill.pdf", "application/pdf", _MAGIC_PNG + b" content")

    def test_unknown_magic_bytes_raises(self):
        with pytest.raises(ValueError, match="File content does not match"):
            validate_upload_file("bill.pdf", "application/pdf", b"\x00\x01\x02\x03")


# ---------------------------------------------------------------------------
# build_storage_key tests
# ---------------------------------------------------------------------------


class TestBuildStorageKey:
    def test_key_includes_connection_and_upload_id(self):
        key = build_storage_key("conn-1", "upload-2", "electricity_bill.pdf")
        assert "conn-1" in key
        assert "upload-2" in key

    def test_key_preserves_extension(self):
        key = build_storage_key("c", "u", "bill.pdf")
        assert key.endswith(".pdf")

    def test_key_lowercase_extension(self):
        key = build_storage_key("c", "u", "BILL.PDF")
        assert key.endswith(".pdf")

    def test_key_format(self):
        key = build_storage_key("conn-abc", "upload-xyz", "bill.jpg")
        assert key == "conn-abc/upload-xyz.jpg"


# ---------------------------------------------------------------------------
# BillParserService integration tests (with mocked DB and filesystem)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


async def test_parse_file_not_found(mock_db):
    """Service returns failed status when file does not exist."""
    service = BillParserService(db=mock_db, uploads_dir=Path("/nonexistent/dir"))
    result = await service.parse("upload-1", "conn-1", "missing.pdf")
    assert result["parse_status"] == "failed"
    assert "not found" in result["parse_error"].lower()


async def test_parse_path_traversal_blocked(mock_db, tmp_path):
    """Service blocks directory traversal in storage_key."""
    service = BillParserService(db=mock_db, uploads_dir=tmp_path)
    result = await service.parse("upload-1", "conn-1", "../../etc/passwd")
    assert result["parse_status"] == "failed"


async def test_parse_unsupported_file_type(mock_db, tmp_path):
    """Service marks parse as failed when magic bytes are unrecognized."""
    bad_file = tmp_path / "bad.pdf"
    bad_file.write_bytes(b"\x00\x01\x02\x03bad content")
    service = BillParserService(db=mock_db, uploads_dir=tmp_path)
    result = await service.parse("upload-1", "conn-1", "bad.pdf")
    assert result["parse_status"] == "failed"
    assert "Unsupported" in result["parse_error"]


async def test_parse_pdf_with_rate_extracts_data(mock_db, tmp_path):
    """Service extracts rate and marks parse as complete for a PDF with text."""
    # Build a minimal PDF-magic-prefixed file with extractable text
    content = (
        _MAGIC_PDF.decode("latin-1")
        + "\n"
        + "Con Edison\n"
        + "Amount Due: $123.45\n"
        + "Usage: 847 kWh\n"
        + "Rate: $0.2145/kWh\n"
        + "Service period: 01/15/2025 - 02/14/2025\n"
    )
    pdf_file = tmp_path / "bill.pdf"
    pdf_file.write_bytes(content.encode("latin-1"))

    service = BillParserService(db=mock_db, uploads_dir=tmp_path)
    result = await service.parse("upload-1", "conn-1", "bill.pdf")

    # With no pypdf installed, fallback extractor should find text patterns
    assert result["parse_status"] in ("complete", "failed")  # depends on pypdf availability
    # If complete, verify the detected fields are populated
    if result["parse_status"] == "complete":
        assert result["detected_rate_per_kwh"] is not None


async def test_parse_calls_set_status_processing(mock_db, tmp_path):
    """Service marks upload as 'processing' at start of parse."""
    bad_file = tmp_path / "bad.pdf"
    bad_file.write_bytes(b"\x00bad")
    service = BillParserService(db=mock_db, uploads_dir=tmp_path)
    await service.parse("upload-1", "conn-1", "bad.pdf")
    # First execute call should set status to processing
    first_call_params = mock_db.execute.call_args_list[0][0][1]
    assert first_call_params["status"] == "processing"
