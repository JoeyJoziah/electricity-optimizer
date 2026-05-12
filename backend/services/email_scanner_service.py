"""
Email scanner service — searches Gmail/Outlook inboxes for utility bill emails.

Uses Gmail API (REST) and Microsoft Graph API to find emails matching
utility bill keywords, then extracts rate data from email body/attachments.
"""

import base64
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

_OAUTH_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


# Keywords that indicate a utility bill email
UTILITY_KEYWORDS = [
    "electricity bill",
    "electric bill",
    "energy bill",
    "utility bill",
    "energy statement",
    "account statement",
    "kWh",
    "kilowatt",
    "monthly statement",
    "billing statement",
    "energy usage",
    "your bill is ready",
    "payment due",
]

# Subject line patterns (case-insensitive)
SUBJECT_PATTERNS = [
    re.compile(
        r"(electric|energy|utility|power)\s*(bill|statement|invoice)", re.IGNORECASE
    ),
    re.compile(r"(monthly|billing)\s*statement", re.IGNORECASE),
    re.compile(r"(your|new)\s*(bill|invoice)\s*(is|from)", re.IGNORECASE),
    re.compile(r"payment\s*(due|reminder)", re.IGNORECASE),
]


class EmailScanResult:
    """Result of scanning a single email for utility bill data."""

    def __init__(
        self,
        email_id: str,
        subject: str,
        sender: str,
        date: datetime,
        is_utility_bill: bool = False,
        extracted_data: dict[str, Any] | None = None,
        attachment_count: int = 0,
    ):
        self.email_id = email_id
        self.subject = subject
        self.sender = sender
        self.date = date
        self.is_utility_bill = is_utility_bill
        self.extracted_data = extracted_data or {}
        self.attachment_count = attachment_count

    def to_dict(self) -> dict:
        return {
            "email_id": self.email_id,
            "subject": self.subject,
            "sender": self.sender,
            "date": self.date.isoformat(),
            "is_utility_bill": self.is_utility_bill,
            "extracted_data": self.extracted_data,
            "attachment_count": self.attachment_count,
        }


def _matches_utility_keywords(text: str) -> bool:
    """Check if text contains utility bill keywords."""
    text_lower = text.lower()
    for keyword in UTILITY_KEYWORDS:
        if keyword.lower() in text_lower:
            return True
    return any(pattern.search(text) for pattern in SUBJECT_PATTERNS)


async def scan_gmail_inbox(
    access_token: str,
    lookback_days: int = 365,
    max_results: int = 50,
) -> list[EmailScanResult]:
    """
    Scan Gmail inbox for utility bill emails.

    Uses Gmail API to search for emails matching utility keywords
    within the lookback period.
    """
    results: list[EmailScanResult] = []
    after_date = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime(
        "%Y/%m/%d"
    )

    # Build Gmail search query
    keyword_query = " OR ".join(f'"{kw}"' for kw in UTILITY_KEYWORDS[:6])
    query = f"({keyword_query}) after:{after_date}"

    async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT) as client:
        # List matching messages
        list_resp = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": query, "maxResults": max_results},
        )
        list_resp.raise_for_status()
        messages = list_resp.json().get("messages", [])

        for msg_stub in messages:
            msg_resp = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_stub['id']}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "format": "metadata",
                    "metadataHeaders": ["Subject", "From", "Date"],
                },
            )
            if msg_resp.status_code != 200:
                continue

            msg_data = msg_resp.json()
            headers = {
                h["name"]: h["value"]
                for h in msg_data.get("payload", {}).get("headers", [])
            }

            subject = headers.get("Subject", "")
            sender = headers.get("From", "")
            date_str = headers.get("Date", "")

            # Count attachments
            parts = msg_data.get("payload", {}).get("parts", [])
            attachment_count = sum(1 for p in parts if p.get("filename"))

            is_bill = _matches_utility_keywords(subject) or _matches_utility_keywords(
                sender
            )

            try:
                email_date = datetime.now(UTC)  # Fallback
                if date_str:
                    # Parse RFC 2822 date (simplified)
                    from email.utils import parsedate_to_datetime

                    email_date = parsedate_to_datetime(date_str)
            except (ValueError, TypeError):
                email_date = datetime.now(UTC)

            results.append(
                EmailScanResult(
                    email_id=msg_stub["id"],
                    subject=subject,
                    sender=sender,
                    date=email_date,
                    is_utility_bill=is_bill,
                    attachment_count=attachment_count,
                )
            )

    return results


