# SMS Bridge Monitoring Code Snippets v2.3

**Technical Implementation Reference**

This document contains all code examples, configuration files, and technical snippets for implementing the monitoring features described in `SMS_Bridge_monitoring_spec_v2.3.md`.

---

## Table of Contents

1. [Configuration Files](#1-configuration-files)
2. [Python Implementation](#2-python-implementation)
3. [Docker & Infrastructure](#3-docker--infrastructure)
4. [Admin UI Endpoints](#4-admin-ui-endpoints)
5. [Prometheus & Grafana](#5-prometheus--grafana)
6. [Helper Scripts](#6-helper-scripts)
7. [Database Queries](#7-database-queries)

---

## 1. Configuration Files

### 1.1 sms_settings.json (with Monitoring Ports)

```json
{
  "version": "2.3.0",
  "settings": {
    "rate_limits": {
      "onboarding_per_minute": 10,
      "sms_per_minute": 20,
      "pin_per_minute": 15
    },
    "validation_checks": {
      "header_hash_check": {
        "enabled": true,
        "failure_action": "reject"
      },
      "foreign_number_check": {
        "enabled": true,
        "allowed_country_codes": ["+91"],
        "failure_action": "reject"
      },
      "count_check": {
        "enabled": true,
        "max_sms_per_hash_24h": 5,
        "failure_action": "reject"
      },
      "blacklist_check": {
        "enabled": true,
        "failure_action": "reject"
      }
    },
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

### 1.2 Docker Compose - Server (Minimal)

```yaml
version: "3.8"

# SMS Bridge - Minimal Server Deployment (No Monitoring Stack)

networks:
  sms_bridge_network:
    driver: bridge

volumes:
  pg_data:
  redis_data:

services:
  postgres:
    image: postgres:15
    container_name: sms_postgres
    restart: unless-stopped
    networks:
      - sms_bridge_network
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./init/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
      - ./init/schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro
      - ./logs/postgres:/var/log/postgresql:rw
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-sms_bridge}
      POSTGRES_LOGGING_COLLECTOR: "on"
      POSTGRES_LOG_DIRECTORY: "/var/log/postgresql"
      POSTGRES_LOG_FILENAME: "postgresql-%Y-%m-%d.log"
      POSTGRES_LOG_ROTATION_AGE: "1d"
      POSTGRES_LOG_ROTATION_SIZE: "10MB"
      POSTGRES_LOG_MIN_DURATION_STATEMENT: "1000"
      POSTGRES_LOG_LINE_PREFIX: "%t [%p]: [%l-1] user=%u,db=%d "
      POSTGRES_LOG_STATEMENT: "none"
      POSTGRES_LOG_MIN_MESSAGES: "WARNING"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-sms_bridge}"]
      interval: 10s
      timeout: 5s
      retries: 5

  pgbouncer:
    image: brainsam/pgbouncer
    container_name: sms_pgbouncer
    restart: unless-stopped
    networks:
      - sms_bridge_network
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DB_HOST: postgres
      DB_PORT: "5432"
      DB_USER: ${POSTGRES_USER:-postgres}
      DB_PASSWORD: ${POSTGRES_PASSWORD}
      DB_NAME: ${POSTGRES_DB:-sms_bridge}
      POOL_MODE: transaction
      MAX_CLIENT_CONN: "1000"
      DEFAULT_POOL_SIZE: "10"
    healthcheck:
      test: ["CMD", "nc", "-z", "localhost", "6432"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: sms_redis
    restart: unless-stopped
    networks:
      - sms_bridge_network
    volumes:
      - redis_data:/data
      - ./logs/redis:/var/log/redis:rw
    command: >
      redis-server 
      --maxmemory 256mb 
      --maxclients 1000 
      --requirepass ${REDIS_PASSWORD}
      --appendonly yes
      --logfile /var/log/redis/redis.log
      --loglevel warning
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  sms_receiver:
    build:
      context: ..
      dockerfile: coolify/Dockerfile
    container_name: sms_receiver
    restart: unless-stopped
    networks:
      - sms_bridge_network
    ports:
      - "${SMS_RECEIVER_PORT:-8080}:8080"
    depends_on:
      pgbouncer:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./logs/application:/app/logs:rw
    environment:
      SMS_BRIDGE_DATABASE__HOST: pgbouncer
      SMS_BRIDGE_DATABASE__NAME: ${POSTGRES_DB:-sms_bridge}
      SMS_BRIDGE_DATABASE__USER: ${POSTGRES_USER:-postgres}
      SMS_BRIDGE_DATABASE__PASSWORD: ${POSTGRES_PASSWORD}
      SMS_BRIDGE_DATABASE__PORT: "6432"
      SMS_BRIDGE_REDIS__HOST: redis
      SMS_BRIDGE_REDIS__PORT: "6379"
      SMS_BRIDGE_REDIS__PASSWORD: ${REDIS_PASSWORD}
      SMS_BRIDGE_ADMIN_USERNAME: ${SMS_BRIDGE_ADMIN_USERNAME:-admin}
      SMS_BRIDGE_ADMIN_PASSWORD: ${SMS_BRIDGE_ADMIN_PASSWORD}
      SMS_BRIDGE_ADMIN_SECRET_KEY: ${SMS_BRIDGE_ADMIN_SECRET_KEY}
      SERVER_IP: ${SERVER_IP:-your-surface-pro-ip}
      LOG_LEVEL: ${LOG_LEVEL:-WARNING}
      LOG_DIR: /app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### 1.3 Docker Compose - Laptop (Monitoring Stack)

```yaml
version: "3.8"

# Monitoring Stack - Run on Laptop (On-Demand)

networks:
  monitoring_network:
    driver: bridge

volumes:
  grafana_data:
  prometheus_data:

services:
  prometheus:
    image: prom/prometheus:v2.48.1
    container_name: monitoring_prometheus
    restart: unless-stopped
    networks:
      - monitoring_network
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus-remote.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=7d'
      - '--web.enable-lifecycle'

  grafana:
    image: grafana/grafana:10.2.3
    container_name: monitoring_grafana
    restart: unless-stopped
    networks:
      - monitoring_network
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana-datasources.yml:/etc/grafana/provisioning/datasources/datasource.yml:ro
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_AUTH_ANONYMOUS_ENABLED: "false"
    depends_on:
      - prometheus
```

### 1.4 Prometheus Configuration (Laptop)

```yaml
# prometheus-remote.yml (run on laptop)
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    monitor: 'sms-bridge-remote'

scrape_configs:
  # Scrape SMS Bridge metrics endpoint
  - job_name: 'sms_receiver'
    static_configs:
      - targets: ['SURFACE_PRO_IP:9100']  # Replace with actual IP and configured port
    metrics_path: '/metrics'
    scrape_interval: 15s
  
  # Self-monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

### 1.5 Grafana Datasource Configuration

```yaml
# grafana-datasources.yml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
  
  # Optional: Direct PostgreSQL connection
  - name: SMS Bridge DB
    type: postgres
    url: SURFACE_PRO_IP:5433
    database: sms_bridge
    user: postgres
    secureJsonData:
      password: YOUR_PASSWORD
    jsonData:
      sslmode: disable
```

---

## 2. Python Implementation

### 2.1 Logging Configuration

```python
# core/config.py or main app file
import logging
from logging.handlers import RotatingFileHandler
import os

# Minimal logging configuration
LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING")

os.makedirs(LOG_DIR, exist_ok=True)

# Single log file with rotation
log_handler = RotatingFileHandler(
    f"{LOG_DIR}/sms_bridge.log",
    maxBytes=10 * 1024 * 1024,  # 10MB per file
    backupCount=7,  # Keep 7 days of logs
)

log_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    handlers=[log_handler]
)

logger = logging.getLogger(__name__)
```

### 2.2 Port Management - Data Models

```python
# core/admin/port_management.py
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import json

# Port mappings persistent storage
PORT_MAPPINGS_FILE = Path("/app/logs/port_mappings.json")

# Service configurations
MONITORING_SERVICES = {
    "postgres": {
        "container": "sms_postgres",
        "internal_port": 5432,
        "external_port": 5433,
        "type": "database"
    },
    "pgbouncer": {
        "container": "sms_pgbouncer",
        "internal_port": 6432,
        "external_port": 6434,
        "type": "database"
    },
    "redis": {
        "container": "sms_redis",
        "internal_port": 6379,
        "external_port": 6380,
        "type": "cache"
    },
    "metrics": {
        "container": "sms_receiver",
        "internal_port": 8080,
        "external_port": 9100,
        "type": "metrics"
    }
}

def load_port_mappings() -> Dict:
    """Load active port mappings from file"""
    if PORT_MAPPINGS_FILE.exists():
        with open(PORT_MAPPINGS_FILE) as f:
            data = json.load(f)
            # Convert ISO strings back to datetime
            for service in data.values():
                service["opened_at"] = datetime.fromisoformat(service["opened_at"])
                service["expires_at"] = datetime.fromisoformat(service["expires_at"])
            return data
    return {}

def save_port_mappings(mappings: Dict):
    """Save port mappings to file"""
    serializable = {}
    for service, data in mappings.items():
        serializable[service] = {
            **data,
            "opened_at": data["opened_at"].isoformat(),
            "expires_at": data["expires_at"].isoformat()
        }
    with open(PORT_MAPPINGS_FILE, "w") as f:
        json.dump(serializable, f, indent=2)
```

### 2.3 Port Configuration Management

```python
# core/admin/port_config.py
import json
import socket
from pathlib import Path
from typing import Dict, List, Tuple

def load_monitoring_config() -> Dict:
    """Load monitoring port configuration from sms_settings.json"""
    settings_file = Path("/app/config/sms_settings.json")
    with open(settings_file) as f:
        config = json.load(f)
    return config.get("settings", {}).get("monitoring_ports", {})

def save_monitoring_config(monitoring_ports: Dict):
    """Save monitoring port configuration to sms_settings.json"""
    settings_file = Path("/app/config/sms_settings.json")
    with open(settings_file) as f:
        config = json.load(f)
    
    config["settings"]["monitoring_ports"] = monitoring_ports
    
    with open(settings_file, "w") as f:
        json.dump(config, f, indent=2)
    
    # Also save to settings_history table
    save_to_settings_history(config)

def validate_port_available(port: int) -> bool:
    """Check if port is available on the system"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('', port))
        sock.close()
        return True
    except OSError:
        return False

def validate_port_config(config: Dict) -> Tuple[bool, List[str]]:
    """Validate monitoring port configuration"""
    errors = []
    used_ports = set()
    
    for service, settings in config.items():
        external_port = settings.get("external_port")
        
        # Range check
        if not (1024 <= external_port <= 65535):
            errors.append(f"{service}: Port {external_port} must be in range 1024-65535")
        
        # Uniqueness check
        if external_port in used_ports:
            errors.append(f"{service}: Port {external_port} already used by another service")
        used_ports.add(external_port)
        
        # Availability check (if enabled)
        if settings.get("enabled", False):
            if not validate_port_available(external_port):
                errors.append(f"{service}: Port {external_port} is already in use")
    
    return len(errors) == 0, errors

def scan_available_ports(start: int = 9000, end: int = 9999, count: int = 10) -> List[int]:
    """Scan for available ports in range"""
    available = []
    for port in range(start, end + 1):
        if len(available) >= count:
            break
        if validate_port_available(port):
            available.append(port)
    return available
```

### 2.4 Port Opening Logic

```python
# core/admin/port_opener.py
import subprocess
import os
from datetime import datetime, timedelta
from typing import Dict

def open_monitoring_port(service: str, duration_minutes: int, username: str) -> Dict:
    """
    Open a monitoring port for external tools
    - Port is exposed via iptables rule
    - Automatically closes after duration
    - Logs who opened it and when
    """
    # Load current configuration from sms_settings.json
    config = load_monitoring_config()
    
    if service not in config:
        raise ValueError(f"Unknown service: {service}")
    
    service_config = config[service]
    
    if not service_config["enabled"]:
        raise ValueError(f"Service '{service}' is disabled in configuration")
    
    external_port = service_config["external_port"]
    internal_port = service_config["internal_port"]
    
    # Validate port still available
    if not validate_port_available(external_port):
        raise ValueError(f"Port {external_port} is no longer available")
    
    # Get server IP
    server_ip = os.getenv("SERVER_IP", "your-server-ip")
    
    # Add iptables rule to expose port
    subprocess.run([
        "iptables", "-A", "INPUT",
        "-p", "tcp",
        "--dport", str(external_port),
        "-j", "ACCEPT"
    ], check=True)
    
    # Add NAT rule for port forwarding
    subprocess.run([
        "iptables", "-t", "nat", "-A", "DOCKER",
        "-p", "tcp",
        "--dport", str(external_port),
        "-j", "DNAT",
        "--to-destination", f"{MONITORING_SERVICES[service]['container']}:{internal_port}"
    ], check=True)
    
    now = datetime.now()
    expires_at = now + timedelta(minutes=duration_minutes)
    
    # Generate connection information
    connection_info = generate_connection_string(service, external_port, server_ip)
    
    # Store mapping
    active_port_mappings[service] = {
        "external_port": external_port,
        "opened_at": now,
        "expires_at": expires_at,
        "opened_by": username,
        "connection_info": connection_info
    }
    
    # Persist to file
    save_port_mappings(active_port_mappings)
    
    # Log the action
    logger.warning(
        f"SECURITY: Monitoring port opened - "
        f"Service: {service}, Port: {external_port}, "
        f"User: {username}, Expires: {expires_at}"
    )
    
    return {
        "status": "opened",
        "service": service,
        "port": external_port,
        "opened_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "connection_info": connection_info
    }

def close_monitoring_port(service: str, username: str) -> Dict:
    """Close an open monitoring port"""
    if service not in active_port_mappings:
        return {"error": "Port not open"}
    
    config = MONITORING_SERVICES[service]
    external_port = active_port_mappings[service]["external_port"]
    
    # Remove iptables rules
    subprocess.run([
        "iptables", "-D", "INPUT",
        "-p", "tcp",
        "--dport", str(external_port),
        "-j", "ACCEPT"
    ], check=False)
    
    subprocess.run([
        "iptables", "-t", "nat", "-D", "DOCKER",
        "-p", "tcp",
        "--dport", str(external_port),
        "-j", "DNAT",
        "--to-destination", f"{config['container']}:{config['internal_port']}"
    ], check=False)
    
    # Log the action
    logger.warning(
        f"SECURITY: Monitoring port closed - "
        f"Service: {service}, Port: {external_port}, "
        f"User: {username}"
    )
    
    # Remove from active mappings
    del active_port_mappings[service]
    save_port_mappings(active_port_mappings)
    
    return {
        "status": "closed",
        "service": service,
        "port": external_port
    }

def generate_connection_string(service: str, port: int, server_ip: str) -> Dict:
    """Generate connection information for a service"""
    if service in ["postgres", "pgbouncer"]:
        return {
            "host": server_ip,
            "port": port,
            "database": os.getenv("POSTGRES_DB", "sms_bridge"),
            "username": os.getenv("POSTGRES_USER", "postgres"),
            "connection_string": f"postgresql://{os.getenv('POSTGRES_USER')}:****@{server_ip}:{port}/{os.getenv('POSTGRES_DB')}"
        }
    elif service == "redis":
        return {
            "host": server_ip,
            "port": port,
            "connection_string": f"redis://:****@{server_ip}:{port}/0"
        }
    elif service == "metrics":
        return {
            "url": f"http://{server_ip}:{port}/metrics",
            "health": f"http://{server_ip}:{port}/health"
        }
    return {}
```

### 2.5 Prometheus Metrics

```python
# core/observability/metrics_v2.py
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import logging

logger = logging.getLogger(__name__)

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

# Helper functions to record metrics
def record_onboarding(status: str):
    """Record an onboarding event"""
    ONBOARDING_TOTAL.labels(status=status).inc()

def record_sms_received(status: str):
    """Record an SMS receive event"""
    SMS_RECEIVED_TOTAL.labels(status=status).inc()

def record_pin_collected(status: str):
    """Record a PIN collection event"""
    PIN_COLLECTED_TOTAL.labels(status=status).inc()

def record_rate_limited():
    """Record a rate limit event"""
    RATE_LIMITED_TOTAL.inc()

def record_validation_failure(check: str):
    """Record a validation failure"""
    VALIDATION_FAILURES_TOTAL.labels(check=check).inc()
```

### 2.6 FastAPI Endpoint Usage

```python
# core/sms_server_v2.py
from fastapi import HTTPException
from core.observability.metrics_v2 import (
    record_onboarding,
    record_sms_received,
    record_pin_collected,
    record_rate_limited,
    record_validation_failure,
    metrics_endpoint
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
        if not validate_header_hash():
            record_validation_failure(check="header_hash_check")
            raise HTTPException(status_code=400, detail="Invalid hash")
        
        if not validate_foreign_number():
            record_validation_failure(check="foreign_number_check")
            raise HTTPException(status_code=400, detail="Foreign number")
        
        record_sms_received(status="received")
        return response
    except Exception:
        record_sms_received(status="failed")
        raise

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return metrics_endpoint()
```

---

## 3. Docker & Infrastructure

### 3.1 Volume Mounts for Persistent Logs

```yaml
volumes:
  # Application logs
  - ./logs/application:/app/logs:rw
  
  # PostgreSQL logs
  - ./logs/postgres:/var/log/postgresql:rw
  
  # Redis logs
  - ./logs/redis:/var/log/redis:rw
```

### 3.2 Environment Variables

```bash
# .env file for server
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=sms_bridge
REDIS_PASSWORD=your_redis_password
SMS_RECEIVER_PORT=8080
SERVER_IP=your.server.ip.address

# Admin credentials
SMS_BRIDGE_ADMIN_USERNAME=admin
SMS_BRIDGE_ADMIN_PASSWORD=your_admin_password
SMS_BRIDGE_ADMIN_SECRET_KEY=your_secret_key

# Logging
LOG_LEVEL=WARNING
LOG_DIR=/app/logs

# Grafana (laptop)
GRAFANA_ADMIN_PASSWORD=admin
```

---

## 4. Admin UI Endpoints

### 4.1 Port Management API

```python
# core/admin/admin.py
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

admin_router = APIRouter(prefix="/admin/monitoring", tags=["monitoring"])

class OpenPortRequest(BaseModel):
    service: str
    duration_minutes: int = 60

class PortConfigUpdate(BaseModel):
    config: Dict[str, Dict]

@admin_router.get("/services")
async def list_monitoring_services(request: Request):
    """List available services for monitoring"""
    return {
        "services": MONITORING_SERVICES,
        "active_ports": await get_active_ports()
    }

@admin_router.post("/open-port")
async def open_port_endpoint(request: Request, body: OpenPortRequest):
    """Open a monitoring port"""
    username = request.state.username  # From auth middleware
    
    if body.duration_minutes > 240:
        raise HTTPException(status_code=400, detail="Max duration is 240 minutes")
    
    return open_monitoring_port(body.service, body.duration_minutes, username)

@admin_router.post("/close-port")
async def close_port_endpoint(request: Request, service: str):
    """Close a monitoring port"""
    username = request.state.username
    return close_monitoring_port(service, username)

@admin_router.get("/port-status")
async def port_status_endpoint(request: Request):
    """Get status of all monitoring ports"""
    now = datetime.now()
    
    # Auto-close expired ports
    expired = [
        service for service, data in active_port_mappings.items()
        if data["expires_at"] < now
    ]
    
    for service in expired:
        await close_port_endpoint(request, service)
    
    return await get_active_ports()

@admin_router.post("/open-all")
async def open_all_ports(request: Request, duration_minutes: int = 60):
    """Open all enabled monitoring ports"""
    config = load_monitoring_config()
    results = {}
    
    for service, settings in config.items():
        if settings.get("enabled", False):
            try:
                result = open_monitoring_port(service, duration_minutes, request.state.username)
                results[service] = result
            except Exception as e:
                results[service] = {"error": str(e)}
    
    return {"status": "completed", "results": results}

@admin_router.post("/close-all")
async def close_all_ports(request: Request):
    """Close all monitoring ports"""
    closed = []
    for service in list(active_port_mappings.keys()):
        try:
            close_monitoring_port(service, request.state.username)
            closed.append(service)
        except Exception as e:
            logger.error(f"Failed to close {service}: {e}")
    
    return {"status": "completed", "closed": closed}

@admin_router.get("/port-config")
async def get_port_config(request: Request):
    """Get current port configuration"""
    config = load_monitoring_config()
    return {
        "current_config": config,
        "active_ports": list(active_port_mappings.keys()),
        "version": "2.3.0"
    }

@admin_router.post("/port-config")
async def update_port_config(request: Request, body: PortConfigUpdate):
    """Update port configuration"""
    # Validate no ports are currently open
    if active_port_mappings:
        raise HTTPException(
            status_code=400,
            detail="Cannot change port configuration while ports are open. Close all ports first."
        )
    
    # Validate configuration
    is_valid, errors = validate_port_config(body.config)
    if not is_valid:
        raise HTTPException(status_code=400, detail={"errors": errors})
    
    # Save configuration
    save_monitoring_config(body.config)
    
    # Log change
    logger.warning(
        f"SECURITY: Port configuration updated - User: {request.state.username}"
    )
    
    return {"status": "success", "config": body.config}

@admin_router.post("/port-config/reset")
async def reset_port_config(request: Request):
    """Reset port configuration to defaults"""
    default_config = {
        "metrics": {"external_port": 9100, "internal_port": 8080, "enabled": true},
        "postgres": {"external_port": 5433, "internal_port": 5432, "enabled": true},
        "pgbouncer": {"external_port": 6434, "internal_port": 6432, "enabled": false},
        "redis": {"external_port": 6380, "internal_port": 6379, "enabled": true}
    }
    
    save_monitoring_config(default_config)
    return {"status": "reset", "config": default_config}

@admin_router.get("/export-prometheus-config")
async def export_prometheus_config(request: Request):
    """Export Prometheus configuration with current ports"""
    config = load_monitoring_config()
    server_ip = os.getenv("SERVER_IP", "your-server-ip")
    
    metrics_port = config.get("metrics", {}).get("external_port", 9100)
    
    prometheus_config = f"""# Generated prometheus-remote.yml
# Server: {server_ip}
# Generated: {datetime.now().isoformat()}

global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'sms_receiver'
    static_configs:
      - targets: ['{server_ip}:{metrics_port}']
"""
    
    return Response(content=prometheus_config, media_type="text/yaml")

@admin_router.get("/logs/download")
async def download_logs(request: Request, service: str):
    """Download logs for a specific service"""
    from fastapi.responses import FileResponse
    
    log_files = {
        "application": Path("/app/logs/sms_bridge.log"),
        "postgres": Path("/app/logs/postgres/postgresql-*.log"),
        "redis": Path("/app/logs/redis/redis.log")
    }
    
    if service not in log_files:
        raise HTTPException(status_code=400, detail="Invalid service")
    
    log_path = log_files[service]
    
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    return FileResponse(
        log_path,
        media_type="text/plain",
        filename=f"{service}-{datetime.now().strftime('%Y%m%d')}.log"
    )
```

---

## 5. Prometheus & Grafana

### 5.1 Prometheus Alert Rules

```yaml
# prometheus/alerts.yml (on laptop - informational only)
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

### 5.2 Grafana Dashboard - PromQL Queries

```promql
# Panel 1: Onboarding Request Rate
rate(sms_bridge_onboarding_total[5m])

# Panel 2: SMS Processing Rate
rate(sms_bridge_sms_received_total[5m])

# Panel 3: PIN Collection Rate
rate(sms_bridge_pin_collected_total[5m])

# Panel 4: Validation Failure Rate (by check type)
rate(sms_bridge_validation_failures_total[5m])

# Panel 5: Queue Depths
sms_bridge_sync_queue_length
sms_bridge_audit_buffer_length

# Panel 6: Active Sessions
sms_bridge_active_onboarding_count
sms_bridge_verified_count

# Panel 7: Blacklist Size
sms_bridge_blacklist_size

# Panel 8: Rate Limiting
rate(sms_bridge_rate_limited_total[5m])

# Panel 9: Success Rate (Onboarding)
sum(rate(sms_bridge_onboarding_total{status="success"}[5m])) / 
sum(rate(sms_bridge_onboarding_total[5m]))

# Panel 10: Error Rate
sum(rate(sms_bridge_onboarding_total{status="failed"}[5m])) + 
sum(rate(sms_bridge_sms_received_total{status="failed"}[5m]))
```

---

## 6. Helper Scripts

### 6.1 Start Monitoring (Laptop)

```bash
#!/bin/bash
# start-monitoring.sh

SURFACE_IP="${1:-your.server.ip}"

echo "🚀 Starting monitoring stack on laptop..."
echo "📊 Will connect to Surface Pro at: $SURFACE_IP"

# Update prometheus config with actual IP
sed -i "s/SURFACE_PRO_IP/$SURFACE_IP/g" prometheus-remote.yml

# Start monitoring containers
docker-compose -f docker-compose-monitoring.yml up -d

echo ""
echo "✅ Monitoring started!"
echo ""
echo "📊 Grafana: http://localhost:3000 (admin/admin)"
echo "🔍 Prometheus: http://localhost:9090"
echo ""
echo "⚠️  Don't forget to:"
echo "   1. Login to Surface Pro admin UI"
echo "   2. Open monitoring ports via Admin UI → Monitoring"
echo "   3. Wait 15-30 seconds for metrics to appear"
echo ""
```

### 6.2 Stop Monitoring (Laptop)

```bash
#!/bin/bash
# stop-monitoring.sh

echo "🛑 Stopping monitoring stack..."

docker-compose -f docker-compose-monitoring.yml down

echo "✅ Monitoring stopped!"
echo ""
echo "💡 Remember to close monitoring ports on Surface Pro via Admin UI"
```

### 6.3 Check Monitoring Status (Laptop)

```bash
#!/bin/bash
# check-monitoring.sh

echo "📊 Monitoring Stack Status"
echo "=========================="
echo ""

# Check if containers are running
if docker ps | grep -q monitoring_prometheus; then
    echo "✅ Prometheus: Running"
    echo "   http://localhost:9090"
else
    echo "❌ Prometheus: Not running"
fi

if docker ps | grep -q monitoring_grafana; then
    echo "✅ Grafana: Running"
    echo "   http://localhost:3000"
else
    echo "❌ Grafana: Not running"
fi

echo ""
echo "📈 Prometheus Targets Status:"
curl -s http://localhost:9090/api/v1/targets | jq -r '.data.activeTargets[] | "\(.labels.job): \(.health)"'

echo ""
echo "💾 Storage Usage:"
docker exec monitoring_prometheus df -h /prometheus | tail -1
```

---

## 7. Database Queries

### 7.1 Grafana SQL Queries (Direct PostgreSQL)

```sql
-- Panel: Recent Logs
SELECT 
    id, 
    event, 
    details::text, 
    created_at
FROM sms_bridge_logs
ORDER BY created_at DESC
LIMIT 50;

-- Panel: Backup Users (Sync Status)
SELECT 
    id, 
    mobile, 
    hash, 
    created_at,
    CASE 
        WHEN synced_at IS NULL THEN 'pending' 
        ELSE 'synced' 
    END as sync_status,
    synced_at
FROM backup_users
ORDER BY created_at DESC
LIMIT 50;

-- Panel: Settings History
SELECT 
    version_id, 
    is_active, 
    created_at, 
    created_by, 
    change_note
FROM settings_history
ORDER BY created_at DESC
LIMIT 20;

-- Panel: Active Settings
SELECT 
    version_id,
    payload::text as settings,
    created_at,
    created_by
FROM settings_history
WHERE is_active = true
LIMIT 1;

-- Panel: Blacklist
SELECT 
    id, 
    mobile, 
    reason, 
    created_at, 
    created_by
FROM blacklist_mobiles
ORDER BY created_at DESC
LIMIT 50;

-- Panel: Recent Blacklist Additions (Last 24h)
SELECT 
    COUNT(*) as count,
    DATE_TRUNC('hour', created_at) as hour
FROM blacklist_mobiles
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour;

-- Panel: Pending Syncs Count
SELECT COUNT(*) as pending_count
FROM backup_users
WHERE synced_at IS NULL;

-- Panel: Sync Success Rate (Last 24h)
SELECT 
    COUNT(*) FILTER (WHERE synced_at IS NOT NULL) * 100.0 / COUNT(*) as sync_rate_percent
FROM backup_users
WHERE created_at > NOW() - INTERVAL '24 hours';
```

### 7.2 Administrative Queries

```sql
-- Check port access audit trail
SELECT * FROM port_access_log
WHERE opened_at > NOW() - INTERVAL '7 days'
ORDER BY opened_at DESC;

-- Find failed login attempts
SELECT * FROM admin_login_attempts
WHERE success = false
ORDER BY attempted_at DESC
LIMIT 20;

-- Settings change history
SELECT 
    version_id,
    created_by,
    created_at,
    change_note,
    CASE 
        WHEN is_active THEN 'ACTIVE'
        ELSE 'INACTIVE'
    END as status
FROM settings_history
ORDER BY created_at DESC;
```

---

## Notes

1. **Security**: All code snippets assume proper authentication middleware is in place
2. **Error Handling**: Production code should include more comprehensive error handling
3. **Logging**: Adjust log levels based on your needs (WARNING for production, DEBUG for development)
4. **Port Numbers**: Update `SURFACE_PRO_IP` and port numbers based on your actual configuration
5. **Passwords**: Never commit passwords or secrets to version control
6. **Testing**: Test all port operations in a safe environment before production use

---

**Document Version**: 2.3  
**Last Updated**: 2026-01-12  
**Related Document**: `SMS_Bridge_monitoring_spec_v2.3.md`
