"""
Blacklist Check Module - Redis-Only Implementation
Validates that mobile number is not blacklisted.

Production_2 Architecture:
- Uses Redis blacklist_mobiles SET (loaded from PostgreSQL)
- NO PostgreSQL query in hot path
- Blacklist populated by background worker from blacklist_sms table
- Check can be enabled/disabled from sms_settings
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


async def blacklist_check(
    mobile_number: str,
    redis_client,
    get_setting_func=None
) -> Tuple[int, str]:
    """
    Check if mobile number is blacklisted.
    
    Args:
        mobile_number: E.164 formatted mobile number
        redis_client: Async Redis client instance
        get_setting_func: Optional function to get cached settings
        
    Returns:
        Tuple of (status_code, message)
        status_code: 1=pass, 2=fail, 3=check_disabled, 4=N/A
        message: Human-readable result
        
    Process:
        1. Check if blacklist_check is enabled (from sms_settings)
        2. Check if mobile_number exists in blacklist_mobiles SET
        3. Return pass/fail status
        
    Note:
        blacklist_mobiles SET is populated by background worker
        from PostgreSQL blacklist_sms table (periodic sync)
    """
    try:
        # Check if blacklist_check is enabled
        if get_setting_func:
            enabled = await get_setting_func('blacklist_check_enabled', default='true')
            if str(enabled).lower() != 'true':
                logger.info(f"Blacklist check disabled for {mobile_number}")
                return (3, "blacklist_check_disabled")
        
        # Check if exists in blacklist_mobiles SET
        is_blacklisted = await redis_client.sismember('blacklist_mobiles', mobile_number)
        
        if is_blacklisted:
            logger.warning(f"Blacklist check FAILED for {mobile_number} - blacklisted")
            return (2, "mobile_blacklisted")
        
        logger.info(f"Blacklist check PASSED for {mobile_number}")
        return (1, "not_blacklisted")
        
    except Exception as e:
        logger.error(
            f"Blacklist check ERROR for {mobile_number}: {str(e)}", 
            exc_info=True
        )
        # On error, fail safe: reject the SMS
        return (2, f"blacklist_check_error_{type(e).__name__}")


# Legacy function for backward compatibility
async def validate_blacklist_check(sms, pool):
    """
    Legacy function - deprecated, use blacklist_check() instead.
    Maintained for backward compatibility during transition.
    
    NOTE: This function no longer accesses PostgreSQL.
    The blacklist is maintained in Redis by background worker.
    """
    logger.warning("validate_blacklist_check() is deprecated, use blacklist_check()")
    
    # Extract mobile from sms object
    mobile = getattr(sms, 'sender_number', '')
    
    # Import redis_client from main module
    from core.redis_client import get_redis_client
    redis_client = await get_redis_client()
    
    status, message = await blacklist_check(mobile, redis_client)
    return status