async def scan_outlook_inbox(
    access_token: str,
    lookback_days: int = 365,
    max_results: int = 50,
) -> list[EmailScanResult]:
    """
    Scan Outlook inbox for utility bill emails.

    Uses Microsoft Graph API to search for emails matching utility keywords.
    """
    results: list[EmailScanResult] = []
    after_date = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()

    # Build $search query for Graph API
    search_terms = " OR ".join(f'"{kw}"' for kw in UTILITY_KEYWORDS[:6])

    async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT) as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "$search": f'"{search_terms}"',
                "$filter": f"receivedDateTime ge {after_date}",
                "$top": max_results,
                "$select": "id,subject,from,receivedDateTime,hasAttachments",
                "$orderby": "receivedDateTime desc",
            },
        )
        resp.raise_for_status()
        messages = resp.json().get("value", [])

        for msg in messages:
            subject = msg.get("subject", "")
            sender_data = msg.get("from", {}).get("emailAddress", {})
            sender = f"{sender_data.get('name', '')} <{sender_data.get('address', '')}>"

            try:
                email_date = datetime.fromisoformat(
                    msg["receivedDateTime"].replace("Z", "+00:00")
                )
            except (ValueError, KeyError):
                email_date = datetime.now(UTC)

            is_bill = _matches_utility_keywords(subject) or _matches_utility_keywords(
                sender
            )

            results.append(
                EmailScanResult(
                    email_id=msg["id"],
                    subject=subject,
                    sender=sender,
                    date=email_date,
                    is_utility_bill=is_bill,
                    attachment_count=1 if msg.get("hasAttachments") else 0,
                )
            )

    return results


async def extract_rates_from_email(
    provider: str,
    access_token: str,
    email_id: str,
) -> dict[str, Any]:
    """
    Extract rate data from a specific email's body and attachments.

    Uses text regex extraction from the email body (same patterns as bill_parser)
    for inline rate/supplier/billing-period detection.
    """
    extracted = {}

    async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT) as client:
        if provider == "gmail":
            resp = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{email_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"format": "full"},
            )
            resp.raise_for_status()
            data = resp.json()

            # Extract text body
            body_text = _extract_gmail_body_text(data.get("payload", {}))
            if body_text:
                extracted = _extract_rates_from_text(body_text)

        elif provider == "outlook":
            resp = await client.get(
                f"https://graph.microsoft.com/v1.0/me/messages/{email_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"$select": "body"},
            )
            resp.raise_for_status()
            data = resp.json()

            body_content = data.get("body", {}).get("content", "")
            if body_content:
                # Strip HTML tags for text extraction
                clean_text = re.sub(r"<[^>]+>", " ", body_content)
                extracted = _extract_rates_from_text(clean_text)

    return extracted


def _extract_gmail_body_text(payload: dict) -> str:
    """Extract plain text body from Gmail message payload."""
    # Check for direct text/plain body
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Check parts
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        # Recurse into nested parts
        if part.get("parts"):
            result = _extract_gmail_body_text(part)
            if result:
                return result
    return ""


async def download_gmail_attachments(
    access_token: str,
    email_id: str,
) -> list[dict[str, Any]]:
    """
    Download all PDF/image attachments from a Gmail message.

    First fetches the message with format=full to inspect parts, then downloads
    each qualifying attachment via the Gmail attachments endpoint.  Attachment
    data arrives as base64url-encoded bytes.

    Returns a list of dicts with keys: filename, data (bytes), mime_type.
    Limits to 5 attachments per email.  Skips non-PDF/image parts.
    """
    _ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT) as client:
        # Fetch message with full payload to read part metadata
        msg_resp = await client.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{email_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"},
        )
        msg_resp.raise_for_status()
        payload = msg_resp.json().get("payload", {})

        def _collect_parts(part: dict) -> None:
            """Recursively collect parts that are downloadable attachments."""
            filename = part.get("filename", "")
            mime_type = part.get("mimeType", "")
            attachment_id = part.get("body", {}).get("attachmentId")

            if filename and attachment_id and mime_type.lower() in _ALLOWED_MIME:
                results.append(
                    {
                        "filename": filename,
                        "attachment_id": attachment_id,
                        "mime_type": mime_type.lower(),
                    }
                )

            for sub in part.get("parts", []):
                _collect_parts(sub)

        _collect_parts(payload)

        # Cap at 5 attachments
        attachments_to_fetch = results[:5]
        results.clear()

        for meta in attachments_to_fetch:
            try:
                att_resp = await client.get(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{email_id}"
                    f"/attachments/{meta['attachment_id']}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                att_resp.raise_for_status()
                raw_data = att_resp.json().get("data", "")
                # Gmail returns base64url-encoded data
                file_bytes = base64.urlsafe_b64decode(raw_data + "==")
                results.append(
                    {
                        "filename": meta["filename"],
                        "data": file_bytes,
                        "mime_type": meta["mime_type"],
                    }
                )
            except Exception:
                # Skip attachments that fail to download
                continue

    return results


async def download_outlook_attachments(
    access_token: str,
    email_id: str,
) -> list[dict[str, Any]]:
    """
    Download all PDF/image attachments from an Outlook/Graph API message.

    Fetches the attachments collection for the given message.  Each item
    exposes contentBytes (base64-encoded) along with name and contentType.

    Returns a list of dicts with keys: filename, data (bytes), mime_type.
    Limits to 5 attachments per email.  Skips non-PDF/image content types.
    """
    _ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=_OAUTH_TIMEOUT) as client:
        resp = await client.get(
            f"https://graph.microsoft.com/v1.0/me/messages/{email_id}/attachments",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "name,contentType,contentBytes"},
        )
        resp.raise_for_status()
        attachments = resp.json().get("value", [])

        for att in attachments[:5]:
            mime_type = att.get("contentType", "").lower().split(";")[0].strip()
            if mime_type not in _ALLOWED_MIME:
                continue
            content_bytes = att.get("contentBytes", "")
            if not content_bytes:
                continue
            try:
                file_bytes = base64.b64decode(content_bytes)
                results.append(
                    {
                        "filename": att.get("name", "attachment"),
                        "data": file_bytes,
                        "mime_type": mime_type,
                    }
                )
            except Exception:
                continue

    return results


