"""
Count Check Module - Redis-Only Implementation
Validates SMS count per mobile number against configurable threshold.

Production_2 Architecture:
- Uses Redis sms_count:{mobile} counter with 24h TTL
- NO PostgreSQL dependency (no count_sms table)
- Threshold dynamically loaded from sms_settings (cached 60s)
- Counter auto-expires after 24h (Redis TTL)
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


async def count_check(
    mobile_number: str, 
    redis_client, 
    get_setting_func=None
) -> Tuple[int, str]:
    """
    Check if mobile number has exceeded SMS count threshold (24h window).
    
    Args:
        mobile_number: E.164 formatted mobile number
        redis_client: Async Redis client instance
        get_setting_func: Optional function to get cached settings
        
    Returns:
        Tuple of (status_code, message)
        status_code: 1=pass, 2=fail, 3=check_disabled, 4=N/A
        message: Human-readable result
        
    Process:
        1. Check if count_check is enabled (from sms_settings)
        2. Get threshold from sms_settings (default: 5)
        3. Increment Redis counter sms_count:{mobile} with 24h TTL
        4. Compare count against threshold
        5. Return pass/fail status
    """
    try:
        # Check if count_check is enabled
        if get_setting_func:
            enabled = await get_setting_func('count_check_enabled', default='true')
            if enabled.lower() != 'true':
                logger.info(f"Count check disabled for {mobile_number}")
                return (3, "count_check_disabled")
        
        # Get threshold from settings (default: 5)
        threshold = 5
        if get_setting_func:
            threshold_str = await get_setting_func('count_check_threshold', default='5')
            try:
                threshold = int(threshold_str)
            except ValueError:
                logger.warning(f"Invalid count_check_threshold: {threshold_str}, using default 5")
                threshold = 5
        
        # Redis key for count
        count_key = f"sms_count:{mobile_number}"
        
        # Increment counter with 24h TTL
        # INCR returns the new value after increment
        current_count = await redis_client.incr(count_key)
        
        # Set TTL on first increment (when count == 1)
        if current_count == 1:
            ttl_seconds = 86400  # 24 hours
            if get_setting_func:
                ttl_str = await get_setting_func('onboarding_ttl_seconds', default='86400')
                try:
                    ttl_seconds = int(ttl_str)
                except ValueError:
                    ttl_seconds = 86400
            
            await redis_client.expire(count_key, ttl_seconds)
            logger.info(f"Set {count_key} TTL to {ttl_seconds}s")
        
        logger.info(f"Count check for {mobile_number}: {current_count}/{threshold}")
        
        # Check against threshold
        if current_count > threshold:
            logger.warning(
                f"Count check FAILED for {mobile_number}: "
                f"{current_count} SMS exceeds threshold {threshold}"
            )
            return (2, f"count_exceeded_{current_count}_of_{threshold}")
        
        logger.info(f"Count check PASSED for {mobile_number}: {current_count}/{threshold}")
        return (1, f"count_ok_{current_count}_of_{threshold}")
        
    except Exception as e:
        logger.error(f"Count check ERROR for {mobile_number}: {str(e)}", exc_info=True)
        # On error, fail safe: reject the SMS
        return (2, f"count_check_error_{type(e).__name__}")


async def get_current_count(mobile_number: str, redis_client) -> int:
    """
    Get current SMS count for mobile number (for monitoring/debugging).
    
    Args:
        mobile_number: E.164 formatted mobile number
        redis_client: Async Redis client instance
        
    Returns:
        Current count (0 if key doesn't exist)
    """
    try:
        count_key = f"sms_count:{mobile_number}"
        count = await redis_client.get(count_key)
        return int(count) if count else 0
    except Exception as e:
        logger.error(f"Error getting count for {mobile_number}: {str(e)}")
        return 0


async def reset_count(mobile_number: str, redis_client) -> bool:
    """
    Reset SMS count for mobile number (admin function).
    
    Args:
        mobile_number: E.164 formatted mobile number
        redis_client: Async Redis client instance
        
    Returns:
        True if reset successful, False otherwise
    """
    try:
        count_key = f"sms_count:{mobile_number}"
        await redis_client.delete(count_key)
        logger.info(f"Reset count for {mobile_number}")
        return True
    except Exception as e:
        logger.error(f"Error resetting count for {mobile_number}: {str(e)}")
        return False


async def get_count_ttl(mobile_number: str, redis_client) -> int:
    """
    Get remaining TTL for count key (for monitoring).
    
    Args:
        mobile_number: E.164 formatted mobile number
        redis_client: Async Redis client instance
        
    Returns:
        Remaining TTL in seconds (-1 if no TTL, -2 if key doesn't exist)
    """
    try:
        count_key = f"sms_count:{mobile_number}"
        ttl = await redis_client.ttl(count_key)
        return ttl
    except Exception as e:
        logger.error(f"Error getting TTL for {mobile_number}: {str(e)}")
        return -2
