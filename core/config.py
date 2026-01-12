"""
SMS Bridge v2.2 - Configuration Module
Loads application config from environment variables.
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import quote_plus

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseModel):
    """PostgreSQL connection settings"""
    host: str = "localhost"
    port: int = 5432
    name: str = "sms_bridge"
    user: str = "sms_bridge"
    password: str = ""
    
    @property
    def url(self) -> str:
        """SQLAlchemy connection URL (sync)"""
        encoded_user = quote_plus(self.user)
        encoded_password = quote_plus(self.password)
        return f"postgresql+psycopg2://{encoded_user}:{encoded_password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseModel):
    """Redis connection settings"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 10
    decode_responses: bool = True
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    
    @property
    def url(self) -> str:
        """Redis connection URL"""
        # None = no auth (omit auth section), empty string = explicit empty password (":@")
        if self.password is None:
            auth = ""
        else:
            encoded_password = quote_plus(self.password)
            auth = f":{encoded_password}@"
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class AppSettings(BaseSettings):
    """
    Main application settings.
    Values loaded from environment variables with SMS_BRIDGE_ prefix.
    """
    # Application metadata
    app_name: str = Field(default="sms-bridge", description="Application name")
    version: str = Field(default="2.2.0", description="Application version")
    debug: bool = Field(default=False, description="Enable debug mode")
    
    # Server settings
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8000, description="Server bind port")
    workers: int = Field(default=1, description="Number of uvicorn workers")
    
    # Database settings (from environment variables)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    
    # Redis settings (from environment variables)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    
    # Admin UI
    admin_enabled: bool = Field(default=True, description="Enable SQLAdmin UI")
    admin_path: str = Field(default="/admin", description="Admin UI path")
    admin_secret_key: str = Field(
        default="",
        description="Secret key for admin session encryption (required in production)"
    )
    admin_username: str = Field(
        default="",
        description="Default admin username (auto-created on startup if not exists)"
    )
    admin_password: str = Field(
        default="",
        description="Default admin password (auto-created on startup if not exists)"
    )
    
    # Metrics
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_path: str = Field(default="/metrics", description="Metrics endpoint path")
    
    # Background workers
    sync_worker_enabled: bool = Field(default=True)
    audit_worker_enabled: bool = Field(default=True)
    
    # Startup behavior
    load_settings_to_redis: bool = Field(
        default=True,
        description="Load active settings from Postgres to Redis on startup"
    )
    
    model_config = {
        "env_prefix": "SMS_BRIDGE_",
        "env_nested_delimiter": "__",
    }


@lru_cache()
def get_settings() -> AppSettings:
    """
    Get cached application settings.
    Loads from environment variables only.
    """
    settings = AppSettings()
    
    # Validate admin_secret_key in non-debug mode
    if settings.admin_enabled and not settings.debug:
        if not settings.admin_secret_key or settings.admin_secret_key == "":
            raise ValueError(
                "SMS_BRIDGE_ADMIN_SECRET_KEY must be set in production. "
                "Generate a secure random key (e.g., using 'openssl rand -hex 32')"
            )
    
    return settings


# Convenience functions for dependency injection
def get_database_url() -> str:
    """Get database URL for SQLAlchemy"""
    return get_settings().database.url


def get_redis_url() -> str:
    """Get Redis URL"""
    return get_settings().redis.url