async def extract_rates_from_attachments(
    attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Parse each attachment through bill_parser extractors.

    Uses lazy import of bill_parser to avoid circular dependency issues.
    Each attachment dict must have keys: filename, data (bytes), mime_type.

    Returns a list of extraction result dicts.  Each result has at least
    a 'filename' key and whatever fields bill_parser could extract
    (rate_per_kwh, total_kwh, total_amount, supplier, billing_period_start,
    billing_period_end).
    """
    # Lazy import to avoid circular deps
    from services.bill_parser import (_validate_magic_bytes,
                                      extract_billing_period,
                                      extract_rate_per_kwh, extract_supplier,
                                      extract_text, extract_total_amount,
                                      extract_total_kwh)

    _MIME_TO_TYPE = {
        "application/pdf": "pdf",
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
    }

    extracted_results: list[dict[str, Any]] = []

    for att in attachments:
        filename = att.get("filename", "unknown")
        data: bytes = att.get("data", b"")
        mime_type = att.get("mime_type", "")

        if not data:
            continue

        # Validate magic bytes match expected type
        detected_type = _validate_magic_bytes(data)
        file_type = _MIME_TO_TYPE.get(mime_type, detected_type or "")
        if not file_type:
            continue

        try:
            text_body = extract_text(data, file_type)
            if not text_body.strip():
                continue

            rate, rate_conf = extract_rate_per_kwh(text_body)
            supplier, _ = extract_supplier(text_body)
            period_start, period_end, _ = extract_billing_period(text_body)
            total_kwh, _ = extract_total_kwh(text_body)
            total_amount, _ = extract_total_amount(text_body)

            result: dict[str, Any] = {"filename": filename}
            if rate is not None and rate_conf >= 0.5:
                result["rate_per_kwh"] = rate
            if supplier:
                result["supplier"] = supplier
            if period_start:
                result["billing_period_start"] = period_start
            if period_end:
                result["billing_period_end"] = period_end
            if total_kwh is not None:
                result["total_kwh"] = total_kwh
            if total_amount is not None:
                result["total_amount"] = total_amount

            extracted_results.append(result)
        except Exception:
            # Never crash on a single attachment — log and move on
            extracted_results.append({"filename": filename})
            continue

    return extracted_results


def _extract_rates_from_text(text: str) -> dict[str, Any]:
    """Extract rate information from email text using regex patterns from bill_parser."""
    result: dict[str, Any] = {}

    # Rate per kWh
    rate_match = re.search(
        r"(?:rate|price|cost|charge)[:\s]*\$?([\d]+\.[\d]{2,4})\s*(?:/\s*)?(?:per\s+)?(?:kWh|kwh|KWH)",
        text,
        re.IGNORECASE,
    )
    if rate_match:
        result["rate_per_kwh"] = float(rate_match.group(1))

    # Total amount
    total_match = re.search(
        r"(?:total|amount\s+due|balance|pay)[:\s]*\$?([\d,]+\.[\d]{2})",
        text,
        re.IGNORECASE,
    )
    if total_match:
        result["total_amount"] = float(total_match.group(1).replace(",", ""))

    # Total kWh
    kwh_match = re.search(
        r"([\d,]+(?:\.\d+)?)\s*(?:kWh|kwh|KWH|kilowatt[\s-]*hours?)",
        text,
        re.IGNORECASE,
    )
    if kwh_match:
        result["total_kwh"] = float(kwh_match.group(1).replace(",", ""))

    # Supplier name (common utility names)
    supplier_patterns = [
        r"(Eversource\s+Energy)",
        r"(United\s+Illuminating)",
        r"(NextEra\s+Energy)",
        r"(Pacific\s+Gas\s*&?\s*Electric|PG&E)",
        r"(ConEdison|Con\s+Edison)",
        r"(Duke\s+Energy)",
        r"(Southern\s+Company)",
        r"(Dominion\s+Energy)",
    ]
    for sp in supplier_patterns:
        m = re.search(sp, text, re.IGNORECASE)
        if m:
            result["supplier"] = m.group(1).strip()
            break

    return result
