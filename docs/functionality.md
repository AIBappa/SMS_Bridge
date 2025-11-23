# SMS Bridge System - Production_2 Complete Functionality Documentation

This document provides comprehensive documentation for the SMS Bridge Production_2 system, including Redis-first architecture, minimal PostgreSQL usage, configurable validation pipeline, dual-sync strategy, and admin UI for settings management.

## System Overview - Production_2 Architecture

The SMS Bridge Production_2 is a **Redis-first, high-performance SMS validation system** designed to minimize PostgreSQL dependency while providing fast user experience, reliable backup, and comprehensive audit trails. The system processes SMS onboarding requests and validation messages entirely in Redis, with periodic batch dumps to PostgreSQL for persistence and remote Supabase sync for validated mobiles only.

### Core Design Principles
1. **Redis-First Hot Path**: All validations execute against Redis data structures (O(1) lookups)
2. **Minimal PostgreSQL**: Only 6 tables for configuration, audit, and backup (no hot path queries)
3. **Dual TTL Strategy**: 24-hour Redis retention (TTL) with 5-minute user deadline (X)
4. **Clubbed Writes**: Batch dumps every 120s (local) and 10s (Hetzner validated only)
5. **Power-Down Resilience**: Automatic fallback to PostgreSQL during Redis failures

### Core Architecture Components
- **FastAPI Server**: Multi-format request handling (JSON/form-encoded) with Redis-first processing
- **Redis Queue System**: Three primary queues (Queue_onboarding_mobile, Queue_input_sms, Queue_validated_mobiles)
- **Sequential Validation Pipeline**: 6 configurable checks (all Redis-based, no PostgreSQL in hot path)
- **Onboarding System**: POST-based registration with email, device_id, and hash generation
- **Dual Sync Strategy**: 10-second Hetzner sync (validated only), 120-second local sync (all data)
- **Admin UI**: FastAPI-based settings management for runtime configuration
- **Power-Down Store**: Automatic PostgreSQL fallback during Redis downtime


## Redis Data Structures (Primary Data Store)

### Queue Tables (HASHes)
1. **queue_onboarding:{mobile}** - Onboarding request data
   - Fields: mobile_number, email, device_id, hash, salt, country_code, local_mobile, request_timestamp, user_deadline, expires_at
   - TTL: 86400 seconds (24 hours) - configurable via `onboarding_ttl_seconds`
   - Purpose: Store onboarding requests pending SMS validation

2. **queue_input_sms:{id}** - Incoming SMS with validation results
   - Fields: id, mobile_number, device_id, sms_message, received_timestamp, country_code, local_mobile, mobile_check, duplicate_check, header_hash_check, count_check, foreign_number_check, blacklist_check, time_window_check, validation_status, failed_at_check
   - TTL: None (persisted until batch dump)
   - Purpose: Store all incoming SMS with sequential check results

### Quick Lookup Keys
3. **onboard_hash:{mobile}** - STRING mapping mobile to hash
   - Value: Generated SHA-256 hash
   - TTL: Same as queue_onboarding:{mobile}
   - Purpose: Fast hash lookup during validation

### Validation Data (SETs)
4. **Queue_validated_mobiles** - SET of validated mobile+device pairs
   - Format: "{mobile}:{device_id}"
   - TTL: None (permanent until manual removal)
   - Purpose: Duplicate detection (if combination exists, reject)

5. **blacklist_mobiles** - SET of blacklisted mobile numbers
   - Format: E.164 mobile number
   - TTL: None (loaded from PostgreSQL by background worker)
   - Purpose: Fast blacklist check

### Counters (STRINGs with INCR)
6. **sms_count:{mobile}** - INT counter for SMS per mobile
   - Value: Count of SMS in 24h window
   - TTL: 86400 seconds (24 hours)
   - Purpose: Count check validation (auto-expires after 24h)

7. **counter:queue_input_sms** - Auto-incrementing ID
   - Value: Next available ID for queue_input_sms
   - TTL: None (persisted to PostgreSQL periodically)
   - Purpose: Unique ID generation

