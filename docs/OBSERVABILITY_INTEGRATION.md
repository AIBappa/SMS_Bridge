# Observability Integration Summary

## Overview
The SMS Bridge application now includes comprehensive Prometheus metrics for monitoring application health and performance.

## Components Added

### 1. Observability Package (`observability/`)

#### `observability/__init__.py`
- Package initialization file
- Exports all metrics and helper functions for easy import
- Makes metrics available via `from observability import SMS_ONBOARD_REQUESTS`

#### `observability/metrics.py`
- **Gauges** (snapshot metrics):
  - `sms_bridge_monitor_queue_length` - Length of sms_monitor_queue in Redis
  - `sms_bridge_out_sms_numbers_count` - Count of validated numbers
  - `sms_bridge_blacklist_mobiles_count` - Count of blacklisted mobiles
  - `sms_bridge_abuse_counters_keys` - Number of active abuse counter keys

- **Counters** (cumulative metrics):
  - `sms_bridge_monitor_events_processed_total` - Total monitor events logged to DB
  - `sms_bridge_onboard_requests_total` - Total onboarding requests

- **Helper function**:
  - `collect_once()` - Async function that updates all gauges from Redis

#### `observability/asgi_metrics.py`
- ASGI application wrapper for Prometheus `/metrics` endpoint
- Calls `collect_once()` before each scrape to refresh gauge values
- Integrates with FastAPI via `app.mount('/metrics', metrics_asgi_app)`

### 2. Application Integration

#### `sms_server.py` Changes
```python
# Line ~116: Mount metrics endpoint
try:
    from observability.asgi_metrics import app as metrics_asgi_app
    app.mount('/metrics', metrics_asgi_app)
except Exception:
    logging.getLogger(__name__).debug('Observability ASGI app not available; /metrics not mounted')

# Line ~682-683: Increment onboard counter
try:
    from observability.metrics import SMS_ONBOARD_REQUESTS
    SMS_ONBOARD_REQUESTS.inc()
except Exception:
    pass
```

#### `background_workers.py` Changes
```python
# Line ~14-16: Import with fallback
try:
    from observability.metrics import SMS_MONITOR_EVENTS_PROCESSED
except Exception:
    SMS_MONITOR_EVENTS_PROCESSED = None

# Line ~198-199: Conditional increment
if SMS_MONITOR_EVENTS_PROCESSED:
    SMS_MONITOR_EVENTS_PROCESSED.inc(len(events))
```

### 3. Deployment Updates

#### Ansible Playbook (`ansible-k3s/setup_sms_bridge_k3s.yml`)
- Added task to copy `observability/` package to build context
- Updated Dockerfile to include `COPY observability/ /app/observability/`

#### `requirements.txt`
- Added `prometheus-client==0.17.1`

### 4. Grafana Dashboard
- Created `grafana/dashboards/sms_bridge_app_metrics.json`
- Panels for:
  - Monitor queue length (real-time queue depth)
  - Out SMS numbers count (validated numbers)
  - Blacklist count (blocked numbers)
  - Abuse counter keys (active monitoring)

## Metrics Endpoint

Once deployed, metrics are available at:
- **Internal**: `http://sms-receiver:8080/metrics`
- **External (NodePort)**: `http://localhost:30080/metrics`

## Prometheus Scrape Configuration

To scrape the SMS receiver metrics, add this job to Prometheus config:

```yaml
scrape_configs:
  - job_name: 'sms-receiver'
    static_configs:
      - targets: ['sms-receiver:8080']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

## Testing

### Local Test
```bash
# Test metrics collector (requires pytest and redis running)
pytest tests/test_metrics_collector.py
```

### Container Test
```bash
# Check metrics endpoint
curl http://localhost:30080/metrics

# Expected output includes:
# sms_bridge_monitor_queue_length 0
# sms_bridge_out_sms_numbers_count 1
# sms_bridge_blacklist_mobiles_count 0
# sms_bridge_abuse_counters_keys 0
# sms_bridge_monitor_events_processed_total 0
# sms_bridge_onboard_requests_total 0
```

## Error Handling

All observability code uses try/except blocks to ensure:
1. Missing `prometheus_client` dependency doesn't break the app
2. Missing `observability` package doesn't prevent startup
3. Metrics collection failures don't impact SMS processing

This defensive approach allows the app to run with or without observability enabled.

## Next Steps

1. ✅ Package created and integrated
2. ✅ Ansible deployment updated
3. ✅ Requirements updated
4. ⏳ Container rebuild needed (run setup playbook)
5. ⏳ Prometheus scrape config update (optional)
6. ⏳ Grafana dashboard import (optional)

## Troubleshooting

### `/metrics` returns 404
- Check container has `/app/observability/` directory
- Verify `prometheus-client` is installed in container
- Check logs for import errors at startup

### Metrics show zero values
- Verify Redis is accessible from the container
- Check Redis has data (monitor queue, out_sms_numbers set, etc.)
- Review collect_once() logs for Redis errors

### Counter not incrementing
- Verify the code path is being executed
- Check import succeeded (look for Exception in logs)
- Ensure Prometheus is scraping frequently enough
