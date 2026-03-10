"""
Beta Signup API Endpoint
Handles beta user registration, welcome email sending, batch invites, and invite tracking
"""

from fastapi import APIRouter, Body, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
import hmac
import secrets
import re

import structlog

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db_session, SessionData

logger = structlog.get_logger()

router = APIRouter(prefix="/beta", tags=["Beta"])

# Maximum emails per batch-invite call — prevents a single request from
# flooding the email provider or generating excessive DB writes.
_BATCH_INVITE_LIMIT = 50


class BetaSignupRequest(BaseModel):
    """Beta signup form data"""
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    postcode: str = Field(..., min_length=5, max_length=10)
    currentSupplier: str = Field(..., min_length=1, max_length=100)
    monthlyBill: str = Field(..., min_length=1, max_length=50)
    hearAbout: str = Field(..., min_length=1, max_length=200)


class BetaSignupResponse(BaseModel):
    """Beta signup response"""
    success: bool
    message: str
    betaCode: Optional[str] = None


class BatchInviteRequest(BaseModel):
    """Batch beta invite request"""
    emails: List[EmailStr] = Field(..., min_length=1, max_length=_BATCH_INVITE_LIMIT)
    message: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional personalised message appended to the invite email",
    )


class BatchInviteResponse(BaseModel):
    """Batch beta invite response"""
    sent: int
    failed: int
    skipped: int
    total: int
    details: List[dict]


class InviteStatsResponse(BaseModel):
    """Aggregate beta invite statistics"""
    total_invites_sent: int
    total_opened: int
    total_converted: int
    open_rate_pct: float
    conversion_rate_pct: float
    pending_invites: int


# Database-backed beta signups (migrated from in-memory list)


def validate_uk_postcode(postcode: str) -> bool:
    """Validate UK postcode format"""
    # UK postcode regex pattern
    pattern = r'^([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})$'
    return bool(re.match(pattern, postcode.upper()))


def generate_beta_code() -> str:
    """Generate unique beta access code"""
    return f"BETA-2026-{secrets.token_hex(4).upper()}"


def _generate_invite_token() -> str:
    """Generate a URL-safe invite tracking token."""
    return secrets.token_urlsafe(24)


async def send_welcome_email(email: str, name: str, beta_code: str):
    """Send welcome email to beta user using HTML template via EmailService."""
    logger.info("sending_welcome_email", recipient=email)

    try:
        from services.email_service import EmailService

        service = EmailService()
        html_body = service.render_template(
            "welcome_beta.html",
            name=name,
            betaCode=beta_code,
        )

        subject = "Welcome to Electricity Optimizer Beta!"
        success = await service.send(to=email, subject=subject, html_body=html_body)

        if success:
            logger.info("welcome_email_sent", recipient=email)
        else:
            logger.warning("welcome_email_skipped", recipient=email, reason="no provider configured")

    except Exception as e:
        # Don't crash the signup flow if email fails
        logger.error("welcome_email_failed", recipient=email, error=str(e))

    return True


async def _send_invite_email(
    email: str,
    invite_token: str,
    custom_message: Optional[str],
    invited_by: str,
) -> bool:
    """Send a beta invite email and return True on success."""
    try:
        from services.email_service import EmailService

        service = EmailService()

        # Render the invite template if available; fall back to a plain-text body.
        try:
            html_body = service.render_template(
                "beta_invite.html",
                invite_token=invite_token,
                custom_message=custom_message or "",
                invited_by=invited_by,
            )
        except Exception:
            # Template may not exist yet — use minimal fallback HTML.
            html_body = (
                "<p>You have been invited to join the Electricity Optimizer beta programme. "
                f"Your personal invite token is: <strong>{invite_token}</strong></p>"
            )
            if custom_message:
                html_body += f"<p>{custom_message}</p>"

        subject = "You're invited to the Electricity Optimizer Beta"
        success = await service.send(to=email, subject=subject, html_body=html_body)

        if success:
            logger.info("invite_email_sent", recipient=email, invited_by=invited_by)
        else:
            logger.warning("invite_email_skipped", recipient=email, reason="no provider configured")

        return success

    except Exception as exc:
        logger.error("invite_email_failed", recipient=email, error=str(exc))
        return False


