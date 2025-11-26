"""
Async background workers for abuse detection and sms_monitor logging.
These workers run independently and never block the main SMS processing flow.
"""

import asyncio
import json
import logging
from core.redis_client import redis_pool
import asyncpg
import os
try:
    from core.observability.metrics import SMS_MONITOR_EVENTS_PROCESSED
except Exception:
    SMS_MONITOR_EVENTS_PROCESSED = None

logger = logging.getLogger(__name__)

# DB settings for audit/reporting
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'database': os.getenv('POSTGRES_DB', 'sms_bridge'),
    'user': os.getenv('POSTGRES_USER', 'sms_user'),
    'password': os.getenv('POSTGRES_PASSWORD', ''),
    'port': int(os.getenv('POSTGRES_PORT', 6432)),  # pgbouncer port
}

async def get_db_pool():
    """Get database connection pool"""
    return await asyncpg.create_pool(
        **POSTGRES_CONFIG,
        min_size=1,
        max_size=5,
        statement_cache_size=0  # Required for PgBouncer
    )

async def abuse_detector_worker(pool, blacklist_threshold: int = 10, interval: int = 60):
    """
    Periodically checks abuse_counter:* keys, blacklists mobiles exceeding threshold,
    and resets keys. Production_2: No count_sms table - counters in Redis only.
    
    Args:
        pool: PostgreSQL connection pool
        blacklist_threshold: Number of abuse attempts before blacklisting
        interval: How often to run the check (in seconds)
    """
    logger.info(f"Starting abuse detector worker (threshold={blacklist_threshold}, interval={interval}s)")
    
    try:
        
        while True:
            try:
                # Scan for all abuse counter keys
                keys = await redis_pool.scan("abuse_counter:*")
                
                if keys:
                    logger.info(f"Found {len(keys)} abuse counter keys to process")
                    
                blacklist_batch = []
                
                for key in keys:
                    try:
                        mobile = key.split(":", 1)[1] if ":" in key else key
                        count = int(await redis_pool.get(key) or 0)
                        
                        if count >= blacklist_threshold:
                            # Add to blacklist
                            await redis_pool.sadd("blacklist_mobiles", mobile)
                            blacklist_batch.append((mobile, count))
                            logger.warning(f"Blacklisted mobile {mobile} (abuse count: {count})")
                        
                        # Delete the counter key after processing
                        await redis_pool.delete(key)
                        
                    except Exception as e:
                        logger.error(f"Error processing abuse counter for key {key}: {e}")
                
                # Log blacklist actions to DB (Production_2: use mobile_number column)
                if blacklist_batch:
                    try:
                        async with pool.acquire() as conn:
                            await conn.executemany(
                                """
                                INSERT INTO blacklist_sms (mobile_number, blacklisted_at, reason, message_count)
                                VALUES ($1, NOW(), 'abuse_threshold', $2)
                                ON CONFLICT (mobile_number) DO UPDATE
                                SET message_count = EXCLUDED.message_count,
                                    blacklisted_at = NOW()
                                """,
                                blacklist_batch
                            )
                        logger.info(f"Logged {len(blacklist_batch)} blacklist actions to database")
                    except Exception as e:
                        logger.error(f"Error logging blacklist to DB: {e}")
                
            except Exception as e:
                logger.error(f"Error in abuse detector iteration: {e}")
            
            await asyncio.sleep(interval)
            
    except Exception as e:
        logger.error(f"Fatal error in abuse detector worker: {e}")

async def sms_monitor_logger(batch_size: int = 100, interval: int = 30):
    """
    Batch-process sms_monitor_queue, log events for debugging.
    Production_2: No sms_monitor table - events logged to console/file only.
    
    Args:
        batch_size: Maximum number of events to process per batch
        interval: How often to run the batch process (in seconds)
    """
    logger.info(f"Starting SMS monitor logger (batch_size={batch_size}, interval={interval}s)")
    
    while True:
        try:
            # Check queue length
            queue_len = await redis_pool.llen("sms_monitor_queue")
            
            if queue_len > 0:
                # Get events from queue
                events_raw = await redis_pool.lrange("sms_monitor_queue", 0, batch_size - 1)
                
                if events_raw:
                    logger.info(f"Processing {len(events_raw)} monitor events from queue")
                    
                    # Parse and log JSON events (no DB write in Production_2)
                    events = []
                    for event_str in events_raw:
                        try:
                            event = json.loads(event_str) if isinstance(event_str, str) else event_str
                            events.append(event)
                            logger.debug(f"Monitor event: {event}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse event JSON: {event_str}, error: {e}")
                    
                    if events:
                        logger.info(f"Logged {len(events)} monitor events")
                        # Increment Prometheus counter for processed events
                        try:
                            if SMS_MONITOR_EVENTS_PROCESSED:
                                SMS_MONITOR_EVENTS_PROCESSED.inc(len(events))
                        except Exception as e:
                            logger.error(f"Failed to increment SMS_MONITOR_EVENTS_PROCESSED: {e}")
                    
                    # Remove processed events from queue
                    await redis_pool.ltrim("sms_monitor_queue", len(events_raw), -1)
            
        except Exception as e:
            logger.error(f"Error in monitor logger iteration: {e}")
        
        await asyncio.sleep(interval)

