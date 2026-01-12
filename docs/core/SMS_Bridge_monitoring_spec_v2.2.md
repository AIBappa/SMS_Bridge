# SMS Bridge Monitoring Specification v2.3

This document defines the monitoring strategy for SMS Bridge v2.3, including minimal logging, on-demand port management, and remote monitoring architecture. This is separate from the core tech spec to maintain clear separation of concerns.

## 1. Overview

### Design Philosophy

**Lightweight & On-Demand**: Instead of running a full monitoring stack 24/7 on the server, SMS Bridge uses a minimal approach:
- **Server (Surface Pro)**: Only exposes metrics endpoint, no monitoring containers
- **Client (Laptop)**: Runs monitoring stack (Prometheus/Grafana) only when needed
- **Security**: Monitoring ports opened via authenticated Admin UI, auto-close after timeout
- **Efficiency**: Saves ~500MB RAM and ~2GB disk on server

### Architecture
```
┌────────────────────────────────────────────────────────────────┐
│                    Surface Pro (Production Server)              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  SMS Bridge (Port 8080 - ONLY exposed port)              │  │
│  │    ├─ /metrics endpoint (Prometheus format)              │  │
│  │    ├─ /health endpoint                                   │  │
│  │    ├─ /admin UI (authenticated)                          │  │
│  │    │    ├─ Port Management (open/close monitoring ports) │  │
│  │    │    ├─ Log Viewer/Download                           │  │
│  │    │    └─ Audit Trail                                   │  │
│  │    └─ Persistent Logs (minimal, 7-day rotation)          │  │
│  │                                                           │  │
│  │  Internal Services (no exposed ports):                   │  │
│  │    ├─ postgres (5432 internal only)                      │  │
│  │    ├─ pgbouncer (6432 internal only)                     │  │
│  │    └─ redis (6379 internal only)                         │  │
│  │                                                           │  │
│  │  Temporary Monitoring Ports (opened via Admin UI):       │  │
│  │    ├─ 9100 → /metrics endpoint (for Prometheus)          │  │
│  │    ├─ 5433 → postgres (for DBeaver)                      │  │
│  │    └─ 6380 → redis (for Redis Desktop Manager)           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           │                                     │
│                    Cloudflare Tunnel                            │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                    HTTPS over Internet
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│                    Laptop (Monitoring Client)                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Monitoring Stack (on-demand, when user needs it)        │  │
│  │    ├─ Prometheus (scrapes Surface Pro:9100)              │  │
│  │    │    └─ Stores 7 days of metrics history              │  │
│  │    ├─ Grafana (visualizes data)                          │  │
│  │    │    └─ Pre-configured dashboards                     │  │
│  │    ├─ DBeaver (connects to Surface Pro:5433)             │  │
│  │    └─ Redis Desktop Manager (connects to Surface Pro:6380)│ │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Components
| Component | Location | Purpose | Port |
|-----------|----------|---------|------|
| SMS Bridge `/metrics` | Server | Expose application metrics | 8080 (always) |
| Admin UI Port Manager | Server | Open/close monitoring ports | 8080/admin |
| Prometheus | Laptop | Scrape and store metrics (on-demand) | 9090 |
| Grafana | Laptop | Visualize metrics and data (on-demand) | 3000 |
| Monitoring Ports | Server | Temporary access for external tools | 9100, 5433, 6380 (when opened) |

## 2. Logging Strategy

### 2.1 Minimal Logging Configuration

**Philosophy**: Log only what matters - warnings and errors. Keep logs for 7 days.

**Storage**: ~100MB total for all logs
- Application logs: 10MB × 7 files = 70MB max
- PostgreSQL logs: 10MB × 1 day = 10MB max  
- Redis logs: ~5MB max
- Port access audit trail: ~5MB

### 2.2 Log Levels by Service

| Service | Log Level | What Gets Logged |
|---------|-----------|------------------|
| SMS Bridge | WARNING | Errors, security events, port access |
| PostgreSQL | WARNING | Errors, slow queries (>1s) |
| Redis | WARNING | Errors, warnings |

### 2.3 Log Rotation

```yaml
# Application logs (Python RotatingFileHandler)
max_bytes: 10MB per file
backup_count: 7  # Keep 7 daily rotations
location: ./logs/application/sms_bridge.log

