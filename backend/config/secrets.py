"""
Secrets Manager

Provides secure secret retrieval from:
1. 1Password (production)
2. Environment variables (development)
3. Local .env file (testing)

Uses 1Password CLI (op) for secure secrets management in production.
"""

import os
import subprocess
from typing import Optional, Dict
from functools import lru_cache

import structlog

from config.settings import settings


logger = structlog.get_logger()


class SecretsError(Exception):
    """Exception raised when secret retrieval fails"""
    pass


class SecretsManager:
    """
    Manages secure retrieval of secrets.

    In production, uses 1Password CLI.
    In development, uses environment variables.
    """

    # 1Password vault and item references
    OP_VAULT = "electricity-optimizer"

    # Mapping of secret names to 1Password item.field paths
    SECRET_MAPPINGS = {
        "jwt_secret": "api-secrets.jwt_secret",
        "supabase_service_key": "supabase.service_key",
        "supabase_anon_key": "supabase.anon_key",
        "flatpeak_api_key": "pricing-apis.flatpeak",
        "nrel_api_key": "pricing-apis.nrel",
        "iea_api_key": "pricing-apis.iea",
        "redis_password": "infrastructure.redis_password",
        "postgres_password": "infrastructure.postgres_password",
        "sentry_dsn": "monitoring.sentry_dsn",
    }

    def __init__(self, use_1password: bool = None):
        """
        Initialize secrets manager.

        Args:
            use_1password: Force 1Password usage (auto-detects if not specified)
        """
        if use_1password is None:
            self.use_1password = settings.is_production and self._is_op_available()
        else:
            self.use_1password = use_1password

        self._cache: Dict[str, str] = {}

        if self.use_1password:
            logger.info("secrets_manager_using_1password")
        else:
            logger.info("secrets_manager_using_env_vars")

    def _is_op_available(self) -> bool:
        """Check if 1Password CLI is available and authenticated"""
        try:
            result = subprocess.run(
                ["op", "whoami"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_secret(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a secret value.

        Args:
            name: Secret name (e.g., "jwt_secret")
            default: Default value if secret not found

        Returns:
            Secret value or default

        Raises:
            SecretsError: If secret not found and no default provided
        """
        # Check cache first
        if name in self._cache:
            return self._cache[name]

        value = None

        if self.use_1password:
            value = self._get_from_1password(name)

        if value is None:
            value = self._get_from_env(name)

        if value is None:
            if default is not None:
                return default
            raise SecretsError(f"Secret '{name}' not found")

        # Cache the value
        self._cache[name] = value
        return value

    def _get_from_1password(self, name: str) -> Optional[str]:
        """Get secret from 1Password"""
        if name not in self.SECRET_MAPPINGS:
            logger.warning("secret_not_mapped", name=name)
            return None

        item_field = self.SECRET_MAPPINGS[name]

        try:
            result = subprocess.run(
                [
                    "op", "read",
                    f"op://{self.OP_VAULT}/{item_field}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                value = result.stdout.strip()
                logger.debug("secret_retrieved_from_1password", name=name)
                return value
            else:
                logger.warning(
                    "1password_read_failed",
                    name=name,
                    error=result.stderr,
                )
                return None

        except subprocess.TimeoutExpired:
            logger.error("1password_timeout", name=name)
            return None
        except Exception as e:
            logger.error("1password_error", name=name, error=str(e))
            return None

    def _get_from_env(self, name: str) -> Optional[str]:
        """Get secret from environment variable"""
        env_name = name.upper()
        value = os.environ.get(env_name)

        if value:
            logger.debug("secret_retrieved_from_env", name=name)

        return value

    def clear_cache(self) -> None:
        """Clear the secrets cache"""
        self._cache.clear()
        logger.info("secrets_cache_cleared")

    @staticmethod
    @lru_cache(maxsize=1)
    def get_instance() -> "SecretsManager":
        """Get singleton instance of SecretsManager"""
        return SecretsManager()


# Convenience functions


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a secret value.

    Args:
        name: Secret name
        default: Default value if not found

    Returns:
        Secret value
    """
    return SecretsManager.get_instance().get_secret(name, default)


def require_secret(name: str) -> str:
    """
    Get a required secret value.

    Args:
        name: Secret name

    Returns:
        Secret value

    Raises:
        SecretsError: If secret not found
    """
    value = get_secret(name)
    if value is None:
        raise SecretsError(f"Required secret '{name}' not found")
    return value


# Pre-defined secret getters


def get_jwt_secret() -> str:
    """Get JWT signing secret"""
    return require_secret("jwt_secret")


def get_supabase_service_key() -> str:
    """Get Supabase service role key"""
    return require_secret("supabase_service_key")


def get_database_password() -> str:
    """Get database password"""
    return require_secret("postgres_password")


def get_redis_password() -> Optional[str]:
    """Get Redis password (optional)"""
    return get_secret("redis_password")