async def get_setting_value(pool, setting_key: str, default: str = None) -> str:
    """
    Get setting value from sms_settings table with Redis cache (60s TTL).
    
    Args:
        pool: PostgreSQL connection pool
        setting_key: Setting name
        default: Default value if not found
        
    Returns:
        Setting value or default
        
    Flow:
        1. Check Redis cache (setting:{key} with 60s TTL)
        2. If miss, query PostgreSQL sms_settings table
        3. Cache result in Redis
        4. Return value
    """
    try:
        # Check Redis cache first
        cached_value = await redis_pool.get_setting_value(setting_key)
        if cached_value is not None:
            return cached_value
        
        # Cache miss - query PostgreSQL
        async with pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT setting_value FROM sms_settings WHERE setting_key = $1",
                setting_key
            )
        
        if value is None:
            logger.warning(f"Setting '{setting_key}' not found in database, using default: {default}")
            value = default
        
        # Cache in Redis for 60s
        if value is not None:
            await redis_pool.cache_setting_value(setting_key, value, ttl=60)
        
        return value or default
    except Exception as e:
        logger.error(f"Failed to get setting '{setting_key}': {e}", exc_info=True)
        return default


async def dump_queue_input_sms_to_postgres(pool):
    """
    Production_2 Worker: Batch dump queue_input_sms to PostgreSQL input_sms table.
    
    Frequency: Configurable via local_sync_interval_seconds (default: 120s)
    Process:
        1. Get all queue_input_sms:{id} keys from Redis
        2. Batch insert to input_sms table with check results
        3. Delete processed keys from Redis
    """
    logger.info("Starting dump_queue_input_sms_to_postgres worker")
    
    while True:
        try:
            # Get interval from settings (dynamic)
            interval_str = await get_setting_value(pool, 'local_sync_interval_seconds', '120')
            interval = int(interval_str)
            
            # Scan for queue_input_sms keys
            keys = await redis_pool.scan("queue_input_sms:*")
            
            if keys:
                logger.info(f"Dumping {len(keys)} SMS records to PostgreSQL")
                
                batch = []
                for key in keys:
                    try:
                        data = await redis_pool.hgetall(key)
                        if data:
                            batch.append((
                                int(data.get('id', 0)),
                                data.get('mobile_number', ''),
                                data.get('country_code', ''),
                                data.get('local_mobile', ''),
                                data.get('sms_message', ''),
                                data.get('received_timestamp', ''),
                                data.get('device_id', ''),
                                int(data.get('mobile_check', 3)),
                                int(data.get('duplicate_check', 3)),
                                int(data.get('header_hash_check', 3)),
                                int(data.get('count_check', 3)),
                                int(data.get('foreign_number_check', 3)),
                                int(data.get('blacklist_check', 3)),
                                int(data.get('time_window_check', 3)),
                                data.get('validation_status', 'pending'),
                                data.get('failed_at_check', '')
                            ))
                    except Exception as e:
                        logger.error(f"Error processing {key}: {e}")
                
                if batch:
                    async with pool.acquire() as conn:
                        await conn.executemany(
                            """
                            INSERT INTO input_sms (
                                redis_id, mobile_number, country_code, local_mobile,
                                sms_message, received_timestamp, device_id,
                                mobile_check, duplicate_check, header_hash_check,
                                count_check, foreign_number_check, blacklist_check,
                                time_window_check, validation_status, failed_at_check
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                            ON CONFLICT (redis_id) DO NOTHING
                            """,
                            batch
                        )
                    logger.info(f"Dumped {len(batch)} SMS records to input_sms table")
                    
                    # Delete processed keys
                    await redis_pool.delete(*keys)
                    logger.info(f"Deleted {len(keys)} processed keys from Redis")
            
        except Exception as e:
            logger.error(f"Error in dump_queue_input_sms_to_postgres: {e}", exc_info=True)
        
        await asyncio.sleep(interval)


async def sync_validated_mobiles_to_hetzner(pool):
    """
    Production_2 Worker: Sync validated mobiles to Hetzner Supabase.
    
    Frequency: Configurable via hetzner_sync_interval_seconds (default: 10s)
    Data: ONLY validated mobiles (validation_status='passed')
    Process:
        1. Query input_sms WHERE validation_status='passed' AND synced_to_hetzner=false
        2. Sync to Hetzner Supabase via HTTP/Supabase client
        3. Mark as synced_to_hetzner=true
    
    Note: Hetzner sync implementation depends on Supabase client setup.
    """
    logger.info("Starting sync_validated_mobiles_to_hetzner worker")
    
    while True:
        try:
            # Get interval from settings (dynamic)
            interval_str = await get_setting_value(pool, 'hetzner_sync_interval_seconds', '10')
            interval = int(interval_str)
            
            # TODO: Query input_sms for unsynced validated mobiles
            # TODO: Sync to Hetzner Supabase (requires Supabase client configuration)
            # TODO: Mark as synced_to_hetzner=true
            
            logger.debug(f"Hetzner sync check (interval={interval}s)")
            
        except Exception as e:
            logger.error(f"Error in sync_validated_mobiles_to_hetzner: {e}", exc_info=True)
        
        await asyncio.sleep(interval)


