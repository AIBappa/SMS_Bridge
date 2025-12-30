The following system block diagram shows the various aspects of the SMS_Bridge proposed for Production_2.
The objective is to have a production ready system with less of PostgreSQL and more of Redis to provide a faster experience to the user (Redis) plus cater for backup, reliability and audits.

Legend is as follows:
1) The frontend part of the system is shown in Blue.
2) Cloudflare Hono in Green
3) Local Redis in Orange
4) Local PostgreSQL in Yellow
5) Hetzner Supabase in Cream.

<img width="1710" height="803" alt="Mobile_Validation_System" src="https://github.com/user-attachments/assets/a5f00579-e9e2-479a-97cb-0e3f8a256410" />

The system caters to the following user case scenarios.

Use case 1) The general workflow is from the user end, user sends details to onboard which include mobile number, device ID , email and the time of application.
This information passes via CF , through a local tunnel to local Redis, where a hash is generated and fed back to the user alongwith a mobile number where hash can be sent and confirmed. This is supposed to be done within a timelimit.
User then sends SMS to the recieving number with the Hash to confirm mobile number. Sending Hash from the same mobile number as that provided to generarate Hash will allow confirmation, plus costs for sending SMS from application end can be avoided.
Once the SMS reaches the local reciever, it is parsed and undergoes a series of checks to be confirmed.

Use case 2) Malicious users who send SMS to the recieving number will be inherently prohibited because it will cost them to send SMS. Also even if they do send SMSes, because the checks are in Redis, it should prevent an impact on the Supabase Hetzner.
Malicious users that send fake mobile numbers over IP, those mobiles cannot be registered unless SMS is recieved with hash. Also if they send multiple spurious mobiles numbers, IP rate limiting at CF end will protect from multiple requests.
These requests will also be captured in PostgreSQL locally to audit and report wherever necessary.

Use case 3) Local issues - Power loss and local server not reachable. In this case, Mobile number will still operate and recieve SMSes. The weblink between the mobile and the local server will break, however this can be tracked to understand which SMSes
were recieved and when power is resurrected, those SMSes can be pushed back on the weblink. Potential update to mobile software reciever (Android) could be required. However, a manual push from mobile is also possible. Health tracker will also push message
to User over IP that mobile onboarding is currently paused due to server issue.

User case 4) Local issues - Redis down but PostgreSQL still working. In this scenario, PostgreSQL has power down table to save local SMSes from mobile. These will be pushed to Redis when Redis is brought back on.

Requirements for Local Server - Python core
1) Have a UI for SMS_Settings table, so that these settings can be changed by user directly on local machine.
2) Read SMS Recieved as per Swagger API call and add it to the Queue_input_sms table in Redis. This table is kept updated with the results of the various checks that the SMS (message + number) undergo.
3) The checks are enabled as per the SMS_Settings table enable/disable check. If check disabled, the next enabled check shall be proceeded with. If check disabled, that field in Queue_input_sms should be "disabled". If one check fails, the next checks are not required and should be noted "N/A".
4) If the hash recieved and the hash generated tally and their mobile numbers tally as well, the mobile is considered validated. Accordingly the row in the Queue_input_sms shall be updated.
5)  Queue_validated_mobiles is new Redis table that will be used to record validated mobile numbers. This will be used in duplicate check.
6) Queue_Input_SMS shall be periodically dumped in parts into PostgreSQL in Table Input_SMS. an incrementing counter shall be implemented for each entry. A counter shall be held for the purpose of copying this table in parts to postgresql. The value of counter is stored in postgresql table power_down_store_counters. When Redis goes down and comes back up, new incrementing IDs will start from this counter. During the duration of Redis power down, incoming SMSes shall be directly stored as per Swagger API call into power_down_store.

## Production_2 Architecture Details

### Dual Time Window Strategy
The system implements two distinct time windows with different purposes:

1. **User Deadline (X)**: 5 minutes (300 seconds)
   - User-facing deadline for sending SMS with hash
   - Displayed to users via `user_deadline` and `user_timelimit_seconds` in API response
   - Configurable via `user_timelimit_seconds` in sms_settings table
   
2. **Redis TTL (Audit Retention)**: 24 hours (86400 seconds)
   - System-level audit retention period
   - Automatically managed by Redis TTL mechanism (no worker needed)
   - Displayed to users via `expires_at` and `redis_ttl_seconds` in API response
   - Configurable via `onboarding_ttl_seconds` in sms_settings table

### Redis-First Architecture (6 PostgreSQL Tables Only)
All validation checks execute in Redis (no PostgreSQL in hot path). PostgreSQL is used only for:
- Audit trail (input_sms)
- Configuration (sms_settings)
- Blacklist persistence (blacklist_sms)
- Onboarding audit (onboarding_mobile)
- Power down resilience (power_down_store, power_down_store_counters)

