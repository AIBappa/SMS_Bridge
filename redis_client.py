"""
Async Redis client with pooling, retries, and helpers for SMS Bridge.
Provides both sync (redis.StrictRedis) and async (RedisPool) interfaces.
"""

import redis
import os
import asyncio
from typing import Any, Optional, Union, List, Dict
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
        raise last_exc

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
        except:
            return False

    async def close(self):
        """Close Redis connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Redis pool closed")

# Singleton async Redis pool instance
redis_pool = RedisPool(
    host=REDIS_CONFIG['host'],
    port=REDIS_CONFIG['port'],
    password=REDIS_CONFIG['password'],
    db=REDIS_CONFIG['db']
)