# PostgreSQL logs
rotation_age: 1d
rotation_size: 10MB
location: ./logs/postgres/postgresql-YYYY-MM-DD.log

# Redis logs
location: ./logs/redis/redis.log
loglevel: warning
```

### 2.4 Persistent Log Storage

All logs are stored in host-mounted volumes to survive container restarts:

```yaml
volumes:
  # Application logs
  - ./logs/application:/app/logs:rw
  
  # PostgreSQL logs
  - ./logs/postgres:/var/log/postgresql:rw
  
  # Redis logs
  - ./logs/redis:/var/log/redis:rw
```

### 2.5 What Gets Logged

**Security Events (Always Logged):**
- Admin UI login attempts (success/failure)
- Monitoring port opened (who, what, when, duration)
- Monitoring port closed (who, when)
- Settings changes
- Blacklist modifications

**Application Events (WARNING+ only):**
- HTTP 4xx/5xx errors
- Database connection failures
- Redis connection failures
- Rate limiting triggered
- Validation failures
- Unexpected exceptions

**NOT Logged:**
- Successful requests (use metrics instead)
- Debug information
- Verbose connection info
- Routine operations

### 2.6 Log Access via Admin UI

Administrators can:
1. View recent logs in browser
2. Download log files for offline analysis
3. Filter logs by service (application, postgres, redis)
4. Access audit trail for port opening/closing

## 3. On-Demand Port Management

### 3.1 Port Management via Admin UI

Instead of permanently exposing monitoring ports, administrators can temporarily open them when needed.

**Available Services:**
| Service | Internal Port | External Port | Use Case |
|---------|---------------|---------------|----------|
| metrics | 8080 | 9100 | Prometheus scraping |
| postgres | 5432 | 5433 | DBeaver, pgAdmin, psql |
| pgbouncer | 6432 | 6434 | Direct connection pooler access |
| redis | 6379 | 6380 | Redis Desktop Manager, redis-cli |

### 3.2 Port Opening Workflow

```
1. Admin logs into https://your-domain.com/admin
2. Navigate to "Monitoring Services" page
3. Select service (e.g., "postgres")
4. Choose duration (15-240 minutes)
5. Click "Open Port"
6. System returns connection string and credentials
7. Port auto-closes after duration expires
```

### 3.3 Security Features

**Access Control:**
- Must be authenticated admin to open ports
- Session must be valid
- Actions logged to audit trail

**Auto-Close:**
- Ports automatically close after specified duration
- Maximum duration: 4 hours (240 minutes)
- Default duration: 1 hour (60 minutes)

**Audit Trail:**
- Who opened the port
- When it was opened
- How long it was open
- When it was closed (manual or auto)
- Connection details (IP, port)

**Port State Persistence:**
- Port mappings stored in `/app/logs/port_mappings.json`
- Survives container restarts
- Admin can manually close ports anytime

### 3.4 Configurable Monitoring Ports

**Philosophy**: Allow administrators to customize monitoring port mappings to avoid conflicts with existing services or security policies.

#### 3.4.1 Default Port Configuration

Monitoring ports are stored in `sms_settings.json` under the `monitoring_ports` key:

```json
{
  "version": "2.3.0",
  "settings": {
    "rate_limits": { /* ... */ },
    "validation_checks": { /* ... */ },
    "monitoring_ports": {
      "metrics": {
        "external_port": 9100,
        "internal_port": 8080,
        "description": "Prometheus metrics endpoint",
        "enabled": true
      },
      "postgres": {
        "external_port": 5433,
        "internal_port": 5432,
        "description": "PostgreSQL database access",
        "enabled": true
      },
      "pgbouncer": {
        "external_port": 6434,
        "internal_port": 6432,
        "description": "PgBouncer connection pooler",
        "enabled": false
      },
      "redis": {
        "external_port": 6380,
        "internal_port": 6379,
        "description": "Redis cache access",
        "enabled": true
      }
    }
  }
}
```

#### 3.4.2 Port Configuration UI

**Admin UI Location**: `/admin/monitoring/port-config`

**Features:**
- View current port assignments
- Modify external port numbers
- Enable/disable specific monitoring services
- Validate port availability before saving
- Preview connection strings with new ports
- Reset to defaults

**UI Elements:**
| Field | Type | Validation | Default |
|-------|------|------------|---------|
| External Port | Number (1024-65535) | Unique, not in use | Service-specific |
| Internal Port | Number (read-only) | - | Service-specific |
| Enabled | Checkbox | - | true |
| Description | Text (read-only) | - | Service-specific |

**Validation Rules:**
1. External ports must be in range 1024-65535 (non-privileged)
2. External ports must be unique across all services
3. External ports must not conflict with existing open ports
4. Changes require Admin UI authentication
5. Port changes logged to audit trail

#### 3.4.3 Port Configuration Workflow

**Initial Setup (First Deployment):**
```
1. SMS Bridge starts with default ports from sms_settings.json
2. Admin reviews defaults: /admin/monitoring/port-config
3. If conflicts detected, admin modifies ports
4. Admin saves configuration
5. System validates and updates sms_settings.json
6. No restart required - changes take effect immediately
```

**Changing Ports (Operational):**
```
1. Admin navigates to /admin/monitoring/port-config
2. System checks if any ports currently open
   - If ports open: Show warning "Close open ports before changing config"
   - If ports closed: Allow editing
