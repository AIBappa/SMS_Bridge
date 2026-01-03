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
| `sms_bridge_requests_total` | Counter | endpoint, method, status_code | Total HTTP requests |
| `sms_bridge_request_duration_seconds` | Histogram | endpoint | Request latency (buckets: 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10) |
| `sms_bridge_validation_checks_total` | Counter | check_name, status | Validation results (pass/fail/disabled) |
| `sms_bridge_sync_queue_length` | Gauge | - | Current items in sync_queue |
| `sms_bridge_retry_queue_length` | Gauge | - | Current items in retry_queue |
| `sms_bridge_audit_buffer_length` | Gauge | - | Current items in audit_buffer |
| `sms_bridge_redis_connected` | Gauge | - | Redis connection status (1=up, 0=down) |
| `sms_bridge_postgres_connected` | Gauge | - | Postgres connection status (1=up, 0=down) |

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
# core/observability/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Counters
REQUEST_COUNT = Counter(
    'sms_bridge_requests_total',
    'Total HTTP requests',
    ['endpoint', 'method', 'status_code']
)

VALIDATION_COUNT = Counter(
    'sms_bridge_validation_checks_total',
    'Validation check results',
    ['check_name', 'status']
)

# Histograms
REQUEST_LATENCY = Histogram(
    'sms_bridge_request_duration_seconds',
    'Request latency',
    ['endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
)

# Gauges
SYNC_QUEUE_LENGTH = Gauge('sms_bridge_sync_queue_length', 'Sync queue length')
RETRY_QUEUE_LENGTH = Gauge('sms_bridge_retry_queue_length', 'Retry queue length')
AUDIT_BUFFER_LENGTH = Gauge('sms_bridge_audit_buffer_length', 'Audit buffer length')
REDIS_CONNECTED = Gauge('sms_bridge_redis_connected', 'Redis connection status')
POSTGRES_CONNECTED = Gauge('sms_bridge_postgres_connected', 'Postgres connection status')

def metrics_endpoint():
    """Endpoint handler for /metrics"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

### 3.2 Middleware for Request Metrics

```python
# core/observability/middleware.py
import time
from starlette.middleware.base import BaseHTTPMiddleware
from .metrics import REQUEST_COUNT, REQUEST_LATENCY

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        
        endpoint = request.url.path
        REQUEST_COUNT.labels(
            endpoint=endpoint,
            method=request.method,
            status_code=response.status_code
        ).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
        
        return response
```

## 4. Grafana Dashboards

### 4.1 SMS Bridge Overview Dashboard

**Panel 1: Request Rate**
```promql
rate(sms_bridge_requests_total[5m])
```
- Group by: endpoint, status_code
- Visualization: Time series

**Panel 2: Request Latency (P95)**
```promql
histogram_quantile(0.95, rate(sms_bridge_request_duration_seconds_bucket[5m]))
```
- Group by: endpoint
- Visualization: Time series

**Panel 3: Validation Success Rate**
```promql
sum(rate(sms_bridge_validation_checks_total{status="pass"}[5m])) 
/ 
sum(rate(sms_bridge_validation_checks_total{status!="disabled"}[5m])) * 100
```
- Visualization: Gauge (0-100%)

**Panel 4: Queue Depths**
```promql
sms_bridge_sync_queue_length
sms_bridge_retry_queue_length
sms_bridge_audit_buffer_length
```
- Visualization: Time series (stacked)

**Panel 5: Service Health**
```promql
sms_bridge_redis_connected
sms_bridge_postgres_connected
```
- Visualization: Stat (1=green, 0=red)

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
      # Critical: Service Down
      - alert: SMSBridgeRedisDown
        expr: sms_bridge_redis_connected == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Redis connection lost"
          description: "SMS Bridge cannot connect to Redis for {{ $labels.instance }}"

      - alert: SMSBridgePostgresDown
        expr: sms_bridge_postgres_connected == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL connection lost"
          description: "SMS Bridge cannot connect to PostgreSQL for {{ $labels.instance }}"

      # Warning: Performance Issues
      - alert: SMSBridgeHighLatency
        expr: histogram_quantile(0.95, rate(sms_bridge_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High request latency"
          description: "P95 latency is {{ $value }}s (threshold: 2s)"

      - alert: SMSBridgeHighErrorRate
        expr: rate(sms_bridge_requests_total{status_code=~"5.."}[5m]) / rate(sms_bridge_requests_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate"
          description: "Error rate is {{ $value | humanizePercentage }} (threshold: 10%)"

      # Warning: Queue Backlog
      - alert: SMSBridgeSyncQueueBacklog
        expr: sms_bridge_sync_queue_length > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Sync queue backlog"
          description: "Sync queue has {{ $value }} items (threshold: 100)"

      - alert: SMSBridgeRetryQueueGrowing
        expr: sms_bridge_retry_queue_length > 10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Retry queue growing"
          description: "Retry queue has {{ $value }} items (threshold: 10)"
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
