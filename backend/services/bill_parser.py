"""
Bill Parser Service — Phase 2

Reads an uploaded bill file from local storage and uses regex heuristics to
extract key fields: rate per kWh, supplier name, billing period, total usage,
and total amount charged.  Each extracted field carries a confidence score
(0.0–1.0) indicating how reliable the extraction is.

Supported file types:
  - PDF  : text is extracted via the ``pypdf`` package when available; falls
            back to a plain-bytes scan so the service degrades gracefully.
  - Image (PNG / JPG): text content is read as raw bytes and searched for
            ASCII-printable strings; for production OCR quality, install
            ``pytesseract`` + Tesseract (not required for MVP).

After extraction the service:
  1. Updates the ``bill_uploads`` row with detected_* columns and
     parse_status = 'complete' or 'failed'.
  2. Inserts a row into ``connection_extracted_rates`` when a rate was found
     with confidence >= 0.5.

All DB writes use raw SQL with ``sqlalchemy.text()`` to follow the project
convention.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Magic bytes for supported file types
# ---------------------------------------------------------------------------

_MAGIC_PDF = b"%PDF"
_MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
_MAGIC_JPG = b"\xff\xd8\xff"

ALLOWED_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg"}
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# Maximum file size: 10 MB
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Known utility supplier name fragments (case-insensitive scan)
# ---------------------------------------------------------------------------

_KNOWN_SUPPLIERS = [
    "Eversource",
    "United Illuminating",
    "Avangrid",
    "National Grid",
    "NextEra Energy",
    "Duke Energy",
    "Pacific Gas",
    "Con Edison",
    "ConEdison",
    "Southern California Edison",
    "Xcel Energy",
    "Dominion Energy",
    "Ameren",
    "Entergy",
    "Evergy",
    "PSEG",
    "PPL Electric",
    "AEP",
    "First Energy",
    "FirstEnergy",
    "Exelon",
    "Commonwealth Edison",
    "ComEd",
    "Pepco",
    "Delmarva Power",
    "Atlantic City Electric",
    "Green Mountain Power",
    "Central Vermont",
    "Emera Maine",
    "Versant Power",
]


# ---------------------------------------------------------------------------
# Regex patterns for field extraction
# ---------------------------------------------------------------------------

# Rate per kWh — matches patterns such as:
#   "$0.2145/kWh", "21.45 cents per kWh", "0.2145 $/kWh", "21.45¢/kWh"
_RATE_PATTERNS = [
    # Dollar-per-kWh: "$0.2145/kWh" or "0.2145 $/kWh"
    re.compile(
        r"\$?\s*(0\.\d{2,6})\s*/?\s*k[Ww][Hh]",
        re.IGNORECASE,
    ),
    # Cents-per-kWh: "21.45 cents/kWh" or "21.45¢/kWh"
    re.compile(
        r"(\d{1,2}(?:\.\d{1,4})?)\s*(?:cents?|¢)\s*/?\s*k[Ww][Hh]",
        re.IGNORECASE,
    ),
    # Dollar rate with label: "Energy Charge 0.2145 per kWh"
    re.compile(
        r"(?:energy|supply|generation|distribution)\s+charge\s+\$?\s*(0\.\d{2,6})\s+per\s+k[Ww][Hh]",
        re.IGNORECASE,
    ),
    # Generic "X.XXXX per kWh"
    re.compile(
        r"(0\.\d{2,6})\s+per\s+k[Ww][Hh]",
        re.IGNORECASE,
    ),
]

# Total kWh usage: "Usage: 847 kWh" or "847 kWh used"
_KWH_USAGE_PATTERNS = [
    re.compile(
        r"(?:usage|consumption|used|total\s+usage)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*k[Ww][Hh]",
        re.IGNORECASE,
    ),
    re.compile(
        r"([\d,]+(?:\.\d+)?)\s*k[Ww][Hh]\s+(?:used|consumed|billed)",
        re.IGNORECASE,
    ),
    re.compile(
        r"k[Ww][Hh]\s+used\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        re.IGNORECASE,
    ),
]

# Total amount: "Total Amount Due: $123.45" or "Amount Due $123.45"
_AMOUNT_PATTERNS = [
    re.compile(
        r"(?:total\s+)?amount\s+due\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:total\s+)?balance\s+due\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"please\s+pay\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"total\s+charges?\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})",
        re.IGNORECASE,
    ),
]

# Billing period: various date range formats
_DATE_PATTERNS = [
    # "01/15/2025 - 02/14/2025" or "01/15/2025 to 02/14/2025"
    re.compile(
        r"(\d{1,2}/\d{1,2}/\d{4})\s*(?:-|to|through)\s*(\d{1,2}/\d{1,2}/\d{4})",
        re.IGNORECASE,
    ),
    # "Jan 15, 2025 - Feb 14, 2025"
    re.compile(
        r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\s*(?:-|to|through)\s*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    ),
    # "2025-01-15 to 2025-02-14" ISO
    re.compile(
        r"(\d{4}-\d{2}-\d{2})\s*(?:-|to|through)\s*(\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    ),
    # "Service From: 01/15/2025 To: 02/14/2025"
    re.compile(
        r"(?:service\s+from|billing\s+period\s+from|from)\s*[:\-]?\s*"
        r"(\d{1,2}/\d{1,2}/\d{4})\s*(?:to|through|-)\s*(\d{1,2}/\d{1,2}/\d{4})",
        re.IGNORECASE,
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date_flexible(raw: str) -> Optional[str]:
    """Parse a date string in several common formats, returning ISO YYYY-MM-DD."""
    raw = raw.strip().rstrip(",")
    formats = [
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%B %d %Y",
        "%b %d %Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _strip_commas(value: str) -> str:
    return value.replace(",", "")


def _validate_magic_bytes(data: bytes) -> Optional[str]:
    """
    Return the detected file type based on magic bytes, or None if unsupported.

    Returns one of: 'pdf', 'png', 'jpg'
    """
    if data[:4] == _MAGIC_PDF:
        return "pdf"
    if data[:8] == _MAGIC_PNG:
        return "png"
    if data[:3] == _MAGIC_JPG:
        return "jpg"
    return None


# ---------------------------------------------------------------------------
# Text extraction from file bytes
# ---------------------------------------------------------------------------


def _extract_text_from_pdf(data: bytes) -> str:
    """
    Extract text from PDF bytes.

    Tries ``pypdf`` first (optional dependency); if not installed, falls back
    to a simple ASCII printable extraction from the raw PDF byte stream (good
    enough for text-based PDFs — scanned PDFs produce no output without OCR).
    """
    # Try pypdf (optional)
    try:
        import io
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("pypdf_extraction_failed", error=str(exc))

    # Fallback: collect ASCII printable bytes from raw stream
    # PDF streams embed text operators between BT/ET markers.
    text_chars = []
    for byte in data:
        ch = chr(byte)
        if ch.isprintable() or ch in ("\n", "\r", "\t"):
            text_chars.append(ch)
        else:
            text_chars.append(" ")
    raw_text = "".join(text_chars)
    # Collapse excessive whitespace
    raw_text = re.sub(r" {3,}", "  ", raw_text)
    return raw_text


def _extract_text_from_image(data: bytes) -> str:
    """
    Extract text from image bytes.

    Tries ``pytesseract`` (optional dependency); if not installed returns an
    empty string so the parser produces a 'failed' status with a clear message.
    """
    try:
        import io
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        image = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(image)
    except ImportError:
        return ""
    except Exception as exc:
        logger.warning("tesseract_extraction_failed", error=str(exc))
        return ""


def extract_text(data: bytes, file_type: str) -> str:
    """Route text extraction to the correct backend based on file_type."""
    if file_type == "pdf":
        return _extract_text_from_pdf(data)
    if file_type in ("png", "jpg", "jpeg"):
        return _extract_text_from_image(data)
    return ""


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------


def extract_rate_per_kwh(text_body: str) -> tuple[Optional[float], float]:
    """
    Return (rate_per_kwh, confidence) from bill text.

    Confidence:
      1.0  — matched a specific dollar-per-kWh pattern
      0.8  — matched a cents-per-kWh pattern (converted to dollars)
      0.6  — matched a generic "X.XXXX per kWh" pattern
    """
    # Patterns in priority order; first match wins
    for i, pattern in enumerate(_RATE_PATTERNS):
        m = pattern.search(text_body)
        if m:
            raw = m.group(1)
            try:
                value = float(raw)
                # Cents patterns (index 1) need division by 100
                if i == 1:
                    value = value / 100.0
                # Sanity: US electricity rates fall between $0.05 and $0.80/kWh
                if 0.05 <= value <= 0.80:
                    confidence = 1.0 if i == 0 else (0.8 if i == 1 else 0.6)
                    return round(value, 6), confidence
            except ValueError:
                continue
    return None, 0.0


def extract_supplier(text_body: str) -> tuple[Optional[str], float]:
    """
    Return (supplier_name, confidence) from bill text.

    Confidence:
      0.9  — exact known supplier name found
      0.0  — no match
    """
    text_upper = text_body.upper()
    for name in _KNOWN_SUPPLIERS:
        if name.upper() in text_upper:
            return name, 0.9
    return None, 0.0


def extract_billing_period(
    text_body: str,
) -> tuple[Optional[str], Optional[str], float]:
    """
    Return (start_date_iso, end_date_iso, confidence) from bill text.

    Confidence:
      0.85 — billing period date range found and parsed
      0.0  — not found
    """
    for pattern in _DATE_PATTERNS:
        m = pattern.search(text_body)
        if m:
            start_raw, end_raw = m.group(1), m.group(2)
            start = _parse_date_flexible(start_raw)
            end = _parse_date_flexible(end_raw)
            if start and end:
                return start, end, 0.85
    return None, None, 0.0


def extract_total_kwh(text_body: str) -> tuple[Optional[float], float]:
    """
    Return (total_kwh, confidence) from bill text.

    Confidence:
      0.85 — explicit usage pattern matched
      0.0  — not found
    """
    for pattern in _KWH_USAGE_PATTERNS:
        m = pattern.search(text_body)
        if m:
            raw = _strip_commas(m.group(1))
            try:
                value = float(raw)
                if 0 < value < 100_000:  # Sanity: residential up to ~100k kWh
                    return round(value, 2), 0.85
            except ValueError:
                continue
    return None, 0.0


def extract_total_amount(text_body: str) -> tuple[Optional[float], float]:
    """
    Return (total_amount_usd, confidence) from bill text.

    Confidence:
      0.9  — "Amount Due" / "Total Amount Due" pattern matched
      0.0  — not found
    """
    for pattern in _AMOUNT_PATTERNS:
        m = pattern.search(text_body)
        if m:
            raw = _strip_commas(m.group(1))
            try:
                value = float(raw)
                if 0 < value < 100_000:  # Sanity
                    return round(value, 2), 0.9
            except ValueError:
                continue
    return None, 0.0


# ---------------------------------------------------------------------------
# BillParserService
# ---------------------------------------------------------------------------


class BillParserService:
    """
    Orchestrates bill file parsing from storage through to DB updates.

    Usage::

        parser = BillParserService(db=db_session, uploads_dir=Path("uploads"))
        result = await parser.parse(upload_id, connection_id, storage_key)
    """

    def __init__(
        self,
        db: AsyncSession,
        uploads_dir: Optional[Path] = None,
    ) -> None:
        self.db = db
        self.uploads_dir = uploads_dir or Path("uploads")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse(
        self,
        upload_id: str,
        connection_id: str,
        storage_key: str,
    ) -> Dict[str, Any]:
        """
        Parse the bill file identified by *storage_key* and persist results.

        Returns a dict containing all detected_* fields plus parse_status.
        """
        log = logger.bind(upload_id=upload_id, connection_id=connection_id)

        # Mark as processing
        await self._set_status(upload_id, "processing")

        try:
            # Path traversal guard: resolved path must stay within uploads_dir
            resolved = (self.uploads_dir / storage_key).resolve()
            if not str(resolved).startswith(str(self.uploads_dir.resolve())):
                raise ValueError(f"Illegal storage_key: {storage_key!r}")

            try:
                file_path = self.uploads_dir / storage_key
                data = file_path.read_bytes()
            except (FileNotFoundError, PermissionError) as exc:
                err = f"File not found or unreadable: {exc}"
                log.error("bill_parse_file_error", error=err)
                await self._mark_failed(upload_id, err)
                return {"parse_status": "failed", "parse_error": err}

            # Detect file type from magic bytes
            detected_type = _validate_magic_bytes(data)
            if not detected_type:
                err = "Unsupported file type detected from content."
                log.warning("bill_parse_bad_magic", upload_id=upload_id)
                await self._mark_failed(upload_id, err)
                return {"parse_status": "failed", "parse_error": err}

            # Extract text from file
            text_body = extract_text(data, detected_type)

            if not text_body.strip():
                err = (
                    "No extractable text found. "
                    "For image bills, pytesseract + Tesseract must be installed."
                )
                if detected_type in ("png", "jpg"):
                    log.warning("bill_parse_no_ocr", upload_id=upload_id)
                else:
                    log.warning("bill_parse_empty_text", upload_id=upload_id)
                await self._mark_failed(upload_id, err)
                return {"parse_status": "failed", "parse_error": err}

            # Run extractors
            rate, rate_conf = extract_rate_per_kwh(text_body)
            supplier, sup_conf = extract_supplier(text_body)
            period_start, period_end, period_conf = extract_billing_period(text_body)
            total_kwh, kwh_conf = extract_total_kwh(text_body)
            total_amount, amount_conf = extract_total_amount(text_body)

            parsed_data: Dict[str, Any] = {
                "text_length": len(text_body),
                "confidences": {
                    "rate": rate_conf,
                    "supplier": sup_conf,
                    "billing_period": period_conf,
                    "total_kwh": kwh_conf,
                    "total_amount": amount_conf,
                },
            }

            # Persist extraction results
            await self._save_results(
                upload_id=upload_id,
                parsed_data=parsed_data,
                detected_supplier=supplier,
                detected_rate_per_kwh=rate,
                detected_billing_period_start=period_start,
                detected_billing_period_end=period_end,
                detected_total_kwh=total_kwh,
                detected_total_amount=total_amount,
            )

            # Insert into connection_extracted_rates if we have a confident rate
            if rate is not None and rate_conf >= 0.5:
                await self._insert_extracted_rate(
                    connection_id=connection_id,
                    rate_per_kwh=rate,
                    raw_label=f"bill_parse:{storage_key}",
                )

            log.info(
                "bill_parse_complete",
                rate=rate,
                supplier=supplier,
                total_kwh=total_kwh,
                total_amount=total_amount,
            )

            return {
                "parse_status": "complete",
                "detected_supplier": supplier,
                "detected_rate_per_kwh": rate,
                "detected_billing_period_start": period_start,
                "detected_billing_period_end": period_end,
                "detected_total_kwh": total_kwh,
                "detected_total_amount": total_amount,
            }
        except Exception as exc:
            err = f"Unexpected error during parsing: {exc}"
            log.error("bill_parse_unexpected_error", error=err)
            try:
                await self._mark_failed(upload_id, err)
            except Exception:
                log.error("bill_parse_mark_failed_error", upload_id=upload_id)
            return {"parse_status": "failed", "parse_error": err}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _set_status(self, upload_id: str, status: str) -> None:
        await self.db.execute(
            text("""
                UPDATE bill_uploads
                SET parse_status = :status, updated_at = NOW()
                WHERE id = :upload_id
            """),
            {"status": status, "upload_id": upload_id},
        )
        await self.db.commit()

    async def _mark_failed(self, upload_id: str, error: str) -> None:
        await self.db.execute(
            text("""
                UPDATE bill_uploads
                SET parse_status = 'failed',
                    parse_error  = :error,
                    updated_at   = NOW()
                WHERE id = :upload_id
            """),
            {"error": error, "upload_id": upload_id},
        )
        await self.db.commit()

    async def _save_results(
        self,
        *,
        upload_id: str,
        parsed_data: Dict[str, Any],
        detected_supplier: Optional[str],
        detected_rate_per_kwh: Optional[float],
        detected_billing_period_start: Optional[str],
        detected_billing_period_end: Optional[str],
        detected_total_kwh: Optional[float],
        detected_total_amount: Optional[float],
    ) -> None:
        import json

        await self.db.execute(
            text("""
                UPDATE bill_uploads
                SET parse_status                  = 'complete',
                    parsed_data                   = :parsed_data,
                    parse_error                   = NULL,
                    parsed_at                     = NOW(),
                    detected_supplier             = :supplier,
                    detected_rate_per_kwh         = :rate,
                    detected_billing_period_start = :period_start,
                    detected_billing_period_end   = :period_end,
                    detected_total_kwh            = :total_kwh,
                    detected_total_amount         = :total_amount,
                    updated_at                    = NOW()
                WHERE id = :upload_id
            """),
            {
                "upload_id": upload_id,
                "parsed_data": json.dumps(parsed_data),
                "supplier": detected_supplier,
                "rate": detected_rate_per_kwh,
                "period_start": detected_billing_period_start,
                "period_end": detected_billing_period_end,
                "total_kwh": detected_total_kwh,
                "total_amount": detected_total_amount,
            },
        )
        await self.db.commit()

    async def _insert_extracted_rate(
        self,
        *,
        connection_id: str,
        rate_per_kwh: float,
        raw_label: str,
    ) -> None:
        rate_id = str(uuid4())
        await self.db.execute(
            text("""
                INSERT INTO connection_extracted_rates
                    (id, connection_id, rate_per_kwh, effective_date, source, raw_label)
                VALUES
                    (:id, :connection_id, :rate, NOW(), 'bill_parse', :label)
            """),
            {
                "id": rate_id,
                "connection_id": connection_id,
                "rate": rate_per_kwh,
                "label": raw_label,
            },
        )
        await self.db.commit()


# ---------------------------------------------------------------------------
# File storage helpers (Phase 2 — local filesystem)
# ---------------------------------------------------------------------------


def build_storage_key(connection_id: str, upload_id: str, original_filename: str) -> str:
    """
    Construct a storage key (relative path within uploads_dir) that:
      - Namespaces by connection_id to avoid collisions
      - Includes the upload UUID for uniqueness
      - Preserves the original file extension
    """
    suffix = Path(original_filename).suffix.lower()
    return f"{connection_id}/{upload_id}{suffix}"


def validate_upload_file(
    filename: str,
    content_type: str,
    data: bytes,
) -> str:
    """
    Validate that an upload is an allowed file type, confirmed by magic bytes.

    Returns the canonical file type string: 'pdf', 'png', or 'jpg'.

    Raises:
        ValueError: with a descriptive message if validation fails.
    """
    # Extension check
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # MIME type check (advisory — browsers can lie)
    normalised_mime = content_type.split(";")[0].strip().lower()
    if normalised_mime not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported content type '{normalised_mime}'. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )

    # Magic bytes check (ground truth)
    detected = _validate_magic_bytes(data[:16])
    if detected is None:
        raise ValueError(
            "File content does not match a supported format (PDF, PNG, or JPEG). "
            "Please upload an original bill file — re-saved or converted files may fail this check."
        )

    # Cross-check: extension must align with detected type
    if detected == "pdf" and suffix not in (".pdf",):
        raise ValueError("File content is PDF but extension is not '.pdf'.")
    if detected in ("png",) and suffix not in (".png",):
        raise ValueError("File content is PNG but extension is not '.png'.")
    if detected == "jpg" and suffix not in (".jpg", ".jpeg"):
        raise ValueError("File content is JPEG but extension is not '.jpg' or '.jpeg'.")

    return detected
