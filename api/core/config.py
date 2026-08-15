"""
MangoPoint API — Configuration
================================
Environment-based configuration using Pydantic settings.
"""

import json
from functools import lru_cache
from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from spatial.orchard_location import ORCHARD_LAT, ORCHARD_LON


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Application
    APP_NAME: str = "MangoPoint API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database (PostgreSQL + PostGIS)
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/mangopoint"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    # Cloud backup / synchronization (server-side only)
    SUPABASE_URL: Optional[str] = None
    SUPABASE_DATABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET: str = "orchard-assets"
    CLOUD_SYNC_ENABLED: bool = True
    # Database rows are backed up; large orchard files remain local by default.
    CLOUD_SYNC_ASSETS: bool = False
    CLOUD_SYNC_INTERVAL_SECONDS: int = 7200
    CLOUD_SYNC_BATCH_SIZE: int = 100
    CLOUD_SYNC_MAX_RETRIES: int = 8

    # Authentication
    AUTH_SECRET_KEY: Optional[str] = None
    AUTH_ALGORITHM: str = "HS256"
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    DEFAULT_ADMIN_ENABLED: bool = True
    DEFAULT_ADMIN_FULL_NAME: str = "MangoPoint Administrator"
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_EMAIL: str = "admin@mangopoint.local"
    DEFAULT_ADMIN_PASSWORD: str = "change-this-admin-password"
    DEFAULT_ADMIN_ROLE: str = "admin"
    
    # Weather API (Open-Meteo — free, no API key required)
    WEATHER_CACHE_TTL_SECONDS: int = 600  # 10 minutes
    
    # Default location (derived from the orchard orthophoto centroid)
    DEFAULT_LAT: float = ORCHARD_LAT
    DEFAULT_LON: float = ORCHARD_LON
    
    # SMTP Email Settings
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "alerts@mangopoint.local"
    
    # Twilio SMS Settings (stub)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None
    
    # Alert thresholds
    ALERT_RISK_THRESHOLD: float = 0.75
    ALERT_MONITORING_ENABLED: bool = False
    ALERT_MONITORING_INTERVAL_SECONDS: int = 3600
    ALERT_MONITORING_FORECAST_HOURS: int = 48
    ALERT_MONITORING_DEDUPE_HOURS: int = 6
    
    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        """Accept both boolean-like and environment-style debug values."""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "dev", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return value

    @field_validator("DEFAULT_ADMIN_ENABLED", mode="before")
    @classmethod
    def parse_default_admin_enabled(cls, value: Any) -> Any:
        """Accept environment-style booleans for default admin seeding."""
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        """Support JSON arrays and comma-separated origin lists."""
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
