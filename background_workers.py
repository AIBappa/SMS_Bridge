"""
Async background workers for abuse detection and sms_monitor logging.
These workers run independently and never block the main SMS processing flow.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List
from redis_client import redis_pool
import asyncpg
import os

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

async def abuse_detector_worker(blacklist_threshold: int = 10, interval: int = 60):
    """
    Periodically checks abuse_counter:* keys, blacklists mobiles exceeding threshold,
    exports counts to DB, and resets keys.
    
    Args:
        blacklist_threshold: Number of abuse attempts before blacklisting
        interval: How often to run the check (in seconds)
    """
    logger.info(f"Starting abuse detector worker (threshold={blacklist_threshold}, interval={interval}s)")
    pool = None
    
    try:
        pool = await get_db_pool()
        
        while True:
            try:
                # Scan for all abuse counter keys
                keys = await redis_pool.scan("abuse_counter:*")
                
                if keys:
                    logger.info(f"Found {len(keys)} abuse counter keys to process")
                    
                blacklist_batch = []
                count_batch = []
                
                for key in keys:
                    try:
                        mobile = key.split(":", 1)[1] if ":" in key else key
                        count = int(await redis_pool.get(key) or 0)
                        
                        if count >= blacklist_threshold:
                            # Add to blacklist
                            await redis_pool.sadd("blacklist_mobiles", mobile)
                            await redis_pool.lpush("blacklist_queue", {
                                "mobile": mobile,
                                "count": count,
                                "action": "blacklisted"
                            })
                            blacklist_batch.append(mobile)
                            logger.warning(f"Blacklisted mobile {mobile} (abuse count: {count})")
                        
                        count_batch.append((mobile, count))
                        
                        # Delete the counter key after processing
                        await redis_pool.delete(key)
                        
                    except Exception as e:
                        logger.error(f"Error processing abuse counter for key {key}: {e}")
                
                # Export counts to DB (count_sms table) for audit
                if count_batch:
                    try:
                        async with pool.acquire() as conn:
                            await conn.executemany(
                                """
                                INSERT INTO count_sms (sender_number, message_count, last_updated, country_code, local_mobile)
                                VALUES ($1, $2, NOW(), '', $1)
                                ON CONFLICT (sender_number) DO UPDATE
                                SET message_count = count_sms.message_count + EXCLUDED.message_count,
                                    last_updated = NOW()
                                """,
                                count_batch
                            )
                        logger.info(f"Exported {len(count_batch)} abuse counts to database")
                    except Exception as e:
                        logger.error(f"Error exporting abuse counts to DB: {e}")
                
                # Log blacklist actions to DB
                if blacklist_batch:
                    try:
                        async with pool.acquire() as conn:
                            await conn.executemany(
                                """
                                INSERT INTO blacklist_sms (sender_number, blacklisted_at, reason, message_count, country_code, local_mobile)
                                VALUES ($1, NOW(), 'abuse_threshold', $2, '', $1)
                                ON CONFLICT (sender_number) DO UPDATE
                                SET message_count = EXCLUDED.message_count,
                                    blacklisted_at = NOW()
                                """,
                                [(mobile, count) for mobile, count in count_batch if mobile in blacklist_batch]
                            )
                        logger.info(f"Logged {len(blacklist_batch)} blacklist actions to database")
                    except Exception as e:
                        logger.error(f"Error logging blacklist to DB: {e}")
                
            except Exception as e:
                logger.error(f"Error in abuse detector iteration: {e}")
            
            await asyncio.sleep(interval)
            
    except Exception as e:
        logger.error(f"Fatal error in abuse detector worker: {e}")
    finally:
        if pool:
            await pool.close()

async def sms_monitor_logger(batch_size: int = 100, interval: int = 30):
    """
    Batch-process sms_monitor_queue, insert bulk rows into sms_monitor table in Postgres.
    
    Args:
        batch_size: Maximum number of events to process per batch
        interval: How often to run the batch process (in seconds)
    """
    logger.info(f"Starting SMS monitor logger (batch_size={batch_size}, interval={interval}s)")
    pool = None
    
    try:
        pool = await get_db_pool()
        
        while True:
            try:
                # Check queue length
                queue_len = await redis_pool.llen("sms_monitor_queue")
                
                if queue_len > 0:
                    # Get events from queue
                    events_raw = await redis_pool.lrange("sms_monitor_queue", 0, batch_size - 1)
                    
                    if events_raw:
                        logger.info(f"Processing {len(events_raw)} monitor events from queue")
                        
                        # Parse JSON events
                        events = []
                        for event_str in events_raw:
                            try:
                                event = json.loads(event_str) if isinstance(event_str, str) else event_str
                                events.append(event)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse event JSON: {event_str}, error: {e}")
                        
                        # Insert to sms_monitor table
                        if events:
                            try:
                                async with pool.acquire() as conn:
                                    # Insert events (uuid, overall_status, failed_at_check, etc.)
                                    await conn.executemany(
                                        """
                                        INSERT INTO sms_monitor (uuid, overall_status, failed_at_check, processing_completed_at, country_code, local_mobile)
                                        VALUES ($1, $2, $3, NOW(), $4, $5)
                                        ON CONFLICT (uuid) DO UPDATE
                                        SET overall_status = EXCLUDED.overall_status,
                                            failed_at_check = EXCLUDED.failed_at_check,
                                            processing_completed_at = EXCLUDED.processing_completed_at
                                        """,
                                        [
                                            (
                                                e.get("uuid", ""),
                                                e.get("status", "unknown"),
                                                e.get("reason", ""),
                                                e.get("country_code", ""),
                                                e.get("mobile", "")
                                            )
                                            for e in events
                                        ]
                                    )
                                logger.info(f"Logged {len(events)} events to sms_monitor table")
                            except Exception as e:
                                logger.error(f"Error inserting monitor events to DB: {e}")
                        
                        # Remove processed events from queue
                        await redis_pool.ltrim("sms_monitor_queue", len(events_raw), -1)
                
            except Exception as e:
                logger.error(f"Error in monitor logger iteration: {e}")
            
            await asyncio.sleep(interval)
            
    except Exception as e:
        logger.error(f"Fatal error in SMS monitor logger: {e}")
    finally:
        if pool:
            await pool.close()

async def start_background_workers():
    """Start all background workers"""
    logger.info("Starting background workers...")
    
    # Read configuration from environment or use defaults
    abuse_threshold = int(os.getenv('ABUSE_THRESHOLD', 10))
    abuse_interval = int(os.getenv('ABUSE_CHECK_INTERVAL', 60))
    monitor_batch_size = int(os.getenv('MONITOR_BATCH_SIZE', 100))
    monitor_interval = int(os.getenv('MONITOR_LOG_INTERVAL', 30))
    
    # Start workers as background tasks
    asyncio.create_task(abuse_detector_worker(abuse_threshold, abuse_interval))
    asyncio.create_task(sms_monitor_logger(monitor_batch_size, monitor_interval))
    
    logger.info("Background workers started successfully")

# Entrypoint for workers (run in separate process if needed)
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    loop = asyncio.get_event_loop()
    loop.create_task(start_background_workers())
    loop.run_forever()