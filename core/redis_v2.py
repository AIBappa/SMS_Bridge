"""
SMS Bridge v2.2 - Redis Client Module
Sync redis-py client with ConnectionPool as per tech spec.

Redis Keys Structure (from tech spec Section 3):
- config:current          JSON (settings_payload) - SET by admin, READ by workers
- active_onboarding:{hash} JSON {mobile, gen_ts, email?, device_id?} - TTL=ttl_hash_seconds
- pending_sms:{msg_id}    JSON {mobile, hash, recv_ts} - TTL=900s
- verified:{mobile}       JSON {mobile, hash, verified_ts} - TTL=3600s
- sync_queue              LIST of JSON OutboundValidatedSms - LPUSH by workers, RPOP by sync
- audit_buffer            LIST of JSON AuditEvent - LPUSH for batch insert
- rate:{mobile}           COUNTER - INCR, TTL=60s for count_check
- blacklist               SET of mobile strings
"""
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

import redis
from redis import ConnectionPool

from core.config import get_settings

logger = logging.getLogger(__name__)

# Global pool and client
_pool: Optional[ConnectionPool] = None
_redis: Optional[redis.Redis] = None


def get_redis_pool() -> ConnectionPool:
    """Get or create the Redis connection pool"""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            host=settings.redis.host,
            port=settings.redis.port,
            db=settings.redis.db,
            password=settings.redis.password,
            max_connections=settings.redis.max_connections,
            decode_responses=settings.redis.decode_responses,
            socket_timeout=settings.redis.socket_timeout,
            socket_connect_timeout=settings.redis.socket_connect_timeout,
            retry_on_timeout=settings.redis.retry_on_timeout,
        )
        logger.info(f"Redis pool initialized: {settings.redis.host}:{settings.redis.port}")
    return _pool


def get_redis() -> redis.Redis:
    """Get Redis client from pool"""
    global _redis
    if _redis is None:
        _redis = redis.Redis(connection_pool=get_redis_pool())
    return _redis


def close_redis():
    """Close Redis connections"""
    global _pool, _redis
    if _redis is not None:
        _redis.close()
        _redis = None
    if _pool is not None:
        _pool.disconnect()
        _pool = None
        logger.info("Redis pool closed")


def check_redis_health() -> str:
    """
    Check Redis health.
    Returns: 'healthy' | 'degraded' | 'unhealthy'
    """
    try:
        r = get_redis()
        r.ping()
        return "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return "unhealthy"


# =============================================================================
# Config Operations (config:current)
# =============================================================================

def get_config_current() -> Optional[Dict[str, Any]]:
    """Get current settings from config:current"""
    r = get_redis()
    data = r.get("config:current")
    if data:
        return json.loads(data)
    return None


def set_config_current(payload: Dict[str, Any]):
    """Set config:current with settings payload"""
    r = get_redis()
    r.set("config:current", json.dumps(payload))
    logger.info("config:current updated in Redis")


# =============================================================================
# Active Onboarding (active_onboarding:{hash})
# =============================================================================

def set_active_onboarding(hash_val: str, mobile: str, gen_ts: datetime,
                          email: Optional[str] = None, device_id: Optional[str] = None,
                          ttl_seconds: int = 900):
    """
    Store active onboarding entry.
    Key: active_onboarding:{hash}
    Value: JSON {mobile, gen_ts, email?, device_id?}
    """
    r = get_redis()
    data = {
        "mobile": mobile,
        "gen_ts": gen_ts.isoformat(),
    }
    if email:
        data["email"] = email
    if device_id:
        data["device_id"] = device_id
    
    r.setex(f"active_onboarding:{hash_val}", ttl_seconds, json.dumps(data))
    logger.debug(f"Active onboarding set for hash={hash_val[:4]}...")


def get_active_onboarding(hash_val: str) -> Optional[Dict[str, Any]]:
    """Get active onboarding entry by hash"""
    r = get_redis()
    data = r.get(f"active_onboarding:{hash_val}")
    if data:
        return json.loads(data)
    return None


def delete_active_onboarding(hash_val: str):
    """Delete active onboarding entry"""
    r = get_redis()
    r.delete(f"active_onboarding:{hash_val}")
    logger.debug(f"Active onboarding deleted for hash={hash_val[:4]}...")