8. **counter:queue_onboarding** - Auto-incrementing ID
   - Value: Next available ID for queue_onboarding
   - TTL: None (persisted to PostgreSQL periodically)
   - Purpose: Unique ID generation

### Settings Cache (STRINGs)
9. **setting:{key}** - Cached settings from PostgreSQL
   - Value: Setting value from sms_settings table
   - TTL: 60 seconds
   - Purpose: Performance optimization for frequent setting reads

## PostgreSQL Tables (6 Tables - Configuration, Audit, Backup Only)

### Table 1: input_sms (Audit Trail with Check Results)
```sql
CREATE TABLE input_sms (
    id SERIAL PRIMARY KEY,
    redis_id INTEGER NOT NULL,
    mobile_number VARCHAR(15) NOT NULL,
    country_code VARCHAR(5),
    local_mobile VARCHAR(15),
    sms_message TEXT NOT NULL,
    received_timestamp TIMESTAMPTZ NOT NULL,
    device_id VARCHAR(100),
    mobile_check INTEGER DEFAULT 3,
    duplicate_check INTEGER DEFAULT 3,
    header_hash_check INTEGER DEFAULT 3,
    count_check INTEGER DEFAULT 3,
    foreign_number_check INTEGER DEFAULT 3,
    blacklist_check INTEGER DEFAULT 3,
    time_window_check INTEGER DEFAULT 3,
    validation_status VARCHAR(20) DEFAULT 'pending',
    failed_at_check VARCHAR(30),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```
**Purpose**: Complete audit trail of all SMS with check results
**Check Result Values**: 1=pass, 2=fail, 3=disabled, 4=N/A
**Sync**: Batch dump every 120s from queue_input_sms (configurable)

### Table 2: onboarding_mobile (Onboarding Audit)
```sql
CREATE TABLE onboarding_mobile (
    id SERIAL PRIMARY KEY,
    mobile_number VARCHAR(15) NOT NULL,
    email VARCHAR(100),
    device_id VARCHAR(100),
    hash VARCHAR(64) NOT NULL,
    salt VARCHAR(32) NOT NULL,
    country_code VARCHAR(5),
    local_mobile VARCHAR(15),
    request_timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_deadline TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```
**Purpose**: Audit trail of onboarding requests
**Sync**: Written during onboarding POST request

### Table 3: blacklist_sms (Persistent Blacklist)
```sql
CREATE TABLE blacklist_sms (
    mobile_number VARCHAR(15) PRIMARY KEY,
    country_code VARCHAR(5),
    local_mobile VARCHAR(15),
    blacklisted_at TIMESTAMPTZ DEFAULT NOW(),
    reason VARCHAR(100) DEFAULT 'threshold_exceeded',
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```
**Purpose**: Permanent blacklist storage
**Sync**: Loaded into Redis blacklist_mobiles SET every 300s (configurable)

### Table 4: power_down_store (Redis Failure Backup)
```sql
CREATE TABLE power_down_store (
    id SERIAL PRIMARY KEY,
    mobile_number VARCHAR(15) NOT NULL,
    sms_message TEXT NOT NULL,
    received_timestamp TIMESTAMPTZ NOT NULL,
    device_id VARCHAR(100),
    stored_at TIMESTAMPTZ DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ
);
```
**Purpose**: Store incoming SMS when Redis is down
**Sync**: Processed back to Redis when Redis recovers

### Table 5: power_down_store_counters (Counter Persistence)
```sql
CREATE TABLE power_down_store_counters (
    counter_name VARCHAR(50) PRIMARY KEY,
    counter_value BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```
**Purpose**: Persist Redis counter values for recovery
**Sync**: Updated periodically during Redis operation

### Table 6: sms_settings (UI-Configurable Settings)
```sql
CREATE TABLE sms_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    setting_type VARCHAR(20) DEFAULT 'string',
    category VARCHAR(50) DEFAULT 'general',
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```
**Purpose**: Runtime configuration (all timing, thresholds, check toggles)
**Categories**: general, sync, validation, thresholds, infrastructure, monitoring
**Admin UI**: FastAPI-based UI for runtime updates (no restarts required)