3. Admin modifies port numbers
4. System validates:
   - Port range check
   - Uniqueness check
   - Availability check (scan if port in use)
5. Admin saves
6. System updates sms_settings.json
7. New ports used on next port opening
```

#### 3.4.4 Security & Best Practices

**Port Selection Guidelines:**
- **Metrics (9xxx)**: Use 9000-9999 range (Prometheus convention)
- **Databases (5xxx/6xxx)**: Use non-standard ports to avoid scanners
- **Avoid**: 22 (SSH), 80 (HTTP), 443 (HTTPS), 3306 (MySQL), 5432 (default PostgreSQL)
- **Consider**: Firewall rules, existing services, security policy

**Security Recommendations:**
1. Change default ports after initial deployment
2. Use non-obvious port numbers
3. Document port changes in secure location
4. Rotate ports periodically (every 6 months)
5. Monitor audit trail for unauthorized port access

#### 3.4.5 Integration with Port Opening

When opening a port, the system uses the current configuration from `sms_settings.json`:

```python
# Pseudocode - port opening logic
def open_monitoring_port(service: str):
    # Load current configuration from sms_settings.json
    config = load_monitoring_config()
    
    if service not in config["monitoring_ports"]:
        raise ValueError(f"Unknown service: {service}")
    
    service_config = config["monitoring_ports"][service]
    
    if not service_config["enabled"]:
        raise ValueError(f"Service '{service}' is disabled")
    
    external_port = service_config["external_port"]
    internal_port = service_config["internal_port"]
    
    # Validate port still available
    if not validate_port_available(external_port):
        raise ValueError(f"Port {external_port} is no longer available")
    
    # Create iptables rule using configured ports
    create_iptables_rule(external_port, internal_port)
    
    return {
        "service": service,
        "external_port": external_port,
        "connection_string": generate_connection_string(service, external_port)
    }
```

### 3.5 Admin UI Endpoints

```
GET  /admin/monitoring/services            - List available services and status
POST /admin/monitoring/open-port           - Open a monitoring port
POST /admin/monitoring/close-port          - Close a monitoring port
GET  /admin/monitoring/port-status         - Get current port status
POST /admin/monitoring/open-all            - Open all monitoring ports
POST /admin/monitoring/close-all           - Close all monitoring ports
GET  /admin/monitoring/port-config         - Get current port configuration
POST /admin/monitoring/port-config         - Update port configuration
POST /admin/monitoring/port-config/reset   - Reset to defaults
GET  /admin/monitoring/export-prometheus-config - Download Prometheus config with current ports
GET  /admin/logs/download                  - Download log files
```

## 4. Prometheus Metrics

### 4.1 Application Metrics (SMS Bridge)

Exposed at: `GET /metrics` (Prometheus text format, always available)

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

| `sms_bridge_verified_count` | Gauge | - | Current number of verified mobiles awaiting PIN |

### 4.2 Server Deployment (No Exporters)

**Note**: Unlike v2.2, postgres_exporter and redis_exporter are NOT deployed on the server to save resources.

If PostgreSQL/Redis metrics are needed:
1. Deploy exporters on laptop alongside Prometheus/Grafana
2. Open postgres/redis ports via Admin UI
3. Configure exporters to scrape remote ports
4. Close ports when done monitoring

**Alternative**: Query PostgreSQL directly from Grafana using PostgreSQL datasource (more efficient).

## 5. Remote Monitoring Stack (Laptop)

### 5.1 Laptop Deployment

Run monitoring stack on your laptop only when you need to check metrics.

**Docker Compose for Laptop:**
```yaml
# docker-compose-monitoring.yml (run on laptop)
version: "3.8"

