"""Observability helpers for SMS Bridge.

This package exposes Prometheus metrics and an ASGI /metrics app.
"""

# Import and re-export key metrics for convenience
from .metrics import (
    SMS_MONITOR_QUEUE_LEN,
    OUT_SMS_NUMBERS_COUNT,
    BLACKLIST_MOBILES_COUNT,
    ABUSE_COUNTER_KEYS,
    SMS_MONITOR_EVENTS_PROCESSED,
    SMS_ONBOARD_REQUESTS,
    collect_once
)

__all__ = [
    "metrics",
    "asgi_metrics",
    "SMS_MONITOR_QUEUE_LEN",
    "OUT_SMS_NUMBERS_COUNT",
    "BLACKLIST_MOBILES_COUNT",
    "ABUSE_COUNTER_KEYS",
    "SMS_MONITOR_EVENTS_PROCESSED",
    "SMS_ONBOARD_REQUESTS",
    "collect_once",
]
