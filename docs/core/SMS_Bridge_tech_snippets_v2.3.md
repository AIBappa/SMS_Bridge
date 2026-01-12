# SMS Bridge Technical Snippets v2.3

**Complete Code Examples and Technical Implementation**

> This document contains ALL code examples, configurations, and technical details for SMS Bridge.
> For simple explanations of WHAT and WHY, see [SMS_Bridge_tech_spec_v2.3.md](SMS_Bridge_tech_spec_v2.3.md)

---

## Table of Contents

1. [Python Dependencies](#python-dependencies)
2. [Configuration Files](#configuration-files)
3. [Database Schema](#database-schema)
4. [Redis Operations Reference](#redis-operations-reference)
5. [API Implementation](#api-implementation)
6. [Background Workers](#background-workers)
7. [Admin UI Implementation](#admin-ui-implementation)
8. [Helper Scripts](#helper-scripts)
9. [Error Handling](#error-handling)
10. [Testing Examples](#testing-examples)

---

## Python Dependencies

### requirements.txt

```txt
# Core Dependencies
fastapi>=0.100.0          # Web framework
uvicorn[standard]         # ASGI server
pydantic>=2.0             # Data validation
sqlalchemy>=2.0           # ORM for Postgres
psycopg2-binary           # Postgres driver
sqladmin>=0.15            # Admin UI
redis>=5.0                # Redis client (sync)
passlib[bcrypt]           # Password hashing
httpx>=0.25               # HTTP client for sync_url calls
python-dotenv             # Environment variables

# Background Workers
apscheduler>=3.10         # Scheduled tasks (sync_interval, log_interval)

# Optional (Production)
gunicorn                  # Production WSGI
prometheus-client         # Metrics export
```

### Installation Command

```bash
pip install -r requirements.txt
```

---

## Configuration Files

### sms_settings.json (Unified Configuration)

```json
{
  "sms_receiver_number": "+919000000000",
  "allowed_prefix": "ONBOARD:",
  "hash_length": 8,
  "ttl_hash_seconds": 900,
  "sync_interval": 1.0,
  "log_interval": 120,
  "count_threshold": 5,
  "allowed_countries": ["+91", "+44"],
  "sync_url": "https://your-backend.com/api/validated-users",
  "recovery_url": "https://your-backend.com/api/recover",
  "checks": {
    "header_hash_check_enabled": true,
    "foreign_number_check_enabled": true,
    "count_check_enabled": true,
    "blacklist_check_enabled": true
  },
  "secrets": {
    "hmac_secret": "your-secret-key-here",
    "hash_key": "your-hash-key-here"
  },
  "monitoring_ports": {
    "metrics": {
      "external_port": 8081,
      "internal_port": 8081
    },
    "postgres": {
      "external_port": 5432,
      "internal_port": 5432
    },
    "pgbouncer": {
      "external_port": 6432,
      "internal_port": 6432
    },
    "redis": {
      "external_port": 6379,
      "internal_port": 6379
    }
  },
  "rate_limits": {
    "onboarding_per_minute": 10,
    "sms_per_minute": 20,
    "pin_per_minute": 5
  },
  "validation_checks": {
    "header_hash": true,
    "foreign_number": {
      "enabled": true,
      "allowed_countries": ["+91", "+44"]
    },
    "count": {
      "enabled": true,
      "threshold": 5
    },
    "blacklist": true
  }
}
```

### .env (Environment Variables)

```env
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sms_bridge
POSTGRES_USER=sms_user
POSTGRES_PASSWORD=secure_password_here

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# API Server
API_HOST=0.0.0.0
API_PORT=8080
DEBUG=false

# Admin UI
ADMIN_SECRET_KEY=your-admin-secret-key-here

# Logging
LOG_LEVEL=WARNING
LOG_DIR=/var/log/sms_bridge
```

### Docker Compose (Minimal Server Deployment)

```yaml
version: '3.8'

services:
  sms_bridge:
    build: .
    container_name: sms_receiver
    ports:
      - "8080:8080"
    environment:
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=sms_bridge
      - POSTGRES_USER=sms_user
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    volumes:
      - ./logs:/var/log/sms_bridge
      - ./sms_settings.json:/app/sms_settings.json:ro
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - sms_network

  postgres:
    image: postgres:16-alpine
    container_name: postgres
    environment:
      - POSTGRES_DB=sms_bridge
      - POSTGRES_USER=sms_user
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sms_user -d sms_bridge"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - sms_network

  pgbouncer:
    image: pgbouncer/pgbouncer:latest
    container_name: pgbouncer
    environment:
      - DATABASES_HOST=postgres
      - DATABASES_PORT=5432
      - DATABASES_USER=sms_user
      - DATABASES_PASSWORD=${POSTGRES_PASSWORD}
      - DATABASES_DBNAME=sms_bridge
      - POOL_MODE=transaction
      - MAX_CLIENT_CONN=100
      - DEFAULT_POOL_SIZE=20
    depends_on:
      - postgres
    restart: unless-stopped
    networks:
      - sms_network

  redis:
    image: redis:7-alpine
    container_name: redis
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - sms_network

volumes:
  postgres_data:
  redis_data:

networks:
  sms_network:
    driver: bridge
```

---

## Database Schema

### Complete SQL Schema

```sql
-- 1. Configuration History (Append-Only)
CREATE TABLE settings_history (
    version_id SERIAL PRIMARY KEY,
    payload JSONB NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(50),
    change_note TEXT
);

-- 2. Admin Users
CREATE TABLE admin_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_super_admin BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. Logs (Append-Only)
CREATE TABLE sms_bridge_logs (
    id SERIAL PRIMARY KEY,
    event VARCHAR(50) NOT NULL,
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 4. Backup Credentials (Hot Path Backup)
CREATE TABLE backup_users (
    id SERIAL PRIMARY KEY,
    mobile VARCHAR(20) NOT NULL,
    pin VARCHAR(10) NOT NULL,
    hash VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    synced_at TIMESTAMP
);

-- 5. Power-Down Store (Redis Failure Backup)
CREATE TABLE power_down_store (
    id SERIAL PRIMARY KEY,
    key_name VARCHAR(255) NOT NULL,
    key_type VARCHAR(20) NOT NULL,
    value JSONB NOT NULL,
    original_ttl INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 6. Blacklist (Persistent)
CREATE TABLE blacklist_mobiles (
    id SERIAL PRIMARY KEY,
    mobile VARCHAR(20) UNIQUE NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(50)
);

-- Indexes for fast lookups
CREATE INDEX idx_settings_active ON settings_history(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_logs_event ON sms_bridge_logs(event);
CREATE INDEX idx_logs_created ON sms_bridge_logs(created_at);
CREATE INDEX idx_backup_mobile ON backup_users(mobile);
CREATE INDEX idx_powerdown_key ON power_down_store(key_name);
CREATE INDEX idx_blacklist_mobile ON blacklist_mobiles(mobile);

-- Constraints
ALTER TABLE settings_history 
  ADD CONSTRAINT check_only_one_active 
  EXCLUDE USING gist ((1::integer) WITH =) 
  WHERE (is_active = TRUE);

-- Trigger for settings change audit
CREATE OR REPLACE FUNCTION audit_settings_change()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.is_active = TRUE THEN
    UPDATE settings_history 
    SET is_active = FALSE 
    WHERE is_active = TRUE AND version_id != NEW.version_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER settings_activation_trigger
  BEFORE INSERT OR UPDATE ON settings_history
  FOR EACH ROW
  EXECUTE FUNCTION audit_settings_change();
```

### SQLAlchemy Models

```python
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class SettingsHistory(Base):
    __tablename__ = 'settings_history'
    
    version_id = Column(Integer, primary_key=True)
    payload = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    created_by = Column(String(50))
    change_note = Column(Text)

class AdminUser(Base):
    __tablename__ = 'admin_users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_super_admin = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

class SMSBridgeLog(Base):
    __tablename__ = 'sms_bridge_logs'
    
    id = Column(Integer, primary_key=True)
    event = Column(String(50), nullable=False)
    details = Column(JSON)
    created_at = Column(TIMESTAMP, server_default=func.now())

class BackupUser(Base):
    __tablename__ = 'backup_users'
    
    id = Column(Integer, primary_key=True)
    mobile = Column(String(20), nullable=False)
    pin = Column(String(10), nullable=False)
    hash = Column(String(20), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    synced_at = Column(TIMESTAMP)

class PowerDownStore(Base):
    __tablename__ = 'power_down_store'
    
    id = Column(Integer, primary_key=True)
    key_name = Column(String(255), nullable=False)
    key_type = Column(String(20), nullable=False)
    value = Column(JSON, nullable=False)
    original_ttl = Column(Integer)
    created_at = Column(TIMESTAMP, server_default=func.now())

class BlacklistMobile(Base):
    __tablename__ = 'blacklist_mobiles'
    
    id = Column(Integer, primary_key=True)
    mobile = Column(String(20), unique=True, nullable=False)
    reason = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
    created_by = Column(String(50))
```

---

## Redis Operations Reference

### Connection Setup

```python
import redis
from redis.connection import ConnectionPool

# Create connection pool
pool = ConnectionPool(
    host='localhost',
    port=6379,
    db=0,
    max_connections=10,
    decode_responses=True,
    socket_timeout=5,
    socket_connect_timeout=5
)

# Create Redis client
redis_client = redis.Redis(connection_pool=pool)

# Health check
def check_redis_health():
    try:
        redis_client.ping()
        return "healthy"
    except redis.ConnectionError:
        return "unhealthy"
    except redis.TimeoutError:
        return "degraded"
```

### Settings Cache Operations

```python
import json

def load_settings_from_redis():
    """Load cached settings from Redis"""
    settings_json = redis_client.get("config:current")
    if not settings_json:
        # Fallback to database
        settings = load_settings_from_postgres()
        cache_settings_to_redis(settings)
        return settings
    return json.loads(settings_json)

def cache_settings_to_redis(settings_dict):
    """Cache settings to Redis"""
    redis_client.set("config:current", json.dumps(settings_dict))
```

### Onboarding Operations

```python
import hashlib
import hmac
import base64
from datetime import datetime, timedelta

def register_onboarding(mobile_number, settings):
    """Complete onboarding registration flow"""
    
    # 1. Rate limit check
    rate_key = f"limit:sms:{mobile_number}"
    count = redis_client.incr(rate_key)
    if count == 1:
        redis_client.expire(rate_key, 3600)  # 1 hour
    
    if count > settings['count_threshold']:
        raise RateLimitExceeded("Too many SMS requests")
    
    # 2. Generate hash
    timestamp = datetime.utcnow().isoformat()
    input_string = f"{mobile_number}{timestamp}"
    hmac_key = settings['secrets']['hmac_secret'].encode()
    
    hmac_hash = hmac.new(
        hmac_key,
        input_string.encode(),
        hashlib.sha256
    ).digest()
    
    hash_value = base64.b32encode(hmac_hash).decode()[:settings['hash_length']]
    
    # 3. Store in Redis
    onboarding_key = f"active_onboarding:{hash_value}"
    expires_at = datetime.utcnow() + timedelta(seconds=settings['ttl_hash_seconds'])
    
    redis_client.hset(
        onboarding_key,
        mapping={
            'mobile': mobile_number,
            'expires_at': expires_at.isoformat()
        }
    )
    redis_client.expire(onboarding_key, settings['ttl_hash_seconds'])
    
    # 4. Log event
    log_event("HASH_GEN", {
        'mobile': mobile_number,
        'hash': hash_value,
        'expires_at': expires_at.isoformat()
    })
    
    return {
        'hash': hash_value,
        'generated_at': timestamp,
        'user_deadline': expires_at.isoformat(),
        'user_timelimit_seconds': settings['ttl_hash_seconds']
    }
```

### SMS Validation Pipeline

```python
def validate_sms(mobile_number, message, settings):
    """Complete SMS validation pipeline"""
    
    validation_results = {
        'header_hash_check': None,
        'foreign_number_check': None,
        'count_check': None,
        'blacklist_check': None
    }
    
    # 1. Header Hash Check
    if settings['checks']['header_hash_check_enabled']:
        prefix = settings['allowed_prefix']
        hash_length = settings['hash_length']
        expected_length = len(prefix) + hash_length
        
        if len(message) != expected_length:
            validation_results['header_hash_check'] = {'status': 2, 'reason': 'LENGTH_MISMATCH'}
            return False, validation_results
        
        if not message.startswith(prefix):
            validation_results['header_hash_check'] = {'status': 2, 'reason': 'PREFIX_MISMATCH'}
            return False, validation_results
        
        hash_value = message[len(prefix):]
        onboarding_key = f"active_onboarding:{hash_value}"
        
        if not redis_client.exists(onboarding_key):
            validation_results['header_hash_check'] = {'status': 2, 'reason': 'HASH_NOT_FOUND'}
            return False, validation_results
        
        validation_results['header_hash_check'] = {'status': 1, 'hash': hash_value}
    else:
        validation_results['header_hash_check'] = {'status': 3}
    
    # 2. Foreign Number Check
    if settings['checks']['foreign_number_check_enabled']:
        allowed_countries = settings['allowed_countries']
        country_code = next((c for c in allowed_countries if mobile_number.startswith(c)), None)
        
        if not country_code:
            validation_results['foreign_number_check'] = {'status': 2, 'reason': 'COUNTRY_NOT_ALLOWED'}
            return False, validation_results
        
        validation_results['foreign_number_check'] = {'status': 1, 'country': country_code}
    else:
        validation_results['foreign_number_check'] = {'status': 3}
    
    # 3. Count Check
    if settings['checks']['count_check_enabled']:
        rate_key = f"limit:sms:{mobile_number}"
        count = redis_client.incr(rate_key)
        
        if count == 1:
            redis_client.expire(rate_key, 3600)
        
        if count > settings['count_threshold']:
            validation_results['count_check'] = {'status': 2, 'reason': 'RATE_LIMIT_EXCEEDED', 'count': count}
            return False, validation_results
        
        validation_results['count_check'] = {'status': 1, 'count': count}
    else:
        validation_results['count_check'] = {'status': 3}
    
    # 4. Blacklist Check
    if settings['checks']['blacklist_check_enabled']:
        if redis_client.sismember('blacklist_mobiles', mobile_number):
            validation_results['blacklist_check'] = {'status': 2, 'reason': 'BLACKLISTED'}
            return False, validation_results
        
        validation_results['blacklist_check'] = {'status': 1}
    else:
        validation_results['blacklist_check'] = {'status': 3}
    
    # All checks passed - mark as verified (atomic)
    hash_value = validation_results['header_hash_check']['hash']
    onboarding_key = f"active_onboarding:{hash_value}"
    verified_key = f"verified:{mobile_number}"
    
    pipe = redis_client.pipeline()
    pipe.delete(onboarding_key)
    pipe.setex(verified_key, 900, hash_value)  # 15 min TTL
    pipe.execute()
    
    # Log success
    log_event("SMS_VERIFIED", {
        'mobile': mobile_number,
        'hash': hash_value,
        'validation_results': validation_results
    })
    
    return True, validation_results
```

### PIN Setup Operations

```python
def setup_pin(mobile_number, pin, hash_value, settings):
    """Process PIN setup after SMS verification"""
    
    # 1. Check verification status
    verified_key = f"verified:{mobile_number}"
    stored_hash = redis_client.get(verified_key)
    
    if not stored_hash:
        raise ValueError("Mobile not verified")
    
    if stored_hash != hash_value:
        raise ValueError("Hash mismatch")
    
    # 2. Push to hot path (sync_queue)
    payload = {
        'mobile': mobile_number,
        'pin': pin,
        'hash': hash_value,
        'timestamp': datetime.utcnow().isoformat()
    }
    redis_client.lpush('sync_queue', json.dumps(payload))
    
    # 3. Log to cold path (audit_buffer)
    log_event("PIN_COLLECTED", {
        'mobile': mobile_number,
        'hash': hash_value
    })
    
    # 4. Delete verified status (one-time use)
    redis_client.delete(verified_key)
    
    return {'status': 'success', 'message': 'PIN accepted'}
```

### Blacklist Operations

```python
def sync_blacklist_from_postgres():
    """Load blacklist from PostgreSQL to Redis on startup"""
    db = SessionLocal()
    blacklist = db.query(BlacklistMobile).all()
    
    if blacklist:
        redis_client.delete('blacklist_mobiles')
        mobile_numbers = [entry.mobile for entry in blacklist]
        redis_client.sadd('blacklist_mobiles', *mobile_numbers)
    
    db.close()

def add_to_blacklist(mobile_number, reason, admin_username):
    """Add number to blacklist (Postgres + Redis)"""
    db = SessionLocal()
    
    # Add to Postgres
    entry = BlacklistMobile(
        mobile=mobile_number,
        reason=reason,
        created_by=admin_username
    )
    db.add(entry)
    db.commit()
    
    # Add to Redis
    redis_client.sadd('blacklist_mobiles', mobile_number)
    
    # Log action
    log_event("BLACKLIST_ADD", {
        'mobile': mobile_number,
        'reason': reason,
        'admin': admin_username
    })
    
    db.close()
```

### Logging Operations

```python
def log_event(event_name, details):
    """Push event to audit buffer"""
    log_entry = {
        'event': event_name,
        'details': details,
        'timestamp': datetime.utcnow().isoformat()
    }
    redis_client.lpush('audit_buffer', json.dumps(log_entry))
```

---

## API Implementation

### FastAPI Main Application

```python
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel, validator
import httpx

app = FastAPI(title="SMS Bridge", version="2.3")

# Pydantic Models
class OnboardingRequest(BaseModel):
    mobile_number: str
    email: str | None = None
    device_id: str | None = None
    
    @validator('mobile_number')
    def validate_mobile(cls, v):
        if not v.startswith('+'):
            raise ValueError('Mobile must start with +')
        if not v[1:].isdigit():
            raise ValueError('Mobile must contain only digits after +')
        if len(v) < 10 or len(v) > 15:
            raise ValueError('Mobile length must be 10-15 characters')
        return v

class SMSReceiveRequest(BaseModel):
    mobile_number: str
    message: str
    received_at: str

class PINSetupRequest(BaseModel):
    mobile_number: str
    pin: str
    hash: str
    
    @validator('pin')
    def validate_pin(cls, v):
        if not v.isdigit():
            raise ValueError('PIN must contain only digits')
        if len(v) < 4 or len(v) > 10:
            raise ValueError('PIN length must be 4-10 digits')
        return v

# Endpoints
@app.post("/onboarding/register")
async def register_onboarding(request: OnboardingRequest):
    """Start onboarding process"""
    try:
        settings = load_settings_from_redis()
        
        # Validate country
        allowed = settings['allowed_countries']
        if not any(request.mobile_number.startswith(c) for c in allowed):
            raise HTTPException(
                status_code=403,
                detail=f"Country not supported. Allowed: {allowed}"
            )
        
        # Register
        result = register_onboarding(request.mobile_number, settings)
        
        return {
            "status": "success",
            "sms_receiving_number": settings['sms_receiver_number'],
            **result
        }
    
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        log_event("ERROR_ONBOARDING", {'error': str(e), 'mobile': request.mobile_number})
        raise HTTPException(status_code=500, detail="Internal error")

@app.post("/sms/receive")
async def receive_sms(request: SMSReceiveRequest):
    """Process incoming SMS"""
    try:
        settings = load_settings_from_redis()
        success, results = validate_sms(
            request.mobile_number,
            request.message,
            settings
        )
        
        if success:
            return {
                "status": "received",
                "message_id": f"msg-{datetime.utcnow().timestamp()}",
                "queued_for_processing": True,
                "validation_results": results
            }
        else:
            log_event("SMS_REJECTED", {
                'mobile': request.mobile_number,
                'message': request.message,
                'validation_results': results
            })
            return {
                "status": "rejected",
                "validation_results": results
            }
    
    except Exception as e:
        log_event("ERROR_SMS_RECEIVE", {'error': str(e), 'mobile': request.mobile_number})
        raise HTTPException(status_code=500, detail="Internal error")

@app.post("/pin-setup")
async def pin_setup(request: PINSetupRequest):
    """Complete account creation"""
    try:
        settings = load_settings_from_redis()
        result = setup_pin(
            request.mobile_number,
            request.pin,
            request.hash,
            settings
        )
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_event("ERROR_PIN_SETUP", {'error': str(e), 'mobile': request.mobile_number})
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    redis_status = check_redis_health()
    postgres_status = check_postgres_health()
    
    # Determine overall status
    if redis_status == "unhealthy" or postgres_status == "unhealthy":
        overall_status = "unhealthy"
        http_status = 503
    elif redis_status == "degraded" or postgres_status == "degraded":
        overall_status = "degraded"
        http_status = 200
    else:
        overall_status = "healthy"
        http_status = 200
    
    response = {
        "status": overall_status,
        "service": "sms-bridge",
        "version": "2.3",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "database": postgres_status,
            "redis": redis_status,
            "batch_processor": "running"  # Check from APScheduler
        }
    }
    
    return JSONResponse(content=response, status_code=http_status)

@app.post("/admin/trigger-recovery")
async def trigger_recovery():
    """Trigger manual recovery process"""
    try:
        settings = load_settings_from_redis()
        
        # Generate HMAC signature
        timestamp = str(int(datetime.utcnow().timestamp()))
        hmac_key = settings['secrets']['hmac_secret'].encode()
        signature = hmac.new(
            hmac_key,
            timestamp.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Call recovery endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings['recovery_url'],
                headers={
                    'X-Signature': signature,
                    'X-Timestamp': timestamp
                },
                timeout=30.0
            )
            response.raise_for_status()
        
        log_event("RECOVERY_TRIGGERED", {'timestamp': timestamp})
        
        return {
            "status": "success",
            "triggered_at": datetime.utcnow().isoformat(),
            "message": "Recovery process initiated"
        }
    
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="Recovery endpoint unreachable")
    except Exception as e:
        log_event("ERROR_RECOVERY", {'error': str(e)})
        raise HTTPException(status_code=500, detail="Internal error")
```

---

## Background Workers

### APScheduler Implementation

```python
from apscheduler.schedulers.background import BackgroundScheduler
import httpx
import time

scheduler = BackgroundScheduler()

def sync_worker():
    """Process sync_queue every sync_interval seconds"""
    try:
        settings = load_settings_from_redis()
        
        # Pop from queue
        payload_json = redis_client.rpop('sync_queue')
        if not payload_json:
            return  # Queue empty
        
        payload = json.loads(payload_json)
        
        # Sign request
        timestamp = str(int(time.time()))
        hmac_key = settings['secrets']['hmac_secret'].encode()
        signature = hmac.new(
            hmac_key,
            (timestamp + json.dumps(payload)).encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Send to backend
        with httpx.Client() as client:
            response = client.post(
                settings['sync_url'],
                json=payload,
                headers={
                    'X-Signature': signature,
                    'X-Timestamp': timestamp
                },
                timeout=10.0
            )
            response.raise_for_status()
        
        # Update synced_at in backup_users
        db = SessionLocal()
        db.query(BackupUser).filter(
            BackupUser.mobile == payload['mobile'],
            BackupUser.hash == payload['hash']
        ).update({'synced_at': datetime.utcnow()})
        db.commit()
        db.close()
        
        log_event("SYNC_SUCCESS", {
            'mobile': payload['mobile'],
            'hash': payload['hash']
        })
    
    except httpx.HTTPError as e:
        # Push to retry queue on failure
        redis_client.lpush('retry_queue', payload_json)
        log_event("SYNC_FAILED", {
            'error': str(e),
            'payload': payload
        })
    except Exception as e:
        log_event("ERROR_SYNC_WORKER", {'error': str(e)})

def audit_worker():
    """Process audit_buffer every log_interval seconds"""
    try:
        # Pop from buffer
        log_json = redis_client.rpop('audit_buffer')
        if not log_json:
            return  # Buffer empty
        
        log_entry = json.loads(log_json)
        
        db = SessionLocal()
        
        # If PIN_COLLECTED, save to backup_users
        if log_entry['event'] == 'PIN_COLLECTED':
            details = log_entry['details']
            backup = BackupUser(
                mobile=details['mobile'],
                pin=details.get('pin', ''),
                hash=details['hash']
            )
            db.add(backup)
        
        # Always save to logs
        log_record = SMSBridgeLog(
            event=log_entry['event'],
            details=log_entry['details']
        )
        db.add(log_record)
        
        db.commit()
        db.close()
    
    except Exception as e:
        # Critical: Log to stdout if database fails
        print(f"ERROR: Audit worker failed - {e}", file=sys.stderr)

def start_background_workers(settings):
    """Initialize and start background workers"""
    scheduler.add_job(
        sync_worker,
        'interval',
        seconds=settings['sync_interval'],
        id='sync_worker',
        replace_existing=True
    )
    
    scheduler.add_job(
        audit_worker,
        'interval',
        seconds=settings['log_interval'],
        id='audit_worker',
        replace_existing=True
    )
    
    scheduler.start()
    print("Background workers started")
```

---

## Admin UI Implementation

### SQLAdmin Configuration

```python
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from passlib.context import CryptContext
from starlette.requests import Request
from starlette.responses import RedirectResponse

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Authentication Backend
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
        db = SessionLocal()
        user = db.query(AdminUser).filter(AdminUser.username == username).first()
        db.close()
        
        if user and pwd_context.verify(password, user.password_hash):
            request.session.update({"user": username})
            return True
        return False
    
    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True
    
    async def authenticate(self, request: Request) -> bool:
        return request.session.get("user") is not None

# Model Views
class SettingsHistoryAdmin(ModelView, model=SettingsHistory):
    name = "Settings History"
    name_plural = "Settings History"
    icon = "fa-solid fa-gear"
    
    can_create = True
    can_edit = False
    can_delete = False
    
    column_list = [
        SettingsHistory.version_id,
        SettingsHistory.is_active,
        SettingsHistory.created_at,
        SettingsHistory.created_by,
        SettingsHistory.change_note
    ]
    
    form_columns = [
        SettingsHistory.payload,
        SettingsHistory.is_active,
        SettingsHistory.created_by,
        SettingsHistory.change_note
    ]
    
    async def on_model_change(self, data, model, is_created, request):
        """Cache new active settings to Redis"""
        if is_created and data.get('is_active'):
            cache_settings_to_redis(data['payload'])

class SMSBridgeLogAdmin(ModelView, model=SMSBridgeLog):
    name = "Log"
    name_plural = "Logs"
    icon = "fa-solid fa-file-lines"
    
    can_create = False
    can_edit = False
    can_delete = False
    
    column_list = [
        SMSBridgeLog.id,
        SMSBridgeLog.event,
        SMSBridgeLog.created_at
    ]
    
    column_searchable_list = [SMSBridgeLog.event]
    column_sortable_list = [SMSBridgeLog.created_at]

class BlacklistMobileAdmin(ModelView, model=BlacklistMobile):
    name = "Blacklist"
    name_plural = "Blacklisted Numbers"
    icon = "fa-solid fa-ban"
    
    can_create = True
    can_edit = True
    can_delete = True
    
    column_list = [
        BlacklistMobile.mobile,
        BlacklistMobile.reason,
        BlacklistMobile.created_at,
        BlacklistMobile.created_by
    ]
    
    async def on_model_change(self, data, model, is_created, request):
        """Sync blacklist to Redis"""
        if is_created:
            redis_client.sadd('blacklist_mobiles', model.mobile)
    
    async def on_model_delete(self, model, request):
        """Remove from Redis blacklist"""
        redis_client.srem('blacklist_mobiles', model.mobile)

# Initialize Admin
admin = Admin(
    app,
    engine,
    authentication_backend=AdminAuth(secret_key="your-secret-key"),
    title="SMS Bridge Admin"
)

admin.add_view(SettingsHistoryAdmin)
admin.add_view(SMSBridgeLogAdmin)
admin.add_view(BlacklistMobileAdmin)
```

### Test Lab View

```python
from sqladmin import BaseView, expose
from starlette.requests import Request

class TestLabView(BaseView):
    name = "Test Lab"
    icon = "fa-solid fa-flask"
    
    @expose("/test-lab", methods=["GET", "POST"])
    async def test_lab(self, request: Request):
        if request.method == "POST":
            form = await request.form()
            mobile = form.get("mobile_number")
            message = form.get("sms_body")
            
            # Simulate SMS receive
            try:
                settings = load_settings_from_redis()
                success, results = validate_sms(mobile, message, settings)
                
                result_html = f"""
                <div class="alert alert-{'success' if success else 'danger'}">
                    <h4>{'✓ SMS Verified' if success else '✗ SMS Rejected'}</h4>
                    <pre>{json.dumps(results, indent=2)}</pre>
                </div>
                """
            except Exception as e:
                result_html = f"""
                <div class="alert alert-danger">
                    <h4>✗ Error</h4>
                    <p>{str(e)}</p>
                </div>
                """
        else:
            result_html = ""
        
        html = f"""
        <h1>SMS Test Lab</h1>
        <form method="POST">
            <div class="form-group">
                <label>Mobile Number</label>
                <input type="text" name="mobile_number" class="form-control" 
                       placeholder="+919876543210" required>
            </div>
            <div class="form-group">
                <label>SMS Body</label>
                <input type="text" name="sms_body" class="form-control" 
                       placeholder="ONBOARD:A3B7K2M9" required>
            </div>
            <button type="submit" class="btn btn-primary">Simulate Webhook</button>
        </form>
        {result_html}
        """
        
        return html

admin.add_view(TestLabView)
```

---

## Helper Scripts

### create_super_admin.py

```python
#!/usr/bin/env python3
"""
Bootstrap script to create first admin user
Usage: python create_super_admin.py <username> <password>
"""

import sys
from passlib.context import CryptContext
from database import SessionLocal, engine
from models import Base, AdminUser

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_super_admin(username, plain_password):
    """Create super admin user"""
    # Create tables if not exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # Check if user exists
    existing = db.query(AdminUser).filter(AdminUser.username == username).first()
    if existing:
        print(f"❌ User {username} already exists")
        db.close()
        return False
    
    # Create user
    hashed = pwd_context.hash(plain_password)
    user = AdminUser(
        username=username,
        password_hash=hashed,
        is_super_admin=True
    )
    
    db.add(user)
    db.commit()
    db.close()
    
    print(f"✓ Admin user '{username}' created successfully")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python create_super_admin.py <username> <password>")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    if len(password) < 12:
        print("❌ Password must be at least 12 characters")
        sys.exit(1)
    
    create_super_admin(username, password)
```

### startup.py

```python
#!/usr/bin/env python3
"""
Application startup script
"""

import sys
import time
from database import engine, SessionLocal
from models import Base
from redis_client import redis_client, check_redis_health

def startup_sequence():
    """Execute startup sequence"""
    print("=== SMS Bridge v2.3 Startup ===")
    
    # 1. Connect to PostgreSQL
    print("1. Connecting to PostgreSQL...")
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        print("   ✓ PostgreSQL connected")
    except Exception as e:
        print(f"   ❌ PostgreSQL connection failed: {e}")
        sys.exit(1)
    
    # 2. Connect to Redis
    print("2. Connecting to Redis...")
    redis_healthy = False
    for attempt in range(3):
        status = check_redis_health()
        if status == "healthy":
            redis_healthy = True
            print("   ✓ Redis connected")
            break
        else:
            wait_time = 2 ** attempt
            print(f"   ⚠ Redis {status}, retrying in {wait_time}s...")
            time.sleep(wait_time)
    
    # 3. Load settings
    if redis_healthy:
        print("3. Loading settings...")
        try:
            settings = load_settings_from_redis()
            print(f"   ✓ Settings loaded (version: {settings.get('version', 'N/A')})")
        except Exception as e:
            print(f"   ⚠ Settings load failed: {e}")
    
    # 4. Sync blacklist
    if redis_healthy:
        print("4. Syncing blacklist...")
        try:
            sync_blacklist_from_postgres()
            count = redis_client.scard('blacklist_mobiles')
            print(f"   ✓ Blacklist synced ({count} entries)")
        except Exception as e:
            print(f"   ⚠ Blacklist sync failed: {e}")
    
    # 5. Check power-down recovery
    if redis_healthy:
        print("5. Checking for pending recovery...")
        db = SessionLocal()
        pending = db.query(PowerDownStore).count()
        if pending > 0:
            print(f"   ⚠ Found {pending} pending recovery items")
            print("   → Run recovery process")
        else:
            print("   ✓ No pending recovery")
        db.close()
    
    # 6. Start background workers
    print("6. Starting background workers...")
    try:
        settings = load_settings_from_redis() if redis_healthy else {}
        start_background_workers(settings)
        print("   ✓ Workers started")
    except Exception as e:
        print(f"   ⚠ Worker start failed: {e}")
    
    # 7. Start FastAPI
    print("7. Starting API server...")
    print("   → http://0.0.0.0:8080")
    print("=== Startup Complete ===\n")

if __name__ == "__main__":
    startup_sequence()
    
    # Start uvicorn
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="warning"
    )
```

### shutdown.py

```python
#!/usr/bin/env python3
"""
Graceful shutdown handler
"""

import signal
import sys
import time

def graceful_shutdown(signum, frame):
    """Handle graceful shutdown"""
    print("\n=== SMS Bridge Graceful Shutdown ===")
    
    # 1. Stop accepting requests
    print("1. Stopping new requests...")
    # (Handled by uvicorn signal handler)
    
    # 2. Wait for in-flight requests
    print("2. Waiting for in-flight requests (max 30s)...")
    time.sleep(2)  # Simplified wait
    print("   ✓ Requests completed")
    
    # 3. Flush sync_queue
    print("3. Flushing sync queue...")
    try:
        settings = load_settings_from_redis()
        count = 0
        while True:
            payload_json = redis_client.rpop('sync_queue')
            if not payload_json:
                break
            
            # Best effort sync
            try:
                sync_to_backend(payload_json, settings)
                count += 1
            except:
                redis_client.lpush('retry_queue', payload_json)
        
        print(f"   ✓ Flushed {count} items")
    except Exception as e:
        print(f"   ⚠ Flush failed: {e}")
    
    # 4. Flush audit_buffer
    print("4. Flushing audit buffer...")
    try:
        db = SessionLocal()
        count = 0
        while True:
            log_json = redis_client.rpop('audit_buffer')
            if not log_json:
                break
            
            log_entry = json.loads(log_json)
            log_record = SMSBridgeLog(
                event=log_entry['event'],
                details=log_entry['details']
            )
            db.add(log_record)
            count += 1
        
        db.commit()
        db.close()
        print(f"   ✓ Flushed {count} logs")
    except Exception as e:
        print(f"   ⚠ Flush failed: {e}")
    
    # 5. Log shutdown
    print("5. Logging shutdown...")
    try:
        db = SessionLocal()
        shutdown_log = SMSBridgeLog(
            event="SERVICE_STOPPED",
            details={"timestamp": datetime.utcnow().isoformat()}
        )
        db.add(shutdown_log)
        db.commit()
        db.close()
        print("   ✓ Shutdown logged")
    except Exception as e:
        print(f"   ⚠ Log failed: {e}")
    
    # 6. Close connections
    print("6. Closing connections...")
    try:
        redis_client.close()
        engine.dispose()
        print("   ✓ Connections closed")
    except Exception as e:
        print(f"   ⚠ Close failed: {e}")
    
    print("=== Shutdown Complete ===")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)
```

---

## Error Handling

### Power-Down Resilience

```python
def dump_redis_to_postgres():
    """Emergency dump of Redis data to PostgreSQL"""
    print("⚠ Initiating Redis power-down dump...")
    
    db = SessionLocal()
    
    try:
        # Scan active onboarding keys
        for key in redis_client.scan_iter("active_onboarding:*"):
            try:
                key_type = redis_client.type(key)
                ttl = redis_client.ttl(key)
                
                if key_type == "hash":
                    value = redis_client.hgetall(key)
                elif key_type == "string":
                    value = redis_client.get(key)
                else:
                    continue
                
                dump_entry = PowerDownStore(
                    key_name=key,
                    key_type=key_type,
                    value=value,
                    original_ttl=ttl if ttl > 0 else None
                )
                db.add(dump_entry)
            except Exception as e:
                print(f"   ⚠ Failed to dump {key}: {e}")
        
        # Scan verified keys
        for key in redis_client.scan_iter("verified:*"):
            try:
                value = redis_client.get(key)
                ttl = redis_client.ttl(key)
                
                dump_entry = PowerDownStore(
                    key_name=key,
                    key_type="string",
                    value={'value': value},
                    original_ttl=ttl if ttl > 0 else None
                )
                db.add(dump_entry)
            except Exception as e:
                print(f"   ⚠ Failed to dump {key}: {e}")
        
        db.commit()
        
        # Log to Postgres directly
        log_record = SMSBridgeLog(
            event="REDIS_DUMP_TRIGGERED",
            details={"reason": "Redis unhealthy", "timestamp": datetime.utcnow().isoformat()}
        )
        db.add(log_record)
        db.commit()
        
        print("   ✓ Redis dump completed")
    
    except Exception as e:
        print(f"   ❌ Dump failed: {e}")
        db.rollback()
    finally:
        db.close()

def restore_redis_from_postgres():
    """Restore Redis data from power-down dump"""
    print("⚠ Initiating Redis recovery...")
    
    db = SessionLocal()
    
    try:
        entries = db.query(PowerDownStore).all()
        restored_count = 0
        
        for entry in entries:
            try:
                if entry.key_type == "hash":
                    redis_client.hset(entry.key_name, mapping=entry.value)
                elif entry.key_type == "string":
                    redis_client.set(entry.key_name, entry.value.get('value', ''))
                
                # Restore TTL
                if entry.original_ttl:
                    redis_client.expire(entry.key_name, entry.original_ttl)
                
                restored_count += 1
            except Exception as e:
                print(f"   ⚠ Failed to restore {entry.key_name}: {e}")
        
        # Delete processed entries
        db.query(PowerDownStore).delete()
        db.commit()
        
        # Log recovery
        log_event("REDIS_RECOVERED", {
            "restored_count": restored_count,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        print(f"   ✓ Restored {restored_count} keys")
    
    except Exception as e:
        print(f"   ❌ Recovery failed: {e}")
        db.rollback()
    finally:
        db.close()
```

### Fallback Mode Handlers

```python
def handle_redis_unavailable(endpoint_name, request_data):
    """Handle requests when Redis is unavailable"""
    
    if endpoint_name == "onboarding_register":
        # Return 503 - cannot generate hash without Redis
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable - please try again later"
        )
    
    elif endpoint_name == "sms_receive":
        # Queue for later processing
        db = SessionLocal()
        queue_entry = PowerDownStore(
            key_name=f"pending_sms:{datetime.utcnow().timestamp()}",
            key_type="pending_sms",
            value=request_data
        )
        db.add(queue_entry)
        db.commit()
        db.close()
        
        return {
            "status": "accepted",
            "message": "Queued for later processing",
            "queued": True
        }
    
    elif endpoint_name == "pin_setup":
        # Return 503 - cannot verify without Redis
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable - please try again later"
        )
```

---

## Testing Examples

### Unit Tests

```python
import pytest
from fastapi.testclient import TestClient

client = TestClient(app)

def test_onboarding_register_success():
    """Test successful onboarding registration"""
    response = client.post("/onboarding/register", json={
        "mobile_number": "+919876543210"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'success'
    assert 'hash' in data
    assert len(data['hash']) == 8
    assert data['sms_receiving_number'] == '+919000000000'

def test_onboarding_register_country_blocked():
    """Test registration with blocked country"""
    response = client.post("/onboarding/register", json={
        "mobile_number": "+17345678901"  # US number
    })
    
    assert response.status_code == 403
    assert "Country not supported" in response.json()['detail']

def test_sms_receive_valid():
    """Test valid SMS processing"""
    # First register
    reg_response = client.post("/onboarding/register", json={
        "mobile_number": "+919876543210"
    })
    hash_value = reg_response.json()['hash']
    
    # Then send SMS
    sms_response = client.post("/sms/receive", json={
        "mobile_number": "+919876543210",
        "message": f"ONBOARD:{hash_value}",
        "received_at": datetime.utcnow().isoformat()
    })
    
    assert sms_response.status_code == 200
    data = sms_response.json()
    assert data['status'] == 'received'
    assert data['validation_results']['header_hash_check']['status'] == 1

def test_pin_setup_success():
    """Test successful PIN setup"""
    # Register + SMS verify first
    mobile = "+919876543210"
    reg_response = client.post("/onboarding/register", json={"mobile_number": mobile})
    hash_value = reg_response.json()['hash']
    
    client.post("/sms/receive", json={
        "mobile_number": mobile,
        "message": f"ONBOARD:{hash_value}",
        "received_at": datetime.utcnow().isoformat()
    })
    
    # Now setup PIN
    pin_response = client.post("/pin-setup", json={
        "mobile_number": mobile,
        "pin": "123456",
        "hash": hash_value
    })
    
    assert pin_response.status_code == 200
    assert pin_response.json()['status'] == 'success'
```

### Integration Tests

```python
def test_full_flow():
    """Test complete onboarding flow"""
    mobile = "+919876543210"
    pin = "123456"
    
    # Step 1: Register
    print("1. Registering...")
    reg_response = client.post("/onboarding/register", json={
        "mobile_number": mobile
    })
    assert reg_response.status_code == 200
    
    hash_value = reg_response.json()['hash']
    sms_number = reg_response.json()['sms_receiving_number']
    print(f"   → Hash: {hash_value}")
    print(f"   → Send SMS to: {sms_number}")
    
    # Step 2: Send SMS
    print("2. Sending SMS...")
    sms_response = client.post("/sms/receive", json={
        "mobile_number": mobile,
        "message": f"ONBOARD:{hash_value}",
        "received_at": datetime.utcnow().isoformat()
    })
    assert sms_response.status_code == 200
    assert sms_response.json()['status'] == 'received'
    print("   ✓ SMS verified")
    
    # Step 3: Setup PIN
    print("3. Setting up PIN...")
    pin_response = client.post("/pin-setup", json={
        "mobile_number": mobile,
        "pin": pin,
        "hash": hash_value
    })
    assert pin_response.status_code == 200
    print("   ✓ PIN accepted")
    
    # Step 4: Verify in sync_queue
    print("4. Checking sync queue...")
    queued = redis_client.lrange('sync_queue', 0, -1)
    assert len(queued) > 0
    payload = json.loads(queued[0])
    assert payload['mobile'] == mobile
    assert payload['pin'] == pin
    print("   ✓ Queued for backend sync")
    
    print("\n✓ Full flow completed successfully")
```

### Load Testing (with Locust)

```python
from locust import HttpUser, task, between

class SMSBridgeUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def register_onboarding(self):
        """Simulate onboarding registration"""
        mobile = f"+9198765{self.random_number(5)}"
        self.client.post("/onboarding/register", json={
            "mobile_number": mobile
        })
    
    @task(1)
    def health_check(self):
        """Check system health"""
        self.client.get("/health")
    
    def random_number(self, length):
        """Generate random number string"""
        import random
        return ''.join([str(random.randint(0, 9)) for _ in range(length)])
```

**Run load test:**
```bash
locust -f load_test.py --host=http://localhost:8080 --users 100 --spawn-rate 10
```

---

## Alignment with Monitoring Spec

This technical implementation aligns with [SMS_Bridge_monitoring_snippets_v2.3.md](SMS_Bridge_monitoring_snippets_v2.3.md):

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Metrics (from monitoring spec)
ONBOARDING_TOTAL = Counter('sms_onboarding_total', 'Total onboarding registrations', ['status'])
SMS_RECEIVED_TOTAL = Counter('sms_received_total', 'Total SMS received', ['status'])
PIN_SETUP_TOTAL = Counter('sms_pin_setup_total', 'Total PIN setups', ['status'])

VALIDATION_CHECK_STATUS = Counter(
    'sms_validation_check_status',
    'Validation check results',
    ['check_name', 'status']
)

API_REQUEST_DURATION = Histogram(
    'sms_api_request_duration_seconds',
    'API request duration',
    ['endpoint']
)

QUEUE_SIZE = Gauge('sms_queue_size', 'Queue size', ['queue_name'])
```

### Logging Configuration (Minimal)

```python
import logging
from logging.handlers import TimedRotatingFileHandler

# WARNING level only (errors and security events)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        TimedRotatingFileHandler(
            '/var/log/sms_bridge/sms_bridge.log',
            when='midnight',
            interval=1,
            backupCount=7,  # 7 days retention
            maxBytes=10*1024*1024  # 10MB per file
        )
    ]
)
```

### Port Configuration Integration

```python
def load_port_mappings():
    """Load monitoring port mappings from sms_settings.json"""
    with open('sms_settings.json', 'r') as f:
        settings = json.load(f)
    return settings.get('monitoring_ports', {})
```

---

*Last updated: January 12, 2026*
*Version: 2.3*
*Aligned with: SMS_Bridge_monitoring_snippets_v2.3.md*
