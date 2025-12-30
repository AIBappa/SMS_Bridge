"""
SMS Bridge v2.2 - Configuration Module
Loads application config from environment variables and optional vault file.
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any

import yaml
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
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


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
        auth = f":{self.password}@" if self.password else ""
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
    
    # Vault file path (optional - for secrets)
    vault_file: Optional[str] = Field(default="vault.yml", description="Path to vault.yml")
    
    # Database settings (can be overridden by vault)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    
    # Redis settings (can be overridden by vault)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    
    # Admin UI
    admin_enabled: bool = Field(default=True, description="Enable SQLAdmin UI")
    admin_path: str = Field(default="/admin", description="Admin UI path")
    
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
    
    class Config:
        env_prefix = "SMS_BRIDGE_"
        env_nested_delimiter = "__"


def load_vault(vault_path: str) -> Dict[str, Any]:
    """Load secrets from vault.yml file"""
    path = Path(vault_path)
    if not path.exists():
        return {}
    
    with open(path, 'r') as f:
        vault_data = yaml.safe_load(f) or {}
    
    return vault_data


def merge_vault_settings(settings: AppSettings, vault_data: Dict[str, Any]) -> AppSettings:
    """Merge vault secrets into settings"""
    if not vault_data:
        return settings
    
    # Database settings from vault
    if 'database' in vault_data:
        db_vault = vault_data['database']
        settings.database.host = db_vault.get('host', settings.database.host)
        settings.database.port = db_vault.get('port', settings.database.port)
        settings.database.name = db_vault.get('name', settings.database.name)
        settings.database.user = db_vault.get('user', settings.database.user)
        settings.database.password = db_vault.get('password', settings.database.password)
    
    # Redis settings from vault
    if 'redis' in vault_data:
        redis_vault = vault_data['redis']
        settings.redis.host = redis_vault.get('host', settings.redis.host)
        settings.redis.port = redis_vault.get('port', settings.redis.port)
        settings.redis.db = redis_vault.get('db', settings.redis.db)
        settings.redis.password = redis_vault.get('password', settings.redis.password)
    
    return settings


@lru_cache()
def get_settings() -> AppSettings:
    """
    Get cached application settings.
    Loads from environment + vault file.
    """
    settings = AppSettings()
    
    # Load vault if path specified
    if settings.vault_file:
        vault_data = load_vault(settings.vault_file)
        settings = merge_vault_settings(settings, vault_data)
    
    return settings


# Convenience functions for dependency injection
def get_database_url() -> str:
    """Get database URL for SQLAlchemy"""
    return get_settings().database.url


def get_redis_url() -> str:
    """Get Redis URL"""
    return get_settings().redis.url
