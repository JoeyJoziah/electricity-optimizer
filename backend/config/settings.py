"""
Application Settings and Configuration Management

Uses pydantic-settings for type-safe configuration from environment variables.
"""

import json as _json
import os
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    app_name: str = "RateShift API"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    debug: bool = Field(default=False)

    # API Configuration
    api_prefix: str = "/api/v1"
    backend_port: int = Field(default=8000, validation_alias="BACKEND_PORT")

    # CORS — stored as str to avoid pydantic-settings JSON-parse failures on
    # comma-separated env var values.  Parsed into a list via the property.
    cors_origins_raw: str = Field(
        default='["http://localhost:3000","http://localhost:3001","http://localhost:8000"]',
        validation_alias="CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> List[str]:
        """Parse CORS origins from JSON array or comma-separated string."""
        raw = self.cors_origins_raw
        if not raw:
            return ["http://localhost:3000"]
        raw = raw.strip()
        if raw.startswith("["):
            try:
                return _json.loads(raw)
            except _json.JSONDecodeError:
                pass
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    # Database - Neon PostgreSQL
    database_url: Optional[str] = Field(default=None, validation_alias="DATABASE_URL")
    # Connection pool sizing (configurable for scaling without code changes)
    db_pool_size: int = Field(default=3, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=5, validation_alias="DB_MAX_OVERFLOW")

    # Redis
    redis_url: Optional[str] = Field(default=None, validation_alias="REDIS_URL")
    redis_password: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")

    # Internal API Key (HMAC signing for service-to-service auth)
    jwt_secret: str = Field(
        default_factory=lambda: __import__("secrets").token_hex(32),
        validation_alias="JWT_SECRET",
    )

    # Service-to-service API key (must NOT be the same as jwt_secret)
    internal_api_key: Optional[str] = Field(default=None, validation_alias="INTERNAL_API_KEY")

    # Better Auth session token signing secret
    better_auth_secret: Optional[str] = Field(default=None, validation_alias="BETTER_AUTH_SECRET")

    # External APIs
    flatpeak_api_key: Optional[str] = Field(default=None, validation_alias="FLATPEAK_API_KEY")
    nrel_api_key: Optional[str] = Field(default=None, validation_alias="NREL_API_KEY")
    nrel_api_base_url: str = Field(
        default="https://developer.nrel.gov/api/utility_rates/v3",
        validation_alias="NREL_API_BASE_URL",
    )
    iea_api_key: Optional[str] = Field(default=None, validation_alias="IEA_API_KEY")
    eia_api_key: Optional[str] = Field(default=None, validation_alias="EIA_API_KEY")
    utilityapi_key: Optional[str] = Field(default=None, validation_alias="UTILITYAPI_KEY")
    openvolt_api_key: Optional[str] = Field(default=None, validation_alias="OPENVOLT_API_KEY")
    openweathermap_api_key: Optional[str] = Field(
        default=None, validation_alias="OPENWEATHERMAP_API_KEY"
    )

    # Rate Scraping (Diffbot — free tier, 10K credits/month)
    diffbot_api_token: Optional[str] = Field(default=None, validation_alias="DIFFBOT_API_TOKEN")

    # Market Intelligence (Tavily — free tier, 1K searches/month)
    tavily_api_key: Optional[str] = Field(default=None, validation_alias="TAVILY_API_KEY")

    # Geocoding (Google Maps — free tier, 10K geocodes/month, card required)
    google_maps_api_key: Optional[str] = Field(default=None, validation_alias="GOOGLE_MAPS_API_KEY")

    # Push Notifications (OneSignal — free tier, unlimited mobile push)
    onesignal_app_id: Optional[str] = Field(default=None, validation_alias="ONESIGNAL_APP_ID")
    onesignal_rest_api_key: Optional[str] = Field(
        default=None, validation_alias="ONESIGNAL_REST_API_KEY"
    )

    # Uptime Monitoring (UptimeRobot — free tier, 50 monitors)
    uptimerobot_api_key: Optional[str] = Field(default=None, validation_alias="UPTIMEROBOT_API_KEY")

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
    model_retrain_interval_days: int = Field(
        default=7, validation_alias="MODEL_RETRAIN_INTERVAL_DAYS"
    )
    model_accuracy_threshold_mape: float = Field(
        default=10.0, validation_alias="MODEL_ACCURACY_THRESHOLD_MAPE"
    )

    # Email - Resend (primary)
    resend_api_key: Optional[str] = Field(default=None, validation_alias="RESEND_API_KEY")
    # Email - SMTP (fallback)
    smtp_host: Optional[str] = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_username: Optional[str] = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(default=None, validation_alias="SMTP_PASSWORD")
    # Email - Common
    email_from_address: str = Field(
        default="noreply@rateshift.app", validation_alias="EMAIL_FROM_ADDRESS"
    )
    email_from_name: str = Field(default="RateShift", validation_alias="EMAIL_FROM_NAME")

    # Stripe Billing
    stripe_secret_key: Optional[str] = Field(default=None, validation_alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: Optional[str] = Field(
        default=None, validation_alias="STRIPE_WEBHOOK_SECRET"
    )
    stripe_price_pro: Optional[str] = Field(default=None, validation_alias="STRIPE_PRICE_PRO")
    stripe_price_business: Optional[str] = Field(
        default=None, validation_alias="STRIPE_PRICE_BUSINESS"
    )

    # Billing redirect domain allowlist — stored as str to avoid pydantic-settings
    # JSON-parse failures on comma-separated env var values. Parsed by the property.
    allowed_redirect_domains_raw: str = Field(
        default='["rateshift.app","localhost"]',
        validation_alias="ALLOWED_REDIRECT_DOMAINS",
    )

    @property
    def allowed_redirect_domains(self) -> List[str]:
        """Parse allowed redirect domains from JSON array or comma-separated string."""
        raw = self.allowed_redirect_domains_raw
        if not raw:
            return ["localhost"]
        raw = raw.strip()
        if raw.startswith("["):
            try:
                return _json.loads(raw)
            except _json.JSONDecodeError:
                pass
        return [domain.strip() for domain in raw.split(",") if domain.strip()]

    # Field-level encryption (AES-256-GCM for account numbers etc.)
    field_encryption_key: Optional[str] = Field(
        default=None, validation_alias="FIELD_ENCRYPTION_KEY"
    )

    # GitHub Webhook
    github_webhook_secret: Optional[str] = Field(
        default=None, validation_alias="GITHUB_WEBHOOK_SECRET"
    )

    # Email OAuth (Gmail + Outlook)
    gmail_client_id: Optional[str] = Field(default=None, validation_alias="GMAIL_CLIENT_ID")
    gmail_client_secret: Optional[str] = Field(default=None, validation_alias="GMAIL_CLIENT_SECRET")
    outlook_client_id: Optional[str] = Field(default=None, validation_alias="OUTLOOK_CLIENT_ID")
    outlook_client_secret: Optional[str] = Field(
        default=None, validation_alias="OUTLOOK_CLIENT_SECRET"
    )
    oauth_redirect_base_url: str = Field(
        default="http://localhost:8000", validation_alias="OAUTH_REDIRECT_BASE_URL"
    )
    # TODO: Set FRONTEND_URL=https://rateshift.app on Render (and any other
    # non-local deployment) so OAuth callbacks redirect to the correct frontend
    # origin.  The default covers local development only.
    frontend_url: str = Field(default="http://localhost:3000", validation_alias="FRONTEND_URL")

    # AI Agent (Gemini primary + Groq fallback + Composio tools)
    gemini_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_API_KEY")
    groq_api_key: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY")
    composio_api_key: Optional[str] = Field(default=None, validation_alias="COMPOSIO_API_KEY")
    enable_ai_agent: bool = Field(default=False, validation_alias="ENABLE_AI_AGENT")
    agent_free_daily_limit: int = Field(default=3, validation_alias="AGENT_FREE_DAILY_LIMIT")
    agent_pro_daily_limit: int = Field(default=20, validation_alias="AGENT_PRO_DAILY_LIMIT")

    # Feature Flags
    enable_auto_switching: bool = Field(default=False, validation_alias="ENABLE_AUTO_SWITCHING")
    enable_load_optimization: bool = Field(
        default=True, validation_alias="ENABLE_LOAD_OPTIMIZATION"
    )
    enable_real_time_updates: bool = Field(
        default=True, validation_alias="ENABLE_REAL_TIME_UPDATES"
    )

    # Monitoring
    sentry_dsn: Optional[str] = Field(default=None, validation_alias="SENTRY_DSN")
    prometheus_port: int = Field(default=9090, validation_alias="PROMETHEUS_PORT")

    # OpenTelemetry — opt-in distributed tracing
    # Set OTEL_ENABLED=true to activate instrumentation.
    # Set OTEL_EXPORTER_OTLP_ENDPOINT to ship traces to a collector (e.g.
    # http://localhost:4318).  When the endpoint is absent but OTEL_ENABLED
    # is true, traces are written to stdout (debug) or discarded (prod).
    otel_enabled: bool = Field(default=False, validation_alias="OTEL_ENABLED")
    otel_endpoint: Optional[str] = Field(
        default=None, validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )

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

    @field_validator("field_encryption_key")
    @classmethod
    def validate_field_encryption_key(cls, v: Optional[str]) -> Optional[str]:
        """Ensure field encryption key is configured in production."""
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production":
            if not v:
                raise ValueError(
                    "CRITICAL: FIELD_ENCRYPTION_KEY must be set in production. "
                    'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            try:
                key_bytes = bytes.fromhex(v)
            except ValueError:
                raise ValueError("FIELD_ENCRYPTION_KEY must be a valid hex string.")
            if len(key_bytes) != 32:
                raise ValueError(
                    "FIELD_ENCRYPTION_KEY must be exactly 32 bytes (64 hex characters)."
                )
        return v

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Ensure JWT secret is not using default value in production"""
        env = os.environ.get("ENVIRONMENT", "development")
        insecure_defaults = [
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
            raise ValueError("JWT_SECRET must be at least 32 characters in production.")
        return v

    @field_validator("better_auth_secret")
    @classmethod
    def validate_better_auth_secret(cls, v: Optional[str]) -> Optional[str]:
        """Ensure Better Auth secret is strong when provided in production."""
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production" and v is not None and len(v) < 32:
            raise ValueError(
                "BETTER_AUTH_SECRET must be at least 32 characters in production. "
                "Generate one with: openssl rand -hex 32"
            )
        return v

    @field_validator("internal_api_key")
    @classmethod
    def validate_internal_api_key(cls, v: Optional[str]) -> Optional[str]:
        """Ensure internal API key is present and strong in production."""
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production":
            if not v:
                raise ValueError(
                    "CRITICAL: INTERNAL_API_KEY must be set in production. "
                    'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            if len(v) < 32:
                raise ValueError("INTERNAL_API_KEY must be at least 32 characters in production.")
        return v

    @field_validator("stripe_secret_key")
    @classmethod
    def validate_stripe_secret_key(cls, v: Optional[str]) -> Optional[str]:
        """Ensure Stripe secret key is present and valid in production."""
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production":
            if not v:
                raise ValueError("CRITICAL: STRIPE_SECRET_KEY must be set in production.")
            if not v.startswith("sk_"):
                raise ValueError("STRIPE_SECRET_KEY must start with 'sk_' (live or test key).")
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: Optional[str]) -> Optional[str]:
        """Ensure database URL is present and valid in production."""
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production":
            if not v:
                raise ValueError("CRITICAL: DATABASE_URL must be set in production.")
            if not v.startswith("postgresql://"):
                raise ValueError("DATABASE_URL must start with 'postgresql://' in production.")
        return v

    @field_validator("resend_api_key")
    @classmethod
    def validate_resend_api_key(cls, v: Optional[str]) -> Optional[str]:
        """Ensure Resend API key is present and valid in production."""
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production":
            if not v:
                raise ValueError("CRITICAL: RESEND_API_KEY must be set in production.")
            if not v.startswith("re_"):
                raise ValueError("RESEND_API_KEY must start with 're_'.")
        return v

    @model_validator(mode="after")
    def validate_ai_agent_keys(self) -> "Settings":
        """Ensure AI agent has required credentials when enabled in production."""
        if (
            self.enable_ai_agent
            and self.gemini_api_key is None
            and os.environ.get("ENVIRONMENT", "development") == "production"
        ):
            raise ValueError(
                "CRITICAL: GEMINI_API_KEY must be set when ENABLE_AI_AGENT=true in production."
            )
        return self

    @model_validator(mode="after")
    def validate_api_key_differs_from_jwt(self) -> "Settings":
        """Ensure INTERNAL_API_KEY and JWT_SECRET are not identical."""
        if self.internal_api_key and self.jwt_secret and self.internal_api_key == self.jwt_secret:
            raise ValueError(
                "INTERNAL_API_KEY must differ from JWT_SECRET to maintain "
                "separation of concerns between user auth and service auth."
            )
        return self

    # NOTE: cors_origins parsing is handled by the cors_origins property above.
    # The cors_origins_raw field stores the raw env var string to avoid
    # pydantic-settings JSON-parse errors on comma-separated values.

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


def get_settings() -> Settings:
    """Get the global settings instance (FastAPI dependency-injection compatible)."""
    return settings
