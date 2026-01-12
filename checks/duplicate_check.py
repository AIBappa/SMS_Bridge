import redis
import os

# Use the same Redis configuration as main app
REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'password': os.getenv('REDIS_PASSWORD', None),
    'db': 0,
}
redis_client = redis.StrictRedis(**REDIS_CONFIG)

async def validate_duplicate_check(sms, pool):
    # Use structured mobile data for duplicate tracking
    local_mobile = sms.local_mobile if hasattr(sms, 'local_mobile') and sms.local_mobile else sms.sender_number
    
    if redis_client.sismember('out_sms_numbers', local_mobile):
        return 2  # fail
    return 1  # pass