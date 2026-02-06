"""
Application Settings and Configuration Management

Uses pydantic-settings for type-safe configuration from environment variables.
"""

from typing import Optional, List
from pydantic import Field, field_validator
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
        default=["http://localhost:3000", "http://localhost:8000"],
        validation_alias="CORS_ORIGINS"
    )

    # Database - Supabase (optional for local dev)
    supabase_url: Optional[str] = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_anon_key: Optional[str] = Field(default=None, validation_alias="SUPABASE_ANON_KEY")
    supabase_service_key: Optional[str] = Field(default=None, validation_alias="SUPABASE_SERVICE_KEY")

    # Database - TimescaleDB
    timescaledb_url: str = Field(validation_alias="TIMESCALEDB_URL")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", validation_alias="REDIS_URL")
    redis_password: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")

    # Authentication
    jwt_secret: str = Field(validation_alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, validation_alias="JWT_EXPIRATION_HOURS")

    # External APIs
    flatpeak_api_key: str = Field(validation_alias="FLATPEAK_API_KEY")
    nrel_api_key: str = Field(validation_alias="NREL_API_KEY")
    iea_api_key: Optional[str] = Field(default=None, validation_alias="IEA_API_KEY")
    utilityapi_key: Optional[str] = Field(default=None, validation_alias="UTILITYAPI_KEY")
    openvolt_api_key: Optional[str] = Field(default=None, validation_alias="OPENVOLT_API_KEY")

    # Rate Limiting
    rate_limit_per_minute: int = Field(default=100, validation_alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(default=1000, validation_alias="RATE_LIMIT_PER_HOUR")

    # GDPR & Compliance
    data_retention_days: int = Field(default=730, validation_alias="DATA_RETENTION_DAYS")
    consent_required: bool = Field(default=True, validation_alias="CONSENT_REQUIRED")
    data_residency: str = Field(default="EU", validation_alias="DATA_RESIDENCY")

    # ML Model Configuration
    model_forecast_hours: int = Field(default=24, validation_alias="MODEL_FORECAST_HOURS")
    model_retrain_interval_days: int = Field(default=7, validation_alias="MODEL_RETRAIN_INTERVAL_DAYS")
    model_accuracy_threshold_mape: float = Field(default=10.0, validation_alias="MODEL_ACCURACY_THRESHOLD_MAPE")

    # Feature Flags
    enable_auto_switching: bool = Field(default=False, validation_alias="ENABLE_AUTO_SWITCHING")
    enable_load_optimization: bool = Field(default=True, validation_alias="ENABLE_LOAD_OPTIMIZATION")
    enable_real_time_updates: bool = Field(default=True, validation_alias="ENABLE_REAL_TIME_UPDATES")

    # Monitoring
    sentry_dsn: Optional[str] = Field(default=None, validation_alias="SENTRY_DSN")
    prometheus_port: int = Field(default=9090, validation_alias="PROMETHEUS_PORT")

    # Celery
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Ensure environment is valid"""
        allowed = ["development", "staging", "production", "test"]
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set Celery URLs based on Redis
        if not self.celery_broker_url:
            self.celery_broker_url = self.redis_url
        if not self.celery_result_backend:
            self.celery_result_backend = self.redis_url

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment == "development"


# Global settings instance
settings = Settings()