services:
  prometheus:
    image: prom/prometheus:v2.48.1
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus-remote.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--storage.tsdb.retention.time=7d'

  grafana:
    image: grafana/grafana:10.2.3
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana-datasources.yml:/etc/grafana/provisioning/datasources/datasource.yml:ro
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
```

**Prometheus Config (prometheus-remote.yml):**
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'sms_receiver'
    static_configs:
      - targets: ['SURFACE_PRO_IP:9100']  # Use port from Admin UI config
```

**Note**: Port numbers may be different if customized in Admin UI. Download current config:
```bash
# Download Prometheus config with correct ports
curl -o prometheus-remote.yml \
  https://your-domain.com/admin/monitoring/export-prometheus-config
```

**Grafana Datasource (grafana-datasources.yml):**
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
  
  # Optional: Direct PostgreSQL connection
  - name: SMS Bridge DB
    type: postgres
    url: SURFACE_PRO_IP:5433
    database: sms_bridge
    user: postgres
    secureJsonData:
      password: YOUR_PASSWORD
```

### 5.2 Monitoring Workflow

**Step 0: (Optional) Configure Ports**
```
If default ports conflict with existing services:
1. Navigate to https://your-domain.com/admin/monitoring/port-config
2. Modify port assignments as needed
3. Save configuration
4. Download updated Prometheus config
```

**Step 1: Open Ports on Server**
```
1. Navigate to https://your-domain.com/admin/monitoring/services
2. Click "Open All Monitoring Ports" (or select individually)
3. Choose duration: 60 minutes
4. System displays connection info for each service
```

**Step 2: Start Monitoring on Laptop**
```bash
cd ~/sms-bridge-monitoring

# Update config with server IP
export SURFACE_IP="your.server.ip"
sed -i "s/SURFACE_PRO_IP/$SURFACE_IP/g" prometheus-remote.yml

# Start monitoring stack
docker-compose -f docker-compose-monitoring.yml up -d

# Access dashboards
open http://localhost:3000  # Grafana (admin/admin)
open http://localhost:9090  # Prometheus
```

**Step 3: Connect External Tools (Optional)**
```bash
# DBeaver
Host: your.server.ip
Port: 5433
Database: sms_bridge
User: postgres
Password: [from env]

# Redis Desktop Manager
Host: your.server.ip
Port: 6380
Auth: [REDIS_PASSWORD from env]
```

**Step 4: Done Monitoring**
```bash
# Stop monitoring stack on laptop
docker-compose -f docker-compose-monitoring.yml down

# Close ports on server (or wait for auto-close)
# Admin UI → "Close All Monitoring Ports"
```

### 5.3 Helper Scripts

**start-monitoring.sh** (run on laptop):
```bash
#!/bin/bash
SURFACE_IP="${1:-your.server.ip}"

echo "🚀 Starting monitoring stack..."
sed -i "s/SURFACE_PRO_IP/$SURFACE_IP/g" prometheus-remote.yml

docker-compose -f docker-compose-monitoring.yml up -d

echo "✅ Monitoring started!"
echo "📊 Grafana: http://localhost:3000 (admin/admin)"
echo "🔍 Prometheus: http://localhost:9090"
echo ""
echo "⚠️  Don't forget to open monitoring ports via Admin UI"
```

**stop-monitoring.sh** (run on laptop):
```bash
#!/bin/bash
docker-compose -f docker-compose-monitoring.yml down
echo "✅ Monitoring stopped!"
echo "💡 Remember to close ports on server via Admin UI"
```

## 6. Grafana Dashboards

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

## 6. Grafana Dashboards

### 6.1 SMS Bridge Overview Dashboard

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

### 6.2 Data Tables Dashboard (PostgreSQL Direct)

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

**Note**: When using PostgreSQL direct queries:
1. Configure Grafana with PostgreSQL datasource pointing to Surface Pro:5433
2. Open postgres port via Admin UI before querying
3. Queries execute directly against live database (no additional exporters needed)

## 7. FastAPI Metrics Integration

### 7.1 Implementation Example

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

### 7.2 Recording Metrics in Endpoints

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

## 8. Alert Rules (Optional)

### 8.1 Prometheus Alert Rules (Laptop Deployment)

**Note**: Since Prometheus runs on laptop (not 24/7), alerts are only active when monitoring stack is running. Consider these informational rather than critical alerting.

```yaml
# prometheus/alerts.yml (on laptop)
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

