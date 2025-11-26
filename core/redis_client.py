"""
Async Redis client with pooling, retries, and helpers for SMS Bridge.
Provides both sync (redis.StrictRedis) and async (RedisPool) interfaces.
"""

import redis
import os
import asyncio
from typing import Any, Optional, List, Dict
import logging

logger = logging.getLogger(__name__)

# Sync Redis client (for backward compatibility with existing code)
REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'password': os.getenv('REDIS_PASSWORD', None),
    'db': 0,
}
redis_client = redis.StrictRedis(**REDIS_CONFIG)

class RedisPool:
    """Async Redis client with connection pooling and retry logic"""
    def __init__(self, host: str, port: int, password: Optional[str] = None, db: int = 0, max_connections: int = 10):
        self.pool = None
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.max_connections = max_connections
        self._redis_client = None

    async def init(self):
        """Initialize async Redis connection pool"""
        try:
            # Use redis-py's asyncio support (redis.asyncio)
            import redis.asyncio as aioredis
            self.pool = await aioredis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}",
                password=self.password,
                max_connections=self.max_connections,
                decode_responses=True
            )
            logger.info(f"Redis async pool initialized: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to initialize Redis pool: {e}")
            raise

    async def retry(self, coro, retries=3, delay=0.2):
        """Retry a coroutine with exponential backoff"""
        last_exc = None
        for attempt in range(retries):
            try:
                return await coro
            except Exception as e:
                last_exc = e
                logger.warning(f"Redis operation failed (attempt {attempt + 1}/{retries}): {e}")
                await asyncio.sleep(delay * (2 ** attempt))
        logger.error(f"Redis operation failed after {retries} retries: {last_exc}")
        if last_exc is not None:
            raise last_exc
        else:
            raise RuntimeError("Redis operation failed after retries, but no exception was captured.")
    # Redis primitives with retry logic
    async def setex(self, key: str, ttl: int, value: Any):
        """Set key with expiration"""
        return await self.retry(self.pool.setex(key, ttl, value))

    async def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        return await self.retry(self.pool.get(key))

    async def sadd(self, key: str, *members: str):
        """Add members to a set"""
        return await self.retry(self.pool.sadd(key, *members))

    async def sismember(self, key: str, member: str) -> bool:
        """Check if member exists in set"""
        return await self.retry(self.pool.sismember(key, member))

    async def smembers(self, key: str) -> set:
        """Get all members of a set"""
        return await self.retry(self.pool.smembers(key))

    async def scard(self, key: str) -> int:
        """Get cardinality (count) of a set"""
        return await self.retry(self.pool.scard(key))

    async def srem(self, key: str, *members: str):
        """Remove members from a set"""
        return await self.retry(self.pool.srem(key, *members))

    async def incr(self, key: str) -> int:
        """Increment key by 1"""
        return await self.retry(self.pool.incr(key))

    async def lpush(self, key: str, *values: Any):
        """Push values to head of list"""
        import json
        # Serialize dict/list values to JSON
        serialized = [json.dumps(v) if isinstance(v, (dict, list)) else str(v) for v in values]
        return await self.retry(self.pool.lpush(key, *serialized))

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        """Get range of elements from list"""
        return await self.retry(self.pool.lrange(key, start, end))

    async def ltrim(self, key: str, start: int, end: int):
        """Trim list to specified range"""
        return await self.retry(self.pool.ltrim(key, start, end))

    async def llen(self, key: str) -> int:
        """Get length of list"""
        return await self.retry(self.pool.llen(key))

    async def scan(self, match: str, count: int = 100) -> List[str]:
        """Scan for keys matching pattern"""
        cursor = 0
        results = []
        while True:
            cursor, keys = await self.retry(self.pool.scan(cursor=cursor, match=match, count=count))
            results.extend(keys)
            if cursor == 0:
                break
        return results

    async def delete(self, *keys: str):
        """Delete one or more keys"""
        if not keys:
            return 0
        return await self.retry(self.pool.delete(*keys))

    async def expire(self, key: str, ttl: int):
        """Set expiration on key"""
        return await self.retry(self.pool.expire(key, ttl))

    async def ping(self) -> bool:
        """Health check for Redis connection"""
        try:
            return await self.retry(self.pool.ping())
        except Exception:
            return False

    async def close(self):
        """Close Redis connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Redis pool closed")

    # ========================================
    # Production_2 Queue Management Functions
    # ========================================

    async def hset(self, key: str, field: str, value: Any):
        """Set field in hash"""
        return await self.retry(self.pool.hset(key, field, value))

    async def hmset(self, key: str, mapping: Dict[str, Any]):
        """Set multiple fields in hash"""
        return await self.retry(self.pool.hset(key, mapping=mapping))

    async def hget(self, key: str, field: str) -> Optional[str]:
        """Get field from hash"""
        return await self.retry(self.pool.hget(key, field))

    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all fields from hash"""
        return await self.retry(self.pool.hgetall(key))

    async def ttl(self, key: str) -> int:
        """Get TTL of key"""
        return await self.retry(self.pool.ttl(key))

    async def add_to_queue_onboarding(
        self,
        mobile_number: str,
        email: str,
        device_id: str,
        hash_value: str,
        salt: str,
        country_code: str,
        local_mobile: str,
        request_timestamp: str,
        user_deadline: str,
        expires_at: str,
        user_timelimit_seconds: int,
        redis_ttl_seconds: int
    ) -> bool:
        """
        Store onboarding request in Redis Queue.
        
        Creates:
        - queue_onboarding:{mobile} HASH with all fields
        - onboard_hash:{mobile} STRING for quick lookup
        - Both with TTL = redis_ttl_seconds
        """
        try:
            queue_key = f"queue_onboarding:{mobile_number}"
            hash_key = f"onboard_hash:{mobile_number}"
            
            # Store onboarding data in HASH
            await self.hmset(queue_key, {
                'mobile_number': mobile_number,
                'email': email,
                'device_id': device_id,
                'hash': hash_value,
                'salt': salt,
                'country_code': country_code,
                'local_mobile': local_mobile,
                'request_timestamp': request_timestamp,
                'user_deadline': user_deadline,
                'expires_at': expires_at,
                'user_timelimit_seconds': str(user_timelimit_seconds),
                'redis_ttl_seconds': str(redis_ttl_seconds)
            })
            await self.expire(queue_key, redis_ttl_seconds)
            
            # Store hash for quick lookup
            await self.setex(hash_key, redis_ttl_seconds, hash_value)
            
            logger.info(f"Onboarding queued for {mobile_number} with TTL {redis_ttl_seconds}s")
            return True
        except Exception as e:
            logger.error(f"Failed to queue onboarding for {mobile_number}: {e}", exc_info=True)
            return False

    async def add_to_queue_input_sms(
        self,
        redis_id: int,
        mobile_number: str,
        device_id: str,
        sms_message: str,
        received_timestamp: str,
        country_code: str = None,
        local_mobile: str = None
    ) -> bool:
        """
        Store incoming SMS in Redis Queue.
        
        Creates queue_input_sms:{id} HASH with SMS data and check result fields.
        No TTL - persisted until batch dump.
        """
        try:
            queue_key = f"queue_input_sms:{redis_id}"
            
            await self.hmset(queue_key, {
                'id': str(redis_id),
                'mobile_number': mobile_number,
                'device_id': device_id,
                'sms_message': sms_message,
                'received_timestamp': received_timestamp,
                'country_code': country_code or '',
                'local_mobile': local_mobile or '',
                'mobile_check': '3',  # 3=disabled by default
                'duplicate_check': '3',
                'header_hash_check': '3',
                'count_check': '3',
                'foreign_number_check': '3',
                'blacklist_check': '3',
                'time_window_check': '3',
                'validation_status': 'pending',
                'failed_at_check': ''
            })
            
            logger.info(f"SMS queued: queue_input_sms:{redis_id} from {mobile_number}")
            return True
        except Exception as e:
            logger.error(f"Failed to queue SMS {redis_id}: {e}", exc_info=True)
            return False

    async def update_check_result(
        self,
        redis_id: int,
        check_name: str,
        status_code: int,
        validation_status: str = None,
        failed_at_check: str = None
    ) -> bool:
        """
        Update check result in queue_input_sms:{id}.
        
        Args:
            redis_id: SMS ID in queue
            check_name: Name of check (mobile_check, duplicate_check, etc.)
            status_code: 1=pass, 2=fail, 3=disabled, 4=N/A
            validation_status: Optional overall status update
            failed_at_check: Optional failed check name
        """
        try:
            queue_key = f"queue_input_sms:{redis_id}"
            
            updates = {check_name: str(status_code)}
            if validation_status:
                updates['validation_status'] = validation_status
            if failed_at_check:
                updates['failed_at_check'] = failed_at_check
            
            await self.hmset(queue_key, updates)
            
            logger.debug(f"Updated {check_name}={status_code} for queue_input_sms:{redis_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update check result: {e}", exc_info=True)
            return False

    async def mark_mobile_validated(
        self,
        mobile_number: str,
        device_id: str
    ) -> bool:
        """
        Add mobile+device to Queue_validated_mobiles SET.
        
        Format: {mobile}:{device_id}
        Used for duplicate detection.
        """
        try:
            composite_key = f"{mobile_number}:{device_id}"
            await self.sadd('Queue_validated_mobiles', composite_key)
            
            logger.info(f"Marked validated: {composite_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to mark validated {mobile_number}:{device_id}: {e}", exc_info=True)
            return False

    async def get_next_id(self, counter_name: str) -> int:
        """
        Get next auto-incrementing ID.
        
        Args:
            counter_name: 'queue_input_sms' or 'queue_onboarding'
            
        Returns:
            Next available ID
        """
        try:
            counter_key = f"counter:{counter_name}"
            next_id = await self.incr(counter_key)
            return next_id
        except Exception as e:
            logger.error(f"Failed to get next ID for {counter_name}: {e}", exc_info=True)
            raise

    async def get_setting_value(
        self,
        setting_key: str,
        default: str = None
    ) -> Optional[str]:
        """
        Get setting value with 60s Redis cache.
        
        Cache key format: setting:{key}
        If not in cache, returns None (caller should fetch from PostgreSQL).
        
        Args:
            setting_key: Setting name from sms_settings table
            default: Default value if not found
            
        Returns:
            Setting value or default
        """
        try:
            cache_key = f"setting:{setting_key}"
            value = await self.get(cache_key)
            
            if value is not None:
                logger.debug(f"Setting cache HIT: {setting_key}={value}")
                return value
            
            logger.debug(f"Setting cache MISS: {setting_key}")
            return default
        except Exception as e:
            logger.error(f"Failed to get setting {setting_key}: {e}", exc_info=True)
            return default

    async def cache_setting_value(
        self,
        setting_key: str,
        value: str,
        ttl: int = 60
    ) -> bool:
        """
        Cache setting value in Redis with TTL.
        
        Args:
            setting_key: Setting name
            value: Setting value
            ttl: Cache TTL in seconds (default: 60)
        """
        try:
            cache_key = f"setting:{setting_key}"
            await self.setex(cache_key, ttl, value)
            
            logger.debug(f"Cached setting: {setting_key}={value} (TTL={ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Failed to cache setting {setting_key}: {e}", exc_info=True)
            return False

    async def invalidate_setting_cache(
        self,
        setting_key: str = None
    ) -> bool:
        """
        Invalidate setting cache.
        
        Args:
            setting_key: Specific setting to invalidate, or None for all settings
        """
        try:
            if setting_key:
                cache_key = f"setting:{setting_key}"
                await self.delete(cache_key)
                logger.info(f"Invalidated setting cache: {setting_key}")
            else:
                # Invalidate all settings
                keys = await self.scan("setting:*")
                if keys:
                    await self.delete(*keys)
                    logger.info(f"Invalidated all setting caches ({len(keys)} keys)")
            
            return True
        except Exception as e:
            logger.error(f"Failed to invalidate setting cache: {e}", exc_info=True)
            return False

# Singleton async Redis pool instance
redis_pool = RedisPool(
    host=REDIS_CONFIG['host'],
    port=REDIS_CONFIG['port'],
    password=REDIS_CONFIG['password'],
    db=REDIS_CONFIG['db']
)


# Helper function for easy access
async def get_redis_client() -> RedisPool:
    """Get initialized Redis pool instance"""
    if not redis_pool.pool:
        await redis_pool.init()
    return redis_pool