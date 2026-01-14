# SMS Bridge Monitoring Setup Guide

**Quick Start Guide for Monitoring SMS Bridge from Your Laptop**

> 💡 **For security considerations**, see [docs/core/ADMIN_SECURITY.md](core/ADMIN_SECURITY.md)  
> 💡 **For technical details**, see [Monitoring Spec v2.3](core/SMS_Bridge_monitoring_spec_v2.3.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [First-Time Setup](#first-time-setup)
4. [Daily Monitoring Workflow](#daily-monitoring-workflow)
5. [Day in the Life Examples](#day-in-the-life-examples)
6. [Script Reference](#script-reference)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Usage](#advanced-usage)

---

## Overview

### What is This?

SMS Bridge uses an **on-demand monitoring** approach:
- **Server**: Runs SMS Bridge with minimal logging (no monitoring stack)
- **Laptop**: Runs Prometheus + Grafana only when you need to monitor
- **Security**: Monitoring ports open temporarily via Admin UI, auto-close after timeout

### Benefits

- ✅ Server saves ~500MB RAM (no monitoring containers)
- ✅ Ports only open when needed (better security)
- ✅ Monitor from any laptop (portable setup)
- ✅ No 24/7 monitoring overhead

### Architecture

```
┌─────────────────┐         ┌──────────────────┐
│ Your Laptop     │         │ Surface Pro      │
│                 │         │ (Server)         │
│ Prometheus ◄────┼─────────┼─► Port 9100     │
│ Grafana         │  HTTPS  │    (metrics)     │
│                 │         │                  │
│ DBeaver ◄───────┼─────────┼─► Port 5433     │
│ (optional)      │  TCP    │    (postgres)    │
└─────────────────┘         └──────────────────┘
```

---

## Prerequisites

### On Server (Surface Pro)
- ✅ SMS Bridge v2.3+ deployed and running
- ✅ Admin UI accessible (e.g., `https://sms-bridge.yourdomain.com/admin`)
- ✅ Port configuration feature enabled

### On Laptop
- ✅ Docker installed and running
- ✅ Docker Compose v2.0+ installed
- ✅ Git (to clone repository)
- ✅ Network access to server (internet or VPN)
- ✅ ~1GB free disk space (for Docker images)

### Check Prerequisites

```bash
# Check Docker
docker --version
# Should show: Docker version 20.x or higher

# Check Docker Compose
docker-compose --version
# Should show: Docker Compose version 2.x or higher

# Check connectivity
curl -I https://sms-bridge.yourdomain.com/health
# Should return: 200 OK
```

---

## First-Time Setup

**Do this once, reuse forever!**

### Step 1: Clone Repository

```bash
cd ~/
git clone https://github.com/your-org/sms-bridge.git
cd sms-bridge/coolify-monitoring
```

### Step 2: Configure Server URL

```bash
# Copy environment template
cp .env.example .env

# Edit with your server URL
nano .env
```

**Set in `.env`:**
```bash
SMS_BRIDGE_URL=https://sms-bridge.yourdomain.com

# Optional: Grafana credentials
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=change-this-password

# Optional: Database credentials (for DBeaver)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-db-password
POSTGRES_DB=sms_bridge
```

### Step 3: Export Prometheus Config

**Via Admin UI:**
1. Login: `https://sms-bridge.yourdomain.com/admin`
2. Navigate: **Monitoring → Port Configuration**
3. Click: **"Export Prometheus Config"**
4. Save downloaded file as: `config/prometheus-remote.yml`

**Or via command line:**
```bash
# Download directly (replace URL and credentials)
curl -u admin:password \
  https://sms-bridge.yourdomain.com/admin/monitoring/export-prometheus-config \
  -o config/prometheus-remote.yml
```

### Step 4: Verify Setup

```bash
# Check files exist
ls -lh config/prometheus-remote.yml  # Should exist
ls -lh .env                           # Should exist

# Validate prometheus config
cat config/prometheus-remote.yml | grep yourdomain.com
# Should show your server URL
```

### Step 5: Test Start (Optional)

```bash
# Try starting (will show reminder if ports not open)
./scripts/start-monitoring.sh

# Should see:
# ✅ Containers started
# ⚠️  Remember to open ports on server

# Stop for now
./scripts/stop-monitoring.sh
```

**First-time setup complete!** ✅

---

## Daily Monitoring Workflow

**Use this every time you want to monitor:**

### Quick Workflow (5 minutes)

```bash
# 1. Open ports on server (via Admin UI)
Login → Monitoring → Open All Ports (15 min)

# 2. Start monitoring on laptop
cd ~/sms-bridge/coolify-monitoring
./scripts/start-monitoring.sh
# Browser opens to http://localhost:3000

# 3. View dashboards in Grafana

# 4. Done? Stop monitoring
./scripts/stop-monitoring.sh

# 5. Ports auto-close on server after 15 min
```

### Detailed Workflow

#### 1. On Server: Open Monitoring Ports

**Option A: Open All Ports**
1. Login to Admin UI: `https://sms-bridge.yourdomain.com/admin`
2. Navigate: **Monitoring → Port Management**
3. Click: **"Open All Monitoring Ports"**
4. Select duration: **60 minutes** (or 15-240 min)
5. Click: **"Open"**

**Result:**
- ✅ Metrics port (9100) opened
- ✅ Postgres port (5433) opened (if enabled)
- ✅ Redis port (6380) opened (if enabled)
- ⏱️ Auto-close timer started

**Option B: Open Specific Ports**
1. Navigate: **Monitoring → Port Management**
2. Select service (e.g., "metrics")
3. Click: **"Open Port"** → Duration: 60 min
4. Repeat for other services if needed

#### 2. On Laptop: Start Monitoring

```bash
cd ~/sms-bridge/coolify-monitoring
./scripts/start-monitoring.sh
```

**What happens:**
1. Validates setup (checks .env, prometheus config)
2. Starts Prometheus container (scrapes metrics every 15s)
3. Starts Grafana container (displays dashboards)
4. Opens browser to http://localhost:3000
5. Shows reminder to open server ports

**Access points:**
- Grafana: http://localhost:3000 (dashboards)
- Prometheus: http://localhost:9090 (raw metrics)

**Default Grafana login:**
- Username: `admin`
- Password: `admin` (or value from `.env`)

#### 3. View Dashboards

**Pre-loaded dashboards:**
1. **SMS Bridge Overview** - Request rates, errors, queue depth
2. **PostgreSQL Metrics** - Database performance, connections
3. **Redis Metrics** - Cache hit rate, memory usage

**Explore metrics in Prometheus:**
- Visit: http://localhost:9090/graph
- Query examples:
  - `sms_requests_total`
  - `postgres_connections`
  - `redis_memory_used_bytes`

#### 4. Optional: Connect Database Tools

**If postgres port is open (5433):**

```bash
# DBeaver connection
Host: sms-bridge.yourdomain.com
Port: 5433
Database: sms_bridge
User: postgres
Password: (from .env)
```

**If redis port is open (6380):**

```bash
# Redis Desktop Manager
Host: sms-bridge.yourdomain.com
Port: 6380
Password: (from .env, if auth enabled)
```

#### 5. Stop Monitoring

```bash
cd ~/sms-bridge/coolify-monitoring
./scripts/stop-monitoring.sh
```

**What happens:**
1. Stops Prometheus container (gracefully)
2. Stops Grafana container (saves settings)
3. Removes containers (keeps data volumes)
4. Shows reminder to close server ports

**Your data is preserved:**
- ✅ Grafana dashboards
- ✅ Grafana user settings
- ✅ Prometheus metric history

#### 6. Close Server Ports

**Option 1: Let auto-close work**
- Ports close automatically after timeout (e.g., 60 min)

**Option 2: Close manually**
1. Admin UI → Monitoring → Port Management
2. Click: **"Close All Ports"**

---

## Day in the Life Examples

### Example 1: Monday Morning Health Check

**Scenario:** Quick 5-minute check before starting work

```
Timeline:
---------
9:00 AM - Open ports (Admin UI)
         Login → Monitoring → Open metrics port → 15 minutes

9:01 AM - Start monitoring (Laptop)
         cd ~/sms-bridge/coolify-monitoring
         ./scripts/start-monitoring.sh

9:02 AM - Check Grafana
         View "SMS Bridge Overview" dashboard
         - Request rate: normal ✅
         - Error rate: 0.1% ✅
         - Queue depth: 12 messages ✅

9:05 AM - Done, stop monitoring
         ./scripts/stop-monitoring.sh

9:15 AM - Ports auto-close on server
```

**Result:** Quick health check, no issues found, continue working.

---

### Example 2: Investigating Slow Response Times

**Scenario:** Users reporting slow SMS delivery, need to debug

```
Timeline:
---------
2:00 PM - Open all ports for deep inspection (Admin UI)
         Login → Monitoring → Open All Ports → 120 minutes

2:01 PM - Start monitoring (Laptop)
         ./scripts/start-monitoring.sh

2:02 PM - Check Grafana
         SMS Bridge Overview dashboard:
         - Request rate: high but normal ✅
         - Database connections: maxed out ⚠️
         - Queue depth: 500 messages (growing) ❌

2:05 PM - Connect DBeaver to investigate
         Host: sms-bridge.yourdomain.com:5433
         Run query: SELECT * FROM sms_queue WHERE status='pending'
         Result: 500 messages stuck in queue

2:10 PM - Check slow queries
         Grafana → PostgreSQL dashboard
         - Slow query: SELECT with missing index ❌

2:15 PM - Found root cause
         Missing index on sms_queue(status, created_at)

2:20 PM - Fix deployed, monitoring improvement
         Queue draining: 500 → 200 → 50 → 0 ✅

3:00 PM - Issue resolved, stop monitoring
         ./scripts/stop-monitoring.sh

4:00 PM - Ports auto-close
```

**Result:** Identified missing database index, deployed fix, verified resolution.

---

### Example 3: All-Day Monitoring During High Traffic

**Scenario:** Expected high traffic day (marketing campaign), want continuous monitoring

```
Timeline:
---------
8:00 AM - Open ports for maximum duration (Admin UI)
         Login → Monitoring → Open All Ports → 240 minutes (4 hours)

8:05 AM - Start monitoring (Laptop)
         ./scripts/start-monitoring.sh

8:10 AM - 12:00 PM - Monitor dashboards periodically
         Check Grafana every 30 minutes
         - Request rate increasing: 10/s → 50/s → 100/s
         - System handling load well ✅
         - No errors ✅

12:00 PM - Ports close (4 hour limit)
          Re-open ports (Admin UI)
          Login → Monitoring → Open All Ports → 240 minutes

12:05 PM - 4:00 PM - Continue monitoring
          Peak traffic: 150 req/s
          - CPU usage: 60% ✅
          - Memory usage: 70% ✅
          - Queue depth: stable at 20-30 ✅

4:00 PM - Traffic declining, campaign ending
         Stop monitoring
         ./scripts/stop-monitoring.sh

4:10 PM - Close ports manually (Admin UI)
         Login → Monitoring → Close All Ports
```

**Result:** Successfully monitored high-traffic event, no incidents.

---

### Example 4: Team Member Onboarding

**Scenario:** New developer needs to set up monitoring

```
Steps:
------
1. Share repository access
   Grant GitHub repo access to new team member

2. New dev clones repo (their laptop)
   git clone https://github.com/your-org/sms-bridge.git
   cd sms-bridge/coolify-monitoring

3. Configure their .env
   cp .env.example .env
   # You send them: SMS_BRIDGE_URL value (via secure channel)

4. Export prometheus config (you do this)
   Admin UI → Export Prometheus Config
   # Send file to new dev (via secure channel)

5. New dev copies config
   # Save received file as: config/prometheus-remote.yml

6. Test setup
   ./scripts/check-monitoring.sh
   # ✅ .env found
   # ✅ prometheus-remote.yml found
   # ✅ Docker running
   # ⚠️  Server ports not open (expected)

7. You open ports (Admin UI)
   Login → Monitoring → Open All Ports → 60 minutes

8. New dev starts monitoring
   ./scripts/start-monitoring.sh
   # Success! They see dashboards ✅

9. Done onboarding
   ./scripts/stop-monitoring.sh
```

**Result:** New team member can now monitor independently.

---

## Script Reference

### `start-monitoring.sh`

**What it does:**
1. Validates setup (.env, prometheus config)
2. Starts Prometheus + Grafana containers
3. Opens browser to Grafana
4. Shows reminder to open server ports

**Usage:**
```bash
./scripts/start-monitoring.sh
```

**What happens behind the scenes:**
- Runs `docker-compose -f docker-compose-monitoring.yml up -d`
- Mounts config files into containers
- Waits for containers to be healthy
- Opens http://localhost:3000 in browser

**Troubleshooting:**
```bash
# If fails, check:
docker ps  # Are containers running?
docker logs prometheus  # Prometheus errors?
docker logs grafana  # Grafana errors?
```

---

### `stop-monitoring.sh`

**What it does:**
1. Stops Prometheus + Grafana containers
2. Removes containers (keeps data)
3. Shows reminder to close server ports

**Usage:**
```bash
./scripts/stop-monitoring.sh
```

**What happens behind the scenes:**
- Runs `docker-compose -f docker-compose-monitoring.yml down`
- Preserves `prometheus_data` and `grafana_data` volumes
- Cleans up Docker network

**Data preservation:**
- ✅ Grafana dashboards kept
- ✅ Prometheus metrics kept (until you run `docker-compose down -v`)

---

### `check-monitoring.sh`

**What it does:**
1. Checks if .env exists and valid
2. Checks if prometheus config exists
3. Checks if containers running
4. Tests server connectivity
5. Tests if ports open on server

**Usage:**
```bash
./scripts/check-monitoring.sh
```

**Example output:**
```
🔍 SMS Bridge Monitoring Health Check

Configuration:
  ✅ .env found
  ✅ SMS_BRIDGE_URL set
  ✅ prometheus-remote.yml found

Docker:
  ✅ Docker daemon running
  ✅ Prometheus container: Running
  ✅ Grafana container: Running

Server Connectivity:
  ✅ Server reachable (ping successful)
  ✅ HTTPS working (200 OK)

Monitoring Ports:
  ✅ Port 9100 (metrics): OPEN
  ❌ Port 5433 (postgres): CLOSED
  ❌ Port 6380 (redis): CLOSED

Summary: 2 issues found
  - Open postgres and redis ports via Admin UI
```

---

## Troubleshooting

### "prometheus-remote.yml not found"

**Problem:** Missing Prometheus configuration file

**Solution:**
```bash
# Export from Admin UI
Login → Monitoring → Port Configuration → Export Prometheus Config
# Save as: config/prometheus-remote.yml

# Or download via curl
curl -u admin:password \
  https://sms-bridge.yourdomain.com/admin/monitoring/export-prometheus-config \
  -o config/prometheus-remote.yml
```

---

### Grafana shows "No data"

**Problem:** Prometheus can't scrape metrics from server

**Possible causes:**
1. ❌ Ports not open on server
2. ❌ Firewall blocking connection
3. ❌ Wrong server URL in config

**Solution:**
```bash
# 1. Check if ports open (Admin UI)
Login → Monitoring → Port Management → Status

# 2. Test connectivity
curl -I https://sms-bridge.yourdomain.com:9100/metrics
# Should return: 200 OK

# 3. Check Prometheus targets
Open: http://localhost:9090/targets
# Should show: sms_receiver (UP)

# 4. If DOWN, check Prometheus logs
docker logs prometheus
```

---

### "Port already in use" (Docker start fails)

**Problem:** Ports 3000 or 9090 already used by another application

**Solution:**
```bash
# Check what's using the port
sudo lsof -i :3000  # For Grafana
sudo lsof -i :9090  # For Prometheus

# Option 1: Stop the conflicting service
# (depends on what's using it)

# Option 2: Change ports in docker-compose
nano docker-compose-monitoring.yml
# Change:
#   ports: ["3000:3000"]  → ["3001:3000"]
#   ports: ["9090:9090"]  → ["9091:9090"]
```

---

### Containers won't start

**Problem:** Docker containers fail to start

**Solution:**
```bash
# Check logs
docker-compose -f docker-compose-monitoring.yml logs

# Common issues:

# 1. Invalid prometheus config
docker logs prometheus 2>&1 | grep -i error

# 2. Grafana plugin issues
docker logs grafana 2>&1 | grep -i error

# 3. Permission issues (volumes)
ls -la config/
# Should be readable by current user

# 4. Docker daemon not running
sudo systemctl status docker
# Should show: active (running)
```

---

### Changed port numbers, now monitoring broken

**Problem:** You changed port configuration in Admin UI but didn't update laptop

**Solution:**
```bash
# 1. Re-export prometheus config from Admin UI
Login → Monitoring → Port Configuration → Export Prometheus Config

# 2. Replace old config
mv ~/Downloads/prometheus-remote.yml config/
# (Overwrite existing file)

# 3. Restart monitoring if running
./scripts/stop-monitoring.sh
./scripts/start-monitoring.sh

# 4. Verify new ports being used
docker logs prometheus | grep "Server listening"
```

---

## Advanced Usage

### SSH Tunnel (More Secure Alternative)

Instead of opening ports via Admin UI, use SSH tunnels:

```bash
# Setup SSH tunnel for postgres
ssh -L 5432:localhost:5432 user@sms-bridge-server

# Connect DBeaver to localhost:5432
# (Encrypted through SSH tunnel, no exposed port)

# Setup SSH tunnel for metrics
ssh -L 9100:localhost:8080 user@sms-bridge-server

# Update prometheus config to scrape localhost:9100
```

**Benefits:**
- ✅ No ports exposed to internet
- ✅ Encrypted connection
- ✅ No Admin UI needed

**Drawbacks:**
- ❌ More complex setup
- ❌ Requires SSH access
- ❌ Must maintain tunnel while monitoring

---

### Custom Grafana Dashboards

**Create your own dashboards:**

1. Login to Grafana: http://localhost:3000
2. Navigate: **Dashboards → New Dashboard**
3. Add panel → Query:
   ```promql
   rate(sms_requests_total[5m])
   ```
4. Save dashboard
5. Export dashboard: **Share → Export → Save to file**
6. Add to repo: `coolify-monitoring/config/grafana-dashboards/`

**Dashboard persists** in `grafana_data` volume across restarts.

---

### Long-Term Metrics Storage

**Problem:** Prometheus only keeps metrics while container runs

**Solution:** Configure Prometheus persistence (already done by default)

```yaml
# docker-compose-monitoring.yml
services:
  prometheus:
    volumes:
      - prometheus_data:/prometheus
    command:
      - '--storage.tsdb.retention.time=7d'  # Keep 7 days
      - '--storage.tsdb.path=/prometheus'
```

**Metrics persist** across `stop-monitoring.sh` runs (unless you run `docker-compose down -v`).

---

## What Changes When?

### Port Configuration Changes (Rare)

**Scenario:** You want to change external port 9100 → 9200

```
1. Admin UI → Close all open ports first
2. Admin UI → Port Configuration → Change 9100 to 9200
3. Admin UI → Export Prometheus Config (download new file)
4. Laptop → Replace config/prometheus-remote.yml
5. Laptop → Restart monitoring if running
   docker-compose -f docker-compose-monitoring.yml restart

Next time you open ports, they use 9200 (not 9100)
```

### Daily Monitoring (Frequent)

**Scenario:** Regular monitoring session

```
1. Admin UI → Open ports (60 min)
2. Laptop → start-monitoring.sh
3. Monitor for 30 minutes
4. Laptop → stop-monitoring.sh
5. Admin UI → Close ports (or wait for auto-close)

NO configuration changes needed!
```

---

## Quick Reference

### Configuration Sources

| Setting | Source | Configured Via |
|---------|--------|----------------|
| **Server URL** | `.env` (laptop) | Manual edit |
| **Monitoring Ports** | `sms_settings.json` (server) | Admin UI |
| **Grafana Password** | `.env` (laptop) | Manual edit |
| **Database Credentials** | `.env` (laptop) | Copy from server |

### Port Numbers Reference

| Service | Internal Port | External Port (Default) | Configurable? |
|---------|---------------|------------------------|---------------|
| SMS Bridge | 8080 | 8080 | No (always exposed) |
| Metrics | 8080 | 9100 | Yes (via Admin UI) |
| PostgreSQL | 5432 | 5433 | Yes (via Admin UI) |
| Redis | 6379 | 6380 | Yes (via Admin UI) |

---

## Questions?

- **Security concerns:** See [docs/core/ADMIN_SECURITY.md](core/ADMIN_SECURITY.md)
- **Technical details:** See [docs/core/SMS_Bridge_monitoring_spec_v2.3.md](core/SMS_Bridge_monitoring_spec_v2.3.md)
- **Code examples:** See [docs/core/SMS_Bridge_monitoring_snippets_v2.3.md](core/SMS_Bridge_monitoring_snippets_v2.3.md)
- **General help:** Open GitHub issue or check [README](../README.md)

---

**Last Updated:** January 13, 2026  
**Version:** 2.3  
**Status:** Ready for implementation

**Happy Monitoring!** 🚀📊