### 8.2 Alternative: Log-Based Alerting

Since monitoring is on-demand, consider log-based alerting for 24/7 monitoring:

**Option 1: Log aggregation service**
- Send WARNING+ logs to external service (e.g., Sentry, Papertrail)
- Configure alerts on error patterns
- Cost-effective for small deployments

**Option 2: Simple email alerts**
```python
# In application code
if critical_error:
    logger.error(f"CRITICAL: {error_message}")
    send_email_alert(admin_email, error_message)
```

**Option 3: Cloudflare monitoring**
- Use Cloudflare's uptime monitoring for `/health` endpoint
- Get notified if server goes down
- Free with Cloudflare tunnel

## 9. Security Considerations

### 9.1 Port Exposure Security

**Threat Model:**
- External attacker scanning open ports
- Brute force attacks on temporarily exposed ports
- Unauthorized access to monitoring data

**Mitigations:**
1. **Authentication Required**: Must login to Admin UI to open ports
2. **Time-Limited**: Ports auto-close after max 4 hours
3. **Audit Trail**: All port access logged with user, timestamp
4. **Strong Passwords**: Enforce strong passwords for database/redis
5. **Firewall Rules**: Use iptables to restrict port access
6. **Rate Limiting**: Admin UI protected by rate limiting

### 9.2 Cloudflare Tunnel Benefits

- Main application (port 8080) behind Cloudflare
- DDoS protection
- HTTPS/TLS termination
- No direct server IP exposure
- Monitoring ports NOT routed through CF (direct access only)

### 9.3 Admin UI Security

- Session-based authentication
- HTTP-only cookies
- CSRF protection
- Password hashing (bcrypt)
- Login attempt logging
- Auto-logout after inactivity

### 9.4 Log Security

- Passwords/secrets NOT logged
- Connection strings sanitized in UI display
- Logs readable only by admin users
- Log rotation prevents disk filling

## 10. Resource Comparison

### 10.1 v2.2 (Full Stack on Server)

```
Server Resources:
- sms_receiver: ~100MB RAM
- postgres + pgbouncer: ~200MB RAM
- redis: ~50MB RAM
- prometheus: ~400MB RAM, ~1.5GB disk
- grafana: ~100MB RAM, ~500MB disk
- exporters: ~50MB RAM
Total: ~900MB RAM, ~2GB disk

Containers: 8
Exposed Ports: 3 (8080, 9090, 3001)
```

### 10.2 v2.3 (Minimal Server + Laptop Monitoring)

```
Server Resources:
- sms_receiver: ~100MB RAM
- postgres + pgbouncer: ~200MB RAM
- redis: ~50MB RAM
- logs: ~100MB disk
Total: ~350MB RAM, ~100MB disk

Laptop Resources (when running):
- prometheus: ~400MB RAM, ~1.5GB disk
- grafana: ~100MB RAM, ~500MB disk
Total: ~500MB RAM, ~2GB disk

Server Containers: 4
Server Exposed Ports: 1 (8080 only)
Monitoring Ports: 0-3 (only when opened)
```

**Savings on Server:**
- **RAM**: ~550MB (60% reduction)
- **Disk**: ~1.9GB (95% reduction)
- **Containers**: 4 fewer containers
- **Attack Surface**: 2 fewer exposed ports

## 11. Schema Reference

### 11.1 Database Alignment

**Important**: Grafana dashboard SQL queries must align with table definitions in `schema.sql`.

When updating `schema.sql`:
1. Update table names/columns in schema
2. Update corresponding Grafana dashboard queries
3. Update monitoring documentation
4. Redeploy dashboards to Grafana (on laptop)

### 11.2 Dashboard Configuration

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

### 11.3 Server Deployment (No Prometheus/Grafana)

```yaml
# docker-compose.yml (server - NO monitoring containers)
services:
  postgres:
    # ... no ports exposed ...
  
  pgbouncer:
    # ... no ports exposed ...
  
  redis:
    # ... no ports exposed ...
  
  sms_receiver:
    ports:
      - "${SMS_RECEIVER_PORT:-8080}:8080"  # ONLY exposed port
```