# =============================================================================
# Pending SMS (pending_sms:{msg_id})
# =============================================================================

def set_pending_sms(msg_id: str, mobile: str, hash_val: str, recv_ts: datetime,
                    ttl_seconds: int = 900):
    """
    Store pending SMS for validation.
    Key: pending_sms:{msg_id}
    Value: JSON {mobile, hash, recv_ts}
    """
    r = get_redis()
    data = {
        "mobile": mobile,
        "hash": hash_val,
        "recv_ts": recv_ts.isoformat(),
    }
    r.setex(f"pending_sms:{msg_id}", ttl_seconds, json.dumps(data))
    logger.debug(f"Pending SMS set for msg_id={msg_id[:8]}...")


def get_pending_sms(msg_id: str) -> Optional[Dict[str, Any]]:
    """Get pending SMS by message ID"""
    r = get_redis()
    data = r.get(f"pending_sms:{msg_id}")
    if data:
        return json.loads(data)
    return None


def delete_pending_sms(msg_id: str):
    """Delete pending SMS entry"""
    r = get_redis()
    r.delete(f"pending_sms:{msg_id}")


# =============================================================================
# Verified (verified:{mobile})
# =============================================================================

def set_verified(mobile: str, hash_val: str, verified_ts: datetime,
                 ttl_seconds: int = 3600):
    """
    Store verified mobile entry.
    Key: verified:{mobile}
    Value: JSON {mobile, hash, verified_ts}
    """
    r = get_redis()
    data = {
        "mobile": mobile,
        "hash": hash_val,
        "verified_ts": verified_ts.isoformat(),
    }
    r.setex(f"verified:{mobile}", ttl_seconds, json.dumps(data))
    logger.debug(f"Verified entry set for mobile={mobile[-4:]}...")


def get_verified(mobile: str) -> Optional[Dict[str, Any]]:
    """Get verified entry by mobile"""
    r = get_redis()
    data = r.get(f"verified:{mobile}")
    if data:
        return json.loads(data)
    return None


def delete_verified(mobile: str):
    """Delete verified entry"""
    r = get_redis()
    r.delete(f"verified:{mobile}")


# =============================================================================
# Sync Queue (sync_queue) - LIST
# =============================================================================

def lpush_sync_queue(outbound_data: Dict[str, Any]):
    """Push validated user to sync_queue (left push)"""
    r = get_redis()
    r.lpush("sync_queue", json.dumps(outbound_data))
    logger.debug("Pushed to sync_queue")


def rpop_sync_queue() -> Optional[Dict[str, Any]]:
    """Pop from sync_queue (right pop - FIFO)"""
    r = get_redis()
    data = r.rpop("sync_queue")
    if data:
        return json.loads(data)
    return None


def llen_sync_queue() -> int:
    """Get length of sync_queue"""
    r = get_redis()
    return r.llen("sync_queue")


def lrange_sync_queue(start: int = 0, end: int = -1) -> List[Dict[str, Any]]:
    """Get range of items from sync_queue"""
    r = get_redis()
    items = r.lrange("sync_queue", start, end)
    return [json.loads(item) for item in items]


# =============================================================================
# Audit Buffer (audit_buffer) - LIST
# =============================================================================

def lpush_audit_event(event: str, details: Dict[str, Any]):
    """Push audit event to audit_buffer"""
    r = get_redis()
    data = {
        "event": event,
        "details": details,
        "timestamp": datetime.utcnow().isoformat(),
    }
    r.lpush("audit_buffer", json.dumps(data))


def lrange_audit_buffer(start: int = 0, end: int = -1) -> List[Dict[str, Any]]:
    """Get range of audit events"""
    r = get_redis()
    items = r.lrange("audit_buffer", start, end)
    return [json.loads(item) for item in items]


def ltrim_audit_buffer(start: int, end: int):
    """Trim audit buffer to keep only specified range"""
    r = get_redis()
    r.ltrim("audit_buffer", start, end)


def flush_audit_buffer() -> List[Dict[str, Any]]:
    """
    Atomically flush audit buffer using MULTI/EXEC.
    Returns all events and clears the buffer.
    Per tech spec Section 3.1: DELETE+SET uses MULTI/EXEC
    """
    r = get_redis()
    pipe = r.pipeline()
    pipe.lrange("audit_buffer", 0, -1)
    pipe.delete("audit_buffer")
    results = pipe.execute()
    items = results[0]  # lrange result
    return [json.loads(item) for item in items]