### Removed Tables (No Longer Needed)
- **out_sms**: Replaced by Queue_validated_mobiles SET in Redis
- **sms_monitor**: Merged into input_sms (check result columns)
- **count_sms**: Replaced by sms_count:{mobile} counters in Redis
- **system_settings**: Replaced by sms_settings table

## File Summaries

### core/sms_server.py
FastAPI application with Production_2 endpoints and admin UI.

**Key Functions**:
- `POST /onboard/register` - Onboarding with email, device_id, dual time windows
- `POST /sms/receive` - Incoming SMS processing with sequential validation
- `GET /admin/settings/ui` - Admin UI for settings management
- `GET /admin/settings/{key}` - Get individual setting value
- `PUT /admin/settings/{key}` - Update individual setting with cache invalidation
- `GET /health` - Health check with Redis/PostgreSQL status

**Production_2 Updates**:
- POST endpoint for onboarding (was GET with path param)
- Email and device_id fields in onboarding request
- Dual time window response (user_deadline vs expires_at)
- Redis Queue_onboarding_mobile storage
- Admin UI routes for sms_settings management

### core/redis_client.py
Async Redis client with Queue management and settings cache.

**Key Functions**:
- `add_to_queue_onboarding()` - Store onboarding data with dual TTL
- `add_to_queue_input_sms()` - Store incoming SMS with check results
- `mark_mobile_validated()` - Add to Queue_validated_mobiles SET
- `get_setting_value()` - Get cached setting with 60s TTL
- `invalidate_setting_cache()` - Clear setting cache on update
- `get_next_id()` - Auto-incrementing ID generation
- `update_check_result()` - Update validation check status

**Production_2 Updates**:
- Queue management functions for Production_2 Redis schema
- Settings cache with 60s TTL for performance
- Dual TTL support (user_deadline and expires_at)

### core/background_workers.py
Async background workers for batch dumps and sync operations.

**Key Functions**:
- `dump_queue_input_sms_to_postgres()` - Batch dump to input_sms (every 120s)
- `sync_validated_mobiles_to_hetzner()` - Sync to Supabase (every 10s, validated only)
- `populate_blacklist_from_postgres()` - Load blacklist to Redis (every 300s)
- `cleanup_expired_sorted_sets()` - Remove expired sorted set entries
- `persist_counters_to_postgres()` - Backup Redis counters
- `get_setting_value()` - Helper to read dynamic settings

**Production_2 Updates**:
- All timing parameters from sms_settings (not hardcoded)
- Dual sync strategy (10s Hetzner, 120s local)
- Dynamic settings with Redis caching

### core/checks/mobile_check.py
E.164 format validation and country code extraction.

**Returns**: (status_code, country_code, local_mobile, message)
- Validates E.164 format (starts with +, 10-15 digits)
- Extracts country_code and local_mobile
- Configurable via `mobile_check_enabled` setting

### core/checks/duplicate_check.py (Production_2 Updated)
Redis-only duplicate detection using Queue_validated_mobiles SET.

**Returns**: (status_code, message)
- Checks if {mobile}:{device_id} exists in Queue_validated_mobiles SET
- NO PostgreSQL query (was querying out_sms table)
- Configurable via `duplicate_check_enabled` setting

### core/checks/header_hash_check.py
Validates "ONBOARD:" prefix and hash match against queue_onboarding:{mobile}.

**Returns**: (status_code, message)
- Checks for "ONBOARD:" header
- Validates hash against stored onboard_hash:{mobile}
- Configurable via `header_hash_check_enabled` setting

### core/checks/count_check.py (NEW - Production_2)
Redis-only SMS count validation per mobile (24h window).

**Returns**: (status_code, message)
- Increments sms_count:{mobile} counter with 24h TTL
- Checks against threshold from `count_check_threshold` setting
- NO PostgreSQL dependency (was using count_sms table)
- Configurable via `count_check_enabled` setting