async def populate_blacklist_from_postgres(pool):
    """
    Production_2 Worker: Load blacklist from PostgreSQL to Redis.
    
    Frequency: Configurable via blacklist_check_interval_seconds (default: 300s)
    Process:
        1. Query blacklist_sms table
        2. Load all mobile numbers into blacklist_mobiles SET
        3. Replace existing SET (full refresh)
    """
    logger.info("Starting populate_blacklist_from_postgres worker")
    
    while True:
        try:
            # Get interval from settings (dynamic)
            interval_str = await get_setting_value(pool, 'blacklist_check_interval_seconds', '300')
            interval = int(interval_str)
            
            # Query blacklist_sms table
            async with pool.acquire() as conn:
                blacklist = await conn.fetch("SELECT mobile_number FROM blacklist_sms")
            
            if blacklist:
                # Clear existing blacklist SET
                await redis_pool.delete('blacklist_mobiles')
                
                # Add all blacklisted mobiles
                mobiles = [row['mobile_number'] for row in blacklist]
                await redis_pool.sadd('blacklist_mobiles', *mobiles)
                
                logger.info(f"Loaded {len(mobiles)} blacklisted mobiles to Redis")
            else:
                logger.info("No blacklisted mobiles found")
            
        except Exception as e:
            logger.error(f"Error in populate_blacklist_from_postgres: {e}", exc_info=True)
        
        await asyncio.sleep(interval)


async def persist_counters_to_postgres(pool):
    """
    Production_2 Worker: Backup Redis counter values to PostgreSQL.
    
    Frequency: Every 60 seconds
    Process:
        1. Get counter:queue_input_sms and counter:queue_onboarding values
        2. Update power_down_store_counters table
        3. Used for Redis recovery after power-down
    """
    logger.info("Starting persist_counters_to_postgres worker")
    
    while True:
        try:
            # Get counter values from Redis
            input_sms_counter = await redis_pool.get('counter:queue_input_sms')
            onboarding_counter = await redis_pool.get('counter:queue_onboarding')
            
            # Update PostgreSQL
            async with pool.acquire() as conn:
                if input_sms_counter:
                    await conn.execute(
                        """
                        INSERT INTO power_down_store_counters (counter_name, counter_value, updated_at)
                        VALUES ('queue_input_sms', $1, NOW())
                        ON CONFLICT (counter_name) DO UPDATE
                        SET counter_value = EXCLUDED.counter_value, updated_at = NOW()
                        """,
                        int(input_sms_counter)
                    )
                
                if onboarding_counter:
                    await conn.execute(
                        """
                        INSERT INTO power_down_store_counters (counter_name, counter_value, updated_at)
                        VALUES ('queue_onboarding', $1, NOW())
                        ON CONFLICT (counter_name) DO UPDATE
                        SET counter_value = EXCLUDED.counter_value, updated_at = NOW()
                        """,
                        int(onboarding_counter)
                    )
            
            logger.debug(f"Persisted counters: input_sms={input_sms_counter}, onboarding={onboarding_counter}")
            
        except Exception as e:
            logger.error(f"Error in persist_counters_to_postgres: {e}", exc_info=True)
        
        await asyncio.sleep(60)


async def start_background_workers():
    """Start all background workers (Production_2)"""
    logger.info("Starting Production_2 background workers...")
    
    # Get database pool
    pool = await get_db_pool()
    
    # Read legacy configuration from environment (for backward compatibility)
    abuse_threshold = int(os.getenv('ABUSE_THRESHOLD', 10))
    abuse_interval = int(os.getenv('ABUSE_CHECK_INTERVAL', 60))
    monitor_batch_size = int(os.getenv('MONITOR_BATCH_SIZE', 100))
    monitor_interval = int(os.getenv('MONITOR_LOG_INTERVAL', 30))
    
    # Start legacy workers (if needed)
    asyncio.create_task(abuse_detector_worker(pool, abuse_threshold, abuse_interval))
    asyncio.create_task(sms_monitor_logger(monitor_batch_size, monitor_interval))
    
    # Start Production_2 workers
    asyncio.create_task(dump_queue_input_sms_to_postgres(pool))
    asyncio.create_task(sync_validated_mobiles_to_hetzner(pool))
    asyncio.create_task(populate_blacklist_from_postgres(pool))
    asyncio.create_task(persist_counters_to_postgres(pool))
    
    logger.info("All background workers started successfully")

# Entrypoint for workers (run in separate process if needed)
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    loop = asyncio.get_event_loop()
    loop.create_task(start_background_workers())
    loop.run_forever()