# =============================================================================
# Rate Limiting (rate:{mobile})
# =============================================================================

def incr_rate(mobile: str, ttl_seconds: int = 60) -> int:
    """
    Increment rate counter for mobile.
    Sets TTL on first increment.
    Returns current count.
    """
    r = get_redis()
    key = f"rate:{mobile}"
    count = r.incr(key)
    if count == 1:
        r.expire(key, ttl_seconds)
    return count


def get_rate(mobile: str) -> int:
    """Get current rate count for mobile"""
    r = get_redis()
    count = r.get(f"rate:{mobile}")
    return int(count) if count else 0


# =============================================================================
# Blacklist (blacklist) - SET
# =============================================================================

def sadd_blacklist(mobile: str):
    """Add mobile to blacklist set"""
    r = get_redis()
    r.sadd("blacklist", mobile)
    logger.info(f"Added to blacklist: {mobile[-4:]}...")


def srem_blacklist(mobile: str):
    """Remove mobile from blacklist set"""
    r = get_redis()
    r.srem("blacklist", mobile)
    logger.info(f"Removed from blacklist: {mobile[-4:]}...")


def sismember_blacklist(mobile: str) -> bool:
    """Check if mobile is in blacklist"""
    r = get_redis()
    return r.sismember("blacklist", mobile)


def smembers_blacklist() -> set:
    """Get all blacklisted mobiles"""
    r = get_redis()
    return r.smembers("blacklist")


def load_blacklist_from_db(mobiles: List[str]):
    """
    Load blacklist from database to Redis.
    Uses MULTI/EXEC for atomicity as per tech spec.
    """
    r = get_redis()
    pipe = r.pipeline()
    pipe.delete("blacklist")
    if mobiles:
        pipe.sadd("blacklist", *mobiles)
    pipe.execute()
    logger.info(f"Loaded {len(mobiles)} mobiles to Redis blacklist")


# =============================================================================
# Power-Down Store Operations
# =============================================================================

def backup_to_power_down_store(db_session, model_class):
    """
    Backup Redis keys to power_down_store table.
    Called by Postgres trigger or shutdown sequence.
    """
    r = get_redis()
    from core.models.postgres import PowerDownStore
    
    # Scan and backup all relevant keys
    keys_to_backup = []
    
    # Backup active_onboarding:* keys
    for key in r.scan_iter("active_onboarding:*"):
        data = r.get(key)
        if data:
            keys_to_backup.append(PowerDownStore(
                key_name=key,
                key_value=data,
            ))
    
    # Backup verified:* keys
    for key in r.scan_iter("verified:*"):
        data = r.get(key)
        if data:
            keys_to_backup.append(PowerDownStore(
                key_name=key,
                key_value=data,
            ))
    
    # Backup pending_sms:* keys
    for key in r.scan_iter("pending_sms:*"):
        data = r.get(key)
        if data:
            keys_to_backup.append(PowerDownStore(
                key_name=key,
                key_value=data,
            ))
    
    # Backup config:current
    config = r.get("config:current")
    if config:
        keys_to_backup.append(PowerDownStore(
            key_name="config:current",
            key_value=config,
        ))
    
    # Insert all to database
    if keys_to_backup:
        db_session.add_all(keys_to_backup)
        db_session.commit()
        logger.info(f"Backed up {len(keys_to_backup)} Redis keys to power_down_store")


def restore_from_power_down_store(db_session):
    """
    Restore Redis keys from power_down_store table.
    Called during startup sequence.
    """
    r = get_redis()
    from core.models.postgres import PowerDownStore
    
    entries = db_session.query(PowerDownStore).all()
    
    pipe = r.pipeline()
    for entry in entries:
        pipe.set(entry.key_name, entry.value)
        # Set TTL from original_ttl if available
        if entry.original_ttl is not None and entry.original_ttl > 0:
            pipe.expire(entry.key_name, entry.original_ttl)
    pipe.execute()
    
    # Clear power_down_store after successful restore
    db_session.query(PowerDownStore).delete()
    db_session.commit()
    
    logger.info(f"Restored {len(entries)} Redis keys from power_down_store")
