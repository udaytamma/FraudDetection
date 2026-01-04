"""
Fraud Detection Platform - Configuration Settings

Centralized configuration using Pydantic Settings for type-safe
environment variable handling with validation.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden via environment variables.
    Example: APP_ENV=production will set app_env to "production"
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # Application Settings
    # =========================================================================
    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Application environment"
    )
    app_debug: bool = Field(
        default=True,
        description="Enable debug mode"
    )
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level"
    )

    # =========================================================================
    # Redis Configuration
    # =========================================================================
    redis_host: str = Field(
        default="localhost",
        description="Redis server hostname"
    )
    redis_port: int = Field(
        default=6379,
        description="Redis server port"
    )
    redis_db: int = Field(
        default=0,
        description="Redis database number"
    )
    redis_key_prefix: str = Field(
        default="fraud:",
        description="Prefix for all Redis keys to avoid conflicts"
    )
    redis_password: str | None = Field(
        default=None,
        description="Redis password (optional)"
    )

    @computed_field
    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # =========================================================================
    # PostgreSQL Configuration
    # =========================================================================
    postgres_host: str = Field(
        default="localhost",
        description="PostgreSQL server hostname"
    )
    postgres_port: int = Field(
        default=5432,
        description="PostgreSQL server port"
    )
    postgres_db: str = Field(
        default="fraud_detection",
        description="PostgreSQL database name"
    )
    postgres_user: str = Field(
        default="fraud_user",
        description="PostgreSQL username"
    )
    postgres_password: str = Field(
        default="REDACTED_POSTGRES_PASSWORD",
        description="PostgreSQL password"
    )

    @computed_field
    @property
    def postgres_url(self) -> str:
        """Construct PostgreSQL connection URL for asyncpg."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def postgres_sync_url(self) -> str:
        """Construct PostgreSQL connection URL for sync operations (migrations)."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # =========================================================================
    # API Configuration
    # =========================================================================
    api_host: str = Field(
        default="0.0.0.0",
        description="API server bind address"
    )
    api_port: int = Field(
        default=8000,
        description="API server port"
    )
    api_workers: int = Field(
        default=1,
        description="Number of API worker processes"
    )

    # =========================================================================
    # Latency Targets (milliseconds)
    # These are the SLA requirements from the design document
    # =========================================================================
    target_e2e_latency_ms: int = Field(
        default=200,
        description="Target end-to-end latency in milliseconds"
    )
    target_feature_latency_ms: int = Field(
        default=50,
        description="Target feature computation latency in milliseconds"
    )
    target_scoring_latency_ms: int = Field(
        default=25,
        description="Target model/scoring latency in milliseconds"
    )

    # =========================================================================
    # Metrics Configuration
    # =========================================================================
    metrics_enabled: bool = Field(
        default=True,
        description="Enable Prometheus metrics endpoint"
    )
    metrics_port: int = Field(
        default=9100,
        description="Prometheus metrics port"
    )

    # =========================================================================
    # Feature Store Configuration (Velocity Windows)
    # =========================================================================
    velocity_window_10m_seconds: int = Field(
        default=600,
        description="10-minute velocity window in seconds"
    )
    velocity_window_1h_seconds: int = Field(
        default=3600,
        description="1-hour velocity window in seconds"
    )
    velocity_window_24h_seconds: int = Field(
        default=86400,
        description="24-hour velocity window in seconds"
    )

    # =========================================================================
    # Detection Thresholds (Rule-Based)
    # These can be tuned via config without code changes
    # =========================================================================
    # Card Testing Detection
    card_testing_attempts_threshold: int = Field(
        default=5,
        description="Max card attempts in 10 minutes before flagging"
    )
    card_testing_decline_ratio_threshold: float = Field(
        default=0.8,
        description="Decline ratio threshold for card testing detection"
    )

    # Velocity Attack Detection
    velocity_card_attempts_1h_threshold: int = Field(
        default=10,
        description="Max card attempts in 1 hour"
    )
    velocity_device_cards_24h_threshold: int = Field(
        default=5,
        description="Max distinct cards per device in 24 hours"
    )
    velocity_ip_cards_1h_threshold: int = Field(
        default=10,
        description="Max distinct cards per IP in 1 hour"
    )

    # High-Value Transaction Thresholds
    high_value_threshold_usd: float = Field(
        default=1000.0,
        description="Amount threshold for high-value transaction rules"
    )

    # New Account Risk Window
    new_account_days_threshold: int = Field(
        default=7,
        description="Days after which account is no longer 'new'"
    )


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses LRU cache to avoid re-parsing environment on every call.
    """
    return Settings()


# Singleton settings instance for easy import
settings = get_settings()
