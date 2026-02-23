"""
Configuration Tests - Written FIRST following TDD principles

Tests for:
- Settings loading from environment
- Settings validation
- Database URL formatting

RED phase: These tests verify the existing Settings class works correctly.
"""

import os
import pytest
from unittest.mock import patch


# =============================================================================
# SETTINGS TESTS
# =============================================================================


class TestSettings:
    """Tests for the Settings configuration class"""

    def test_settings_loads_from_env(self):
        """Test that settings loads from environment variables"""
        from config.settings import Settings

        # Create settings with test environment
        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
            "ENVIRONMENT": "test"
        }):
            settings = Settings()

            assert settings.timescaledb_url == "postgresql://test:test@localhost:5432/test"
            assert settings.jwt_secret == "test-secret-key"
            assert settings.environment == "test"

    def test_settings_validates_environment(self):
        """Test that environment must be one of allowed values"""
        from config.settings import Settings
        from pydantic import ValidationError

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
            "ENVIRONMENT": "invalid_environment"  # Invalid
        }):
            with pytest.raises(ValidationError):
                Settings()

    def test_settings_default_environment(self):
        """Test default environment is development"""
        from config.settings import Settings

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
        }, clear=False):
            # Remove ENVIRONMENT if it exists
            env = os.environ.copy()
            env.pop("ENVIRONMENT", None)
            with patch.dict(os.environ, env, clear=True):
                # Force required fields
                with patch.dict(os.environ, {
                    "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
                    "JWT_SECRET": "test-secret-key",
                    "FLATPEAK_API_KEY": "test-flatpeak",
                    "NREL_API_KEY": "test-nrel",
                }):
                    settings = Settings()
                    assert settings.environment == "development"

    def test_database_url_format(self):
        """Test database URL is properly formatted"""
        from config.settings import Settings

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://user:pass@host:5432/db",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
        }):
            settings = Settings()
            assert settings.timescaledb_url.startswith("postgresql://")

    def test_cors_origins_parsing(self):
        """Test CORS origins can be parsed from JSON string"""
        from config.settings import Settings

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
            "CORS_ORIGINS": '["http://localhost:3000","http://localhost:8000","https://app.example.com"]'
        }):
            settings = Settings()

            assert len(settings.cors_origins) == 3
            assert "http://localhost:3000" in settings.cors_origins
            assert "https://app.example.com" in settings.cors_origins

    def test_is_production_property(self):
        """Test is_production property works correctly"""
        from config.settings import Settings

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key-that-is-at-least-32-chars-long-for-production",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
            "ENVIRONMENT": "production"
        }):
            settings = Settings()

            assert settings.is_production is True
            assert settings.is_development is False

    def test_is_development_property(self):
        """Test is_development property works correctly"""
        from config.settings import Settings

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
            "ENVIRONMENT": "development"
        }):
            settings = Settings()

            assert settings.is_development is True
            assert settings.is_production is False

    def test_api_prefix_default(self):
        """Test API prefix has correct default"""
        from config.settings import Settings

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
        }):
            settings = Settings()

            assert settings.api_prefix == "/api/v1"

    def test_rate_limit_defaults(self):
        """Test rate limit defaults are sensible"""
        from config.settings import Settings

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
        }):
            settings = Settings()

            assert settings.rate_limit_per_minute == 100
            assert settings.rate_limit_per_hour == 1000

    def test_model_config_defaults(self):
        """Test ML model config defaults"""
        from config.settings import Settings

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
        }):
            settings = Settings()

            assert settings.model_forecast_hours == 24
            assert settings.model_retrain_interval_days == 7
            assert settings.model_accuracy_threshold_mape == 10.0

    def test_gdpr_compliance_settings(self):
        """Test GDPR compliance settings"""
        from config.settings import Settings

        with patch.dict(os.environ, {
            "TIMESCALEDB_URL": "postgresql://test:test@localhost:5432/test",
            "JWT_SECRET": "test-secret-key",
            "FLATPEAK_API_KEY": "test-flatpeak",
            "NREL_API_KEY": "test-nrel",
            "DATA_RETENTION_DAYS": "365",
            "DATA_RESIDENCY": "UK"
        }):
            settings = Settings()

            assert settings.data_retention_days == 365
            assert settings.data_residency == "UK"
            assert settings.consent_required is True  # Default


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
        assert db_manager.supabase_client is None  # Not initialized yet
        assert db_manager.timescale_pool is None  # Not initialized yet
        assert db_manager.redis_client is None  # Not initialized yet

    @pytest.mark.asyncio
    async def test_get_redis_returns_none_if_not_initialized(self):
        """Test get_redis_client returns None if not initialized"""
        from config.database import DatabaseManager

        db_manager = DatabaseManager()

        result = await db_manager.get_redis_client()
        assert result is None

    def test_get_supabase_returns_none_if_not_initialized(self):
        """Test get_supabase_client returns None if not initialized"""
        from config.database import DatabaseManager

        db_manager = DatabaseManager()

        result = db_manager.get_supabase_client()
        assert result is None