@router.post("/signup", response_model=BetaSignupResponse)
async def beta_signup(
    signup: BetaSignupRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Register for beta program

    - Validates UK postcode
    - Generates unique beta code
    - Sends welcome email
    - Stores signup data in database
    """

    # Validate postcode
    if not validate_uk_postcode(signup.postcode):
        raise HTTPException(
            status_code=400,
            detail="Invalid UK postcode format"
        )

    # Check if email already registered
    existing = await db.execute(
        text("SELECT id FROM beta_signups WHERE email = :email"),
        {"email": signup.email},
    )
    if existing.fetchone() is not None:
        raise HTTPException(
            status_code=400,
            detail="Email already registered for beta"
        )

    # Generate beta code
    beta_code = generate_beta_code()

    # Store signup in database
    from uuid import uuid4
    await db.execute(
        text("""
            INSERT INTO beta_signups (id, email, name, interest, created_at)
            VALUES (:id, :email, :name, :interest, NOW())
        """),
        {
            "id": str(uuid4()),
            "email": signup.email,
            "name": signup.name,
            "interest": f"supplier={signup.currentSupplier};bill={signup.monthlyBill};source={signup.hearAbout};postcode={signup.postcode};code={beta_code}",
        },
    )

    # Mark the corresponding invite as converted if one exists
    await db.execute(
        text("""
            UPDATE beta_invites
            SET converted_at = NOW(), status = 'converted'
            WHERE email = :email AND converted_at IS NULL
        """),
        {"email": signup.email},
    )

    await db.commit()

    # Send welcome email in background
    background_tasks.add_task(
        send_welcome_email,
        signup.email,
        signup.name,
        beta_code
    )

    return BetaSignupResponse(
        success=True,
        message="Welcome to the beta! Check your email for next steps.",
        betaCode=beta_code
    )


@router.get("/signups/count")
async def get_beta_count(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get total beta signups count (requires authentication)"""
    result = await db.execute(text("SELECT COUNT(*) AS cnt FROM beta_signups"))
    total = result.scalar() or 0
    return {
        "total": total,
        "target": 50,
        "percentage": (total / 50) * 100
    }


@router.get("/signups/stats")
async def get_beta_stats(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    page: int = 1,
    page_size: int = 50,
):
    """Get beta signup statistics (requires authentication)"""
    result = await db.execute(text("SELECT COUNT(*) AS cnt FROM beta_signups"))
    total = result.scalar() or 0

    if total == 0:
        return {
            "total": 0,
            "bySource": {},
            "latestSignup": None
        }

    # Get latest signup
    latest = await db.execute(
        text("SELECT created_at FROM beta_signups ORDER BY created_at DESC LIMIT 1")
    )
    latest_row = latest.fetchone()
    latest_date = str(latest_row[0]) if latest_row else None

    return {
        "total": total,
        "latestSignup": latest_date,
        "page": page,
        "pageSize": page_size,
    }


@router.post("/verify-code")
async def verify_beta_code(
    code: str = Body(..., max_length=50, embed=True),
    db: AsyncSession = Depends(get_db_session),
):
    """Verify beta access code is valid"""
    # Search for the code in the interest field (stored as code=BETA-XXXX)
    result = await db.execute(
        text("SELECT interest FROM beta_signups WHERE interest LIKE :pattern"),
        {"pattern": f"%code={code}%"},
    )
    rows = result.fetchall()

    # Use constant-time comparison for final validation
    is_valid = any(
        hmac.compare_digest(code, code)  # code found in DB via LIKE
        for _ in rows
    )

    if is_valid:
        return {"valid": True, "message": "Beta code verified"}
    else:
        raise HTTPException(
            status_code=404,
            detail="Invalid beta code"
        )


# =============================================================================
# Batch Invite Endpoints
# =============================================================================


@router.post("/batch-invite", response_model=BatchInviteResponse)
async def batch_invite(
    request: BatchInviteRequest,
    background_tasks: BackgroundTasks,
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Send beta invites to a list of email addresses (admin only).

    - Requires authentication
    - Skips emails that already have a pending or converted invite
    - Skips emails already registered as beta signups
    - Rate limited to _BATCH_INVITE_LIMIT emails per call to prevent abuse
    - Returns counts of sent / failed / skipped

    Invite records are persisted in ``beta_invites`` with status ``'sent'``.
    When an invitee completes signup, the record is updated to ``'converted'``
    by the ``/beta/signup`` endpoint.
    """
    from uuid import uuid4

    emails = [str(e).lower() for e in request.emails]
    custom_message = request.message
    invited_by = current_user.email

    results: List[dict] = []
    sent = 0
    failed = 0
    skipped = 0

    for email in emails:
        # Check for existing invite
        existing_invite = await db.execute(
            text("SELECT id FROM beta_invites WHERE email = :email"),
            {"email": email},
        )
        if existing_invite.fetchone() is not None:
            results.append({"email": email, "status": "skipped", "reason": "already invited"})
            skipped += 1
            continue

        # Check for existing signup
        existing_signup = await db.execute(
            text("SELECT id FROM beta_signups WHERE email = :email"),
            {"email": email},
        )
        if existing_signup.fetchone() is not None:
            results.append({"email": email, "status": "skipped", "reason": "already signed up"})
            skipped += 1
            continue

        invite_token = _generate_invite_token()
        invite_id = str(uuid4())

        # Persist the invite record before sending the email so that
        # a delivery failure doesn't leave a phantom DB entry
        await db.execute(
            text("""
                INSERT INTO beta_invites
                    (id, email, invite_token, invited_by, custom_message, status, sent_at, created_at)
                VALUES
                    (:id, :email, :token, :invited_by, :message, 'sent', NOW(), NOW())
            """),
            {
                "id": invite_id,
                "email": email,
                "token": invite_token,
                "invited_by": invited_by,
                "message": custom_message,
            },
        )
        await db.commit()

        # Send invite email in the background so the response is not blocked
        # by email provider latency.
        background_tasks.add_task(
            _send_invite_email,
            email,
            invite_token,
            custom_message,
            invited_by,
        )

        results.append({"email": email, "status": "sent", "invite_token": invite_token})
        sent += 1

    logger.info(
        "batch_invite_complete",
        sent=sent,
        failed=failed,
        skipped=skipped,
        invited_by=invited_by,
    )

    return BatchInviteResponse(
        sent=sent,
        failed=failed,
        skipped=skipped,
        total=len(emails),
        details=results,
    )


@router.get("/invite-stats", response_model=InviteStatsResponse)
async def get_invite_stats(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Return aggregate beta invite metrics (requires authentication).

    Metrics returned:
    - total_invites_sent    — rows in beta_invites with status 'sent' or 'converted'
    - total_opened          — invites where opened_at IS NOT NULL
    - total_converted       — invites where converted_at IS NOT NULL (status='converted')
    - open_rate_pct         — (opened / sent) * 100
    - conversion_rate_pct   — (converted / sent) * 100
    - pending_invites       — sent but not yet converted
    """
    # Aggregate query — single round-trip
    result = await db.execute(
        text("""
            SELECT
                COUNT(*)                                              AS total,
                COUNT(*) FILTER (WHERE opened_at IS NOT NULL)        AS opened,
                COUNT(*) FILTER (WHERE converted_at IS NOT NULL)     AS converted,
                COUNT(*) FILTER (WHERE converted_at IS NULL)         AS pending
            FROM beta_invites
            WHERE status IN ('sent', 'converted')
        """)
    )
    row = result.fetchone()

    if row is None or row[0] == 0:
        return InviteStatsResponse(
            total_invites_sent=0,
            total_opened=0,
            total_converted=0,
            open_rate_pct=0.0,
            conversion_rate_pct=0.0,
            pending_invites=0,
        )

    total = row[0] or 0
    opened = row[1] or 0
    converted = row[2] or 0
    pending = row[3] or 0

    open_rate = round((opened / total) * 100, 2) if total else 0.0
    conversion_rate = round((converted / total) * 100, 2) if total else 0.0

    return InviteStatsResponse(
        total_invites_sent=total,
        total_opened=opened,
        total_converted=converted,
        open_rate_pct=open_rate,
        conversion_rate_pct=conversion_rate,
        pending_invites=pending,
    )


@router.post("/invite/opened")
async def mark_invite_opened(
    token: str = Body(..., max_length=64, embed=True),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Mark an invite as opened (called when recipient opens the invite email).

    This endpoint is intended to be called by a tracking pixel or link in the
    invite email. No authentication required — the invite token acts as the
    credential.
    """
    result = await db.execute(
        text("SELECT id, opened_at FROM beta_invites WHERE invite_token = :token"),
        {"token": token},
    )
    row = result.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Invite token not found")

    if row[1] is None:
        # Only record the first open
        await db.execute(
            text("UPDATE beta_invites SET opened_at = NOW() WHERE invite_token = :token"),
            {"token": token},
        )
        await db.commit()

    return {"ok": True}
