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

from api.dependencies import get_current_user, TokenData

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


# In-memory storage for beta (replace with database in production)
beta_signups = []


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
    background_tasks: BackgroundTasks
):
    """
    Register for beta program

    - Validates UK postcode
    - Generates unique beta code
    - Sends welcome email
    - Stores signup data
    """

    # Validate postcode
    if not validate_uk_postcode(signup.postcode):
        raise HTTPException(
            status_code=400,
            detail="Invalid UK postcode format"
        )

    # Check if email already registered
    if any(s["email"] == signup.email for s in beta_signups):
        raise HTTPException(
            status_code=400,
            detail="Email already registered for beta"
        )

    # Generate beta code
    beta_code = generate_beta_code()

    # Store signup
    beta_signups.append({
        "email": signup.email,
        "name": signup.name,
        "postcode": signup.postcode,
        "currentSupplier": signup.currentSupplier,
        "monthlyBill": signup.monthlyBill,
        "hearAbout": signup.hearAbout,
        "betaCode": beta_code,
        "signupDate": datetime.utcnow().isoformat(),
        "status": "pending"
    })

    # Send welcome email in background
    background_tasks.add_task(
        send_welcome_email,
        signup.email,
        signup.name,
        beta_code
    )

    # Track signup event (analytics)
    # analytics.track('beta_signup', {
    #     'email': signup.email,
    #     'supplier': signup.currentSupplier,
    #     'source': signup.hearAbout
    # })

    return BetaSignupResponse(
        success=True,
        message="Welcome to the beta! Check your email for next steps.",
        betaCode=beta_code
    )


@router.get("/signups/count")
async def get_beta_count(
    current_user: TokenData = Depends(get_current_user),
):
    """Get total beta signups count (requires authentication)"""
    return {
        "total": len(beta_signups),
        "target": 50,
        "percentage": (len(beta_signups) / 50) * 100
    }


@router.get("/signups/stats")
async def get_beta_stats(
    current_user: TokenData = Depends(get_current_user),
):
    """Get beta signup statistics (requires authentication)"""
    if not beta_signups:
        return {
            "total": 0,
            "bySupplier": {},
            "bySource": {},
            "byBillRange": {}
        }

    # Aggregate statistics
    by_supplier = {}
    by_source = {}
    by_bill = {}

    for signup in beta_signups:
        # By supplier
        supplier = signup["currentSupplier"]
        by_supplier[supplier] = by_supplier.get(supplier, 0) + 1

        # By source
        source = signup["hearAbout"]
        by_source[source] = by_source.get(source, 0) + 1

        # By bill range
        bill = signup["monthlyBill"]
        by_bill[bill] = by_bill.get(bill, 0) + 1

    return {
        "total": len(beta_signups),
        "bySupplier": by_supplier,
        "bySource": by_source,
        "byBillRange": by_bill,
        "latestSignup": beta_signups[-1]["signupDate"] if beta_signups else None
    }


@router.post("/verify-code")
async def verify_beta_code(code: str = Body(..., max_length=50, embed=True)):
    """Verify beta access code is valid"""
    # Use constant-time comparison to prevent timing-based enumeration
    is_valid = any(
        hmac.compare_digest(s["betaCode"], code)
        for s in beta_signups
    )

    if is_valid:
        return {"valid": True, "message": "Beta code verified"}
    else:
        raise HTTPException(
            status_code=404,
            detail="Invalid beta code"
        )
