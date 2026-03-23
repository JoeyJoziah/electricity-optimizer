"""
Configuration Tests - Written FIRST following TDD principles

Tests for:
- Settings loading from environment
- Settings validation
- Database URL formatting

RED phase: These tests verify the existing Settings class works correctly.
"""

import os
from unittest.mock import patch

import pytest

# =============================================================================
# SETTINGS TESTS
# =============================================================================


class TestSettings:
    """Tests for the Settings configuration class"""

    def test_settings_loads_from_env(self):
        """Test that settings loads from environment variables"""
        from config.settings import Settings

        # Create settings with test environment
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "JWT_SECRET": "test-secret-key",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
                "ENVIRONMENT": "test",
            },
        ):
            settings = Settings()

            assert settings.database_url == "postgresql://test:test@localhost:5432/test"
            assert settings.jwt_secret == "test-secret-key"
            assert settings.environment == "test"

    def test_settings_validates_environment(self):
        """Test that environment must be one of allowed values"""
        from pydantic import ValidationError

        from config.settings import Settings

        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                    "JWT_SECRET": "test-secret-key",
                    "FLATPEAK_API_KEY": "test-flatpeak",
                    "NREL_API_KEY": "test-nrel",
                    "ENVIRONMENT": "invalid_environment",  # Invalid
                },
            ),
            pytest.raises(ValidationError),
        ):
            Settings()

    def test_settings_default_environment(self):
        """Test default environment is development"""
        from config.settings import Settings

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "JWT_SECRET": "test-secret-key",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
            },
            clear=False,
        ):
            # Remove ENVIRONMENT if it exists
            env = os.environ.copy()
            env.pop("ENVIRONMENT", None)
            with (
                patch.dict(os.environ, env, clear=True),
                patch.dict(
                    os.environ,
                    {
                        "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                        "JWT_SECRET": "test-secret-key",
                        "FLATPEAK_API_KEY": "test-flatpeak",
                        "NREL_API_KEY": "test-nrel",
                    },
                ),
            ):
                settings = Settings()
                assert settings.environment == "development"

    def test_database_url_format(self):
        """Test database URL is properly formatted"""
        from config.settings import Settings

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "JWT_SECRET": "test-secret-key",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
            },
        ):
            settings = Settings()
            assert settings.database_url.startswith("postgresql://")

    def test_cors_origins_parsing(self):
        """Test CORS origins can be parsed from JSON string"""
        from config.settings import Settings

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "JWT_SECRET": "test-secret-key",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
                "CORS_ORIGINS": '["http://localhost:3000","http://localhost:8000","https://app.example.com"]',
            },
        ):
            settings = Settings()

            assert len(settings.cors_origins) == 3
            assert "http://localhost:3000" in settings.cors_origins
            assert "https://app.example.com" in settings.cors_origins

    def test_is_production_property(self):
        """Test is_production property works correctly"""
        from config.settings import Settings

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "JWT_SECRET": "test-secret-key-that-is-at-least-32-chars-long-for-production",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
                "ENVIRONMENT": "production",
                "FIELD_ENCRYPTION_KEY": "a" * 64,
                "INTERNAL_API_KEY": "a" * 64,
                "BETTER_AUTH_SECRET": "b" * 64,
                "STRIPE_SECRET_KEY": "sk_test_placeholder_for_unit_tests",
                "RESEND_API_KEY": "re_test_placeholder_for_unit_tests",
                "OAUTH_STATE_SECRET": "c" * 64,
                "ML_MODEL_SIGNING_KEY": "d" * 64,
            },
        ):
            settings = Settings()

            assert settings.is_production is True
            assert settings.is_development is False

    def test_is_development_property(self):
        """Test is_development property works correctly"""
        from config.settings import Settings

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "JWT_SECRET": "test-secret-key",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
                "ENVIRONMENT": "development",
            },
        ):
            settings = Settings()

            assert settings.is_development is True
            assert settings.is_production is False

    def test_api_prefix_default(self):
        """Test API prefix has correct default"""
        from config.settings import Settings

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "JWT_SECRET": "test-secret-key",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
            },
        ):
            settings = Settings()

            assert settings.api_prefix == "/api/v1"

    def test_rate_limit_defaults(self):
        """Test rate limit defaults are sensible"""
        from config.settings import Settings

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "JWT_SECRET": "test-secret-key",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
            },
        ):
            settings = Settings()

            assert settings.rate_limit_per_minute == 100
            assert settings.rate_limit_per_hour == 1000

    def test_model_config_defaults(self):
        """Test ML model config defaults"""
        from config.settings import Settings

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "JWT_SECRET": "test-secret-key",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
            },
        ):
            settings = Settings()

            assert settings.model_forecast_hours == 24
            assert settings.model_retrain_interval_days == 7
            assert settings.model_accuracy_threshold_mape == 10.0

    def test_gdpr_compliance_settings(self):
        """Test GDPR compliance settings"""
        from config.settings import Settings

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
                "JWT_SECRET": "test-secret-key",
                "FLATPEAK_API_KEY": "test-flatpeak",
                "NREL_API_KEY": "test-nrel",
                "DATA_RETENTION_DAYS": "365",
                "DATA_RESIDENCY": "UK",
            },
        ):
            settings = Settings()

            assert settings.data_retention_days == 365
            assert settings.data_residency == "UK"
            assert settings.consent_required is True  # Default


