-- 1. input_sms
CREATE TABLE IF NOT EXISTS input_sms (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_number VARCHAR(15) NOT NULL,
    sms_message TEXT NOT NULL,
    received_timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for input_sms (create only if they don't exist)
CREATE INDEX IF NOT EXISTS idx_uuid_btree ON input_sms (uuid);
CREATE INDEX IF NOT EXISTS idx_received_timestamp ON input_sms (received_timestamp);
CREATE INDEX IF NOT EXISTS idx_created_at ON input_sms (created_at);

-- 2. sms_monitor
CREATE TABLE IF NOT EXISTS sms_monitor (
    uuid UUID PRIMARY KEY REFERENCES input_sms(uuid),
    blacklist_check INTEGER DEFAULT 0,
    duplicate_check INTEGER DEFAULT 0,
    header_hash_check INTEGER DEFAULT 0,
    mobile_check INTEGER DEFAULT 0,
    time_window_check INTEGER DEFAULT 0,
    overall_status VARCHAR(20) DEFAULT 'pending',
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    failed_at_check VARCHAR(20),
    batch_id UUID,
    retry_count INTEGER DEFAULT 0
);

-- Indexes for sms_monitor (create only if they don't exist)
CREATE INDEX IF NOT EXISTS idx_overall_status ON sms_monitor (overall_status);
CREATE INDEX IF NOT EXISTS idx_batch_id ON sms_monitor (batch_id);
CREATE INDEX IF NOT EXISTS idx_processing_started ON sms_monitor (processing_started_at);

-- 3. system_settings
CREATE TABLE IF NOT EXISTS system_settings (
    setting_key VARCHAR(50) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default settings only if they don't exist
INSERT INTO system_settings (setting_key, setting_value) 
SELECT setting_key, setting_value FROM (VALUES
    ('batch_size', '20'),
    ('blacklist_threshold', '10'),
    ('last_processed_uuid', '00000000-0000-0000-0000-000000000000'),
    ('check_sequence', '["blacklist", "duplicate", "foreign_number", "header_hash", "mobile", "time_window"]'),
    ('check_enabled', '{"blacklist":true, "duplicate":true, "foreign_number":true, "header_hash":true, "mobile":true, "time_window":true}'),
    ('validation_time_window', '3600'),
    ('out_sms_cache_ttl', '604800'),
    ('max_database_retries', '3'),
    ('log_level', 'INFO'),
    ('parallel_workers', '1'),
    ('maintenance_mode', 'false'),
    ('pgbouncer_pool_size', '10'),
    ('redis_host', 'localhost'),
    ('redis_port', '6379')
) AS new_settings(setting_key, setting_value)
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE system_settings.setting_key = new_settings.setting_key
);

-- 4. out_sms
CREATE TABLE IF NOT EXISTS out_sms (
    uuid UUID PRIMARY KEY REFERENCES input_sms(uuid),
    sender_number VARCHAR(15) NOT NULL,
    sms_message TEXT NOT NULL,
    validation_status VARCHAR(20) DEFAULT 'valid',
    forwarded_timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for out_sms (create only if they don't exist)
CREATE INDEX IF NOT EXISTS idx_sender_number ON out_sms (sender_number);
CREATE INDEX IF NOT EXISTS idx_forwarded_timestamp ON out_sms (forwarded_timestamp);

-- 5. blacklist_sms
CREATE TABLE IF NOT EXISTS blacklist_sms (
    sender_number VARCHAR(15) PRIMARY KEY,
    blacklisted_at TIMESTAMPTZ DEFAULT NOW(),
    reason VARCHAR(100) DEFAULT 'threshold_exceeded',
    message_count INTEGER DEFAULT 0
);

-- 6. count_sms
CREATE TABLE IF NOT EXISTS count_sms (
    sender_number VARCHAR(15) PRIMARY KEY,
    message_count INTEGER DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for count_sms (create only if they don't exist)
CREATE INDEX IF NOT EXISTS idx_message_count ON count_sms (message_count);
CREATE INDEX IF NOT EXISTS idx_last_updated ON count_sms (last_updated);

-- 7. onboarding_mobile table for mobile number validation
CREATE TABLE IF NOT EXISTS onboarding_mobile (
    mobile_number VARCHAR(15) PRIMARY KEY,
    hash VARCHAR(64) NOT NULL,
    salt VARCHAR(32) NOT NULL,
    request_timestamp TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for onboarding_mobile
CREATE INDEX IF NOT EXISTS idx_onboarding_hash ON onboarding_mobile (hash);
CREATE INDEX IF NOT EXISTS idx_onboarding_request_timestamp ON onboarding_mobile (request_timestamp);
CREATE INDEX IF NOT EXISTS idx_onboarding_is_active ON onboarding_mobile (is_active);

-- Add new system settings for onboarding functionality
INSERT INTO system_settings (setting_key, setting_value) 
SELECT setting_key, setting_value FROM (VALUES
    ('allowed_country_codes', '["91", "1", "44", "61", "33", "49"]'),
    ('hash_salt_length', '16'),
    ('onboarding_expiry_hours', '24'),
    ('foreign_number_validation', 'true')
) AS new_settings(setting_key, setting_value)
WHERE NOT EXISTS (
    SELECT 1 FROM system_settings WHERE system_settings.setting_key = new_settings.setting_key
);

-- Update sms_monitor table to include new columns and remove obsolete ones
ALTER TABLE sms_monitor ADD COLUMN IF NOT EXISTS foreign_number_check INTEGER DEFAULT 0;
ALTER TABLE sms_monitor ADD COLUMN IF NOT EXISTS header_hash_check INTEGER DEFAULT 0;
ALTER TABLE sms_monitor DROP COLUMN IF EXISTS header_check;
ALTER TABLE sms_monitor DROP COLUMN IF EXISTS hash_length_check;

-- Add country code and local mobile columns for better data organization
ALTER TABLE input_sms ADD COLUMN IF NOT EXISTS country_code VARCHAR(5);
ALTER TABLE input_sms ADD COLUMN IF NOT EXISTS local_mobile VARCHAR(15);
ALTER TABLE sms_monitor ADD COLUMN IF NOT EXISTS country_code VARCHAR(5);
ALTER TABLE sms_monitor ADD COLUMN IF NOT EXISTS local_mobile VARCHAR(15);
ALTER TABLE out_sms ADD COLUMN IF NOT EXISTS country_code VARCHAR(5);
ALTER TABLE out_sms ADD COLUMN IF NOT EXISTS local_mobile VARCHAR(15);
ALTER TABLE blacklist_sms ADD COLUMN IF NOT EXISTS country_code VARCHAR(5);
ALTER TABLE blacklist_sms ADD COLUMN IF NOT EXISTS local_mobile VARCHAR(15);
ALTER TABLE count_sms ADD COLUMN IF NOT EXISTS country_code VARCHAR(5);
ALTER TABLE count_sms ADD COLUMN IF NOT EXISTS local_mobile VARCHAR(15);

-- Create indexes for the new columns
CREATE INDEX IF NOT EXISTS idx_input_sms_country_code ON input_sms (country_code);
CREATE INDEX IF NOT EXISTS idx_input_sms_local_mobile ON input_sms (local_mobile);
CREATE INDEX IF NOT EXISTS idx_sms_monitor_country_code ON sms_monitor (country_code);
CREATE INDEX IF NOT EXISTS idx_sms_monitor_local_mobile ON sms_monitor (local_mobile);
CREATE INDEX IF NOT EXISTS idx_out_sms_country_code ON out_sms (country_code);
CREATE INDEX IF NOT EXISTS idx_out_sms_local_mobile ON out_sms (local_mobile);
CREATE INDEX IF NOT EXISTS idx_blacklist_country_mobile ON blacklist_sms (country_code, local_mobile);
CREATE INDEX IF NOT EXISTS idx_count_country_mobile ON count_sms (country_code, local_mobile);

-- Update check_sequence and check_enabled settings to reflect consolidated checks
UPDATE system_settings 
SET setting_value = '["blacklist", "duplicate", "foreign_number", "header_hash", "mobile", "time_window"]'
WHERE setting_key = 'check_sequence';

UPDATE system_settings 
SET setting_value = '{"blacklist":true, "duplicate":true, "foreign_number":true, "header_hash":true, "mobile":true, "time_window":true}'
WHERE setting_key = 'check_enabled';