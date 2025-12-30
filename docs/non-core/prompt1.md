Complete SMS Processing System Enhancement Prompt

Task: Transform the existing SMS processing system into a production-grade, high-performance batch validation pipeline with Redis deduplication, pgbouncer connection pooling, and configurable sequential validation checks.
Current System Files to Update:

    setup_sms_gateway.yml (Ansible deployment script)

    sms_server.py (Python SMS processing server)
    
New System Files:
	Files for the various checks as described below.
	Files for the database schema

Complete Database Schema
1. input_sms (Fast Insert Table)

sql
CREATE TABLE input_sms (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_number VARCHAR(15) NOT NULL,
    sms_message TEXT NOT NULL,
    received_timestamp TIMESTAMPTZ NOT NULL,    -- When SMS reached mobile device
    created_at TIMESTAMPTZ DEFAULT NOW(),       -- When inserted into DB
    INDEX idx_uuid_btree (uuid),                -- B-tree for sequential processing
    INDEX idx_received_timestamp (received_timestamp),
    INDEX idx_created_at (created_at)
);

2. sms_monitor (Processing Results Table)

sql
CREATE TABLE sms_monitor (
    uuid UUID PRIMARY KEY REFERENCES input_sms(uuid),
    
    -- Check results (0=not_done, 1=pass, 2=fail, 3=skipped)
    blacklist_check INTEGER DEFAULT 0,
    duplicate_check INTEGER DEFAULT 0,  
    header_check INTEGER DEFAULT 0,
    hash_length_check INTEGER DEFAULT 0,
    mobile_check INTEGER DEFAULT 0,
    time_window_check INTEGER DEFAULT 0,
    
    -- Processing metadata
    overall_status VARCHAR(20) DEFAULT 'pending',  -- pending, valid, invalid, skipped
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    failed_at_check VARCHAR(20),              -- Which check caused failure
    batch_id UUID,                            -- Batch tracking
    retry_count INTEGER DEFAULT 0,
    
    INDEX idx_overall_status (overall_status),
    INDEX idx_batch_id (batch_id),
    INDEX idx_processing_started (processing_started_at)
);

3. system_settings (Configuration Table)

