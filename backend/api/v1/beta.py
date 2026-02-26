"""
Beta Signup API Endpoint
Handles beta user registration and welcome email sending
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

from api.dependencies import get_current_user, get_db_session, TokenData

logger = structlog.get_logger()

router = APIRouter(prefix="/beta", tags=["beta"])


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


# Database-backed beta signups (migrated from in-memory list)


def validate_uk_postcode(postcode: str) -> bool:
    """Validate UK postcode format"""
    # UK postcode regex pattern
    pattern = r'^([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})$'
    return bool(re.match(pattern, postcode.upper()))


def generate_beta_code() -> str:
    """Generate unique beta access code"""
    return f"BETA-2026-{secrets.token_hex(4).upper()}"


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
    current_user: TokenData = Depends(get_current_user),
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
    current_user: TokenData = Depends(get_current_user),
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
