# SMS Bridge Technical Specification v2.3

**Simple Requirements Document - No Code**

> This document explains WHAT SMS Bridge does and WHY, written for anyone to understand.
> For HOW (code examples), see [SMS_Bridge_tech_snippets_v2.3.md](SMS_Bridge_tech_snippets_v2.3.md)

---

## Table of Contents

1. [What is SMS Bridge?](#what-is-sms-bridge)
2. [How Does it Work? (Simple Explanation)](#how-does-it-work-simple-explanation)
3. [The Big Picture: System Parts](#the-big-picture-system-parts)
4. [Settings and Configuration](#settings-and-configuration)
5. [Data Storage (What Gets Saved Where)](#data-storage-what-gets-saved-where)
6. [API Endpoints (What Each Does)](#api-endpoints-what-each-does)
7. [Background Workers (Automatic Tasks)](#background-workers-automatic-tasks)
8. [Safety Features](#safety-features)
9. [What Happens When Things Break](#what-happens-when-things-break)
10. [Security Rules](#security-rules)
11. [Performance Guidelines](#performance-guidelines)
12. [Glossary](#glossary)
13. [Quick Reference](#quick-reference)

---

## What is SMS Bridge?

SMS Bridge is like a **security guard** for user registration. It makes sure people are real by asking them to send a text message from their phone.

**Why do we need this?**
- Bots and fake accounts can't send SMS messages from real phones
- SMS verification costs money, so spammers avoid it
- Your phone number proves you're a real person

**What does it do?**
1. User wants to create account → We give them a special code
2. User sends SMS with that code → We check it's correct
3. Code matches → User can finish registration

Think of it like a **bouncer at a club** checking tickets. No valid ticket (SMS)? You don't get in.

---

## How Does it Work? (Simple Explanation)

### Step 1: User Asks to Join (Registration Starts)

Your main app (like a login page) calls SMS Bridge and says:
- "Hey, this person with phone number +919876543210 wants to register"

SMS Bridge creates a **special code** (called a "hash") like `A3B7K2M9` and says:
- "Cool! Tell them to text that code to +919000000000 within 5 minutes"

### Step 2: User Sends Text Message

User opens their phone's messaging app and sends:
```
ONBOARD:A3B7K2M9
```

That message arrives at our SMS receiving number (+919000000000).

### Step 3: We Check the Code

SMS Bridge receives the text and checks:
- ✅ Does the code exist? (Is it A3B7K2M9?)
- ✅ Did it arrive in time? (Within 5 minutes?)
- ✅ Is the phone number allowed? (From correct country?)
- ✅ Did they send too many messages? (Rate limiting)
- ✅ Is the number blacklisted? (Banned users)

### Step 4: User Finishes Registration

If all checks pass, SMS Bridge tells your main app:
- "Great! Phone +919876543210 is verified. They can create their account now."

User enters their PIN/password, and account creation completes.

---

## The Big Picture: System Parts

SMS Bridge has **4 main pieces**:

### 1. **The API Server** (FastAPI)
- Handles all requests (register, receive SMS, setup PIN)
- Like a receptionist answering the phone

### 2. **The Fast Memory** (Redis)
- Stores temporary data (codes valid for 5 minutes)
- Like sticky notes that auto-delete after time expires

### 3. **The Permanent Storage** (PostgreSQL)
- Saves logs, settings, user data forever
- Like filing cabinets that never forget

### 4. **The Background Workers** (APScheduler)
- Automatically sync data to your main backend
- Like mail carriers picking up letters every minute

### Dual-Queue Architecture

Think of two conveyor belts running at different speeds:

**Hot Path (Fast Belt - 1 second intervals)**
- Carries verified users to your backend immediately
- Speed matters: User waiting for account creation
- Priority: Login completion

**Cold Path (Slow Belt - 2 minute intervals)**
- Carries logs and audit records to database
- Speed doesn't matter: Just for record-keeping
- Priority: Storage efficiency

---

## Settings and Configuration

### What is the Settings System?

Imagine you have a **control panel** where you can change how SMS Bridge behaves without restarting it.

**Key Settings:**

1. **SMS Receiver Number**
   - What: The phone number users send texts to
   - Example: +919000000000
   
2. **Allowed Prefix**
   - What: The word that must start every SMS
   - Example: "ONBOARD:"
   - Why: Prevents accidental messages

3. **Hash Length**
   - What: How long the special code is
   - Example: 8 characters
   - Why: Longer = more secure but harder to type

4. **TTL (Time To Live)**
   - What: How long the code is valid
   - Example: 900 seconds = 15 minutes
   - Why: Can't reuse old codes

5. **Sync Interval**
   - What: How often we send data to your backend
   - Example: 1.0 seconds
   - Why: Faster = quicker account creation

6. **Audit Interval**
   - What: How often we save logs
   - Example: 120 seconds
   - Why: Don't need to log instantly

7. **Count Threshold**
   - What: Max SMS from one number per hour
   - Example: 5 messages
   - Why: Stop spammers

8. **Allowed Countries**
   - What: Which country codes can register
   - Example: ["+91", "+44"] (India, UK)
   - Why: Restrict to your service regions

9. **Validation Checks**
   - What: Turn different security checks on/off
   - Why: Flexibility during testing

### Settings History (Version Control)

Every time you change settings:
- Old version stays saved (can never delete)
- New version becomes active
- Can rollback by activating old version

Think of it like **Google Docs version history** - you can always go back.

---

## Data Storage (What Gets Saved Where)

### Redis (Fast, Temporary Storage)

**Active Onboarding Codes**
- What: The special codes we give users
- Example: Code "A3B7K2M9" → Phone "+919876543210"
- Lifespan: 15 minutes (auto-deletes)

**Verified Status**
- What: Flag that phone passed SMS verification
- Example: Phone "+919876543210" → Verified
- Lifespan: 15 minutes (one-time use)

**Rate Limit Counters**
- What: Count of SMS sent from each number
- Example: Phone "+919876543210" → 3 messages today
- Lifespan: 1 hour

**Queues**
- What: Waiting lines for tasks
- Example: sync_queue = users ready to send to backend
- Lifespan: Until processed

**Current Settings**
- What: Cached copy of active configuration
- Lifespan: Until settings change

**Blacklist**
- What: Banned phone numbers
- Lifespan: Permanent (synced from Postgres)

### PostgreSQL (Permanent Storage)

**Settings History**
- Every version of configuration ever saved
- Can never be deleted
- Can rollback to any previous version

**Admin Users**
- Usernames and encrypted passwords
- Who can access the admin panel

**Logs**
- Every event that happened (SMS received, errors, etc.)
- Kept forever for compliance/auditing

**Backup Users**
- Copy of user credentials in case Redis fails
- Emergency fallback

**Power-Down Store**
- Emergency backup when Redis crashes
- Temporary until Redis recovers

**Blacklist**
- Authoritative list of banned numbers
- Synced to Redis on startup

---

## API Endpoints (What Each Does)

### 1. POST /onboarding/register

**What it does:** User starts registration process

**Who calls it:** Your main app (backend)

**What happens:**
1. Checks if phone number is from allowed country
2. Checks if user sent too many SMS recently (rate limit)
3. Creates special code (hash)
4. Saves code in Redis with 15-minute timer
5. Returns code to your app

**What your app does:**
- Show user the SMS receiving number (+919000000000)
- Show the code they need to send (A3B7K2M9)
- Show countdown timer (15 minutes)

### 2. POST /sms/receive

**What it does:** Processes incoming text messages

**Who calls it:** SMS gateway provider (like Twilio)

**What happens (validation pipeline):**
1. ✅ Check message format (starts with "ONBOARD:")
2. ✅ Extract code (A3B7K2M9) and verify it exists
3. ✅ Check phone number is from allowed country
4. ✅ Check user hasn't sent too many SMS
5. ✅ Check phone isn't blacklisted

If all pass:
- Delete the code (can't reuse)
- Mark phone as "verified"
- Log the event

**Important:** Each check can be turned on/off in settings

### 3. POST /pin-setup

**What it does:** User completes account creation

**Who calls it:** Your main app (frontend)

**What happens:**
1. Checks phone was verified via SMS
2. Checks the hash matches (security double-check)
3. Sends user credentials to your backend (hot path)
4. Logs the event (cold path)
5. Deletes verified status (one-time use)

**What your app does:**
- Create user account in your database
- Log user in automatically

### 4. GET /health

**What it does:** Reports if system is working

**Who calls it:** Monitoring tools (Prometheus, Grafana)

**What it reports:**
- Overall status: healthy, degraded, or unhealthy
- Database connection: working or broken
- Redis connection: working or broken
- Background workers: running or stopped

### 5. POST /admin/trigger-recovery

**What it does:** Emergency data recovery

**Who calls it:** Admin via Admin UI

**What happens:**
- Sends failed sync attempts back to your backend
- Used when your backend was temporarily down
- Ensures no data lost

---

## Background Workers (Automatic Tasks)

Think of these as **robots that work 24/7** doing repetitive tasks.

### Sync Worker (Runs Every 1 Second)

**Job:** Send verified users to your backend

**Steps:**
1. Check if anyone in sync_queue (waiting line)
2. If yes, take next person
3. Sign the data with secret key (security)
4. Send to your backend API
5. If send fails, put in retry_queue

**Why 1 second?**
- User is waiting for account creation
- Fast sync = better user experience

### Audit Worker (Runs Every 2 Minutes)

**Job:** Save logs to database

**Steps:**
1. Check if any logs in audit_buffer (waiting line)
2. If yes, take next batch
3. Write to PostgreSQL
4. If log mentions PIN setup, also save to backup_users table

**Why 2 minutes?**
- Logs aren't urgent
- Batching reduces database writes
- Saves resources

---

## Safety Features

### 1. Rate Limiting

**Problem:** Spammer tries sending 1000 SMS to verify fake accounts

**Solution:** Maximum 5 SMS per phone number per hour

**How it works:**
- First SMS: Counter = 1
- Second SMS: Counter = 2
- Sixth SMS: Rejected (too many)
- After 1 hour: Counter resets to 0

### 2. Country Restriction

**Problem:** Service only available in India and UK, but someone from Russia tries

**Solution:** Only allow phone numbers starting with +91 (India) or +44 (UK)

**How it works:**
- Phone +919876543210: Starts with +91 ✅ Allowed
- Phone +17345678901: Starts with +1 ❌ Rejected

### 3. Blacklist

**Problem:** Known spammer or abusive user

**Solution:** Permanently ban their phone number

**How it works:**
- Admin adds +919999999999 to blacklist
- All future SMS from that number: Rejected
- Stored in PostgreSQL (survives restarts)

### 4. One-Time Code

**Problem:** User tries reusing same code multiple times

**Solution:** Code deleted after first successful use

**How it works:**
- User sends "ONBOARD:A3B7K2M9" ✅ Verified
- User sends "ONBOARD:A3B7K2M9" again ❌ Code not found

### 5. Time Limits (TTL)

**Problem:** User forgets to send SMS, tries using old code next day

**Solution:** Codes expire after 15 minutes

**How it works:**
- 12:00 PM: Code created
- 12:14 PM: Code still valid ✅
- 12:16 PM: Code expired ❌

### 6. Crash Safety (Atomic Operations)

**Problem:** System crashes between deleting code and marking phone verified

**Solution:** Redis MULTI/EXEC (atomic transactions)

**How it works:**
- Both operations complete together
- Or neither completes
- Never left in broken half-state

### 7. Request Signing (HMAC)

**Problem:** Hacker tries sending fake data to your backend

**Solution:** Every request signed with secret key

**How it works:**
- We create signature using secret only we know
- Your backend verifies signature matches
- If signature wrong: Reject (data tampered with)

---

## What Happens When Things Break

### Scenario 1: Redis Crashes

**Symptoms:** Fast memory (Redis) stops working

**What happens:**
1. System detects Redis is down
2. Dumps all data to PostgreSQL (power_down_store)
3. Switches to "fallback mode"
4. New registrations: Returns "Service temporarily unavailable"
5. Incoming SMS: Queued for later processing
6. PIN setups: Returns "Service temporarily unavailable"

**When Redis comes back:**
1. System detects Redis is healthy again
2. Restores data from power_down_store → Redis
3. Processes queued SMS messages
4. Resumes normal operation
5. Loads blacklist from PostgreSQL → Redis

**User impact:** Brief downtime (minutes), no data lost

### Scenario 2: PostgreSQL Crashes

**Symptoms:** Permanent storage (database) stops working

**What happens:**
1. System cannot start without PostgreSQL
2. All operations fail
3. Health endpoint returns "unhealthy"

**Recovery:**
- Fix PostgreSQL (restart database)
- Restart SMS Bridge
- All data intact (PostgreSQL persistent)

**User impact:** Complete outage until database fixed

### Scenario 3: Background Worker Fails

**Symptoms:** Sync worker or audit worker crashes

**What happens:**
1. Health endpoint reports "degraded"
2. API still works (users can register/verify)
3. But:
   - Sync worker down: Users not sent to backend (queued)
   - Audit worker down: Logs not saved to database (queued)

**Recovery:**
- Restart background workers
- Process accumulated queue
- Catch up on backlog

**User impact:** Delays but no data lost

### Scenario 4: Your Backend is Down

**Symptoms:** Your main backend API not responding

**What happens:**
1. Sync worker tries sending verified user
2. Request fails (connection timeout)
3. User pushed to retry_queue
4. Sync worker tries again later
5. After multiple failures: Stays in retry_queue

**Recovery:**
- Fix your backend
- Admin triggers /admin/trigger-recovery
- All retry_queue items resent
- Users get created in your backend

**User impact:** Account creation delayed but completes eventually

---

## Security Rules

### Admin Panel Access

**Requirements:**
1. Username and password (BCrypt encrypted)
2. Session-based authentication
3. Only super admins can access

**Bootstrap (first time):**
- Run create_super_admin.py script
- Creates first admin account
- Secure password required (minimum 12 characters recommended)

### Settings Changes

**Who can change:**
- Only authenticated admins
- Changes logged (who, when, what)

**What's tracked:**
- Old version kept forever
- New version marked "active"
- Audit trail in settings_history table

### API Security

**External requests (from your backend):**
- Signed with HMAC-SHA256
- Timestamp included (replay attack prevention)
- Your backend verifies signature

**Internal requests (within SMS Bridge):**
- No external access allowed
- Only SMS gateway can call /sms/receive

### Secrets Management

**Where stored:**
- hmac_secret: In settings (encrypted in transit)
- hash_key: In settings (for code generation)
- admin passwords: BCrypt hashed (irreversible)

**Best practices:**
- Rotate secrets quarterly
- Never commit secrets to git
- Use environment variables in production

---

## Performance Guidelines

### Expected Load

**Registration rate:**
- Peak: 100 registrations per minute
- Average: 10 registrations per minute

**SMS processing:**
- Peak: 100 SMS per minute
- Average: 10 SMS per minute

**Response times:**
- /onboarding/register: < 100ms
- /sms/receive: < 200ms
- /pin-setup: < 150ms
- /health: < 50ms

### Resource Requirements

**Minimum (development):**
- CPU: 1 core
- RAM: 512MB
- Disk: 10GB

**Recommended (production):**
- CPU: 2 cores
- RAM: 2GB
- Disk: 50GB (for logs)

**Database connections:**
- Min pool size: 5
- Max pool size: 20

**Redis connections:**
- Max connections: 10

---

## Glossary

**API Endpoint:** A URL that accepts requests (like /onboarding/register)

**APScheduler:** Tool that runs tasks on schedule (like every 1 second)

**Atomic Operation:** Multiple actions that happen together or not at all

**Audit Trail:** Log of who did what and when

**Background Worker:** Program running in background doing automatic tasks

**BCrypt:** Encryption method for passwords (very secure)

**Blacklist:** List of banned phone numbers

**Cold Path:** Slow data processing (logs, not urgent)

**Dual-Queue:** Two separate waiting lines for different speeds

**FastAPI:** Python framework for building APIs (web services)

**Fallback Mode:** Backup plan when something breaks

**Hash:** Special code generated (like A3B7K2M9)

**HMAC:** Method to sign data with secret key (proves authenticity)

**Hot Path:** Fast data processing (user waiting)

**PostgreSQL:** Permanent database (saves forever)

**Queue:** Waiting line (like sync_queue)

**Rate Limit:** Maximum actions allowed per time period

**Redis:** Fast temporary memory (auto-deletes old data)

**Sync:** Sending data to another system

**TTL (Time To Live):** How long before something expires

**Validation Pipeline:** Series of checks (like airport security)

**Webhook:** URL that receives notifications (like SMS arrival)

---

## Quick Reference

### Key Phone Numbers

- **SMS Receiving Number:** +919000000000 (users send texts here)
- **Test Numbers:** +919876543210, +447700900123 (for testing)

### Key Timers

- **Code validity:** 15 minutes (TTL)
- **Verified status:** 15 minutes (one-time use window)
- **Rate limit window:** 1 hour
- **Sync interval:** 1 second (hot path)
- **Audit interval:** 120 seconds (cold path)

### Key Limits

- **Max SMS per hour:** 5 per phone number
- **Hash length:** 8 characters
- **Max request timeout:** 30 seconds
- **Max concurrent connections:** 100

### Allowed Countries

- 🇮🇳 India: +91
- 🇬🇧 United Kingdom: +44
- (Configurable in settings)

### Status Codes

- **200:** Success
- **202:** Accepted (queued for later)
- **400:** Bad request (invalid data)
- **401:** Unauthorized (login required)
- **403:** Forbidden (not allowed)
- **429:** Rate limit exceeded (too many requests)
- **500:** Internal error (system problem)
- **502:** Backend unreachable (your server down)
- **503:** Service unavailable (system maintenance/failure)

### Health Status

- **healthy:** Everything working perfectly ✅
- **degraded:** Partial issues (still usable) ⚠️
- **unhealthy:** Critical failure (not usable) ❌
- **shutting_down:** Graceful shutdown in progress 🔄

---

## Relationship with Monitoring

This specification aligns with [SMS_Bridge_monitoring_spec_v2.3.md](SMS_Bridge_monitoring_spec_v2.3.md):

### Monitoring Integration

- **Metrics collected:** All API endpoints, queue sizes, error rates
- **Logging level:** WARNING (errors and security events only)
- **Log retention:** 7 days (100MB total)
- **Monitoring access:** Via Admin UI temporary port opening
- **Monitoring tools:** Prometheus + Grafana (on laptop, on-demand)

### Port Configuration

- **Main API port:** 8080 (always exposed)
- **Monitoring ports:** Configurable via sms_settings.json
  - metrics_port: 8081 (Prometheus)
  - postgres_port: 5432 (database queries)
  - pgbouncer_port: 6432 (connection pooler)
  - redis_port: 6379 (cache inspection)
- **Port opening:** Temporary (15min-4hr), authenticated, auto-close

### Settings Integration

The `sms_settings.json` file contains:
1. **Validation checks** (described in this spec)
2. **Rate limits** (described in this spec)
3. **Monitoring ports** (described in monitoring spec)

Single configuration file, managed via Admin UI, changes effective immediately.

---

**For implementation details, code examples, and technical configurations, see [SMS_Bridge_tech_snippets_v2.3.md](SMS_Bridge_tech_snippets_v2.3.md)**

---

*Last updated: January 12, 2026*
*Version: 2.3*
*Aligned with: SMS_Bridge_monitoring_spec_v2.3.md*