**PostgreSQL Tables (6 total)**:
1. `input_sms` - Audit trail with check result columns (mobile_check, duplicate_check, foreign_number_check, blacklist_check, count_check, header_hash_check, time_window_check)
2. `onboarding_mobile` - Onboarding audit trail
3. `blacklist_sms` - Persistent blacklist (loaded into Redis blacklist_mobiles SET)
4. `power_down_store` - Redis failure backup for incoming SMS
5. `power_down_store_counters` - Counter persistence for Redis recovery
6. `sms_settings` - UI-configurable settings (all timing parameters, thresholds, check toggles)

**Removed Tables**:
- `out_sms` - Replaced by Queue_validated_mobiles SET in Redis
- `sms_monitor` - Merged into input_sms (check result columns)
- `count_sms` - Replaced by Redis sms_count:{mobile} counters with TTL
- `system_settings` - Replaced by sms_settings

### Sequential Validation Checks (Redis-Only)
All checks execute in Redis following this sequence:
1. **Mobile Match Check** (mobile_check.py) - Validates E.164 format, extracts country code
2. **Duplicate Check** (duplicate_check.py) - Checks Queue_validated_mobiles SET
3. **Header/Hash Check** (header_hash_check.py) - Validates "ONBOARD:" prefix and hash match
4. **Count Check** (count_check.py) - **NEW** - Redis sms_count:{mobile} validation (no PostgreSQL)
5. **Foreign Number Check** (foreign_number_check.py) - Country code validation
6. **Blacklist Check** (blacklist_check.py) - Redis blacklist_mobiles SET lookup
7. **Time Window Check** (time_window_check.py) - Validates within user deadline

Each check reads its threshold/configuration from sms_settings table (cached in Redis for 60s).

### Count Check Implementation (Redis-Only)
- **Storage**: Redis counter `sms_count:{mobile}` with 24h TTL
- **Threshold**: Configurable via `count_check_threshold` in sms_settings
- **Logic**: Increment counter on each SMS, fail if exceeds threshold
- **No PostgreSQL**: Completely Redis-based, no count_sms table

### Dual Sync Strategy (Configurable Intervals)
1. **Hetzner Supabase Sync**: Every 10 seconds (configurable via `hetzner_sync_interval_seconds`)
   - Syncs ONLY validated mobiles (validation_status='passed')
   - Source: input_sms WHERE validation_status='passed'
   
2. **Local PostgreSQL Sync**: Every 120 seconds (configurable via `local_sync_interval_seconds`)
   - Syncs ALL data (audit trail)
   - Source: Queue_input_sms → input_sms

### sms_settings Table Structure
Admin-configurable settings organized by category:

**General Settings**:
- `onboarding_ttl_seconds` (default: 86400) - Redis TTL for onboarding entries
- `user_timelimit_seconds` (default: 300) - User deadline for SMS submission

**Sync Settings**:
- `hetzner_sync_interval_seconds` (default: 10) - Hetzner sync frequency
- `local_sync_interval_seconds` (default: 120) - Local PostgreSQL dump frequency

**Validation Check Toggles**:
- `mobile_check_enabled` (default: true)
- `duplicate_check_enabled` (default: true)
- `header_hash_check_enabled` (default: true)
- `count_check_enabled` (default: true)
- `foreign_number_check_enabled` (default: true)
- `blacklist_check_enabled` (default: true)
- `time_window_check_enabled` (default: true)

**Validation Thresholds**:
- `count_check_threshold` (default: 5) - Max SMS per mobile in 24h
- `blacklist_threshold` (default: 10) - Count to trigger blacklist

**Background Worker Settings**:
- `blacklist_check_interval_seconds` (default: 300) - Blacklist reload frequency

All settings cached in Redis with 60s TTL (key format: `setting:{key}`).

### API Changes (POST Endpoint)
**Endpoint**: `POST /onboard/register` (changed from GET with path param)

**Request Body**:
```json
{
  "mobile_number": "+9199XXYYZZAA",
  "email": "user@example.com",
  "device_id": "device_abc123xyz"
}
```

**Response**:
```json
{
  "status": "success",
  "mobile_number": "+9199XXYYZZAA",
  "hash": "a06f0b785d66...",
  "generated_at": "2025-09-19T12:00:00Z",
  "user_deadline": "2025-09-19T12:05:00Z",
  "user_timelimit_seconds": 300,
  "expires_at": "2025-09-20T12:00:00Z",
  "redis_ttl_seconds": 86400
}
```

### Admin UI
FastAPI-based admin interface for sms_settings management:
- **Endpoint**: `GET /admin/settings/ui` - HTML interface with category grouping
- **Update Endpoint**: `PUT /admin/settings/{key}` - Individual setting updates
- **Cache Invalidation**: Automatic Redis cache invalidation on setting update
- **No Restarts**: All settings applied dynamically without server restart
