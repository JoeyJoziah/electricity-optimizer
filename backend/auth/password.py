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


def generate_password_hash(password: str) -> str:
    """
    Generate secure password hash using PBKDF2-SHA256.

    Note: In production with Neon Auth (Better Auth), password hashing
    is handled by the auth service. This is for local testing only.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    import hashlib
    import secrets

    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        600000  # OWASP 2023 recommendation for PBKDF2-SHA256
    ).hex()

    return f"{salt}${hashed}"


def verify_password_hash(password: str, hashed: str) -> bool:
    """
    Verify password against hash.

    Uses hmac.compare_digest for constant-time comparison to prevent
    timing side-channel attacks.

    Args:
        password: Plain text password
        hashed: Stored hash

    Returns:
        True if password matches
    """
    import hashlib
    import hmac

    try:
        salt, stored_hash = hashed.split('$')
        computed_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            600000  # OWASP 2023 recommendation for PBKDF2-SHA256
        ).hex()
        return hmac.compare_digest(computed_hash, stored_hash)
    except Exception:
        return False
