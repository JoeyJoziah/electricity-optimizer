"""
Authentication Module

Provides JWT token management, Supabase Auth integration,
and authentication middleware for the Electricity Optimizer API.
"""

# Use lazy imports to avoid circular dependencies and settings validation during testing
__all__ = [
    "JWTHandler",
    "InvalidTokenError",
    "TokenExpiredError",
    "TokenRevokedError",
    "SupabaseAuthService",
    "InvalidCredentialsError",
    "InvalidEmailError",
    "WeakPasswordError",
    "EmailAlreadyExistsError",
    "InvalidProviderError",
    "validate_password",
]


def __getattr__(name):
    """Lazy load submodules to avoid import issues during testing"""
    if name in ("JWTHandler", "InvalidTokenError", "TokenExpiredError", "TokenRevokedError"):
        from auth.jwt_handler import JWTHandler, InvalidTokenError, TokenExpiredError, TokenRevokedError
        return locals()[name]
    elif name in ("SupabaseAuthService", "InvalidCredentialsError", "InvalidEmailError",
                  "WeakPasswordError", "EmailAlreadyExistsError", "InvalidProviderError"):
        from auth.supabase_auth import (
            SupabaseAuthService, InvalidCredentialsError, InvalidEmailError,
            WeakPasswordError, EmailAlreadyExistsError, InvalidProviderError
        )
        return locals()[name]
    elif name == "validate_password":
        from auth.password import validate_password
        return validate_password
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