### 11.4 Laptop Deployment (Monitoring Stack)

```yaml
# docker-compose-monitoring.yml (laptop - on-demand)
services:
  prometheus:
    # Scrapes remote server:9100 (when port opened)
  
  grafana:
    # Connects to Prometheus + optional PostgreSQL direct
```

## 12. Deployment Checklist

### 12.1 Server Deployment (Surface Pro)

- [ ] `/metrics` endpoint implemented in SMS Bridge
- [ ] Admin UI port management endpoints implemented
- [ ] Admin UI port configuration page implemented
- [ ] Default monitoring ports in sms_settings.json
- [ ] Port validation logic implemented
- [ ] Minimal logging configured (WARNING level)
- [ ] Log rotation enabled (7 days)
- [ ] Persistent log volumes mounted
- [ ] Port mapping audit trail enabled
- [ ] Cloudflare Tunnel configured
- [ ] Environment variables set (passwords, secrets)
- [ ] No monitoring containers deployed
- [ ] Only port 8080 exposed

### 12.2 Laptop Setup (Monitoring Client)

- [ ] docker-compose-monitoring.yml created
- [ ] prometheus-remote.yml configured with server IP
- [ ] grafana-datasources.yml configured
- [ ] Start/stop scripts created
- [ ] Grafana dashboards exported and ready to import
- [ ] DBeaver connection profile created (saved, not connected)
- [ ] Redis Desktop Manager profile created (saved, not connected)

### 12.3 Operational Checklist

**When Starting Monitoring Session:**
- [ ] Login to Admin UI
- [ ] Navigate to Monitoring Services
- [ ] Click "Open All Monitoring Ports" or select individually
- [ ] Note the expiration time
- [ ] Start monitoring stack on laptop
- [ ] Wait 15-30 seconds for metrics to populate
- [ ] Access Grafana/Prometheus dashboards

**When Ending Monitoring Session:**
- [ ] Stop monitoring stack on laptop (docker-compose down)
- [ ] Close ports via Admin UI (or wait for auto-close)
- [ ] Verify ports closed in port status page

## 13. Troubleshooting

### 13.1 No Metrics in Prometheus

**Symptoms**: Grafana shows "No data" or Prometheus shows target as "DOWN"

**Checks:**
1. Is monitoring port open on server? Check configured port in Admin UI → Port Config
2. Is server IP correct in prometheus-remote.yml?
3. Can you curl the metrics endpoint? `curl http://SERVER_IP:PORT/metrics` (use configured port)
4. Check Prometheus targets: http://localhost:9090/targets
5. Firewall blocking? (Check iptables rules)
6. Did port configuration change? Re-download Prometheus config from Admin UI

### 13.2 Cannot Connect with DBeaver

**Symptoms**: "Connection refused" or "Timeout"

**Checks:**
1. Is postgres port (5433) open on server? (Admin UI → Port Status)
2. Is password correct? (Check .env file)
3. Is SSL mode set to "disable" in DBeaver?
4. Try psql first: `psql "postgresql://user:pass@SERVER_IP:5433/sms_bridge"`
5. Check if pgbouncer is healthy: `docker ps | grep pgbouncer`

### 13.3 Port Won't Open

**Symptoms**: "Failed to configure firewall" error

**Checks:**
1. Is iptables installed on server?
2. Does SMS Bridge container have permissions? (May need --cap-add=NET_ADMIN)
3. Check container logs: `docker logs sms_receiver`
4. Manual iptables check: `sudo iptables -L -n`

**Workaround**: SSH tunnel as fallback
```bash
ssh -L 5433:localhost:5432 user@server  # For postgres
ssh -L 6380:localhost:6379 user@server  # For redis
```

### 13.4 Logs Not Persisting

**Symptoms**: Logs disappear after container restart

**Checks:**
1. Are volumes mounted correctly? `docker inspect sms_receiver | grep Mounts`
2. Do log directories exist on host? `ls -la ./logs/`
3. Permissions correct? `ls -la ./logs/application/`
4. Check docker-compose volumes section

### 13.5 High Memory Usage

**Symptoms**: Server running out of memory

