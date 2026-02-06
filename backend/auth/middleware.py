"""
Authentication Middleware

Provides FastAPI dependencies for authentication and authorization.
"""

from typing import Optional, List

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

import structlog

from auth.jwt_handler import (
    jwt_handler,
    InvalidTokenError,
    TokenExpiredError,
    TokenRevokedError,
)


logger = structlog.get_logger()


# Security scheme for JWT Bearer token
security = HTTPBearer(auto_error=False)


# =============================================================================
# TOKEN DATA MODEL
# =============================================================================


class TokenData(BaseModel):
    """Extracted data from JWT token"""
    user_id: str
    email: Optional[str] = None
    scopes: List[str] = []
    token_type: str = "access"


# =============================================================================
# AUTHENTICATION DEPENDENCIES
# =============================================================================


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenData:
    """
    Get current authenticated user from JWT token.

    This dependency requires a valid JWT token.

    Args:
        credentials: Bearer token from Authorization header

    Returns:
        TokenData with user information

    Raises:
        HTTPException 401: If token is missing, invalid, or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        logger.warning("missing_auth_token")
        raise credentials_exception

    token = credentials.credentials

    try:
        payload = jwt_handler.verify_token(token, expected_type="access")

        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception

        return TokenData(
            user_id=user_id,
            email=payload.get("email"),
            scopes=payload.get("scopes", []),
            token_type=payload.get("type", "access"),
        )

    except TokenExpiredError:
        logger.warning("token_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except TokenRevokedError:
        logger.warning("token_revoked")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except InvalidTokenError as e:
        logger.warning("invalid_token", error=str(e))
        raise credentials_exception


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenData]:
    """
    Get current user if authenticated, None otherwise.

    This dependency does not require authentication.

    Args:
        credentials: Bearer token from Authorization header

    Returns:
        TokenData if authenticated, None otherwise
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# =============================================================================
# AUTHORIZATION DEPENDENCIES
# =============================================================================


def require_permission(required_scope: str):
    """
    Create a dependency that requires a specific permission scope.

    Args:
        required_scope: Required scope name

    Returns:
        Dependency function that checks for the scope
    """
    async def check_permission(
        current_user: TokenData = Depends(get_current_user),
    ) -> TokenData:
        """Check if user has required permission"""
        if required_scope not in current_user.scopes:
            logger.warning(
                "permission_denied",
                user_id=current_user.user_id,
                required_scope=required_scope,
                user_scopes=current_user.scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{required_scope}' required",
            )
        return current_user

    return check_permission


def require_permissions(required_scopes: List[str]):
    """
    Create a dependency that requires multiple permission scopes.

    Args:
        required_scopes: List of required scope names

    Returns:
        Dependency function that checks for all scopes
    """
    async def check_permissions(
        current_user: TokenData = Depends(get_current_user),
    ) -> TokenData:
        """Check if user has all required permissions"""
        missing_scopes = [
            scope for scope in required_scopes
            if scope not in current_user.scopes
        ]

        if missing_scopes:
            logger.warning(
                "permissions_denied",
                user_id=current_user.user_id,
                missing_scopes=missing_scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(missing_scopes)}",
            )

        return current_user

    return check_permissions


def require_any_permission(required_scopes: List[str]):
    """
    Create a dependency that requires at least one of the permission scopes.

    Args:
        required_scopes: List of acceptable scope names

    Returns:
        Dependency function that checks for any scope
    """
    async def check_any_permission(
        current_user: TokenData = Depends(get_current_user),
    ) -> TokenData:
        """Check if user has at least one required permission"""
        has_permission = any(
            scope in current_user.scopes
            for scope in required_scopes
        )

        if not has_permission:
            logger.warning(
                "permission_denied",
                user_id=current_user.user_id,
                required_any=required_scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of these permissions required: {', '.join(required_scopes)}",
            )

        return current_user

    return check_any_permission


# Convenience dependency for admin-only routes
require_admin = require_permission("admin")


# =============================================================================
# RATE LIMITING HELPER
# =============================================================================


class RateLimitState:
    """Track rate limit state for a user"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.request_count = 0
        self.failed_attempts = 0
        self.locked_until = None
