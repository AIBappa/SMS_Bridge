"""
Duplicate Check Module - Redis-Only Implementation
Validates that mobile+device combination hasn't been validated before.

Production_2 Architecture:
- Uses Redis Queue_validated_mobiles SET (format: {mobile}:{device_id})
- NO PostgreSQL dependency (no out_sms table)
- Check can be enabled/disabled from sms_settings
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


async def duplicate_check(
    mobile_number: str,
    device_id: str,
    redis_client,
    get_setting_func=None
) -> Tuple[int, str]:
    """
    Check if mobile+device combination has been validated before.
    
    Args:
        mobile_number: E.164 formatted mobile number
        device_id: Unique device identifier
        redis_client: Async Redis client instance
        get_setting_func: Optional function to get cached settings
        
    Returns:
        Tuple of (status_code, message)
        status_code: 1=pass, 2=fail, 3=check_disabled, 4=N/A
        message: Human-readable result
        
    Process:
        1. Check if duplicate_check is enabled (from sms_settings)
        2. Create composite key: {mobile}:{device_id}
        3. Check if exists in Queue_validated_mobiles SET
        4. Return pass/fail status
    """
    try:
        # Check if duplicate_check is enabled
        if get_setting_func:
            enabled = await get_setting_func('duplicate_check_enabled', default='true')
            if enabled.lower() != 'true':
                logger.info(f"Duplicate check disabled for {mobile_number}")
                return (3, "duplicate_check_disabled")
        
        # Create composite key
        composite_key = f"{mobile_number}:{device_id}"
        
        # Check if exists in Queue_validated_mobiles SET
        is_duplicate = await redis_client.sismember('Queue_validated_mobiles', composite_key)
        
        if is_duplicate:
            logger.warning(
                f"Duplicate check FAILED for {mobile_number}:{device_id} - "
                "already validated"
            )
            return (2, "duplicate_mobile_device")
        
        logger.info(f"Duplicate check PASSED for {mobile_number}:{device_id}")
        return (1, "not_duplicate")
        
    except Exception as e:
        logger.error(
            f"Duplicate check ERROR for {mobile_number}:{device_id}: {str(e)}", 
            exc_info=True
        )
        # On error, fail safe: treat as not duplicate to allow processing
        return (1, f"duplicate_check_error_{type(e).__name__}")


# Legacy function for backward compatibility
async def validate_duplicate_check(sms, pool):
    """
    Legacy function - deprecated, use duplicate_check() instead.
    Maintained for backward compatibility during transition.
    """
    logger.warning("validate_duplicate_check() is deprecated, use duplicate_check()")
    # Extract mobile and device_id from sms object
    mobile = getattr(sms, 'sender_number', '')
    device_id = getattr(sms, 'device_id', 'unknown')
    
    # Import redis_client from main module
    from core.redis_client import get_redis_client
    redis_client = await get_redis_client()
    
    status, message = await duplicate_check(mobile, device_id, redis_client)
    return status