**Checks:**
1. Check container stats: `docker stats`
2. Redis memory limit: Should be 256MB max
3. PostgreSQL connections: Check via pgAdmin or psql
4. Application memory leaks: Check application logs
5. Old log files: Check if logs are rotating properly

### 13.6 Port Configuration Issues

**Symptoms**: Cannot save port configuration, "Port in use" error

**Checks:**
1. Is another process using the port? `sudo netstat -tulpn | grep PORT`
2. Is a monitoring port currently open? Check Port Status page
3. Is port in privileged range (<1024)? Must use 1024-65535
4. Are multiple services configured with same port? Check for duplicates

**Resolution:**
```bash
# Find what's using the port
sudo lsof -i :9100

# Kill the process (if safe)
sudo kill -9 PID

# Or choose a different port in Admin UI
# Use available port ranges: 9000-9999 for metrics, 5400-5499 for postgres
```

**Symptoms**: Laptop monitoring can't connect after port change

**Resolution:**
```bash
# Re-download Prometheus config from Admin UI
curl -o prometheus-remote.yml \
  https://your-domain.com/admin/monitoring/export-prometheus-config

# Or manually update prometheus-remote.yml with new ports
# Check current ports at: /admin/monitoring/port-config

# Restart Prometheus
docker-compose -f docker-compose-monitoring.yml restart prometheus
```

## 14. Migration from v2.2

### 14.1 Removing Old Monitoring Stack

If upgrading from v2.2 (with Prometheus/Grafana on server):

```bash
# Stop and remove old monitoring containers
docker-compose down prometheus grafana postgres_exporter redis_exporter

# Remove old volumes (CAUTION: deletes historical data)
docker volume rm sms_bridge_prometheus_data
docker volume rm sms_bridge_grafana_data

# Update docker-compose.yml to v2.3 format
# Remove prometheus, grafana, exporters sections
```

### 14.2 Exporting Historical Data

If you want to keep historical metrics before migration:

```bash
# Export Grafana dashboards
curl -u admin:password http://localhost:3001/api/dashboards/... > dashboards.json

# Export Prometheus data (requires remote write or snapshot)
# See: https://prometheus.io/docs/prometheus/latest/storage/

# Or just take database backup
docker exec sms_postgres pg_dump sms_bridge > backup.sql
```

### 14.3 Testing Migration

1. Deploy v2.3 to test environment first
2. Test port opening/closing functionality
3. Test laptop monitoring stack
4. Verify logs are persisting
5. Test external tool connections (DBeaver, Redis Desktop Manager)
6. Load test with monitoring ports open
7. Verify auto-close works after timeout

## 15. Future Enhancements

### 15.1 Potential Improvements

**Cloud-Based Monitoring (Optional):**
- Send metrics to Prometheus Cloud or Grafana Cloud
- No need to run monitoring stack locally
- Cost: ~$50-100/month

**Webhook Notifications:**
- Admin UI triggers webhook when port opened
- Integrate with Slack, Discord, email
- Track port access in team chat

**VPN Alternative:**
- Deploy Wireguard VPN on server
- Connect via VPN instead of opening ports
- More secure, always-on option

**Automated Port Closing:**
- Cron job to close ports at scheduled times
- Integration with monitoring stack lifecycle
- Close ports when laptop monitoring stops

**Rate Limiting on Monitoring Ports:**
- Additional iptables rules for rate limiting
- Prevent brute force on temporarily exposed services
- Log excessive connection attempts

### 15.2 Roadmap

| Version | Features | Target Date |
|---------|----------|-------------|
| 2.3 | Current spec (minimal monitoring) | Q1 2026 |
| 2.4 | Webhook notifications, improved audit trail | Q2 2026 |
| 2.5 | Optional cloud monitoring integration | Q3 2026 |

## 16. Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.2 | 2025-01-01 | Initial monitoring spec aligned with Tech Spec v2.2 |
| 2.3 | 2026-01-12 | Major architecture change: Minimal logging, on-demand port management, remote monitoring stack (Prometheus/Grafana on laptop), removed server-side monitoring containers, security hardening, **configurable monitoring ports via Admin UI (Section 3.4)** |

---

**Document Status**: Draft for Review  
**Next Action**: Review specification → Implement code changes → Test → Deploy  
**Owner**: DevOps Team  
**Last Updated**: 2026-01-12 (Added configurable monitoring ports feature)
