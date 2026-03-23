"""
Password Validation and Security

Provides password validation against security requirements.

Audit 2026-03-19 finding 11-P1-3: strengthened beyond basic complexity rules
to include sequential character detection, repeated character limits, and
maximum length enforcement.
"""

import re

# Password requirements
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
REQUIRE_UPPERCASE = True
REQUIRE_LOWERCASE = True
REQUIRE_DIGIT = True
REQUIRE_SPECIAL = True
SPECIAL_CHARACTERS = r"!@#$%^&*()_+-=[]{}|;:,.<>?"

# Maximum consecutive identical characters allowed (e.g., "aaa" fails at 3)
MAX_CONSECUTIVE_IDENTICAL = 3

# Sequential patterns to detect (both forward and reverse)
_SEQUENTIAL_ALPHA = "abcdefghijklmnopqrstuvwxyz"
_SEQUENTIAL_NUMERIC = "0123456789"
_SEQUENTIAL_KEYBOARD_ROWS = [
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
]
_MIN_SEQUENTIAL_LENGTH = 4  # minimum run of sequential chars to flag

# Top 200 most common passwords (NIST SP 800-63B compliance).
# Checked case-insensitively against user input.
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "123456",
        "password",
        "12345678",
        "qwerty",
        "123456789",
        "12345",
        "1234",
        "111111",
        "1234567",
        "dragon",
        "123123",
        "baseball",
        "abc123",
        "football",
        "monkey",
        "letmein",
        "shadow",
        "master",
        "666666",
        "qwertyuiop",
        "123321",
        "mustang",
        "1234567890",
        "michael",
        "654321",
        "superman",
        "1qaz2wsx",
        "7777777",
        "121212",
        "000000",
        "qazwsx",
        "123qwe",
        "killer",
        "trustno1",
        "jordan",
        "jennifer",
        "zxcvbnm",
        "asdfgh",
        "hunter",
        "buster",
        "soccer",
        "harley",
        "batman",
        "andrew",
        "tigger",
        "sunshine",
        "iloveyou",
        "2000",
        "charlie",
        "robert",
        "thomas",
        "hockey",
        "ranger",
        "daniel",
        "starwars",
        "klaster",
        "112233",
        "george",
        "computer",
        "michelle",
        "jessica",
        "pepper",
        "1111",
        "zxcvbn",
        "555555",
        "11111111",
        "131313",
        "freedom",
        "777777",
        "pass",
        "maggie",
        "159753",
        "aaaaaa",
        "ginger",
        "princess",
        "joshua",
        "cheese",
        "amanda",
        "summer",
        "love",
        "ashley",
        "nicole",
        "chelsea",
        "biteme",
        "matthew",
        "access",
        "yankees",
        "987654321",
        "dallas",
        "austin",
        "thunder",
        "taylor",
        "matrix",
        "minecraft",
        "william",
        "corvette",
        "hello",
        "martin",
        "heather",
        "secret",
        "merlin",
        "diamond",
        "1234qwer",
        "gfhjkm",
        "hammer",
        "silver",
        "222222",
        "88888888",
        "anthony",
        "justin",
        "test",
        "bailey",
        "q1w2e3r4t5",
        "patrick",
        "internet",
        "scooter",
        "orange",
        "11111",
        "golfer",
        "cookie",
        "richard",
        "samantha",
        "bigdog",
        "guitar",
        "jackson",
        "whatever",
        "mickey",
        "chicken",
        "sparky",
        "snoopy",
        "maverick",
        "phoenix",
        "camaro",
        "peanut",
        "morgan",
        "welcome",
        "falcon",
        "cowboy",
        "ferrari",
        "samsung",
        "andrea",
        "smokey",
        "steelers",
        "joseph",
        "mercedes",
        "dakota",
        "arsenal",
        "eagles",
        "melissa",
        "boomer",
        "booboo",
        "spider",
        "nascar",
        "tigers",
        "yellow",
        "xtreme",
        "gateway",
        "marina",
        "diablo",
        "bulldogs",
        "compaq",
        "purple",
        "hardcore",
        "banana",
        "junior",
        "hannah",
        "alexander",
        "william123",
        "passw0rd",
        "abcdef",
        "letmein1",
        "trustno1!",
        "admin",
        "administrator",
        "welcome1",
        "changeme",
        "default",
        "guest",
        "root",
        "login",
        "master1",
        "password1",
        "password123",
        "p@ssw0rd",
        "p@ssword",
        "qwerty123",
        "abc1234",
        "iloveu",
        "monkey1",
        "dragon1",
    }
)