sql
CREATE TABLE system_settings (
    setting_key VARCHAR(50) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Initial configuration
INSERT INTO system_settings (setting_key, setting_value) VALUES
('batch_size', '20'),
('blacklist_threshold', '10'),
('last_processed_uuid', '00000000-0000-0000-0000-000000000000'),
('check_sequence', '["blacklist", "duplicate", "header", "hash_length", "mobile", "time_window"]'),
('check_enabled', '{"blacklist":true, "duplicate":true, "header":true, "hash_length":true, "mobile":true, "time_window":true}'),
('validation_time_window', '3600'),
('out_sms_cache_ttl', '604800'),
('max_database_retries', '3'),
('log_level', 'INFO'),
('parallel_workers', '1'),
('maintenance_mode', 'false'),
('pgbouncer_pool_size', '10'),
('redis_host', 'localhost'),
('redis_port', '6379');

4. out_sms (Valid SMS Output)

sql
CREATE TABLE out_sms (
    uuid UUID PRIMARY KEY REFERENCES input_sms(uuid),
    sender_number VARCHAR(15) NOT NULL,
    sms_message TEXT NOT NULL,
    validation_status VARCHAR(20) DEFAULT 'valid',
    forwarded_timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    INDEX idx_sender_number (sender_number),
    INDEX idx_forwarded_timestamp (forwarded_timestamp)
);

5. blacklist_sms (Blocked Numbers)

sql
CREATE TABLE blacklist_sms (
    sender_number VARCHAR(15) PRIMARY KEY,
    blacklisted_at TIMESTAMPTZ DEFAULT NOW(),
    reason VARCHAR(100) DEFAULT 'threshold_exceeded',
    message_count INTEGER DEFAULT 0
);

6. count_sms (Message Counters)

sql
CREATE TABLE count_sms (
    sender_number VARCHAR(15) PRIMARY KEY,
    message_count INTEGER DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    INDEX idx_message_count (message_count),
    INDEX idx_last_updated (last_updated)
);

Required Features Implementation
1. Enhanced Ansible Script (setup_sms_gateway.yml)

Add these components:

pgbouncer Installation & Configuration:

    Install pgbouncer package

    Configure pgbouncer.ini with transaction pooling

    Set connection limits and pool size from system_settings

    Configure pgbouncer to run on port 6432

    Set up authentication and database routing

Database Schema Deployment:

    Create all 6 tables with proper indexes

    Insert initial system_settings values

    Set up pgbouncer user permissions

    Configure PostgreSQL for connection pooling

Redis Setup:

    Install and configure Redis

    Configure persistence and memory settings

    Set up 'out_sms_numbers' SET for deduplication

    Configure Redis authentication if needed

System Services:

    Create systemd service files for SMS server

    Configure auto-restart and logging

    Set up log rotation

    Create monitoring endpoints

2. Enhanced SMS Server (sms_server.py)

Transform into FastAPI with these features:

Fast SMS Reception Endpoint:

python
@app.post("/sms/receive")
async def receive_sms(sms_data: SMSInput):
    # Ultra-fast insert to input_sms only
    # No processing logic here - just store raw SMS data

Batch Processing Engine:

    Background async task that processes SMS batches

    Read settings from system_settings table

    Process UUIDs sequentially using last_processed_uuid checkpoint

    Update checkpoint atomically after successful batch

Sequential Validation Pipeline:

python
async def run_validation_checks(batch_sms_data):
    # Read check_sequence and check_enabled from settings
    # Execute checks in specified order with early exit
    # Update sms_monitor with individual check results
    
    checks = {
        "blacklist": validate_blacklist_check,
        "duplicate": validate_duplicate_check, 
        "header": validate_header_check,
        "hash_length": validate_hash_length_check,
        "mobile": validate_mobile_check,
        "time_window": validate_time_window_check
    }

Individual Validation Functions (Please ensure that each check is in a different file for efficient factoring):

Blacklist Check:

    Query count_sms for sender_number

    Increment message count (upsert)

    Compare against blacklist_threshold setting

    Add to blacklist_sms if threshold exceeded

    Return result code (1=pass, 2=fail)

Duplicate Check:

    Redis SISMEMBER check against 'out_sms_numbers' set

    Fast O(1) lookup for mobile number deduplication

    Return result code (1=pass, 2=fail)

Header Check:

    Validate SMS header format and structure

    Check header length and content rules

    Return result code (1=pass, 2=fail, 3=skipped)

Hash Length Check:

    Validate message content hash/length requirements

    Check encryption/encoding format compliance

    Return result code (1=pass, 2=fail, 3=skipped)

Mobile Check:

    Extract and validate mobile number from message content

    Decrypt/decode mobile number if encrypted

    Verify mobile number format and validity

    Return result code (1=pass, 2=fail, 3=skipped)

Time Window Check:

    Compare received_timestamp vs current time

    Validate within validation_time_window setting

    Check for timestamp tampering or delays

    Return result code (1=pass, 2=fail, 3=skipped)

Connection Management:

    Use pgbouncer connection (port 6432) instead of direct PostgreSQL

    Implement retry logic with max_database_retries setting

    Use async connection pooling for all database operations

Redis Cache Management:

    Cache warmup: bulk load existing out_sms numbers on startup

    Write-through cache: SADD to Redis when inserting valid SMS

    Health check: verify Redis connectivity and cache consistency

Production Features:

    Comprehensive logging with configurable log levels

    Maintenance mode check before processing

    Graceful shutdown and startup procedures

    Health check endpoints for monitoring

    Metrics collection and reporting

    Error handling with exponential backoff

3. Processing Flow

    SMS Reception: FastAPI receives SMS → insert to input_sms (fast)

    Batch Processing: Background task processes batches by UUID order

    Validation Pipeline: Execute checks sequentially per settings

    Result Storage: Update sms_monitor with individual check results

    Valid SMS Output: Insert passing SMS to out_sms + Redis cache

    Checkpoint Update: Update last_processed_uuid atomically

4. Configuration Management

    All settings dynamically read from system_settings table

    No hardcoded values in application code

    Runtime tunable parameters without restarts

    Settings validation and type checking

Expected Deliverables:

    Complete enhanced setup_sms_gateway.yml with pgbouncer and schema setup

    Production-ready sms_server.py with FastAPI and async batch processing

    Database migration scripts for schema deployment

    Configuration templates and documentation

    Monitoring and health check endpoints

    Comprehensive error handling and logging

Architecture Goal: Ultra-fast SMS reception with robust, configurable batch validation pipeline supporting 10M+ SMS processing with Redis deduplication, pgbouncer connection pooling, and fault-tolerant recovery.
