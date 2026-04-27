"""
Unit tests for email_scanner_service.py

Covers bill-classifier heuristics, rate extraction from text,
attachment parsing helpers, and bulk-insert / partial-failure paths.
These tests target internal helpers and pure functions only — API-layer
coverage lives in test_email_oauth.py.
"""

import base64
from datetime import UTC, datetime
from typing import Any  # noqa: F401 — used in helper type hints
from unittest.mock import MagicMock, patch

import pytest

from services.email_scanner_service import (
    EmailScanResult,
    _extract_gmail_body_text,
    _extract_rates_from_text,
    _matches_utility_keywords,
    extract_rates_from_attachments,
)

# =============================================================================
# Fixtures
# =============================================================================


def _make_attachment(
    filename: str = "bill.pdf",
    data: bytes = b"%PDF-1.4 fake content",
    mime_type: str = "application/pdf",
) -> dict[str, Any]:
    return {"filename": filename, "data": data, "mime_type": mime_type}


# =============================================================================
# TestBillClassifier — _matches_utility_keywords
# =============================================================================


class TestBillClassifier:
    """Tests for the subject/body utility-bill heuristic."""

    @pytest.mark.parametrize(
        "text",
        [
            "Your electricity bill is ready",
            "Electric bill for November",
            "energy bill payment due",
            "Monthly statement from Eversource",
            "Your energy statement is available",
            "kWh usage this month",
            "billing statement enclosed",
            "your bill is ready for review",
            "payment due this Friday",
        ],
    )
    def test_utility_text_is_classified_as_bill(self, text: str):
        assert _matches_utility_keywords(text), f"Expected '{text}' to match as a utility bill"

    @pytest.mark.parametrize(
        "text",
        [
            "Welcome to our newsletter",
            "Your Amazon order has shipped",
            "Meeting invitation for Monday",
            "Bank statement available",
            "Gym membership renewal",
        ],
    )
    def test_non_utility_text_is_not_classified_as_bill(self, text: str):
        assert not _matches_utility_keywords(text), (
            f"Expected '{text}' NOT to match as a utility bill"
        )

    def test_empty_string_returns_false(self):
        assert not _matches_utility_keywords("")

    def test_case_insensitive_keyword_match(self):
        assert _matches_utility_keywords("ELECTRIC BILL payment")

    def test_subject_pattern_matches_utility_invoice(self):
        assert _matches_utility_keywords("Your new invoice from National Grid")

    def test_subject_pattern_matches_payment_reminder(self):
        assert _matches_utility_keywords("Payment reminder: balance due")

    def test_kwh_alone_triggers_match(self):
        assert _matches_utility_keywords("Your usage: 850 kWh this cycle")


# =============================================================================
# TestRateExtraction — _extract_rates_from_text
# =============================================================================


class TestRateExtraction:
    """Tests for rate/amount/kWh extraction via regex from email body text."""

    def test_extracts_rate_per_kwh_standard_format(self):
        text = "Energy rate: $0.1587 per kWh"
        result = _extract_rates_from_text(text)
        assert "rate_per_kwh" in result
        assert abs(result["rate_per_kwh"] - 0.1587) < 1e-6

    def test_extracts_rate_per_kwh_with_slash_separator(self):
        text = "Price: $0.2200 / kWh for this billing period"
        result = _extract_rates_from_text(text)
        assert "rate_per_kwh" in result

    def test_no_rate_in_text_returns_empty_dict(self):
        text = "Thank you for being a valued customer. See enclosed statement."
        result = _extract_rates_from_text(text)
        assert "rate_per_kwh" not in result

    def test_extracts_total_amount(self):
        text = "Total amount due: $142.50"
        result = _extract_rates_from_text(text)
        assert "total_amount" in result
        assert abs(result["total_amount"] - 142.50) < 1e-6

    def test_extracts_total_amount_with_comma_separator(self):
        # "balance" alone (without " due") matches the regex keyword set
        text = "balance: $1,234.56"
        result = _extract_rates_from_text(text)
        assert "total_amount" in result
        assert abs(result["total_amount"] - 1234.56) < 1e-6

    def test_extracts_total_kwh(self):
        text = "You used 754 kWh this month."
        result = _extract_rates_from_text(text)
        assert "total_kwh" in result
        assert result["total_kwh"] == 754.0

    def test_extracts_total_kwh_with_comma(self):
        text = "Total usage: 1,200 kilowatt-hours"
        result = _extract_rates_from_text(text)
        assert "total_kwh" in result
        assert result["total_kwh"] == 1200.0

    def test_extracts_known_supplier(self):
        text = "This bill is from Eversource Energy for service at your address."
        result = _extract_rates_from_text(text)
        assert "supplier" in result
        assert "Eversource" in result["supplier"]

    def test_extracts_pge_supplier(self):
        text = "Pacific Gas & Electric charges for period ending Oct 31."
        result = _extract_rates_from_text(text)
        assert "supplier" in result

    def test_multi_rate_text_returns_first_match(self):
        # Two rate patterns in same text — service should return the first match
        text = "Rate: $0.15 per kWh (on-peak). Off-peak rate: $0.09 per kWh"
        result = _extract_rates_from_text(text)
        assert "rate_per_kwh" in result
        assert abs(result["rate_per_kwh"] - 0.15) < 1e-6

    def test_misformatted_rate_not_extracted(self):
        # No decimal component — won't match the [\d]+\.[\d]{2,4} pattern
        text = "Flat charge $15 total"
        result = _extract_rates_from_text(text)
        # Should not contain rate_per_kwh (no kWh unit following a decimal price)
        assert "rate_per_kwh" not in result

    def test_all_fields_extracted_from_rich_text(self):
        text = (
            "Eversource Energy — Monthly Statement\n"
            "Rate: $0.2150 per kWh\n"
            "Usage: 630 kWh\n"
            "Total: $135.45\n"
        )
        result = _extract_rates_from_text(text)
        assert "rate_per_kwh" in result
        assert "total_kwh" in result
        assert "total_amount" in result
        assert "supplier" in result