def _has_consecutive_identical(password: str, max_run: int = MAX_CONSECUTIVE_IDENTICAL) -> bool:
    """Return True if *password* contains *max_run* or more identical consecutive chars."""
    if len(password) < max_run:
        return False
    count = 1
    for i in range(1, len(password)):
        if password[i] == password[i - 1]:
            count += 1
            if count >= max_run:
                return True
        else:
            count = 1
    return False


def _has_sequential_chars(password: str, min_run: int = _MIN_SEQUENTIAL_LENGTH) -> bool:
    """Return True if *password* contains a run of *min_run* sequential chars.

    Checks alphabetic (abc...), numeric (012...), and keyboard-row sequences
    in both forward and reverse directions.  Case-insensitive.
    """
    lower = password.lower()
    sequences = [_SEQUENTIAL_ALPHA, _SEQUENTIAL_NUMERIC, *_SEQUENTIAL_KEYBOARD_ROWS]

    for seq in sequences:
        rev = seq[::-1]
        for source in (seq, rev):
            for start in range(len(source) - min_run + 1):
                pattern = source[start : start + min_run]
                if pattern in lower:
                    return True
    return False


def validate_password(password: str) -> bool:
    """
    Validate password against security requirements.

    Requirements:
    - Minimum 12 characters, maximum 128
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - Not a common / breached password
    - No 3+ consecutive identical characters
    - No 4+ sequential characters (abc, 123, qwer, etc.)

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

    # Check maximum length (DoS prevention)
    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")

    # Check uppercase
    if REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")

    # Check lowercase
    if REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")

    # Check digit
    if REQUIRE_DIGIT and not re.search(r"\d", password):
        errors.append("Password must contain at least one digit")

    # Check special character
    if REQUIRE_SPECIAL and not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password):
        errors.append("Password must contain at least one special character")

    # Check consecutive identical characters (e.g., "aaa")
    if _has_consecutive_identical(password):
        errors.append(
            f"Password must not contain {MAX_CONSECUTIVE_IDENTICAL} or more identical consecutive characters"
        )

    # Check sequential characters (e.g., "abcd", "1234", "qwer")
    if _has_sequential_chars(password):
        errors.append("Password must not contain sequential characters (e.g., abcd, 1234, qwer)")

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
    checks = {
        "length": MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH,
        "uppercase": bool(re.search(r"[A-Z]", password)),
        "lowercase": bool(re.search(r"[a-z]", password)),
        "digit": bool(re.search(r"\d", password)),
        "special": bool(re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password)),
        "not_common": password.lower() not in COMMON_PASSWORDS,
        "no_consecutive": not _has_consecutive_identical(password),
        "no_sequential": not _has_sequential_chars(password),
    }

    # Score based on checks
    score = sum(checks.values())

    # Bonus for extra length
    if len(password) >= 16:
        score += 1
    if len(password) >= 20:
        score += 1

    # Determine strength level (max_score now 10: 8 checks + 2 length bonuses)
    if score >= 9:
        strength = "very_strong"
    elif score >= 7:
        strength = "strong"
    elif score >= 5:
        strength = "medium"
    elif score >= 3:
        strength = "weak"
    else:
        strength = "very_weak"

    return {
        "score": score,
        "max_score": 10,
        "strength": strength,
        "checks": checks,
        "valid": all(checks.values()),
    }
