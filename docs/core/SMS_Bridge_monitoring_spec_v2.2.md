# SMS Bridge Monitoring Specification v2.2

This document defines the monitoring strategy for SMS Bridge v2.2, including Prometheus metrics, Grafana dashboards, and alerting rules. This is separate from the core tech spec to maintain clear separation of concerns.

## 1. Overview

### Architecture
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   SMS Bridge    │────▶│   Prometheus    │────▶│    Grafana      │
│  /metrics       │     │  (scrape)       │     │  (visualize)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   PostgreSQL    │     │  AlertManager   │
│ (direct queries)│     │  (optional)     │
└─────────────────┘     └─────────────────┘
```

### Components
| Component | Purpose | Port |
|-----------|---------|------|
| SMS Bridge `/metrics` | Expose application metrics | 8080 |
| Prometheus | Scrape and store metrics | 9090 |
| Grafana | Visualize metrics and data | 3001 |
| postgres_exporter | PostgreSQL metrics | 9187 |
| redis_exporter | Redis metrics | 9121 |

## 2. Prometheus Metrics

### 2.1 Application Metrics (SMS Bridge)

Exposed at: `GET /metrics` (Prometheus text format)

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `sms_bridge_onboarding_total` | Counter | status | Total onboarding requests (success/failed) |
| `sms_bridge_sms_received_total` | Counter | status | Total SMS messages received (received/failed) |
| `sms_bridge_pin_collected_total` | Counter | status | Total PINs collected (success/failed) |
| `sms_bridge_rate_limited_total` | Counter | - | Total rate-limited requests |
| `sms_bridge_validation_failures_total` | Counter | check | Validation failures by check type (header_hash_check, foreign_number_check, count_check, blacklist_check) |
| `sms_bridge_sync_queue_length` | Gauge | - | Current items in sync_queue |
| `sms_bridge_audit_buffer_length` | Gauge | - | Current items in audit_buffer |
| `sms_bridge_blacklist_size` | Gauge | - | Current size of blacklist set |
| `sms_bridge_active_onboarding_count` | Gauge | - | Current number of active onboarding hashes |
| `sms_bridge_verified_count` | Gauge | - | Current number of verified mobiles awaiting PIN |

### 2.2 Infrastructure Metrics

**Redis Exporter** (redis_exporter:9121):
- `redis_connected_clients`
- `redis_memory_used_bytes`
- `redis_commands_processed_total`
- `redis_keyspace_hits_total` / `redis_keyspace_misses_total`

**Postgres Exporter** (postgres_exporter:9187):
- `pg_stat_database_numbackends` (active connections)
- `pg_stat_database_tup_fetched` (rows fetched)
- `pg_stat_database_tup_inserted` (rows inserted)
- `pg_database_size_bytes`

## 3. FastAPI Metrics Integration

### 3.1 Implementation Example

```python
# core/observability/metrics_v2.py
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Counters
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

# Gauges
SYNC_QUEUE_LENGTH = Gauge('sms_bridge_sync_queue_length', 'Current length of sync_queue')
AUDIT_BUFFER_LENGTH = Gauge('sms_bridge_audit_buffer_length', 'Current length of audit_buffer')
BLACKLIST_SIZE = Gauge('sms_bridge_blacklist_size', 'Current size of blacklist set')
ACTIVE_ONBOARDING_COUNT = Gauge('sms_bridge_active_onboarding_count', 'Current number of active onboarding hashes')
VERIFIED_COUNT = Gauge('sms_bridge_verified_count', 'Current number of verified mobiles awaiting PIN')

def metrics_endpoint():
    """Endpoint handler for /metrics"""
    # Collect current Redis state before returning metrics
    collect_redis_metrics()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

def collect_redis_metrics():
    """Update gauge metrics from Redis state"""
    try:
        from core import redis_v2 as redis_client
        r = redis_client.get_redis()
        
        SYNC_QUEUE_LENGTH.set(r.llen("sync_queue"))
        AUDIT_BUFFER_LENGTH.set(r.llen("audit_buffer"))
        BLACKLIST_SIZE.set(r.scard("blacklist"))
        
        # Count active patterns
        ACTIVE_ONBOARDING_COUNT.set(sum(1 for _ in r.scan_iter("active_onboarding:*")))
        VERIFIED_COUNT.set(sum(1 for _ in r.scan_iter("verified:*")))
    except Exception as e:
        logger.error(f"Failed to collect Redis metrics: {e}")
```

### 3.2 Recording Metrics in Endpoints

```python
# Example usage in core/sms_server_v2.py
from core.observability.metrics_v2 import (
    record_onboarding,
    record_sms_received,
    record_pin_collected,
    record_rate_limited,
    record_validation_failure
)

@app.post("/onboarding/register")
async def register(request: OnboardingRequest):
    try:
        # ... business logic ...
        record_onboarding(status="success")
        return response
    except HTTPException as e:
        if e.status_code == 429:
            record_rate_limited()
        record_onboarding(status="failed")
        raise

@app.post("/sms/receive")
async def receive_sms(request: SmsReceiveRequest):
    try:
        # ... validation checks ...
        if check_failed:
            record_validation_failure(check="header_hash_check")
        
        record_sms_received(status="received")
        return response
    except Exception:
        record_sms_received(status="failed")
        raise
