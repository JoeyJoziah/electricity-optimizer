"""
Tests for email attachment download and parsing pipeline.

Coverage:
  - download_gmail_attachments: fetches message metadata, decodes base64url attachment data
  - download_gmail_attachments: filters non-PDF/image MIME types
  - download_gmail_attachments: caps at 5 attachments
  - download_gmail_attachments: skips attachments whose download request fails
  - download_gmail_attachments: skips parts without an attachmentId
  - download_gmail_attachments: handles nested (multipart) message parts
  - download_outlook_attachments: fetches attachments collection from Graph API
  - download_outlook_attachments: filters non-PDF/image MIME types
  - download_outlook_attachments: caps at 5 attachments
  - download_outlook_attachments: skips items with missing contentBytes
  - download_outlook_attachments: strips MIME type parameters (e.g. charset)
  - extract_rates_from_attachments: calls bill_parser and assembles result dicts
  - extract_rates_from_attachments: skips attachments with empty data
  - extract_rates_from_attachments: skips attachments whose magic bytes mismatch
  - extract_rates_from_attachments: skips attachments whose text body is blank
  - extract_rates_from_attachments: only includes fields with sufficient confidence
  - extract_rates_from_attachments: recovers gracefully when bill_parser raises
  - extract_rates_from_attachments: handles multiple attachments independently
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — minimal valid magic bytes for each supported type
# ---------------------------------------------------------------------------

_PDF_MAGIC = b"%PDF-1.4 fake pdf content with rate 0.1234 per kWh"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
_JPG_MAGIC = b"\xff\xd8\xff" + b"\x00" * 20


def _b64url(data: bytes) -> str:
    """Return standard base64url string (no padding) — matches Gmail API format."""
    return base64.urlsafe_b64encode(data).decode()


def _b64std(data: bytes) -> str:
    """Return standard base64 string — matches Outlook/Graph API format."""
    return base64.b64encode(data).decode()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_gmail_msg_resp(parts: list) -> dict:
    """Build a minimal Gmail API messages.get (format=full) response."""
    return {"payload": {"mimeType": "multipart/mixed", "parts": parts}}


def _make_gmail_part(filename: str, mime_type: str, attachment_id: str) -> dict:
    return {
        "filename": filename,
        "mimeType": mime_type,
        "body": {"attachmentId": attachment_id, "size": 1024},
        "parts": [],
    }


def _make_outlook_attachment(name: str, content_type: str, data: bytes) -> dict:
    return {
        "name": name,
        "contentType": content_type,
        "contentBytes": _b64std(data),
    }


# ===========================================================================
# download_gmail_attachments
# ===========================================================================


class TestDownloadGmailAttachments:
    """Unit tests for download_gmail_attachments()."""

    async def test_downloads_pdf_attachment_and_decodes_base64url(self):
        """Happy path: one PDF attachment returned with decoded bytes."""
        from services.email_scanner_service import download_gmail_attachments

        pdf_bytes = _PDF_MAGIC
        encoded = _b64url(pdf_bytes)

        msg_resp = MagicMock()
        msg_resp.raise_for_status = MagicMock()
        msg_resp.json.return_value = _make_gmail_msg_resp(
            [
                _make_gmail_part("bill.pdf", "application/pdf", "att-001"),
            ]
        )

        att_resp = MagicMock()
        att_resp.raise_for_status = MagicMock()
        att_resp.json.return_value = {"data": encoded}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[msg_resp, att_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token-abc", "msg-111")

        assert len(results) == 1
        assert results[0]["filename"] == "bill.pdf"
        assert results[0]["mime_type"] == "application/pdf"
        # base64url decode should reproduce original bytes
        assert results[0]["data"] == pdf_bytes

    async def test_downloads_png_and_jpeg_attachments(self):
        """PNG and JPEG MIME types are both accepted."""
        from services.email_scanner_service import download_gmail_attachments

        png_encoded = _b64url(_PNG_MAGIC)
        jpg_encoded = _b64url(_JPG_MAGIC)

        msg_resp = MagicMock()
        msg_resp.raise_for_status = MagicMock()
        msg_resp.json.return_value = _make_gmail_msg_resp(
            [
                _make_gmail_part("scan.png", "image/png", "att-png"),
                _make_gmail_part("scan.jpg", "image/jpeg", "att-jpg"),
            ]
        )

        png_resp = MagicMock()
        png_resp.raise_for_status = MagicMock()
        png_resp.json.return_value = {"data": png_encoded}

        jpg_resp = MagicMock()
        jpg_resp.raise_for_status = MagicMock()
        jpg_resp.json.return_value = {"data": jpg_encoded}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[msg_resp, png_resp, jpg_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token-abc", "msg-222")

        assert len(results) == 2
        mime_types = {r["mime_type"] for r in results}
        assert "image/png" in mime_types
        assert "image/jpeg" in mime_types

    async def test_filters_out_non_pdf_image_mime_types(self):
        """Parts with disallowed MIME types (e.g. text/html) are not downloaded."""
        from services.email_scanner_service import download_gmail_attachments

        msg_resp = MagicMock()
        msg_resp.raise_for_status = MagicMock()
        msg_resp.json.return_value = _make_gmail_msg_resp(
            [
                _make_gmail_part("bill.pdf", "application/pdf", "att-001"),
                _make_gmail_part(
                    "letter.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "att-002",
                ),
                _make_gmail_part("inline.html", "text/html", "att-003"),
                _make_gmail_part("note.txt", "text/plain", "att-004"),
            ]
        )

        att_resp = MagicMock()
        att_resp.raise_for_status = MagicMock()
        att_resp.json.return_value = {"data": _b64url(_PDF_MAGIC)}

        mock_client = AsyncMock()
        # Only the PDF part passes the filter, so only 2 HTTP calls total
        mock_client.get = AsyncMock(side_effect=[msg_resp, att_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token-abc", "msg-333")

        assert len(results) == 1
        assert results[0]["mime_type"] == "application/pdf"

    async def test_caps_at_five_attachments(self):
        """At most 5 attachments are downloaded even when more exist."""
        from services.email_scanner_service import download_gmail_attachments

        parts = [
            _make_gmail_part(f"bill{i}.pdf", "application/pdf", f"att-{i:03d}") for i in range(8)
        ]

        msg_resp = MagicMock()
        msg_resp.raise_for_status = MagicMock()
        msg_resp.json.return_value = _make_gmail_msg_resp(parts)

        # Provide 5 download responses (one per allowed attachment)
        att_responses = []
        for _ in range(5):
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.json.return_value = {"data": _b64url(_PDF_MAGIC)}
            att_responses.append(r)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[msg_resp, *att_responses])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token-abc", "msg-444")

        assert len(results) == 5
        # Total calls: 1 metadata + 5 attachment downloads
        assert mock_client.get.call_count == 6

    async def test_skips_failed_attachment_downloads_gracefully(self):
        """If an attachment download raises an exception, it is skipped silently."""
        from services.email_scanner_service import download_gmail_attachments

        msg_resp = MagicMock()
        msg_resp.raise_for_status = MagicMock()
        msg_resp.json.return_value = _make_gmail_msg_resp(
            [
                _make_gmail_part("good.pdf", "application/pdf", "att-good"),
                _make_gmail_part("bad.pdf", "application/pdf", "att-bad"),
            ]
        )

        good_att_resp = MagicMock()
        good_att_resp.raise_for_status = MagicMock()
        good_att_resp.json.return_value = {"data": _b64url(_PDF_MAGIC)}

        bad_att_resp = MagicMock()
        bad_att_resp.raise_for_status = MagicMock(side_effect=Exception("network error"))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[msg_resp, good_att_resp, bad_att_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token-abc", "msg-555")

        # Only the good attachment is returned; no exception propagated
        assert len(results) == 1
        assert results[0]["filename"] == "good.pdf"

    async def test_skips_parts_without_attachment_id(self):
        """Parts that have a filename but no attachmentId are ignored (inline content)."""
        from services.email_scanner_service import download_gmail_attachments

        # Inline part: filename set but no attachmentId in body
        inline_part = {
            "filename": "inline.pdf",
            "mimeType": "application/pdf",
            "body": {"size": 512},  # No attachmentId key
            "parts": [],
        }
        real_part = _make_gmail_part("real.pdf", "application/pdf", "att-real")

        msg_resp = MagicMock()
        msg_resp.raise_for_status = MagicMock()
        msg_resp.json.return_value = _make_gmail_msg_resp([inline_part, real_part])

        att_resp = MagicMock()
        att_resp.raise_for_status = MagicMock()
        att_resp.json.return_value = {"data": _b64url(_PDF_MAGIC)}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[msg_resp, att_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token-abc", "msg-666")

        assert len(results) == 1
        assert results[0]["filename"] == "real.pdf"

    async def test_handles_nested_multipart_parts(self):
        """Deeply nested parts (multipart/related inside multipart/mixed) are collected."""
        from services.email_scanner_service import download_gmail_attachments

        inner_part = _make_gmail_part("nested.pdf", "application/pdf", "att-nested")
        outer_part = {
            "filename": "",
            "mimeType": "multipart/related",
            "body": {},
            "parts": [inner_part],
        }

        msg_resp = MagicMock()
        msg_resp.raise_for_status = MagicMock()
        msg_resp.json.return_value = _make_gmail_msg_resp([outer_part])

        att_resp = MagicMock()
        att_resp.raise_for_status = MagicMock()
        att_resp.json.return_value = {"data": _b64url(_PDF_MAGIC)}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[msg_resp, att_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token-abc", "msg-777")

        assert len(results) == 1
        assert results[0]["filename"] == "nested.pdf"

    async def test_returns_empty_list_when_no_attachments(self):
        """Message with no parts returns empty list without extra HTTP calls."""
        from services.email_scanner_service import download_gmail_attachments

        msg_resp = MagicMock()
        msg_resp.raise_for_status = MagicMock()
        msg_resp.json.return_value = _make_gmail_msg_resp([])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=msg_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token-abc", "msg-888")

        assert results == []
        # Only the metadata call is made
        assert mock_client.get.call_count == 1

    async def test_image_jpg_mime_type_accepted(self):
        """image/jpg (non-standard) is accepted in addition to image/jpeg."""
        from services.email_scanner_service import download_gmail_attachments

        msg_resp = MagicMock()
        msg_resp.raise_for_status = MagicMock()
        msg_resp.json.return_value = _make_gmail_msg_resp(
            [
                _make_gmail_part("scan.jpg", "image/jpg", "att-jpg"),
            ]
        )

        att_resp = MagicMock()
        att_resp.raise_for_status = MagicMock()
        att_resp.json.return_value = {"data": _b64url(_JPG_MAGIC)}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[msg_resp, att_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_gmail_attachments("token-abc", "msg-999")

        assert len(results) == 1
        assert results[0]["mime_type"] == "image/jpg"


# ===========================================================================
# download_outlook_attachments
# ===========================================================================


class TestDownloadOutlookAttachments:
    """Unit tests for download_outlook_attachments()."""

    async def test_downloads_pdf_attachment_and_decodes_base64(self):
        """Happy path: one PDF attachment from Graph API, decoded correctly."""
        from services.email_scanner_service import download_outlook_attachments

        pdf_bytes = _PDF_MAGIC

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "value": [_make_outlook_attachment("bill.pdf", "application/pdf", pdf_bytes)]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token-xyz", "msg-o-111")

        assert len(results) == 1
        assert results[0]["filename"] == "bill.pdf"
        assert results[0]["mime_type"] == "application/pdf"
        assert results[0]["data"] == pdf_bytes

    async def test_accepts_png_and_jpeg_mime_types(self):
        """image/png and image/jpeg are both accepted from Outlook."""
        from services.email_scanner_service import download_outlook_attachments

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "value": [
                _make_outlook_attachment("photo.png", "image/png", _PNG_MAGIC),
                _make_outlook_attachment("photo.jpeg", "image/jpeg", _JPG_MAGIC),
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token-xyz", "msg-o-222")

        assert len(results) == 2
        mime_types = {r["mime_type"] for r in results}
        assert "image/png" in mime_types
        assert "image/jpeg" in mime_types

    async def test_filters_out_non_pdf_image_mime_types(self):
        """Word documents and plain text are filtered out."""
        from services.email_scanner_service import download_outlook_attachments

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "value": [
                _make_outlook_attachment("bill.pdf", "application/pdf", _PDF_MAGIC),
                _make_outlook_attachment("letter.docx", "application/msword", b"PK\x03\x04"),
                _make_outlook_attachment("note.txt", "text/plain", b"hello"),
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token-xyz", "msg-o-333")

        assert len(results) == 1
        assert results[0]["mime_type"] == "application/pdf"

    async def test_caps_at_five_attachments(self):
        """Only first 5 attachments are processed even when API returns more."""
        from services.email_scanner_service import download_outlook_attachments

        attachments = [
            _make_outlook_attachment(f"bill{i}.pdf", "application/pdf", _PDF_MAGIC)
            for i in range(8)
        ]

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"value": attachments}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token-xyz", "msg-o-444")

        assert len(results) == 5

    async def test_skips_items_with_missing_content_bytes(self):
        """Attachments that have no contentBytes are skipped silently."""
        from services.email_scanner_service import download_outlook_attachments

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "value": [
                {"name": "empty.pdf", "contentType": "application/pdf", "contentBytes": ""},
                _make_outlook_attachment("real.pdf", "application/pdf", _PDF_MAGIC),
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token-xyz", "msg-o-555")

        assert len(results) == 1
        assert results[0]["filename"] == "real.pdf"

    async def test_strips_mime_type_parameters(self):
        """Content-Type values like 'application/pdf; name=bill.pdf' are normalised."""
        from services.email_scanner_service import download_outlook_attachments

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "value": [
                {
                    "name": "bill.pdf",
                    "contentType": "application/pdf; name=bill.pdf",
                    "contentBytes": _b64std(_PDF_MAGIC),
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token-xyz", "msg-o-666")

        assert len(results) == 1
        # MIME type should be stripped to just the type/subtype part
        assert results[0]["mime_type"] == "application/pdf"

    async def test_returns_empty_list_when_no_attachments(self):
        """Message with no attachments returns empty list."""
        from services.email_scanner_service import download_outlook_attachments

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"value": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token-xyz", "msg-o-777")

        assert results == []

    async def test_skips_corrupted_base64_gracefully(self):
        """Malformed base64 in contentBytes is caught; other attachments are returned."""
        from services.email_scanner_service import download_outlook_attachments

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "value": [
                {
                    "name": "corrupt.pdf",
                    "contentType": "application/pdf",
                    "contentBytes": "!!!NOT_VALID_BASE64!!!",
                },
                _make_outlook_attachment("good.pdf", "application/pdf", _PDF_MAGIC),
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.email_scanner_service.httpx.AsyncClient", return_value=mock_client):
            results = await download_outlook_attachments("token-xyz", "msg-o-888")

        assert len(results) == 1
        assert results[0]["filename"] == "good.pdf"


# ===========================================================================
# extract_rates_from_attachments
# ===========================================================================


class TestExtractRatesFromAttachments:
    """Unit tests for extract_rates_from_attachments()."""

    def _make_attachment(
        self,
        filename: str = "bill.pdf",
        data: bytes = _PDF_MAGIC,
        mime_type: str = "application/pdf",
    ) -> dict:
        return {"filename": filename, "data": data, "mime_type": mime_type}

    def _bill_parser_patches(
        self,
        magic_type: str = "pdf",
        text_body: str = "Rate: 0.1245/kWh  Usage: 850 kWh  Total: $105.83  Eversource Energy",
        rate: tuple = (0.1245, 0.9),
        supplier: tuple = ("Eversource Energy", 0.8),
        period: tuple = ("2025-01-01", "2025-01-31", 0.7),
        total_kwh: tuple = (850.0, 0.8),
        total_amount: tuple = (105.83, 0.9),
    ):
        """Return a dict of patch targets mapped to their return values."""
        return {
            "services.email_scanner_service.extract_text": MagicMock(return_value=text_body),
            "services.email_scanner_service.extract_rate_per_kwh": MagicMock(return_value=rate),
            "services.email_scanner_service.extract_supplier": MagicMock(return_value=supplier),
            "services.email_scanner_service.extract_billing_period": MagicMock(return_value=period),
            "services.email_scanner_service.extract_total_kwh": MagicMock(return_value=total_kwh),
            "services.email_scanner_service.extract_total_amount": MagicMock(
                return_value=total_amount
            ),
            "services.email_scanner_service._validate_magic_bytes": MagicMock(
                return_value=magic_type
            ),
        }

    async def test_extracts_all_fields_from_pdf_attachment(self):
        """Full extraction pipeline: all bill_parser fields populated."""
        from services.email_scanner_service import extract_rates_from_attachments

        att = self._make_attachment()
        patches = self._bill_parser_patches()

        # Patch the lazily-imported names at the service module level
        with (
            patch(
                "services.bill_parser.extract_text",
                patches["services.email_scanner_service.extract_text"],
            ),
            patch(
                "services.bill_parser.extract_rate_per_kwh",
                patches["services.email_scanner_service.extract_rate_per_kwh"],
            ),
            patch(
                "services.bill_parser.extract_supplier",
                patches["services.email_scanner_service.extract_supplier"],
            ),
            patch(
                "services.bill_parser.extract_billing_period",
                patches["services.email_scanner_service.extract_billing_period"],
            ),
            patch(
                "services.bill_parser.extract_total_kwh",
                patches["services.email_scanner_service.extract_total_kwh"],
            ),
            patch(
                "services.bill_parser.extract_total_amount",
                patches["services.email_scanner_service.extract_total_amount"],
            ),
            patch(
                "services.bill_parser._validate_magic_bytes",
                patches["services.email_scanner_service._validate_magic_bytes"],
            ),
        ):
            results = await extract_rates_from_attachments([att])

        assert len(results) == 1
        r = results[0]
        assert r["filename"] == "bill.pdf"
        assert r["rate_per_kwh"] == pytest.approx(0.1245)
        assert r["supplier"] == "Eversource Energy"
        assert r["billing_period_start"] == "2025-01-01"
        assert r["billing_period_end"] == "2025-01-31"
        assert r["total_kwh"] == pytest.approx(850.0)
        assert r["total_amount"] == pytest.approx(105.83)

    async def test_skips_attachment_with_empty_data(self):
        """An attachment dict with empty bytes is skipped without crashing."""
        from services.email_scanner_service import extract_rates_from_attachments

        att = self._make_attachment(data=b"")
        results = await extract_rates_from_attachments([att])

        assert results == []

    async def test_skips_attachment_when_magic_bytes_mismatch(self):
        """If _validate_magic_bytes returns None and MIME type yields no type, skip."""
        from services.email_scanner_service import extract_rates_from_attachments

        # Data is not a valid PDF/PNG/JPG magic bytes sequence
        garbage_data = b"\x00\x01\x02\x03garbage"
        att = {
            "filename": "garbage.bin",
            "data": garbage_data,
            "mime_type": "application/octet-stream",  # Not in _ALLOWED_MIME for extraction
        }

        # _validate_magic_bytes returns None for unrecognized data; MIME maps to "" → skip
        with patch("services.bill_parser._validate_magic_bytes", return_value=None):
            results = await extract_rates_from_attachments([att])

        assert results == []

    async def test_skips_attachment_when_extracted_text_is_blank(self):
        """When extract_text returns only whitespace the attachment is skipped."""
        from services.email_scanner_service import extract_rates_from_attachments

        att = self._make_attachment()

        with (
            patch("services.bill_parser._validate_magic_bytes", return_value="pdf"),
            patch("services.bill_parser.extract_text", return_value="   \n  "),
        ):
            results = await extract_rates_from_attachments([att])

        assert results == []

    async def test_omits_rate_when_confidence_below_threshold(self):
        """rate_per_kwh is omitted when confidence < 0.5."""
        from services.email_scanner_service import extract_rates_from_attachments

        att = self._make_attachment()

        with (
            patch("services.bill_parser._validate_magic_bytes", return_value="pdf"),
            patch("services.bill_parser.extract_text", return_value="some text"),
            patch("services.bill_parser.extract_rate_per_kwh", return_value=(0.15, 0.3)),
            patch("services.bill_parser.extract_supplier", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_billing_period", return_value=(None, None, 0.0)),
            patch("services.bill_parser.extract_total_kwh", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_total_amount", return_value=(None, 0.0)),
        ):
            results = await extract_rates_from_attachments([att])

        assert len(results) == 1
        assert "rate_per_kwh" not in results[0]
        assert results[0]["filename"] == "bill.pdf"

    async def test_includes_rate_at_exactly_confidence_threshold(self):
        """rate_per_kwh IS included when confidence == 0.5 (boundary case)."""
        from services.email_scanner_service import extract_rates_from_attachments

        att = self._make_attachment()

        with (
            patch("services.bill_parser._validate_magic_bytes", return_value="pdf"),
            patch("services.bill_parser.extract_text", return_value="some text"),
            patch("services.bill_parser.extract_rate_per_kwh", return_value=(0.1234, 0.5)),
            patch("services.bill_parser.extract_supplier", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_billing_period", return_value=(None, None, 0.0)),
            patch("services.bill_parser.extract_total_kwh", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_total_amount", return_value=(None, 0.0)),
        ):
            results = await extract_rates_from_attachments([att])

        assert len(results) == 1
        assert "rate_per_kwh" in results[0]
        assert results[0]["rate_per_kwh"] == pytest.approx(0.1234)

    async def test_omits_optional_fields_when_not_found(self):
        """Fields like supplier and billing period are omitted when None."""
        from services.email_scanner_service import extract_rates_from_attachments

        att = self._make_attachment()

        with (
            patch("services.bill_parser._validate_magic_bytes", return_value="pdf"),
            patch("services.bill_parser.extract_text", return_value="some text"),
            patch("services.bill_parser.extract_rate_per_kwh", return_value=(0.12, 0.8)),
            patch("services.bill_parser.extract_supplier", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_billing_period", return_value=(None, None, 0.0)),
            patch("services.bill_parser.extract_total_kwh", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_total_amount", return_value=(None, 0.0)),
        ):
            results = await extract_rates_from_attachments([att])

        r = results[0]
        assert "supplier" not in r
        assert "billing_period_start" not in r
        assert "billing_period_end" not in r
        assert "total_kwh" not in r
        assert "total_amount" not in r

    async def test_recovers_gracefully_when_bill_parser_raises(self):
        """If bill_parser raises an exception, the attachment gets a fallback result."""
        from services.email_scanner_service import extract_rates_from_attachments

        att = self._make_attachment(filename="broken.pdf")

        with (
            patch("services.bill_parser._validate_magic_bytes", return_value="pdf"),
            patch("services.bill_parser.extract_text", side_effect=RuntimeError("parser crash")),
        ):
            results = await extract_rates_from_attachments([att])

        # Fallback result has only filename, no rate fields, no exception raised
        assert len(results) == 1
        assert results[0] == {"filename": "broken.pdf"}

    async def test_handles_multiple_attachments_independently(self):
        """Each attachment is processed independently; one failure does not affect others."""
        from services.email_scanner_service import extract_rates_from_attachments

        att1 = self._make_attachment(filename="good.pdf", data=_PDF_MAGIC)
        att2 = self._make_attachment(filename="bad.pdf", data=_PDF_MAGIC)

        call_count = {"n": 0}

        def extract_text_side_effect(data, file_type):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "Rate: 0.15/kWh"
            raise RuntimeError("OCR failed on bad.pdf")

        with (
            patch("services.bill_parser._validate_magic_bytes", return_value="pdf"),
            patch("services.bill_parser.extract_text", side_effect=extract_text_side_effect),
            patch("services.bill_parser.extract_rate_per_kwh", return_value=(0.15, 0.9)),
            patch("services.bill_parser.extract_supplier", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_billing_period", return_value=(None, None, 0.0)),
            patch("services.bill_parser.extract_total_kwh", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_total_amount", return_value=(None, 0.0)),
        ):
            results = await extract_rates_from_attachments([att1, att2])

        assert len(results) == 2
        assert results[0]["filename"] == "good.pdf"
        assert results[0].get("rate_per_kwh") == pytest.approx(0.15)
        # bad.pdf got the fallback dict
        assert results[1] == {"filename": "bad.pdf"}

    async def test_processes_png_attachment(self):
        """PNG attachments are routed through the image extraction path."""
        from services.email_scanner_service import extract_rates_from_attachments

        att = self._make_attachment(filename="scan.png", data=_PNG_MAGIC, mime_type="image/png")

        with (
            patch("services.bill_parser._validate_magic_bytes", return_value="png"),
            patch(
                "services.bill_parser.extract_text", return_value="Usage: 600 kWh"
            ) as mock_extract,
            patch("services.bill_parser.extract_rate_per_kwh", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_supplier", return_value=(None, 0.0)),
            patch("services.bill_parser.extract_billing_period", return_value=(None, None, 0.0)),
            patch("services.bill_parser.extract_total_kwh", return_value=(600.0, 0.85)),
            patch("services.bill_parser.extract_total_amount", return_value=(None, 0.0)),
        ):
            results = await extract_rates_from_attachments([att])

        assert len(results) == 1
        # extract_text should be called with file_type="png"
        mock_extract.assert_called_once_with(att["data"], "png")
        assert results[0]["total_kwh"] == pytest.approx(600.0)

    async def test_returns_empty_list_for_empty_attachment_list(self):
        """No attachments input produces empty output with no bill_parser calls."""
        from services.email_scanner_service import extract_rates_from_attachments

        results = await extract_rates_from_attachments([])

        assert results == []