# =============================================================================
# TestGmailBodyExtraction — _extract_gmail_body_text
# =============================================================================


class TestGmailBodyExtraction:
    """Tests for Gmail payload body text extraction."""

    def _b64(self, text: str) -> str:
        return base64.urlsafe_b64encode(text.encode()).decode()

    def test_extracts_direct_text_plain_body(self):
        payload = {
            "mimeType": "text/plain",
            "body": {"data": self._b64("Your bill is $50.00")},
        }
        result = _extract_gmail_body_text(payload)
        assert result == "Your bill is $50.00"

    def test_extracts_from_parts(self):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": self._b64("Bill text here")},
                }
            ],
        }
        result = _extract_gmail_body_text(payload)
        assert result == "Bill text here"

    def test_returns_empty_string_when_no_text_part(self):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/html", "body": {"data": self._b64("<html>hi</html>")}},
            ],
        }
        result = _extract_gmail_body_text(payload)
        assert result == ""

    def test_recurses_into_nested_parts(self):
        inner_text = "Nested bill content"
        payload = {
            "mimeType": "multipart/related",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": self._b64(inner_text)},
                        }
                    ],
                }
            ],
        }
        result = _extract_gmail_body_text(payload)
        assert result == inner_text

    def test_missing_body_data_returns_empty(self):
        payload = {"mimeType": "text/plain", "body": {}}
        result = _extract_gmail_body_text(payload)
        assert result == ""


# =============================================================================
# TestAttachmentParsing — extract_rates_from_attachments
# =============================================================================


class TestAttachmentParsing:
    """Tests for the attachment extraction pipeline."""

    async def test_empty_attachment_list_returns_empty(self):
        result = await extract_rates_from_attachments([])
        assert result == []

    async def test_skips_attachment_with_no_data(self):
        att = {"filename": "bill.pdf", "data": b"", "mime_type": "application/pdf"}
        result = await extract_rates_from_attachments([att])
        assert result == []

    async def test_non_pdf_image_with_no_detected_type_is_skipped(self):
        """
        A text/plain attachment should be silently skipped — mime_type is not
        in the allowed set and _validate_magic_bytes won't produce a recognised type.
        """
        att = {
            "filename": "readme.txt",
            "data": b"Some text content",
            "mime_type": "text/plain",
        }
        # The service internally maps mime types; text/plain has no mapping and
        # _validate_magic_bytes returns None for arbitrary bytes, so file_type
        # ends up empty and the item is skipped.
        with patch("services.bill_parser._validate_magic_bytes", return_value=None):
            result = await extract_rates_from_attachments([att])
        assert result == [], "text/plain attachment must not produce an extraction result"

    async def test_pdf_exception_yields_filename_only_entry(self):
        """
        When bill_parser raises on a PDF, the service should NOT crash —
        it appends a stub dict with filename only (regression: partial-failure resilience).
        """
        pdf_bytes = b"%PDF-1.4 truncated"
        att = _make_attachment(data=pdf_bytes)

        mock_validate = MagicMock(return_value="pdf")
        mock_extract_text = MagicMock(side_effect=Exception("corrupt PDF"))

        with (
            patch(
                "services.email_scanner_service.extract_rates_from_attachments",
                wraps=extract_rates_from_attachments,
            ),
            patch(
                "services.bill_parser._validate_magic_bytes",
                mock_validate,
            ),
            patch(
                "services.bill_parser.extract_text",
                mock_extract_text,
            ),
        ):
            result = await extract_rates_from_attachments([att])

        # The result should contain a stub entry (filename only), not raise
        assert any(r.get("filename") == "bill.pdf" for r in result)

    async def test_pdf_with_empty_text_body_is_skipped(self):
        """extract_rates_from_attachments skips attachments whose extracted text is blank."""
        pdf_bytes = b"%PDF-1.4 empty"
        att = _make_attachment(data=pdf_bytes)

        with (
            patch("services.bill_parser._validate_magic_bytes", return_value="pdf"),
            patch("services.bill_parser.extract_text", return_value="   "),
        ):
            result = await extract_rates_from_attachments([att])

        assert result == [], "Empty-text PDF should produce no result entry"


# =============================================================================
# TestEmailScanResult
# =============================================================================


class TestEmailScanResult:
    """Tests for the EmailScanResult data container."""

    def test_to_dict_contains_required_keys(self):
        result = EmailScanResult(
            email_id="msg_001",
            subject="Your electricity bill",
            sender="billing@eversource.com",
            date=datetime(2026, 3, 1, tzinfo=UTC),
            is_utility_bill=True,
            attachment_count=1,
        )
        d = result.to_dict()
        assert d["email_id"] == "msg_001"
        assert d["is_utility_bill"] is True
        assert d["attachment_count"] == 1
        assert "date" in d

    def test_extracted_data_defaults_to_empty_dict(self):
        result = EmailScanResult(
            email_id="x",
            subject="",
            sender="",
            date=datetime.now(UTC),
        )
        assert result.extracted_data == {}

    def test_is_utility_bill_defaults_to_false(self):
        result = EmailScanResult(
            email_id="x",
            subject="Hello",
            sender="nobody@nowhere.com",
            date=datetime.now(UTC),
        )
        assert result.is_utility_bill is False
