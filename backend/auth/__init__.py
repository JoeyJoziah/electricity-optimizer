"""
Authentication Module

Provides Neon Auth session validation and password utilities
for the Electricity Optimizer API.
"""

__all__ = [
    "SessionData",
    "get_current_user",
    "get_current_user_optional",
    "validate_password",
]


def __getattr__(name):
    """Lazy load submodules to avoid import issues during testing"""
    if name in ("SessionData", "get_current_user", "get_current_user_optional"):
        from auth.neon_auth import SessionData, get_current_user, get_current_user_optional
        return locals()[name]
    elif name == "validate_password":
        from auth.password import validate_password
        return validate_password
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
