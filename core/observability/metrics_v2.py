"""
SMS Bridge v2.2 - Prometheus Metrics
Per monitoring spec Section 2.

Metrics exposed:
1. sms_bridge_onboarding_total (Counter) - Total onboarding requests by status
2. sms_bridge_sms_received_total (Counter) - Total SMS received by status
3. sms_bridge_pin_collected_total (Counter) - Total PINs collected by status
4. sms_bridge_sync_queue_length (Gauge) - Current sync_queue length
5. sms_bridge_audit_buffer_length (Gauge) - Current audit_buffer length
6. sms_bridge_blacklist_size (Gauge) - Current blacklist size
7. sms_bridge_rate_limited_total (Counter) - Total rate-limited requests
8. sms_bridge_validation_failures_total (Counter) - Validation failures by check
"""
import logging
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

# =============================================================================
# Counter Metrics
# =============================================================================

ONBOARDING_TOTAL = Counter(
    'sms_bridge_onboarding_total',
    'Total onboarding registration requests',
    ['status']  # success, failed
)

SMS_RECEIVED_TOTAL = Counter(
    'sms_bridge_sms_received_total',
    'Total SMS messages received',
    ['status']  # received, failed
)

PIN_COLLECTED_TOTAL = Counter(
    'sms_bridge_pin_collected_total',
    'Total PINs collected',
    ['status']  # success, failed
)

RATE_LIMITED_TOTAL = Counter(
    'sms_bridge_rate_limited_total',
    'Total rate-limited requests',
)

VALIDATION_FAILURES_TOTAL = Counter(
    'sms_bridge_validation_failures_total',
    'Total validation check failures',
    ['check']  # header_hash_check, foreign_number_check, count_check, blacklist_check
)

# =============================================================================
# Gauge Metrics
# =============================================================================

SYNC_QUEUE_LENGTH = Gauge(
    'sms_bridge_sync_queue_length',
    'Current length of sync_queue'
)

AUDIT_BUFFER_LENGTH = Gauge(
    'sms_bridge_audit_buffer_length',
    'Current length of audit_buffer'
)

BLACKLIST_SIZE = Gauge(
    'sms_bridge_blacklist_size',
    'Current size of blacklist set'
)

ACTIVE_ONBOARDING_COUNT = Gauge(
    'sms_bridge_active_onboarding_count',
    'Current number of active onboarding hashes'
)

VERIFIED_COUNT = Gauge(
    'sms_bridge_verified_count',
    'Current number of verified mobiles awaiting PIN'
)


# =============================================================================
# Metric Recording Functions
# =============================================================================

def record_onboarding(status: str = "success"):
    """Record onboarding request"""
    ONBOARDING_TOTAL.labels(status=status).inc()


def record_sms_received(status: str = "received"):
    """Record SMS received"""
    SMS_RECEIVED_TOTAL.labels(status=status).inc()


def record_pin_collected(status: str = "success"):
    """Record PIN collection"""
    PIN_COLLECTED_TOTAL.labels(status=status).inc()


def record_rate_limited():
    """Record rate-limited request"""
    RATE_LIMITED_TOTAL.inc()


def record_validation_failure(check: str):
    """Record validation check failure"""
    VALIDATION_FAILURES_TOTAL.labels(check=check).inc()


# =============================================================================
# Metrics Collection (for Gauge updates)
# =============================================================================

def collect_redis_metrics():
    """
    Collect current Redis state metrics.
    Called periodically or on /metrics scrape.
    """
    try:
        from core import redis_v2 as redis_client
        
        r = redis_client.get_redis()
        
        # Sync queue length
        sync_len = r.llen("sync_queue")
        SYNC_QUEUE_LENGTH.set(sync_len)
        
        # Audit buffer length
        audit_len = r.llen("audit_buffer")
        AUDIT_BUFFER_LENGTH.set(audit_len)
        
        # Blacklist size
        blacklist_size = r.scard("blacklist")
        BLACKLIST_SIZE.set(blacklist_size)
        
        # Count active_onboarding:* keys
        active_count = 0
        for _ in r.scan_iter("active_onboarding:*"):
            active_count += 1
        ACTIVE_ONBOARDING_COUNT.set(active_count)
        
        # Count verified:* keys
        verified_count = 0
        for _ in r.scan_iter("verified:*"):
            verified_count += 1
        VERIFIED_COUNT.set(verified_count)
        
    except Exception as e:
        logger.error(f"Error collecting Redis metrics: {e}")


def get_metrics_output() -> bytes:
    """
    Get Prometheus metrics output.
    Collects Redis metrics before generating output.
    """
    collect_redis_metrics()
    return generate_latest()


def get_content_type() -> str:
    """Get Prometheus content type"""
    return CONTENT_TYPE_LATEST
