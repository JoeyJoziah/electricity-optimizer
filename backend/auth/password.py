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

# Top 200 most common passwords (NIST SP 800-63B compliance).
# Checked case-insensitively against user input.
COMMON_PASSWORDS: frozenset[str] = frozenset({
    "123456", "password", "12345678", "qwerty", "123456789", "12345", "1234",
    "111111", "1234567", "dragon", "123123", "baseball", "abc123", "football",
    "monkey", "letmein", "shadow", "master", "666666", "qwertyuiop",
    "123321", "mustang", "1234567890", "michael", "654321", "superman",
    "1qaz2wsx", "7777777", "121212", "000000", "qazwsx", "123qwe",
    "killer", "trustno1", "jordan", "jennifer", "zxcvbnm", "asdfgh",
    "hunter", "buster", "soccer", "harley", "batman", "andrew", "tigger",
    "sunshine", "iloveyou", "2000", "charlie", "robert", "thomas", "hockey",
    "ranger", "daniel", "starwars", "klaster", "112233", "george", "computer",
    "michelle", "jessica", "pepper", "1111", "zxcvbn", "555555", "11111111",
    "131313", "freedom", "777777", "pass", "maggie", "159753", "aaaaaa",
    "ginger", "princess", "joshua", "cheese", "amanda", "summer", "love",
    "ashley", "nicole", "chelsea", "biteme", "matthew", "access", "yankees",
    "987654321", "dallas", "austin", "thunder", "taylor", "matrix",
    "minecraft", "william", "corvette", "hello", "martin", "heather",
    "secret", "merlin", "diamond", "1234qwer", "gfhjkm", "hammer",
    "silver", "222222", "88888888", "anthony", "justin", "test", "bailey",
    "q1w2e3r4t5", "patrick", "internet", "scooter", "orange", "11111",
    "golfer", "cookie", "richard", "samantha", "bigdog", "guitar",
    "jackson", "whatever", "mickey", "chicken", "sparky", "snoopy",
    "maverick", "phoenix", "camaro", "peanut", "morgan", "welcome",
    "falcon", "cowboy", "ferrari", "samsung", "andrea", "smokey",
    "steelers", "joseph", "mercedes", "dakota", "arsenal", "eagles",
    "melissa", "boomer", "booboo", "spider", "nascar", "tigers", "yellow",
    "xtreme", "gateway", "marina", "diablo", "bulldogs", "compaq",
    "purple", "hardcore", "banana", "junior", "hannah", "alexander",
    "william123", "passw0rd", "abcdef", "letmein1", "trustno1!", "admin",
    "administrator", "welcome1", "changeme", "default", "guest", "root",
    "login", "master1", "password1", "password123", "p@ssw0rd", "p@ssword",
    "qwerty123", "abc1234", "iloveu", "monkey1", "dragon1",
})


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

    # Check against common passwords (case-insensitive)
    if password.lower() in COMMON_PASSWORDS:
        errors.append("Password is too common and easily guessed")

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
        "not_common": password.lower() not in COMMON_PASSWORDS,
    }

    # Score based on checks
    score = sum(checks.values())

    # Bonus for extra length
    if len(password) >= 16:
        score += 1
    if len(password) >= 20:
        score += 1

    # Determine strength level
    if score >= 8:
        strength = "very_strong"
    elif score >= 6:
        strength = "strong"
    elif score >= 4:
        strength = "medium"
    elif score >= 2:
        strength = "weak"
    else:
        strength = "very_weak"

    return {
        "score": score,
        "max_score": 8,
        "strength": strength,
        "checks": checks,
        "valid": all(checks.values()),
    }
