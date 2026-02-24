"""
Application Settings and Configuration Management

Uses pydantic-settings for type-safe configuration from environment variables.
"""

import os
from typing import Optional, List
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    app_name: str = "Electricity Optimizer API"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    debug: bool = Field(default=False)

    # API Configuration
    api_prefix: str = "/api/v1"
    backend_port: int = Field(default=8000, validation_alias="BACKEND_PORT")

    # CORS
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:8000",
        ],
        validation_alias="CORS_ORIGINS"
    )

    # Database - Neon PostgreSQL
    timescaledb_url: Optional[str] = Field(default=None, validation_alias="TIMESCALEDB_URL")
    database_url: Optional[str] = Field(default=None, validation_alias="DATABASE_URL")

    # Redis
    redis_url: Optional[str] = Field(default=None, validation_alias="REDIS_URL")
    redis_password: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")

    # Internal API Key (HMAC signing for service-to-service auth)
    jwt_secret: str = Field(default="dev-secret-change-in-production", validation_alias="JWT_SECRET")

    # Service-to-service API key (must NOT be the same as jwt_secret)
    internal_api_key: Optional[str] = Field(default=None, validation_alias="INTERNAL_API_KEY")

    # External APIs
    flatpeak_api_key: Optional[str] = Field(default=None, validation_alias="FLATPEAK_API_KEY")
    nrel_api_key: Optional[str] = Field(default=None, validation_alias="NREL_API_KEY")
    iea_api_key: Optional[str] = Field(default=None, validation_alias="IEA_API_KEY")
    utilityapi_key: Optional[str] = Field(default=None, validation_alias="UTILITYAPI_KEY")
    openvolt_api_key: Optional[str] = Field(default=None, validation_alias="OPENVOLT_API_KEY")
    openweathermap_api_key: Optional[str] = Field(default=None, validation_alias="OPENWEATHERMAP_API_KEY")

    # Rate Limiting
    rate_limit_per_minute: int = Field(default=100, validation_alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=1000, validation_alias="RATE_LIMIT_PER_HOUR")

    # GDPR & Compliance
    data_retention_days: int = Field(default=730, validation_alias="DATA_RETENTION_DAYS")
    consent_required: bool = Field(default=True, validation_alias="CONSENT_REQUIRED")
    data_residency: str = Field(default="US", validation_alias="DATA_RESIDENCY")

    # ML Model Configuration
    model_path: Optional[str] = Field(default=None, validation_alias="MODEL_PATH")
    model_forecast_hours: int = Field(default=24, validation_alias="MODEL_FORECAST_HOURS")
    model_retrain_interval_days: int = Field(default=7, validation_alias="MODEL_RETRAIN_INTERVAL_DAYS")
    model_accuracy_threshold_mape: float = Field(default=10.0, validation_alias="MODEL_ACCURACY_THRESHOLD_MAPE")

    # Email - SendGrid (primary)
    sendgrid_api_key: Optional[str] = Field(default=None, validation_alias="SENDGRID_API_KEY")
    # Email - SMTP (fallback)
    smtp_host: Optional[str] = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_username: Optional[str] = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(default=None, validation_alias="SMTP_PASSWORD")
    # Email - Common
    email_from_address: str = Field(default="noreply@electricity-optimizer.app", validation_alias="EMAIL_FROM_ADDRESS")
    email_from_name: str = Field(default="Electricity Optimizer", validation_alias="EMAIL_FROM_NAME")

    # Stripe Billing
    stripe_secret_key: Optional[str] = Field(default=None, validation_alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: Optional[str] = Field(default=None, validation_alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_pro: Optional[str] = Field(default=None, validation_alias="STRIPE_PRICE_PRO")
    stripe_price_business: Optional[str] = Field(default=None, validation_alias="STRIPE_PRICE_BUSINESS")

    # Feature Flags
    enable_auto_switching: bool = Field(default=False, validation_alias="ENABLE_AUTO_SWITCHING")
    enable_load_optimization: bool = Field(default=True, validation_alias="ENABLE_LOAD_OPTIMIZATION")
    enable_real_time_updates: bool = Field(default=True, validation_alias="ENABLE_REAL_TIME_UPDATES")

    # Monitoring
    sentry_dsn: Optional[str] = Field(default=None, validation_alias="SENTRY_DSN")
    prometheus_port: int = Field(default=9090, validation_alias="PROMETHEUS_PORT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Ensure environment is valid"""
        allowed = ["development", "staging", "production", "test"]
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Ensure JWT secret is not using default value in production"""
        env = os.environ.get("ENVIRONMENT", "development")
        insecure_defaults = [
            "dev-secret-change-in-production",
            "your-super-secret-key-change-in-production",
            "dev-local-secret-key-2026",
            "secret",
            "changeme",
        ]
        if env == "production" and v in insecure_defaults:
            raise ValueError(
                "CRITICAL: JWT_SECRET must be set to a strong, unique value in production. "
                "Do not use default/development secrets."
            )
        if env == "production" and len(v) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters in production."
            )
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment == "development"

    @property
    def effective_database_url(self) -> Optional[str]:
        """Get the effective database URL (DATABASE_URL takes priority over TIMESCALEDB_URL)"""
        return self.database_url or self.timescaledb_url


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance (FastAPI dependency-injection compatible)."""
    return settings
