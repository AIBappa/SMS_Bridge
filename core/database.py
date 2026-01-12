"""
SMS Bridge v2.2 - Database Module
SQLAlchemy engine, session factory, and utilities.
Uses sync psycopg2 driver as per tech spec.
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from core.config import get_settings
from core.models.postgres import Base

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the SQLAlchemy engine"""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database.url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before use
            pool_recycle=3600,   # Recycle connections after 1 hour
            echo=settings.debug,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    """Get or create the session factory"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI route injection.
    Yields a database session and handles cleanup.
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions outside FastAPI routes.
    Usage: with get_db_context() as db: ...
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """
    Initialize database tables.
    Creates all tables defined in models if they don't exist.
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")


def check_db_health() -> str:
    """
    Check database health.
    Returns: 'healthy' | 'degraded' | 'unhealthy'
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return "unhealthy"


def dispose_engine():
    """
    Dispose of the engine and all connections.
    Call during shutdown.
    """
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
        logger.info("Database engine disposed")