# =============================================================================
# JWT SECRET SECURITY TESTS
# =============================================================================


class TestJWTSecretValidation:
    """Security hardening: JWT_SECRET must raise in production when absent."""

    def test_jwt_secret_raises_when_absent_in_production(self):
        """JWT_SECRET env var absent in production must raise ValueError."""
        from pydantic import ValidationError

        from config.settings import Settings

        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "ENVIRONMENT": "production",
            "FIELD_ENCRYPTION_KEY": "a" * 64,
            "INTERNAL_API_KEY": "a" * 64,
            "BETTER_AUTH_SECRET": "b" * 64,
            "STRIPE_SECRET_KEY": "sk_test_placeholder_for_unit_tests",
            "RESEND_API_KEY": "re_test_placeholder_for_unit_tests",
            "OAUTH_STATE_SECRET": "c" * 64,
            "ML_MODEL_SIGNING_KEY": "d" * 64,
        }
        # Explicitly ensure JWT_SECRET is NOT in env
        env.pop("JWT_SECRET", None)
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValidationError, match="JWT_SECRET"),
        ):
            Settings()

    def test_jwt_secret_raises_when_absent_in_staging(self):
        """JWT_SECRET env var absent in staging must raise ValueError."""
        from pydantic import ValidationError

        from config.settings import Settings

        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "ENVIRONMENT": "staging",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValidationError, match="JWT_SECRET"),
        ):
            Settings()

    def test_jwt_secret_auto_generates_in_development(self):
        """JWT_SECRET auto-generation is acceptable in development."""
        from config.settings import Settings

        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "ENVIRONMENT": "development",
        }
        # No JWT_SECRET — should auto-generate without error
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert len(settings.jwt_secret) >= 32

    @pytest.mark.parametrize(
        "insecure_value",
        [
            "password",
            "test",
            "default",
            "supersecret",
            "admin",
            "letmein",
            "changeme",
            "secret",
            "12345678",
            "jwt_secret",
            "jwt-secret",
            "my-secret",
            "development",
            "placeholder",
        ],
    )
    def test_jwt_secret_rejects_insecure_defaults_in_production(self, insecure_value):
        """All insecure default values must be rejected in production."""
        from pydantic import ValidationError

        from config.settings import Settings

        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "ENVIRONMENT": "production",
            "JWT_SECRET": insecure_value,
            "FIELD_ENCRYPTION_KEY": "a" * 64,
            "INTERNAL_API_KEY": "a" * 64,
            "BETTER_AUTH_SECRET": "b" * 64,
            "STRIPE_SECRET_KEY": "sk_test_placeholder_for_unit_tests",
            "RESEND_API_KEY": "re_test_placeholder_for_unit_tests",
            "OAUTH_STATE_SECRET": "c" * 64,
            "ML_MODEL_SIGNING_KEY": "d" * 64,
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValidationError, match="strong, unique value"),
        ):
            Settings()

    def test_jwt_secret_rejects_short_value_in_production(self):
        """JWT_SECRET shorter than 32 chars must be rejected in production."""
        from pydantic import ValidationError

        from config.settings import Settings

        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "ENVIRONMENT": "production",
            "JWT_SECRET": "short-but-not-insecure",  # 22 chars
            "FIELD_ENCRYPTION_KEY": "a" * 64,
            "INTERNAL_API_KEY": "a" * 64,
            "BETTER_AUTH_SECRET": "b" * 64,
            "STRIPE_SECRET_KEY": "sk_test_placeholder_for_unit_tests",
            "RESEND_API_KEY": "re_test_placeholder_for_unit_tests",
            "OAUTH_STATE_SECRET": "c" * 64,
            "ML_MODEL_SIGNING_KEY": "d" * 64,
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValidationError, match="at least 32 characters"),
        ):
            Settings()

    def test_jwt_secret_accepts_strong_value_in_production(self):
        """A strong 64-char hex secret must be accepted in production."""
        from config.settings import Settings

        strong_secret = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        env = {
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "ENVIRONMENT": "production",
            "JWT_SECRET": strong_secret,
            "FIELD_ENCRYPTION_KEY": "a" * 64,
            "INTERNAL_API_KEY": "b" * 64,
            "BETTER_AUTH_SECRET": "c" * 64,
            "STRIPE_SECRET_KEY": "sk_test_placeholder_for_unit_tests",
            "RESEND_API_KEY": "re_test_placeholder_for_unit_tests",
            "OAUTH_STATE_SECRET": "d" * 64,
            "ML_MODEL_SIGNING_KEY": "e" * 64,
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.jwt_secret == strong_secret


# =============================================================================
# DATABASE CONFIG TESTS
# =============================================================================


class TestDatabaseManager:
    """Tests for DatabaseManager configuration"""

    def test_database_manager_can_be_instantiated(self):
        """Test DatabaseManager can be created"""
        from config.database import DatabaseManager

        db_manager = DatabaseManager()

        assert db_manager is not None
        assert db_manager.timescale_pool is None  # Not initialized yet
        assert db_manager.redis_client is None  # Not initialized yet

    async def test_get_redis_returns_none_if_not_initialized(self):
        """Test get_redis_client returns None if not initialized"""
        from config.database import DatabaseManager

        db_manager = DatabaseManager()

        result = await db_manager.get_redis_client()
        assert result is None
