-- =====================================================
-- SMS Bridge Production_2 Schema
-- =====================================================
-- Redis-first architecture with 6 PostgreSQL tables
-- PostgreSQL used only for: audit, config, blacklist, power-down resilience
-- All validation executes in Redis

-- =====================================================
-- 1. input_sms - Audit trail with check results
-- =====================================================
CREATE TABLE IF NOT EXISTS input_sms (
    id SERIAL PRIMARY KEY,
    redis_id INTEGER NOT NULL,
    mobile_number VARCHAR(15) NOT NULL,
    country_code VARCHAR(5),
    local_mobile VARCHAR(15),
    sms_message TEXT NOT NULL,
    received_timestamp TIMESTAMPTZ NOT NULL,
    device_id VARCHAR(100),
    
    -- Check result columns (1=pass, 2=fail, 3=skipped/disabled, 4=N/A)
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

-- Indexes for input_sms
CREATE INDEX IF NOT EXISTS idx_input_redis_id ON input_sms (redis_id);
CREATE INDEX IF NOT EXISTS idx_input_mobile ON input_sms (mobile_number);
CREATE INDEX IF NOT EXISTS idx_input_validation_status ON input_sms (validation_status);
CREATE INDEX IF NOT EXISTS idx_input_received_timestamp ON input_sms (received_timestamp);
CREATE INDEX IF NOT EXISTS idx_input_country_local ON input_sms (country_code, local_mobile);

-- =====================================================
-- 2. onboarding_mobile - Onboarding audit trail
-- =====================================================
CREATE TABLE IF NOT EXISTS onboarding_mobile (
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

-- Indexes for onboarding_mobile
CREATE INDEX IF NOT EXISTS idx_onboard_mobile ON onboarding_mobile (mobile_number);
CREATE INDEX IF NOT EXISTS idx_onboard_hash ON onboarding_mobile (hash);
CREATE INDEX IF NOT EXISTS idx_onboard_request_timestamp ON onboarding_mobile (request_timestamp);
CREATE INDEX IF NOT EXISTS idx_onboard_device ON onboarding_mobile (device_id);

-- =====================================================
-- 3. blacklist_sms - Persistent blacklist
-- =====================================================
CREATE TABLE IF NOT EXISTS blacklist_sms (
    mobile_number VARCHAR(15) PRIMARY KEY,
    country_code VARCHAR(5),
    local_mobile VARCHAR(15),
    blacklisted_at TIMESTAMPTZ DEFAULT NOW(),
    reason VARCHAR(100) DEFAULT 'threshold_exceeded',
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for blacklist_sms
CREATE INDEX IF NOT EXISTS idx_blacklist_country_local ON blacklist_sms (country_code, local_mobile);
CREATE INDEX IF NOT EXISTS idx_blacklist_blacklisted_at ON blacklist_sms (blacklisted_at);

-- =====================================================
-- 4. power_down_store - Redis failure backup
-- =====================================================
CREATE TABLE IF NOT EXISTS power_down_store (
    id SERIAL PRIMARY KEY,
    mobile_number VARCHAR(15) NOT NULL,
    sms_message TEXT NOT NULL,
    received_timestamp TIMESTAMPTZ NOT NULL,
    device_id VARCHAR(100),
    stored_at TIMESTAMPTZ DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ
);

-- Indexes for power_down_store
CREATE INDEX IF NOT EXISTS idx_powerdown_processed ON power_down_store (processed);
CREATE INDEX IF NOT EXISTS idx_powerdown_stored_at ON power_down_store (stored_at);

-- =====================================================
-- 5. power_down_store_counters - Counter persistence
-- =====================================================
CREATE TABLE IF NOT EXISTS power_down_store_counters (
    counter_name VARCHAR(50) PRIMARY KEY,
    counter_value BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Initialize counters
INSERT INTO power_down_store_counters (counter_name, counter_value) 
VALUES 
    ('queue_input_sms', 0),
    ('queue_onboarding', 0)
ON CONFLICT (counter_name) DO NOTHING;

-- =====================================================
-- 6. sms_settings - UI-configurable settings
-- =====================================================
CREATE TABLE IF NOT EXISTS sms_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    setting_type VARCHAR(20) DEFAULT 'string',
    category VARCHAR(50) DEFAULT 'general',
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default settings
INSERT INTO sms_settings (setting_key, setting_value, setting_type, category, description) 
VALUES 
    -- General Settings
    ('onboarding_ttl_seconds', '86400', 'integer', 'general', 'Redis TTL for onboarding entries (24 hours)'),
    ('user_timelimit_seconds', '300', 'integer', 'general', 'User deadline for SMS submission (5 minutes)'),
    ('hash_salt_length', '16', 'integer', 'general', 'Salt length for hash generation'),
    
    -- Sync Settings
    ('hetzner_sync_interval_seconds', '10', 'integer', 'sync', 'Hetzner Supabase sync frequency (validated only)'),
    ('local_sync_interval_seconds', '120', 'integer', 'sync', 'Local PostgreSQL dump frequency (all data)'),
    ('blacklist_check_interval_seconds', '300', 'integer', 'sync', 'Blacklist reload from PostgreSQL frequency'),
    
    -- Validation Check Toggles
    ('mobile_check_enabled', 'true', 'boolean', 'validation', 'Enable mobile format validation'),
    ('duplicate_check_enabled', 'true', 'boolean', 'validation', 'Enable duplicate detection'),
    ('header_hash_check_enabled', 'true', 'boolean', 'validation', 'Enable header and hash validation'),
    ('count_check_enabled', 'true', 'boolean', 'validation', 'Enable SMS count threshold check'),
    ('foreign_number_check_enabled', 'true', 'boolean', 'validation', 'Enable foreign country code check'),
    ('blacklist_check_enabled', 'true', 'boolean', 'validation', 'Enable blacklist check'),
    ('time_window_check_enabled', 'true', 'boolean', 'validation', 'Enable time window validation'),
    
    -- Validation Thresholds
    ('count_check_threshold', '5', 'integer', 'thresholds', 'Max SMS per mobile in 24h before rejection'),
    ('blacklist_threshold', '10', 'integer', 'thresholds', 'Count to trigger permanent blacklist'),
    
    -- Country Codes
    ('allowed_country_codes', '["91", "1", "44", "61", "33", "49"]', 'json', 'validation', 'Allowed country codes for foreign number check'),
    
    -- Redis Connection
    ('redis_host', 'localhost', 'string', 'infrastructure', 'Redis server host'),
    ('redis_port', '6379', 'integer', 'infrastructure', 'Redis server port'),
    
    -- PostgreSQL Connection
    ('pgbouncer_pool_size', '10', 'integer', 'infrastructure', 'PgBouncer connection pool size'),
    
    -- Monitoring
    ('log_level', 'INFO', 'string', 'monitoring', 'Application log level (DEBUG, INFO, WARNING, ERROR)'),
    ('maintenance_mode', 'false', 'boolean', 'monitoring', 'Enable maintenance mode (reject new requests)'),
    
    -- Batch Processor Settings
    ('batch_size', '100', 'integer', 'batch', 'Number of SMS to process per batch'),
    ('batch_timeout', '2.0', 'string', 'batch', 'Timeout in seconds to wait for batch to fill'),
    ('last_processed_uuid', '00000000-0000-0000-0000-000000000000', 'string', 'batch', 'Last processed UUID for batch processor')
ON CONFLICT (setting_key) DO NOTHING;

-- =====================================================
-- DROP obsolete tables from old schema
-- =====================================================
-- These are commented out for safety - uncomment to execute
-- DROP TABLE IF EXISTS out_sms CASCADE;
-- DROP TABLE IF EXISTS sms_monitor CASCADE;
-- DROP TABLE IF EXISTS count_sms CASCADE;
-- DROP TABLE IF EXISTS system_settings CASCADE;

-- =====================================================
-- Comments for Production_2 Architecture
-- =====================================================
-- REDIS-FIRST DESIGN:
-- - All validation checks execute in Redis (no PostgreSQL in hot path)
-- - PostgreSQL used only for audit trail, configuration, and resilience
-- 
-- REDIS DATA STRUCTURES:
-- - queue_onboarding:{mobile} - HASH with onboarding data
-- - onboard_hash:{mobile} - STRING for quick lookup
-- - queue_input_sms:{id} - HASH with SMS + check results
-- - Queue_validated_mobiles - SET for duplicate check (format: {mobile}:{device_id})
-- - sms_count:{mobile} - INT counter with 24h TTL
-- - blacklist_mobiles - SET cached from PostgreSQL
-- - counter:queue_input_sms - Auto-incrementing ID
-- - counter:queue_onboarding - Auto-incrementing ID
-- - setting:{key} - Cached settings with 60s TTL
-- 
-- DUAL TIME WINDOWS:
-- - user_timelimit_seconds (X): 5 minutes - user-facing deadline
-- - onboarding_ttl_seconds (TTL): 24 hours - system audit retention
-- 
-- DUAL SYNC STRATEGY:
-- - Hetzner: Every 10s, validated mobiles ONLY
-- - Local PostgreSQL: Every 120s, ALL data (audit trail)
-- 
-- SEQUENTIAL CHECKS (Redis-only):
-- 1. mobile_check - E.164 validation
-- 2. duplicate_check - Queue_validated_mobiles SET
-- 3. header_hash_check - "ONBOARD:" prefix + hash match
-- 4. count_check - sms_count:{mobile} counter
-- 5. foreign_number_check - Country code validation
-- 6. blacklist_check - blacklist_mobiles SET
-- 7. time_window_check - Within user_deadline
-- 
-- POWER DOWN RESILIENCE:
-- - Redis down: Incoming SMS → power_down_store table
-- - Redis recovery: Restore counters from power_down_store_counters
-- - Background sync: Queue_input_sms → input_sms (periodic)
