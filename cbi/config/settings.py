"""
Application settings loaded from environment variables.

Uses Pydantic Settings for validation and type coercion.
Never log or expose sensitive values.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "CBI"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # Database
    database_url: SecretStr = Field(
        ...,
        description="PostgreSQL connection string with asyncpg driver",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure database URL uses asyncpg driver."""
        if v and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Redis
    redis_url: SecretStr = Field(
        ...,
        description="Redis connection string",
    )

    # Anthropic
    anthropic_api_key: SecretStr = Field(
        ...,
        description="Anthropic API key for Claude models",
    )

    # Telegram
    telegram_bot_token: SecretStr = Field(
        ...,
        description="Telegram Bot API token",
    )
    telegram_webhook_url: str | None = Field(
        default=None,
        description="Public URL for Telegram webhook endpoint",
    )
    telegram_webhook_secret: SecretStr | None = Field(
        default=None,
        description="Secret for validating Telegram webhook requests",
    )

    # WhatsApp (optional for MVP, required for production)
    whatsapp_phone_number_id: str | None = Field(
        default=None,
        description="WhatsApp Business phone number ID",
    )
    whatsapp_access_token: SecretStr | None = Field(
        default=None,
        description="Meta Graph API access token for WhatsApp",
    )
    whatsapp_verify_token: str | None = Field(
        default=None,
        description="Token for verifying WhatsApp webhook setup",
    )
    whatsapp_app_secret: SecretStr | None = Field(
        default=None,
        description="Meta App secret for webhook signature validation",
    )

    # Security
    jwt_secret: SecretStr = Field(
        ...,
        description="256-bit secret for JWT signing",
        min_length=32,
    )
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    encryption_key: SecretStr = Field(
        ...,
        description="32-byte key for AES-256 encryption",
    )
    phone_hash_salt: SecretStr = Field(
        ...,
        description="Salt for phone number hashing",
    )

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # LLM Configuration
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 3

    # Conversation Settings
    conversation_ttl_hours: int = 24
    max_conversation_turns: int = 50

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Returns:
        Settings instance loaded from environment variables.
    """
    return Settings()

settings = get_settings()