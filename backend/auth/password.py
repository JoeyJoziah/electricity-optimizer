"""
Password Validation and Security

Provides password validation against security requirements.
"""

import re
from typing import Optional


# Password requirements
MIN_PASSWORD_LENGTH = 12
REQUIRE_UPPERCASE = True
REQUIRE_LOWERCASE = True
REQUIRE_DIGIT = True
REQUIRE_SPECIAL = True
SPECIAL_CHARACTERS = r'!@#$%^&*()_+-=[]{}|;:,.<>?'


def validate_password(password: str) -> bool:
    """
    Validate password against security requirements.

    Requirements:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: Password to validate

    Returns:
        True if password is valid

    Raises:
        ValueError: If password doesn't meet requirements
    """
    errors = []

    # Check minimum length
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    # Check uppercase
    if REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")

    # Check lowercase
    if REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")

    # Check digit
    if REQUIRE_DIGIT and not re.search(r'\d', password):
        errors.append("Password must contain at least one digit")

    # Check special character
    if REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password):
        errors.append("Password must contain at least one special character")

    if errors:
        raise ValueError("; ".join(errors))

    return True


def check_password_strength(password: str) -> dict:
    """
    Check password strength and return detailed assessment.

    Args:
        password: Password to check

    Returns:
        Dict with strength assessment
    """
    score = 0
    checks = {
        "length": len(password) >= MIN_PASSWORD_LENGTH,
        "uppercase": bool(re.search(r'[A-Z]', password)),
        "lowercase": bool(re.search(r'[a-z]', password)),
        "digit": bool(re.search(r'\d', password)),
        "special": bool(re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password)),
    }

    # Score based on checks
    score = sum(checks.values())

    # Bonus for extra length
    if len(password) >= 16:
        score += 1
    if len(password) >= 20:
        score += 1

    # Determine strength level
    if score >= 7:
        strength = "very_strong"
    elif score >= 5:
        strength = "strong"
    elif score >= 4:
        strength = "medium"
    elif score >= 2:
        strength = "weak"
    else:
        strength = "very_weak"

    return {
        "score": score,
        "max_score": 7,
        "strength": strength,
        "checks": checks,
        "valid": all(checks.values()),
    }
