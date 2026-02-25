"""
Email scanner service — searches Gmail/Outlook inboxes for utility bill emails.

Uses Gmail API (REST) and Microsoft Graph API to find emails matching
utility bill keywords, then extracts rate data from email body/attachments.
"""
import base64
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import httpx

from utils.encryption import decrypt_field


# Keywords that indicate a utility bill email
UTILITY_KEYWORDS = [
    "electricity bill", "electric bill", "energy bill", "utility bill",
    "energy statement", "account statement", "kWh", "kilowatt",
    "monthly statement", "billing statement", "energy usage",
    "your bill is ready", "payment due",
]

# Subject line patterns (case-insensitive)
SUBJECT_PATTERNS = [
    re.compile(r"(electric|energy|utility|power)\s*(bill|statement|invoice)", re.IGNORECASE),
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
        extracted_data: Optional[Dict[str, Any]] = None,
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
    for pattern in SUBJECT_PATTERNS:
        if pattern.search(text):
            return True
    return False


async def scan_gmail_inbox(
    access_token: str,
    lookback_days: int = 365,
    max_results: int = 50,
) -> List[EmailScanResult]:
    """
    Scan Gmail inbox for utility bill emails.

    Uses Gmail API to search for emails matching utility keywords
    within the lookback period.
    """
    results: List[EmailScanResult] = []
    after_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y/%m/%d")

    # Build Gmail search query
    keyword_query = " OR ".join(f'"{kw}"' for kw in UTILITY_KEYWORDS[:6])
    query = f"({keyword_query}) after:{after_date}"

    async with httpx.AsyncClient() as client:
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
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            if msg_resp.status_code != 200:
                continue

            msg_data = msg_resp.json()
            headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}

            subject = headers.get("Subject", "")
            sender = headers.get("From", "")
            date_str = headers.get("Date", "")

            # Count attachments
            parts = msg_data.get("payload", {}).get("parts", [])
            attachment_count = sum(1 for p in parts if p.get("filename"))

            is_bill = _matches_utility_keywords(subject) or _matches_utility_keywords(sender)

            try:
                email_date = datetime.now(timezone.utc)  # Fallback
                if date_str:
                    # Parse RFC 2822 date (simplified)
                    from email.utils import parsedate_to_datetime
                    email_date = parsedate_to_datetime(date_str)
            except (ValueError, TypeError):
                email_date = datetime.now(timezone.utc)

            results.append(EmailScanResult(
                email_id=msg_stub["id"],
                subject=subject,
                sender=sender,
                date=email_date,
                is_utility_bill=is_bill,
                attachment_count=attachment_count,
            ))

    return results


async def scan_outlook_inbox(
    access_token: str,
    lookback_days: int = 365,
    max_results: int = 50,
) -> List[EmailScanResult]:
    """
    Scan Outlook inbox for utility bill emails.

    Uses Microsoft Graph API to search for emails matching utility keywords.
    """
    results: List[EmailScanResult] = []
    after_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

    # Build $search query for Graph API
    search_terms = " OR ".join(f'"{kw}"' for kw in UTILITY_KEYWORDS[:6])

    async with httpx.AsyncClient() as client:
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
                email_date = datetime.fromisoformat(msg["receivedDateTime"].replace("Z", "+00:00"))
            except (ValueError, KeyError):
                email_date = datetime.now(timezone.utc)

            is_bill = _matches_utility_keywords(subject) or _matches_utility_keywords(sender)

            results.append(EmailScanResult(
                email_id=msg["id"],
                subject=subject,
                sender=sender,
                date=email_date,
                is_utility_bill=is_bill,
                attachment_count=1 if msg.get("hasAttachments") else 0,
            ))

    return results


async def extract_rates_from_email(
    provider: str,
    access_token: str,
    email_id: str,
) -> Dict[str, Any]:
    """
    Extract rate data from a specific email's body and attachments.

    Uses text regex extraction from the email body (same patterns as bill_parser)
    for inline rate/supplier/billing-period detection.
    """
    extracted = {}

    async with httpx.AsyncClient() as client:
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


def _extract_rates_from_text(text: str) -> Dict[str, Any]:
    """Extract rate information from email text using regex patterns from bill_parser."""
    result: Dict[str, Any] = {}

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