### core/checks/foreign_number_check.py
Country code validation against allowed list.

**Returns**: (status_code, message)
- Validates country_code against allowed_country_codes from sms_settings
- Configurable via `foreign_number_check_enabled` setting

### core/checks/blacklist_check.py (Production_2 Updated)
Redis-only blacklist check using blacklist_mobiles SET.

**Returns**: (status_code, message)
- Checks if mobile exists in blacklist_mobiles SET
- NO PostgreSQL query (was querying blacklist_sms table)
- Blacklist loaded by background worker
- Configurable via `blacklist_check_enabled` setting

### core/checks/time_window_check.py
Validates SMS received within user_deadline.

**Returns**: (status_code, message)
- Checks received_timestamp against user_deadline from queue_onboarding
- Configurable via `time_window_check_enabled` setting

## Sequential Validation Pipeline (Redis-Only)

All checks execute in Redis following this sequence:

```
Incoming SMS → Queue_input_sms:{id}
               ↓
1. mobile_check (E.164 validation)
               ↓ (pass)
2. duplicate_check (Queue_validated_mobiles SET)
               ↓ (pass)
3. header_hash_check (ONBOARD: + hash match)
               ↓ (pass)
4. count_check (sms_count:{mobile} counter)
               ↓ (pass)
5. foreign_number_check (country code validation)
               ↓ (pass)
6. blacklist_check (blacklist_mobiles SET)
               ↓ (pass)
7. time_window_check (within user_deadline)
               ↓ (pass)
     → validation_status = "passed"
     → Add to Queue_validated_mobiles SET
     → Batch dump to input_sms (120s)
     → Sync to Hetzner (10s, validated only)
```