```

## 4. Grafana Dashboards

### 4.1 SMS Bridge Overview Dashboard

**Panel 1: Onboarding Request Rate**
```promql
rate(sms_bridge_onboarding_total[5m])
```
- Group by: status
- Visualization: Time series

**Panel 2: SMS Processing Rate**
```promql
rate(sms_bridge_sms_received_total[5m])
```
- Group by: status
- Visualization: Time series

**Panel 3: PIN Collection Rate**
```promql
rate(sms_bridge_pin_collected_total[5m])
```
- Group by: status
- Visualization: Time series

**Panel 4: Validation Failure Rate**
```promql
rate(sms_bridge_validation_failures_total[5m])
```
- Group by: check
- Visualization: Time series (stacked)

**Panel 5: Queue Depths**
```promql
sms_bridge_sync_queue_length
sms_bridge_audit_buffer_length
```
- Visualization: Time series (stacked)

**Panel 6: Active Sessions**
```promql
sms_bridge_active_onboarding_count
sms_bridge_verified_count
```
- Visualization: Time series

**Panel 7: Blacklist Size**
```promql
sms_bridge_blacklist_size
```
- Visualization: Stat

**Panel 8: Rate Limiting**
```promql
rate(sms_bridge_rate_limited_total[5m])
```
- Visualization: Time series

### 4.2 Data Tables Dashboard (PostgreSQL Direct)

**Important**: Table names must match `schema.sql`. Update queries if schema changes.

**Panel 1: Recent Logs**
```sql
-- Table: sms_bridge_logs (from schema.sql)
SELECT id, event, details::text, created_at
FROM sms_bridge_logs
ORDER BY created_at DESC
LIMIT 50
```

**Panel 2: Backup Users**
```sql
-- Table: backup_users (from schema.sql)
SELECT id, mobile, hash, created_at,
       CASE WHEN synced_at IS NULL THEN 'pending' ELSE 'synced' END as sync_status
FROM backup_users
ORDER BY created_at DESC
LIMIT 50
```

**Panel 3: Settings History**
```sql
-- Table: settings_history (from schema.sql)
SELECT version_id, is_active, created_at, created_by, change_note
FROM settings_history
ORDER BY created_at DESC
LIMIT 20
```

**Panel 4: Blacklist**
```sql
-- Table: blacklist_mobiles (from schema.sql)
SELECT id, mobile, reason, created_at, created_by
FROM blacklist_mobiles
ORDER BY created_at DESC
LIMIT 50
```

## 5. Alert Rules

### 5.1 Prometheus Alert Rules

```yaml
# prometheus/alerts.yml
groups:
  - name: sms_bridge_alerts
    rules:
      # Critical: Queue Backlog
      - alert: SMSBridgeSyncQueueBacklog
        expr: sms_bridge_sync_queue_length > 100
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Sync queue backlog detected"
          description: "Sync queue has {{ $value }} items (threshold: 100)"

      - alert: SMSBridgeAuditBufferBacklog
        expr: sms_bridge_audit_buffer_length > 500
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Audit buffer backlog detected"
          description: "Audit buffer has {{ $value }} items (threshold: 500)"

      # Warning: High Failure Rates
      - alert: SMSBridgeHighValidationFailures
        expr: rate(sms_bridge_validation_failures_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High validation failure rate"
          description: "Validation failures: {{ $value }} per second"

      - alert: SMSBridgeHighRateLimiting
        expr: rate(sms_bridge_rate_limited_total[5m]) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High rate limiting activity"
          description: "Rate limited requests: {{ $value }} per second"

      - alert: SMSBridgeOnboardingFailures
        expr: rate(sms_bridge_onboarding_total{status="failed"}[5m]) / rate(sms_bridge_onboarding_total[5m]) > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High onboarding failure rate"
          description: "Onboarding failure rate: {{ $value | humanizePercentage }} (threshold: 20%)"

      # Info: Blacklist Growth
      - alert: SMSBridgeBlacklistGrowth
        expr: delta(sms_bridge_blacklist_size[1h]) > 50
        for: 1h
        labels:
          severity: info
        annotations:
          summary: "Unusual blacklist growth"
          description: "Blacklist grew by {{ $value }} entries in 1 hour"
```

## 6. Schema Reference

### 6.1 Database Alignment

**Important**: Grafana dashboard SQL queries must align with table definitions in `schema.sql`.

When updating `schema.sql`:
1. Update table names/columns in schema
2. Update corresponding Grafana dashboard queries
3. Redeploy monitoring stack

### 6.2 Dashboard Configuration

The Grafana SMS dashboard should use table names from `schema.sql`:

```yaml
# Tables from schema.sql v2.2:
# - settings_history (version_id, payload, is_active, created_at, created_by, change_note)
# - admin_users (id, username, password_hash, is_super_admin, created_at)
# - sms_bridge_logs (id, event, details, created_at)
# - backup_users (id, mobile, pin, hash, created_at, synced_at)
# - power_down_store (id, key_name, key_type, value, original_ttl, created_at)
# - blacklist_mobiles (id, mobile, reason, created_at, created_by)
```

### 6.3 Prometheus Scrape Config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'sms-bridge'
    static_configs:
      - targets: ['sms-receiver:8080']
    metrics_path: '/metrics'
    scrape_interval: 15s

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['redis-exporter:9121']
```

## 7. Deployment Checklist

- [ ] `/metrics` endpoint implemented in SMS Bridge
- [ ] Prometheus configured to scrape SMS Bridge
- [ ] postgres_exporter deployed and configured
- [ ] redis_exporter deployed and configured
- [ ] Grafana dashboards imported
- [ ] Alert rules configured in Prometheus
- [ ] Dashboard SQL queries match `schema.sql` tables

## 8. Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.2 | 2025-01-01 | Initial monitoring spec aligned with Tech Spec v2.2 |
