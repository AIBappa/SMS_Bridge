"""
SMS Bridge v2.2 - Background Workers
Sync worker and Audit worker per tech spec Section 5.
"""
import logging
import threading
import time
from datetime import datetime
from typing import Optional

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.config import get_settings
from core import redis_v2 as redis_client
from core.database import get_db_context
from core.models import SMSBridgeLog
from core.services import hash_pin

logger = logging.getLogger(__name__)

# Global scheduler
_scheduler: Optional[BackgroundScheduler] = None
_worker_status = "stopped"


def get_worker_status() -> str:
    """Get current worker status"""
    global _worker_status
    return _worker_status


def start_workers():
    """Start background workers"""
    global _scheduler, _worker_status
    
    if _scheduler is not None:
        logger.warning("Workers already running")
        return
    
    settings = get_settings()
    config = redis_client.get_config_current() or {}
    
    _scheduler = BackgroundScheduler()
    
    # Sync worker
    if settings.sync_worker_enabled:
        sync_interval = config.get("sync_interval", 1.0)
        _scheduler.add_job(
            sync_worker,
            trigger=IntervalTrigger(seconds=sync_interval),
            id="sync_worker",
            name="Sync Queue Worker",
            replace_existing=True,
        )
        logger.info(f"Sync worker scheduled (interval={sync_interval}s)")
    
    # Audit worker
    if settings.audit_worker_enabled:
        log_interval = config.get("log_interval", 120)
        _scheduler.add_job(
            audit_worker,
            trigger=IntervalTrigger(seconds=log_interval),
            id="audit_worker",
            name="Audit Buffer Worker",
            replace_existing=True,
        )
        logger.info(f"Audit worker scheduled (interval={log_interval}s)")
    
    _scheduler.start()
    _worker_status = "running"
    logger.info("Background workers started")


def stop_workers():
    """Stop background workers gracefully"""
    global _scheduler, _worker_status
    
    if _scheduler is None:
        return
    
    _worker_status = "stopping"
    
    try:
        # Pause new job execution
        _scheduler.pause()
        
        # Final drain
        drain_sync_queue()
        flush_audit_buffer()
        
        # Shutdown scheduler
        _scheduler.shutdown(wait=True)
        _scheduler = None
        _worker_status = "stopped"
        logger.info("Background workers stopped")
    except Exception as e:
        logger.error(f"Error stopping workers: {e}")
        _worker_status = "error"


def sync_worker():
    """
    Sync Queue Worker per tech spec Section 5.A.
    
    Polls sync_queue every sync_interval:
    1. RPOP from sync_queue
    2. POST to sync_url
    3. On failure: re-queue (LPUSH)
    4. Log result
    """
    global _worker_status
    
    if _worker_status != "running":
        return
    
    config = redis_client.get_config_current()
    if config is None:
        logger.warning("Sync worker: No config available")
        return
    
    sync_url = config.get("sync_url")
    if not sync_url:
        logger.warning("Sync worker: sync_url not configured")
        return
    
    # Process queue items
    processed = 0
    failed = 0
    
    try:
        while True:
            item = redis_client.rpop_sync_queue()
            if item is None:
                break
            
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(sync_url, json=item)
                    response.raise_for_status()
                
                processed += 1
                logger.debug(f"Synced item to {sync_url}")
                
            except httpx.HTTPError as e:
                logger.error(f"Sync failed for item: {e}")
                # Re-queue on failure (push back to front)
                # NOTE: Consider implementing retry counter in payload or dead-letter queue
                # to prevent infinite retry loops if sync_url is permanently unavailable
                redis_client.lpush_sync_queue(item)
                failed += 1
                break  # Stop processing on failure
                
    except Exception as e:
        logger.error(f"Sync worker error: {e}")
        _worker_status = "degraded"
    
    if processed > 0 or failed > 0:
        logger.info(f"Sync worker: processed={processed}, failed={failed}")


def audit_worker():
    """
    Audit Buffer Worker per tech spec Section 5.B.
    
    Runs every log_interval:
    1. Atomically flush audit_buffer
    2. Batch insert to sms_bridge_logs
    3. Clear buffer
    """
    global _worker_status
    
    if _worker_status != "running":
        return
    
    flush_audit_buffer()


def flush_audit_buffer():
    """Flush audit buffer to database"""
    try:
        # Atomically get and clear buffer
        events = redis_client.flush_audit_buffer()
        
        if not events:
            return
        
        # Batch insert to database
        with get_db_context() as db:
            for event in events:
                log_entry = SMSBridgeLog(
                    event=event.get("event", "UNKNOWN"),
                    details=event.get("details", {}),
                    created_at=datetime.fromisoformat(event.get("timestamp", datetime.utcnow().isoformat())),
                )
                db.add(log_entry)
        
        logger.info(f"Audit worker: flushed {len(events)} events to database")
        
    except Exception as e:
        logger.error(f"Audit worker error: {e}")


def drain_sync_queue():
    """Drain sync queue during shutdown"""
    config = redis_client.get_config_current()
    if config is None:
        return
    
    sync_url = config.get("sync_url")
    if not sync_url:
        return
    
    queue_length = redis_client.llen_sync_queue()
    if queue_length == 0:
        return
    
    logger.info(f"Draining sync_queue: {queue_length} items")
    
    processed = 0
    with httpx.Client(timeout=30.0) as client:
        while True:
            item = redis_client.rpop_sync_queue()
            if item is None:
                break
            
            try:
                response = client.post(sync_url, json=item)
                response.raise_for_status()
                processed += 1
            except httpx.HTTPError as e:
                # Re-queue and stop draining
                redis_client.lpush_sync_queue(item)
                logger.error(f"Drain failed: {e}")
                break
    
    logger.info(f"Drain complete: processed {processed} items")


# =============================================================================
# Fallback Mode (per tech spec Section 7)
# =============================================================================

class FallbackWorker:
    """
    Fallback worker for power-down resilience.
    Directly writes to Postgres when Redis is unavailable.
    """
    
    def __init__(self):
        self._enabled = False
        self._lock = threading.Lock()
    
    def enable(self):
        """Enable fallback mode"""
        with self._lock:
            self._enabled = True
            logger.warning("Fallback mode ENABLED - writing directly to Postgres")
    
    def disable(self):
        """Disable fallback mode"""
        with self._lock:
            self._enabled = False
            logger.info("Fallback mode DISABLED")
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    def write_backup_user(self, mobile: str, hash_val: str, pin: Optional[str] = None):
        """
        Write user data directly to backup_users table.
        Used when Redis is unavailable.
        """
        if not self._enabled:
            return
        
        # Validate PIN is provided (NOT NULL constraint in DB)
        if not pin:
            logger.warning(f"Skipping backup_user write for {mobile[-4:]}: PIN is required but was None/empty")
            return
        
        from core.models import BackupUser
        
        try:
            # Hash PIN before storage using mobile+hash as deterministic salt
            # This ensures PINs are never stored in plaintext
            salt = f"{mobile}{hash_val}"
            hashed_pin = hash_pin(pin, salt)
            
            with get_db_context() as db:
                backup = BackupUser(
                    mobile=mobile,
                    hash=hash_val,
                    pin=hashed_pin,
                )
                db.add(backup)
            
            logger.info(f"Fallback: wrote backup_user for {mobile[-4:]}")
            
        except Exception as e:
            logger.error(f"Fallback write failed: {e}")


# Global fallback worker instance
fallback_worker = FallbackWorker()