**Check Status Codes**:
- 1 = Pass
- 2 = Fail (stop processing, mark failed_at_check)
- 3 = Disabled (skip to next check)
- 4 = N/A (previous check failed, don't run)

**Configuration**:
- Each check can be enabled/disabled via sms_settings
- Thresholds dynamically loaded from sms_settings
- All settings cached in Redis (60s TTL) for performance

## Dual Time Window Strategy

Production_2 implements two distinct time windows:

### User Deadline (X) - 5 Minutes
- **Setting**: `user_timelimit_seconds` (default: 300)
- **Purpose**: User-facing deadline for SMS submission
- **Response Fields**: `user_deadline` (ISO timestamp), `user_timelimit_seconds` (integer)
- **Usage**: Displayed to users, enforced by time_window_check
- **Example**: "Send SMS within 5 minutes"

### Redis TTL (Audit Retention) - 24 Hours
- **Setting**: `onboarding_ttl_seconds` (default: 86400)
- **Purpose**: System-level audit retention period
- **Response Fields**: `expires_at` (ISO timestamp), `redis_ttl_seconds` (integer)
- **Usage**: Automatic Redis expiry (no worker needed)
- **Example**: Data automatically deleted after 24 hours

**Why Dual Windows?**
- User needs short deadline (urgency, security)
- System needs long retention (audit, recovery, investigation)

## Dual Sync Strategy

### Hetzner Supabase Sync (Validated Only)
- **Frequency**: Every 10 seconds (configurable via `hetzner_sync_interval_seconds`)
- **Data**: ONLY validated mobiles (validation_status='passed')
- **Source**: input_sms table WHERE validation_status='passed'
- **Purpose**: Remote backup of successful onboardings
- **Worker**: `sync_validated_mobiles_to_hetzner()`

### Local PostgreSQL Sync (All Data)
- **Frequency**: Every 120 seconds (configurable via `local_sync_interval_seconds`)
- **Data**: ALL SMS (audit trail)
- **Source**: queue_input_sms (Redis) → input_sms (PostgreSQL)
- **Purpose**: Complete audit trail, compliance, investigation
- **Worker**: `dump_queue_input_sms_to_postgres()`

**Why Dual Sync?**
- Hetzner: Minimize bandwidth/cost (validated only, frequent)
- Local: Complete audit (all data, less frequent)

## Admin UI for Settings Management

FastAPI-based web interface for runtime configuration.

### Endpoints
- **GET /admin/settings/ui** - HTML interface with category grouping
- **GET /admin/settings/{key}** - Get individual setting value
- **PUT /admin/settings/{key}** - Update setting with cache invalidation

### UI Features
- **Category Grouping**: general, sync, validation, thresholds, infrastructure, monitoring
- **Type-Based Inputs**: number (integer), checkbox (boolean), text (string), textarea (json)
- **AJAX Updates**: Real-time updates without page reload
- **Cache Invalidation**: Automatic Redis cache invalidation on update
- **No Restarts**: All settings applied dynamically

### Settings Categories

**General**:
- onboarding_ttl_seconds (24h)
- user_timelimit_seconds (5min)
- hash_salt_length (16)

**Sync**:
- hetzner_sync_interval_seconds (10s)
- local_sync_interval_seconds (120s)
- blacklist_check_interval_seconds (300s)

**Validation** (Toggles):
- mobile_check_enabled
- duplicate_check_enabled
- header_hash_check_enabled
- count_check_enabled
- foreign_number_check_enabled
- blacklist_check_enabled
- time_window_check_enabled

**Thresholds**:
- count_check_threshold (5)
- blacklist_threshold (10)

## Deployment Architecture

### Components
1. **FastAPI Server** (core/sms_server.py) - Port 8080
2. **Redis Server** - Port 6379 (localhost)
3. **PostgreSQL + PgBouncer** - Connection pooling
4. **Cloudflare Tunnel** - Public HTTPS endpoint
5. **Background Workers** - Async tasks for sync/cleanup
6. **Hetzner Supabase** - Remote backup (validated only)

### Power-Down Resilience
1. **Redis Down**:
   - Incoming SMS → power_down_store table (direct PostgreSQL write)
   - Counters restored from power_down_store_counters on recovery
   - Background worker processes power_down_store back to Redis

2. **PostgreSQL Down**:
   - Redis continues operation (hot path unaffected)
   - Batch dumps fail (logged, retried)
   - System continues processing (Redis-first design)

3. **Hetzner Down**:
   - Local processing unaffected
   - Sync failures logged, retried
   - Data in local PostgreSQL (can manual sync later)

## Performance Characteristics

### Hot Path (Redis-Only)
- **Onboarding**: < 10ms (HASH write + STRING write + TTL)
- **Validation Pipeline**: < 50ms (7 checks, all O(1) Redis operations)
- **No PostgreSQL**: Zero database queries in validation path

### Batch Operations
- **Local Dump**: 120s interval, batch size configurable
- **Hetzner Sync**: 10s interval, only validated mobiles
- **Blacklist Load**: 300s interval, full SET replacement

### Scalability
- **Redis**: Handle 10K+ req/s per core
- **PostgreSQL**: Minimal load (batch writes only)
- **PgBouncer**: Connection pooling for efficiency
- **Horizontal**: Add Redis replicas for read scaling

## Monitoring and Observability

### Health Check (GET /health)
Returns status of:
- Redis connectivity
- PostgreSQL connectivity
- Background worker status

### Metrics (Prometheus)
- Request rates per endpoint
- Validation check pass/fail rates
- Redis operation latencies
- PostgreSQL batch dump durations
- Queue sizes (queue_input_sms, Queue_validated_mobiles)

### Logging
- Structured logging with log_level from sms_settings
- Check results logged per SMS
- Background worker status updates
- Error tracking with stack traces

---

**Production_2 Architecture Benefits**:
1. **Performance**: Redis-first design eliminates PostgreSQL bottleneck
2. **Scalability**: O(1) operations, horizontal scaling ready
3. **Reliability**: Power-down resilience, dual sync strategy
4. **Auditability**: Complete audit trail in PostgreSQL
5. **Configurability**: Runtime settings via admin UI
6. **Cost-Efficiency**: Hetzner sync only validated mobiles (not all data)
