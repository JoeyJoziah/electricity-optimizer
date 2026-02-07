"""
Beta Signup API Endpoint
Handles beta user registration and welcome email sending
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
import secrets
import re

router = APIRouter(prefix="/beta", tags=["beta"])


class BetaSignupRequest(BaseModel):
    """Beta signup form data"""
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    postcode: str = Field(..., min_length=5, max_length=10)
    currentSupplier: str
    monthlyBill: str
    hearAbout: str


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
    """Send welcome email to beta user"""
    # TODO: Implement actual email sending (SendGrid, AWS SES, etc.)
    # For now, just log
    print(f"📧 Sending welcome email to {email}")
    print(f"   Name: {name}")
    print(f"   Beta Code: {beta_code}")

    # Email template would be here
    subject = "Welcome to Electricity Optimizer Beta! 🎉"
    body = f"""
    Hi {name},

    Congratulations! You've been accepted to the Electricity Optimizer beta program.

    Your Beta Access Code: {beta_code}

    Here's what to expect:

    1. **Get Started**: Visit https://electricity-optimizer.app/auth/signup
       Use your beta code: {beta_code}

    2. **Connect Your Data**: We support UK smart meters via UtilityAPI
       (Optional - you can skip and see demo data)

    3. **Explore Features**:
       - Real-time electricity price tracking
       - 24-hour price forecasting
       - Automatic supplier switching recommendations
       - Smart appliance scheduling

    4. **Share Feedback**: Your feedback shapes the product!
       - In-app feedback widget (bottom-right corner)
       - Direct email: feedback@electricity-optimizer.app
       - Weekly survey (5 min)

    **Support**:
    - Email: support@electricity-optimizer.app
    - Response time: <24 hours

    **Beta Perks**:
    - Lifetime 50% discount when we launch
    - Priority support
    - Shape the product

    Thank you for being an early supporter! 🚀

    Best regards,
    The Electricity Optimizer Team

    P.S. First 50 beta users get lifetime 50% discount!
    """

    # In production, use email service:
    # await email_service.send(to=email, subject=subject, body=body)

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
async def get_beta_count():
    """Get total beta signups count"""
    return {
        "total": len(beta_signups),
        "target": 50,
        "percentage": (len(beta_signups) / 50) * 100
    }


@router.get("/signups/stats")
async def get_beta_stats():
    """Get beta signup statistics"""
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
async def verify_beta_code(code: str):
    """Verify beta access code is valid"""
    is_valid = any(s["betaCode"] == code for s in beta_signups)

    if is_valid:
        return {"valid": True, "message": "Beta code verified"}
    else:
        raise HTTPException(
            status_code=404,
            detail="Invalid beta code"
        )
