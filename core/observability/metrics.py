from prometheus_client import Gauge, Counter
import logging
from typing import Optional
from core.redis_client import redis_pool

logger = logging.getLogger(__name__)

# Define metrics
SMS_MONITOR_QUEUE_LEN = Gauge('sms_bridge_monitor_queue_length', 'Length of sms_monitor_queue')
OUT_SMS_NUMBERS_COUNT = Gauge('sms_bridge_out_sms_numbers_count', 'Count of out_sms_numbers set')
BLACKLIST_MOBILES_COUNT = Gauge('sms_bridge_blacklist_mobiles_count', 'Count of blacklist_mobiles set')
ABUSE_COUNTER_KEYS = Gauge('sms_bridge_abuse_counters_keys', 'Number of abuse_counter:* keys')

SMS_MONITOR_EVENTS_PROCESSED = Counter('sms_bridge_monitor_events_processed_total', 'Total monitor events processed')
SMS_ONBOARD_REQUESTS = Counter('sms_bridge_onboard_requests_total', 'Total onboard requests')


async def collect_once():
    """Collect a snapshot from Redis and update Prometheus metrics.

    This is a synchronous scrape helper called by the ASGI /metrics endpoint.
    """
    try:
        # Use direct redis commands via redis_pool
        qlen = await redis_pool.llen('sms_monitor_queue')
        SMS_MONITOR_QUEUE_LEN.set(qlen)

        out_count = await redis_pool.scard('out_sms_numbers')
        OUT_SMS_NUMBERS_COUNT.set(out_count)

        blacklist_count = await redis_pool.scard('blacklist_mobiles')
        BLACKLIST_MOBILES_COUNT.set(blacklist_count)

        # Count abuse keys using scan (returns all matching keys)
        abuse_keys = await redis_pool.scan('abuse_counter:*')
        ABUSE_COUNTER_KEYS.set(len(abuse_keys))

    except Exception as e:
        logger.error(f"Error collecting observability metrics from Redis: {e}")
