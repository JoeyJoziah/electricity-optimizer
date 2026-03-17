"""
Early Access Signup API Endpoint
Handles early access user registration and welcome email sending
"""

from fastapi import APIRouter, Body, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
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


class BetaSignupRequest(BaseModel):
    """Early access signup form data"""
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    postcode: str = Field(..., min_length=5, max_length=10)
    currentSupplier: str = Field(..., min_length=1, max_length=100)
    monthlyBill: str = Field(..., min_length=1, max_length=50)
    hearAbout: str = Field(..., min_length=1, max_length=200)


class BetaSignupResponse(BaseModel):
    """Early access signup response"""
    success: bool
    message: str
    betaCode: Optional[str] = None


# Database-backed beta signups (migrated from in-memory list)


def validate_postcode(postcode: str) -> bool:
    """Validate US ZIP code or UK postcode format.

    Accepts:
    - US 5-digit ZIP codes (e.g. 06510)
    - US ZIP+4 codes (e.g. 12345-6789)
    - UK postcodes (e.g. SW1A 1AA)
    """
    postcode = postcode.strip()

    # US 5-digit ZIP
    if re.match(r'^\d{5}$', postcode):
        return True

    # US ZIP+4
    if re.match(r'^\d{5}-\d{4}$', postcode):
        return True

    # UK postcode
    uk_pattern = r'^([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})$'
    if re.match(uk_pattern, postcode.upper()):
        return True

    return False


def generate_beta_code() -> str:
    """Generate unique beta access code"""
    return f"BETA-2026-{secrets.token_hex(4).upper()}"


async def send_welcome_email(email: str, name: str, beta_code: str):
    """Send welcome email to early access user using HTML template via EmailService."""
    logger.info("sending_welcome_email", recipient=email)

    try:
        from services.email_service import EmailService

        service = EmailService()
        html_body = service.render_template(
            "welcome_beta.html",
            name=name,
            betaCode=beta_code,
        )

        subject = "Welcome to RateShift!"
        success = await service.send(to=email, subject=subject, html_body=html_body)

        if success:
            logger.info("welcome_email_sent", recipient=email)
        else:
            logger.warning("welcome_email_skipped", recipient=email, reason="no provider configured")

    except Exception as e:
        # Don't crash the signup flow if email fails
        logger.error("welcome_email_failed", recipient=email, error=str(e))

    return True


@router.post("/signup", response_model=BetaSignupResponse)
async def beta_signup(
    signup: BetaSignupRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Register for early access. No invite code required — signup is publicly accessible.

    - Validates US ZIP code or UK postcode
    - Generates unique access code
    - Sends welcome email
    - Stores signup data in database
    """

    # Validate postcode
    if not validate_postcode(signup.postcode):
        raise HTTPException(
            status_code=400,
            detail="Invalid postcode format"
        )

    # Check if email already registered
    existing = await db.execute(
        text("SELECT id FROM beta_signups WHERE email = :email"),
        {"email": signup.email},
    )
    if existing.fetchone() is not None:
        raise HTTPException(
            status_code=400,
            detail="Email already registered for early access"
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
        message="Welcome to RateShift! Check your email for next steps.",
        betaCode=beta_code
    )


@router.get("/signups/count")
async def get_beta_count(
    current_user: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get total early access signups count (requires authentication)"""
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
    """Get early access signup statistics (requires authentication)"""
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
    """Verify access code is valid"""
    # Search for the code in the interest field (stored as code=BETA-XXXX)
    result = await db.execute(
        text("SELECT interest FROM beta_signups WHERE interest LIKE :pattern"),
        {"pattern": f"%code={code}%"},
    )
    rows = result.fetchall()

    # Extract stored codes and use constant-time comparison
    is_valid = False
    for row in rows:
        # Support both SQLAlchemy Row objects and dict-like results
        if hasattr(row, "_mapping"):
            interest = row._mapping.get("interest", "") or ""
        elif isinstance(row, dict):
            interest = row.get("interest", "") or ""
        else:
            interest = str(row[0]) if row else ""
        for part in interest.split(";"):
            if part.startswith("code="):
                stored_code = part[5:]
                if hmac.compare_digest(code, stored_code):
                    is_valid = True
                    break

    if is_valid:
        return {"valid": True, "message": "Access code verified"}
    else:
        raise HTTPException(
            status_code=404,
            detail="Invalid access code"
        )
