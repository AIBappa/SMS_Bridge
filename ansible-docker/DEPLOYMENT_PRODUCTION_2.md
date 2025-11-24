# Production_2 Deployment Guide

## Overview
This guide covers the complete deployment of SMS Bridge Production_2 with Redis-first architecture, dual time windows, and dynamic configuration management.

## Pre-Deployment Checklist

### 1. Verify Prerequisites
```bash
# Check Ansible is installed
ansible --version  # Should be 2.9+

# Check Docker is running
docker ps

# Check vault.yml exists and has required secrets
cat vault.yml | grep -E "pg_password|redis_password|hash_secret_key|cf_api_key"
```

### 2. Review Configuration
- **vault.yml**: Contains all secrets (PostgreSQL, Redis, Cloudflare, hash keys)
- **schema.sql**: Production_2 schema (6 tables)
- **core/**: Updated application code with Production_2 features

### 3. Backup Current System (CRITICAL)
```bash
# Create backup directory
mkdir -p ~/sms_bridge/backups

# Backup current database
docker exec postgres pg_dump -U postgres sms_bridge > ~/sms_bridge/backups/pre_prod2_backup_$(date +%Y%m%d_%H%M%S).sql

# Backup Redis data
docker exec redis redis-cli -a YOUR_REDIS_PASSWORD --rdb ~/sms_bridge/backups/redis_backup_$(date +%Y%m%d_%H%M%S).rdb SAVE

# Backup current code
tar -czf ~/sms_bridge/backups/core_backup_$(date +%Y%m%d_%H%M%S).tar.gz ~/sms_bridge/core/
```

## Deployment Methods

### Method 1: Automated Migration (RECOMMENDED)

This method uses the specialized migration playbook that:
- ✅ Creates automatic backups
- ✅ Gracefully stops all containers
- ✅ Applies schema migration with data preservation
- ✅ Updates application code
- ✅ Restarts all services
- ✅ Performs post-deployment validation

```bash
cd ansible-docker

# Execute Production_2 migration
ansible-playbook -i inventory.txt migrate_to_production_2.yml --ask-vault-pass

# Migration will pause for confirmation at key steps
# Review output carefully for any errors
```

**What This Does:**
1. **Phase 1**: Creates timestamped backups (PostgreSQL dump, Redis RDB)
2. **Phase 2**: Gracefully stops containers (SMS receiver → monitoring → databases)
3. **Phase 3**: Applies Production_2 schema migration
   - Creates new tables with Production_2 structure
   - Migrates data from old input_sms to new structure
   - Updates onboarding_mobile with new fields (email, device_id, dual time windows)
   - Creates power_down_store and power_down_store_counters
   - Creates sms_settings with 20 default settings
   - Preserves audit trail data
4. **Phase 4**: Updates application code (core/, templates/, static/)
5. **Phase 5**: Rebuilds and restarts all containers
6. **Phase 6**: Validates deployment (health checks, API tests)
7. **Phase 7**: Generates migration report

**Migration Report:**
- Location: `~/sms_bridge/migration_report_<timestamp>.txt`
- Contains: Backup locations, container status, health checks, deployed features

---

### Method 2: Manual Step-by-Step Deployment

For advanced users who want full control:

#### Step 1: Stop All Containers
```bash
cd ansible-docker
ansible-playbook -i inventory.txt stop_sms_bridge.yml --ask-vault-pass
```

#### Step 2: Backup Database
```bash
docker start postgres
docker exec postgres pg_dump -U postgres sms_bridge > ~/sms_bridge/backups/manual_backup_$(date +%Y%m%d_%H%M%S).sql
```

#### Step 3: Apply Schema Migration
```bash
# Option A: Recreate database (DESTROYS DATA - only for fresh start)
docker exec -it postgres psql -U postgres
DROP DATABASE sms_bridge;
CREATE DATABASE sms_bridge;
\q

# Copy new schema
docker cp ../schema.sql postgres:/tmp/schema.sql
docker exec postgres psql -U postgres -d sms_bridge -f /tmp/schema.sql

# Option B: Manual migration (PRESERVES DATA - recommended)
# Create migration script on host
cat > ~/sms_bridge/manual_migration.sql << 'EOF'
-- See migrate_to_production_2.yml for full migration SQL
-- This is a condensed version

BEGIN;

-- Create new input_sms structure
CREATE TABLE input_sms_new (
    id SERIAL PRIMARY KEY,
    redis_id INTEGER NOT NULL,
    mobile_number VARCHAR(15) NOT NULL,
    -- ... (see full migration script)
);

-- Migrate data
INSERT INTO input_sms_new SELECT * FROM input_sms;

-- Drop old and rename
DROP TABLE input_sms CASCADE;
ALTER TABLE input_sms_new RENAME TO input_sms;

-- Add new columns to onboarding_mobile
ALTER TABLE onboarding_mobile ADD COLUMN IF NOT EXISTS email VARCHAR(100);
ALTER TABLE onboarding_mobile ADD COLUMN IF NOT EXISTS device_id VARCHAR(100);
-- ... (see full migration script)

-- Create new tables
CREATE TABLE power_down_store (...);
CREATE TABLE power_down_store_counters (...);
CREATE TABLE sms_settings (...);

-- Insert default settings
INSERT INTO sms_settings VALUES (...);

COMMIT;
EOF

# Apply migration
docker cp ~/sms_bridge/manual_migration.sql postgres:/tmp/migration.sql
docker exec postgres psql -U postgres -d sms_bridge -f /tmp/migration.sql
```

#### Step 4: Update Application Code
```bash
# Copy updated core package
cp -r ../core ~/sms_bridge/core

# Verify files
ls -la ~/sms_bridge/core/templates/sms_settings.html
ls -la ~/sms_bridge/core/static/admin.css
```

#### Step 5: Restart Services
```bash
# Restart with updated code
ansible-playbook -i inventory.txt setup_sms_bridge.yml --ask-vault-pass
```

#### Step 6: Verify Deployment
```bash
# Check container status
docker ps --filter "network=sms_bridge_network"

# Test health endpoint
curl http://localhost:8080/health

# Test admin UI
curl http://localhost:8080/admin/settings/ui

# View logs
docker logs sms_receiver --tail 50
```

---

## Post-Deployment Validation

### 1. Container Health Checks
```bash
# All containers should be running
docker ps --filter "network=sms_bridge_network" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Expected containers:
# - postgres (healthy)
# - redis (healthy)
# - pgbouncer (healthy)
# - sms_receiver (healthy)
# - prometheus (healthy)
# - grafana (healthy)
# - postgres_exporter (healthy)
# - redis_exporter (healthy)
```

### 2. Database Schema Validation
```bash
# Verify 6 tables exist
docker exec postgres psql -U postgres -d sms_bridge -c "\dt"

# Expected tables:
# - input_sms
# - onboarding_mobile
# - blacklist_sms
# - power_down_store
# - power_down_store_counters
# - sms_settings

# Check sms_settings has 20 default entries
docker exec postgres psql -U postgres -d sms_bridge -c "SELECT COUNT(*) FROM sms_settings;"

# View settings
docker exec postgres psql -U postgres -d sms_bridge -c "SELECT setting_key, category FROM sms_settings ORDER BY category;"
```

### 3. API Endpoint Tests
```bash
# Health check (should return {"status": "healthy"})
curl http://localhost:8080/health

# Admin UI (should return HTML page)
curl -I http://localhost:8080/admin/settings/ui

# Test POST /onboard/register (replace with actual values)
curl -X POST http://localhost:8080/onboard/register \
  -H "Content-Type: application/json" \
  -d '{
    "mobile": "919876543210",
    "email": "test@example.com",
    "device_id": "TEST_DEVICE_001"
  }'

# Expected response:
# {
#   "hash": "<32-char-hash>",
#   "user_deadline": "<ISO8601-timestamp>",
#   "expires_at": "<ISO8601-timestamp>"
# }
```

### 4. Redis Connectivity Tests
```bash
# Get Redis password from vault
REDIS_PASSWORD=$(grep redis_password vault.yml | awk '{print $2}')

# Test Redis connection
docker exec redis redis-cli -a $REDIS_PASSWORD PING
# Expected: PONG

# Check Redis keys
docker exec redis redis-cli -a $REDIS_PASSWORD KEYS '*'

# Test settings cache
docker exec redis redis-cli -a $REDIS_PASSWORD GET "setting:onboarding_ttl_seconds"
# Expected: "86400"
```

### 5. Background Workers Validation
```bash
# Check logs for background worker startup
docker logs sms_receiver | grep "Background worker"

# Expected log entries:
# - "Background worker: dump_queue_input_sms started"
# - "Background worker: sync_validated_mobiles_to_hetzner started"
# - "Background worker: populate_blacklist started"
# - "Background worker: persist_counters started"
```

### 6. Admin UI Manual Test
```bash
# Open admin UI in browser
xdg-open http://localhost:8080/admin/settings/ui

# Verify:
# ✅ Settings are grouped by category (General, Validation, Thresholds, Sync, Infrastructure, Monitoring)
# ✅ Boolean settings show toggle switches
# ✅ Integer settings show number inputs
# ✅ JSON settings show textarea
# ✅ Can edit and save settings
# ✅ Changes reflect immediately (no restart required)
```

### 7. Monitoring Stack Validation
```bash
# Access Grafana
xdg-open http://localhost:3001
# Login: admin / <grafana_admin_password from vault>

# Check Prometheus targets
xdg-open http://localhost:9090/targets
# All targets should be UP:
# - postgres_exporter (localhost:9187)
# - redis_exporter (localhost:9121)
# - sms_receiver (localhost:8080/metrics)
```

---

## Production_2 New Features

### 1. Redis-First Architecture
- **ALL validation happens in Redis** (no PostgreSQL in hot path)
- Only 6 PostgreSQL tables for audit and configuration
- Background workers handle async PostgreSQL dumps

### 2. Dual Time Windows
- **user_deadline**: 5 minutes (configurable via sms_settings)
- **expires_at**: 24 hours (configurable via sms_settings)
- User must submit SMS within 5 minutes
- Onboarding entry remains valid for 24 hours for audit

### 3. Dynamic Configuration
- 20 configurable settings in `sms_settings` table
- Admin UI at `/admin/settings/ui` for real-time updates
- No application restart required for settings changes
- Settings cached in Redis for performance

### 4. POST /onboard/register Endpoint
- **Method**: POST (changed from GET)
- **Required fields**: mobile, email, device_id
- **Response**: hash, user_deadline, expires_at
- **Validation**: Mobile format, duplicate check

### 5. Count Check Validation
- New `count_check.py` validates SMS count per mobile
- Redis counter: `sms_count:{mobile}` with 24h TTL
- Configurable threshold (default: 5 SMS per 24h)
- Prevents abuse and spam

### 6. Admin UI
- **URL**: http://localhost:8080/admin/settings/ui
- **Features**:
  - Category-grouped settings
  - Type-aware inputs (boolean toggles, number inputs, JSON editors)
  - Real-time updates via AJAX
  - Responsive design with modern CSS
  - Dark mode support

---

## Troubleshooting

### Issue: Migration fails with "relation already exists"
**Solution**: Tables already exist. Either:
1. Drop existing tables manually: `DROP TABLE <table_name> CASCADE;`
2. Use fresh database: Stop containers, delete `pg_data` volume, restart

### Issue: Container fails to start after migration
**Diagnosis**:
```bash
# Check logs
docker logs sms_receiver
docker logs postgres
docker logs redis
```

**Common causes**:
- Wrong credentials in vault.yml
- Port conflicts (8080, 5432, 6379)
- Volume permission issues

**Solution**:
```bash
# Fix permissions
sudo chown -R $(whoami):$(whoami) ~/sms_bridge

# Restart container
docker restart sms_receiver
```

### Issue: Admin UI shows 404
**Diagnosis**:
```bash
# Check if templates and static files exist
docker exec sms_receiver ls -la /app/core/templates/
docker exec sms_receiver ls -la /app/core/static/
```

**Solution**:
```bash
# Rebuild container with updated code
docker stop sms_receiver
docker rm sms_receiver
ansible-playbook -i inventory.txt setup_sms_bridge.yml --ask-vault-pass
```

### Issue: Settings not updating in real-time
**Diagnosis**:
```bash
# Check Redis connection
REDIS_PASSWORD=$(grep redis_password vault.yml | awk '{print $2}')
docker exec redis redis-cli -a $REDIS_PASSWORD PING

# Check settings cache
docker exec redis redis-cli -a $REDIS_PASSWORD KEYS 'setting:*'
```

**Solution**:
```bash
# Clear Redis cache
docker exec redis redis-cli -a $REDIS_PASSWORD FLUSHDB

# Restart SMS receiver to repopulate cache
docker restart sms_receiver
```

### Issue: POST /onboard/register returns 500 error
**Diagnosis**:
```bash
# Check logs for stack trace
docker logs sms_receiver | tail -100

# Common errors:
# - Missing email/device_id fields in request
# - Redis connection failure
# - PostgreSQL connection failure
```

**Solution**:
```bash
# Test with curl
curl -X POST http://localhost:8080/onboard/register \
  -H "Content-Type: application/json" \
  -d '{"mobile": "919876543210", "email": "test@example.com", "device_id": "DEV123"}'

# Check response for validation errors
```

### Issue: Count check always rejects SMS
**Diagnosis**:
```bash
# Check Redis counter
REDIS_PASSWORD=$(grep redis_password vault.yml | awk '{print $2}')
docker exec redis redis-cli -a $REDIS_PASSWORD GET "sms_count:919876543210"

# Check threshold setting
docker exec postgres psql -U postgres -d sms_bridge -c "SELECT setting_value FROM sms_settings WHERE setting_key='count_check_threshold';"
```

**Solution**:
```bash
# Increase threshold via admin UI or database
docker exec postgres psql -U postgres -d sms_bridge -c "UPDATE sms_settings SET setting_value='10' WHERE setting_key='count_check_threshold';"

# Clear Redis counter
docker exec redis redis-cli -a $REDIS_PASSWORD DEL "sms_count:919876543210"
```

---

## Rollback Procedure

If Production_2 deployment fails and you need to rollback:

### Step 1: Stop Production_2 Containers
```bash
cd ansible-docker
ansible-playbook -i inventory.txt stop_sms_bridge.yml --ask-vault-pass
```

### Step 2: Restore Database Backup
```bash
# Find your backup file
ls -lt ~/sms_bridge/backups/

# Restore database
docker start postgres
docker exec -i postgres psql -U postgres -c "DROP DATABASE sms_bridge;"
docker exec -i postgres psql -U postgres -c "CREATE DATABASE sms_bridge;"
docker exec -i postgres psql -U postgres sms_bridge < ~/sms_bridge/backups/sms_bridge_backup_<timestamp>.sql
```

### Step 3: Restore Old Code
```bash
# Extract backup
tar -xzf ~/sms_bridge/backups/core_backup_<timestamp>.tar.gz -C /

# Verify restored
ls -la ~/sms_bridge/core/
```

### Step 4: Restart Old Version
```bash
# Use old setup playbook (if you have it backed up)
ansible-playbook -i inventory.txt setup_sms_bridge.yml --ask-vault-pass
```

### Step 5: Verify Rollback
```bash
# Check old endpoint works
curl http://localhost:8080/health

# Check old schema
docker exec postgres psql -U postgres -d sms_bridge -c "\dt"
```

---

## Performance Tuning (Post-Deployment)

### Redis Configuration
```bash
# Increase max memory if needed
docker exec redis redis-cli -a <password> CONFIG SET maxmemory 512mb

# Adjust eviction policy
docker exec redis redis-cli -a <password> CONFIG SET maxmemory-policy allkeys-lru
```

### PostgreSQL Configuration
```bash
# Increase connection pool size (in vault.yml before deployment)
# pgbouncer_pool_size: 20

# Tune PostgreSQL (edit before deployment)
# shared_buffers = 256MB
# effective_cache_size = 1GB
# max_connections = 100
```

### Application Settings (via Admin UI)
- Increase `hetzner_sync_interval_seconds` to reduce load (e.g., 30s)
- Increase `local_sync_interval_seconds` to reduce disk I/O (e.g., 300s)
- Adjust `count_check_threshold` based on traffic patterns

---

## Monitoring and Alerting

### Key Metrics to Monitor
1. **Redis Memory Usage**: Should stay under maxmemory limit
2. **PostgreSQL Connection Pool**: Should not exceed DEFAULT_POOL_SIZE
3. **API Response Times**: /onboard/register should be <100ms
4. **Background Worker Lag**: Check queue depths
5. **SMS Validation Failure Rate**: Monitor failed_at_check distribution

### Grafana Dashboards
- **URL**: http://localhost:3001
- **Dashboard**: SMS Bridge App Metrics (pre-configured)
- **Panels**:
  - Request rate and latency
  - Redis memory and connections
  - PostgreSQL queries and connections
  - Background worker performance
  - Validation check success/failure rates

### Log Monitoring
```bash
# Follow SMS receiver logs
docker logs sms_receiver -f

# Search for errors
docker logs sms_receiver | grep -i error

# Count validation failures
docker logs sms_receiver | grep "Validation failed" | wc -l
```

---

## Next Steps After Deployment

1. **Test POST endpoint** with real mobile numbers and emails
2. **Access admin UI** and familiarize yourself with settings
3. **Monitor logs** for first 30 minutes to catch any errors
4. **Configure alerts** in Grafana for critical metrics
5. **Test count check** by sending multiple SMS from same number
6. **Verify dual time windows** work correctly (5min user, 24h audit)
7. **Update documentation** with your specific configuration
8. **Train team** on new admin UI and Production_2 features

---

## Support and Documentation

- **Architecture**: See `docs/functionality.md` for complete Production_2 architecture
- **API Docs**: See `docs/integration_openapi.yaml` for OpenAPI spec
- **Release Plan**: See `docs/Release_plan.md` for roadmap
- **Redis Migration**: See `docs/redis_migration_guide.md` for Redis schema details

---

## Production_2 Feature Summary

| Feature | Production_1 | Production_2 |
|---------|-------------|--------------|
| Validation Location | PostgreSQL | Redis (100% Redis) |
| Database Tables | 8 tables | 6 tables |
| Onboarding Endpoint | GET /onboard/register | POST /onboard/register |
| Required Fields | mobile | mobile, email, device_id |
| Time Windows | Single (24h) | Dual (5min user + 24h audit) |
| Configuration | Static (restart required) | Dynamic (admin UI) |
| Count Check | count_sms table | Redis counters |
| Admin UI | None | Full-featured at /admin/settings/ui |
| Settings Management | Manual SQL | Web UI with real-time updates |
| Sync Strategy | Single dump | Dual (10s Hetzner, 120s local) |

---

**Deployment Status**: Ready for production ✅  
**Last Updated**: Production_2 migration playbook  
**Maintainer**: SMS Bridge Team
