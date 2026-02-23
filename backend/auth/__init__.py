"""
Authentication Module

Provides JWT token management, Neon Auth session validation,
and authentication middleware for the Electricity Optimizer API.
"""

# Use lazy imports to avoid circular dependencies and settings validation during testing
__all__ = [
    "JWTHandler",
    "InvalidTokenError",
    "TokenExpiredError",
    "TokenRevokedError",
    "SessionData",
    "get_current_user",
    "get_current_user_optional",
    "validate_password",
]


def __getattr__(name):
    """Lazy load submodules to avoid import issues during testing"""
    if name in ("JWTHandler", "InvalidTokenError", "TokenExpiredError", "TokenRevokedError"):
        from auth.jwt_handler import JWTHandler, InvalidTokenError, TokenExpiredError, TokenRevokedError
        return locals()[name]
    elif name in ("SessionData", "get_current_user", "get_current_user_optional"):
        from auth.neon_auth import SessionData, get_current_user, get_current_user_optional
        return locals()[name]
    elif name == "validate_password":
        from auth.password import validate_password
        return validate_password
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
