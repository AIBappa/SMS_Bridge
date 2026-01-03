-- =====================================================
-- SMS Bridge v2.2 Schema (Aligned with Tech Spec)
-- =====================================================
-- Redis-first architecture with 6 PostgreSQL tables
-- PostgreSQL used only for: config, audit, backup, blacklist, power-down
-- All validation executes in Redis (no PostgreSQL in hot path)

-- =====================================================
-- 1. Configuration History (Append-Only)
-- =====================================================
-- Version-controlled settings with JSON payload
-- Only one row can have is_active = TRUE at any time

CREATE TABLE IF NOT EXISTS settings_history (
    version_id SERIAL PRIMARY KEY,
    payload JSONB NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(50),
    change_note TEXT
);

-- Ensure only one active config at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_settings_active 
    ON settings_history(is_active) WHERE is_active = TRUE;

-- Default settings payload (v2.2 format)
INSERT INTO settings_history (payload, is_active, created_by, change_note)
VALUES (
    '{
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
        "hmac_secret": "CHANGE_ME_IN_PRODUCTION",
        "hash_key": "CHANGE_ME_IN_PRODUCTION"
      }
    }'::jsonb,
    TRUE,
    'system',
    'Initial default settings (v2.2)'
) ON CONFLICT DO NOTHING;

-- =====================================================
-- 2. Admin Users
-- =====================================================
-- SQLAdmin authentication with BCrypt password hashes

CREATE TABLE IF NOT EXISTS admin_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_super_admin BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- 3. Logs (Append-Only)
-- =====================================================
-- Simple event logging with JSONB details
-- Events: HASH_GEN, SMS_VERIFIED, PIN_COLLECTED, RECOVERY_TRIGGERED, etc.

CREATE TABLE IF NOT EXISTS sms_bridge_logs (
    id SERIAL PRIMARY KEY,
    event VARCHAR(50) NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_event ON sms_bridge_logs(event);
CREATE INDEX IF NOT EXISTS idx_logs_created ON sms_bridge_logs(created_at);

-- =====================================================
-- 4. Backup Credentials (Hot Path Backup)
-- =====================================================
-- Stores validated {mobile, pin, hash} from audit_buffer
-- Written by Audit Worker (every log_interval seconds)
-- Does NOT block hot path (sync_queue → sync_url)

CREATE TABLE IF NOT EXISTS backup_users (
    id SERIAL PRIMARY KEY,
    mobile VARCHAR(20) NOT NULL,
    pin VARCHAR(10) NOT NULL,
    hash VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    synced_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_backup_mobile ON backup_users(mobile);

-- =====================================================
-- 5. Power-Down Store (Redis Failure Backup)
-- =====================================================
-- Stores Redis keys when Redis connection fails
-- Restored to Redis when connection recovers

CREATE TABLE IF NOT EXISTS power_down_store (
    id SERIAL PRIMARY KEY,
    key_name VARCHAR(255) NOT NULL,
    key_type VARCHAR(20) NOT NULL,  -- "hash", "string", "set", "list"
    value JSONB NOT NULL,
    original_ttl INTEGER,           -- Remaining TTL in seconds (NULL if no TTL)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_powerdown_key ON power_down_store(key_name);

-- =====================================================
-- 6. Blacklist (Persistent)
-- =====================================================
-- Loaded into Redis SET blacklist_mobiles on startup
-- Synced to Redis on Admin UI add/remove operations

CREATE TABLE IF NOT EXISTS blacklist_mobiles (
    id SERIAL PRIMARY KEY,
    mobile VARCHAR(20) UNIQUE NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_blacklist_mobile ON blacklist_mobiles(mobile);

-- =====================================================
-- ARCHITECTURE NOTES (v2.2)
-- =====================================================
-- 
-- HOT PATH (Redis only, no SQL):
--   /onboarding/register → active_onboarding:{hash} in Redis
--   /sms/receive → 4 validation checks (all Redis)
--   /pin-setup → sync_queue (Redis List)
--   Sync Worker (every sync_interval) → POST to sync_url
-- 
-- COLD PATH (Async, Non-Blocking):
--   Events → audit_buffer (Redis List)
--   Audit Worker (every log_interval) → sms_bridge_logs + backup_users
-- 
-- REDIS DATA STRUCTURES:
--   sync_queue              - List: {mobile, pin, hash} for backend sync
--   retry_queue             - List: Failed sync payloads
--   audit_buffer            - List: {event, details} for Postgres
--   active_onboarding:{hash} - Hash: {mobile, expires_at} with TTL
--   verified:{mobile}       - String: hash value (TTL 15m)
--   limit:sms:{mobile}      - String: rate limit counter (TTL 1h)
--   config:current          - String: cached JSON settings
--   blacklist_mobiles       - Set: blocked mobile numbers
-- 
-- VALIDATION CHECKS (4 checks, configurable via settings):
--   1. header_hash_check    - Prefix + hash lookup (if enabled)
--   2. foreign_number_check - Country code validation (if enabled)
--   3. count_check          - Rate limiting (if enabled)
--   4. blacklist_check      - Blocked numbers (if enabled)
-- 
-- CHECK STATUS CODES:
--   1 = Pass
--   2 = Fail
--   3 = Disabled (skipped)
-- 
-- POWER-DOWN RESILIENCE:
--   Redis failure → Dump active keys to power_down_store
--   Redis recovery → Restore from power_down_store
--   Blacklist: Postgres ↔ Redis sync on startup and admin changes
-- 
-- SETTINGS (JSON payload in settings_history):
--   sms_receiver_number    - Number user sends SMS to
--   allowed_prefix         - Expected message prefix ("ONBOARD:")
--   hash_length            - Generated hash length (default: 8)
--   ttl_hash_seconds       - Redis TTL for active_onboarding (default: 900)
--   sync_interval          - Sync worker frequency in seconds (default: 1.0)
--   log_interval           - Audit worker frequency in seconds (default: 120)
--   count_threshold        - Max SMS per mobile before rejection
--   allowed_countries      - Array of allowed country prefixes
--   sync_url               - Backend endpoint for validated data
--   recovery_url           - Backend endpoint for recovery trigger
--   checks.*_enabled       - Enable/disable individual checks
--   secrets.hmac_secret    - HMAC key for hash generation and signing
--   secrets.hash_key       - Additional key for hash generation
