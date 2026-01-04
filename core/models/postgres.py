"""
SMS Bridge v2.2 - SQLAlchemy Models
Aligned with schema.sql and Tech Spec v2.2
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    Index
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


class SettingsHistory(Base):
    """
    Configuration History (Append-Only)
    Stores JSON payloads with version control for settings.
    """
    __tablename__ = "settings_history"

    version_id = Column(Integer, primary_key=True, autoincrement=True)
    payload = Column(JSONB, nullable=False)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(50))
    change_note = Column(Text)

    __table_args__ = (
        Index("idx_settings_active", "is_active", postgresql_where=(is_active == True)),
    )

    def __repr__(self):
        return f"<SettingsHistory(version_id={self.version_id}, is_active={self.is_active})>"


class AdminUser(Base):
    """
    Admin Users for SQLAdmin authentication.
    Uses BCrypt password hashing via passlib.
    """
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_super_admin = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AdminUser(id={self.id}, username={self.username})>"


class SMSBridgeLog(Base):
    """
    Logs (Append-Only)
    Audit trail for all events from audit_buffer.
    """
    __tablename__ = "sms_bridge_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event = Column(String(50), nullable=False)
    details = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_logs_event", "event"),
        Index("idx_logs_created", "created_at"),
    )

    def __repr__(self):
        return f"<SMSBridgeLog(id={self.id}, event={self.event})>"


class BackupUser(Base):
    """
    Backup Credentials (Hot Path Backup)
    Stores validated user credentials from PIN_COLLECTED events.
    Note: PIN is stored as SHA256 hash (64 chars), not plaintext.
    """
    __tablename__ = "backup_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mobile = Column(String(20), nullable=False)
    pin = Column(String(64), nullable=False)  # SHA256 hash (64 hex chars)
    hash = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    synced_at = Column(DateTime)

    __table_args__ = (
        Index("idx_backup_mobile", "mobile"),
    )

    def __repr__(self):
        return f"<BackupUser(id={self.id}, mobile={self.mobile})>"


class PowerDownStore(Base):
    """
    Power-Down Store (Redis Failure Backup)
    Stores Redis state and pending SMS when Redis unavailable.
    """
    __tablename__ = "power_down_store"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_name = Column(String(255), nullable=False)
    key_type = Column(String(20), nullable=False)  # "hash", "string", "set", "pending_sms"
    value = Column(JSONB, nullable=False)
    original_ttl = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_powerdown_key", "key_name"),
    )

    def __repr__(self):
        return f"<PowerDownStore(id={self.id}, key_name={self.key_name})>"


class BlacklistMobile(Base):
    """
    Blacklist (Persistent)
    Mobile numbers blocked from verification.
    Synced to Redis SET blacklist_mobiles on startup.
    """
    __tablename__ = "blacklist_mobiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mobile = Column(String(20), unique=True, nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(50))

    def __repr__(self):
        return f"<BlacklistMobile(id={self.id}, mobile={self.mobile})>"
