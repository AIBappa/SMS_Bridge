# SMS Bridge v2.3 - Deployment Checklist

## ✅ Pre-Deployment Checklist

### 1. Backup Current System
- [ ] Backup current database
  ```bash
  docker exec sms_postgres pg_dump -U postgres sms_bridge > backup_pre_v2.3.sql
  ```
- [ ] Backup current docker-compose.yml
  ```bash
  cp coolify/docker-compose.yml coolify/docker-compose.yml.backup
  ```
- [ ] Backup sms_settings.json (if exists)
  ```bash
  cp core/config/sms_settings.json core/config/sms_settings.json.backup
  ```

### 2. Server Preparation
- [ ] Ensure Docker and Docker Compose installed
- [ ] Verify iptables available on host
- [ ] Check available disk space (at least 2GB free)
- [ ] Note current container IDs for reference
  ```bash
  docker ps -a
  ```

### 3. Code Deployment
- [ ] Pull/copy v2.3 code to server
- [ ] Verify all new files present:
  ```bash
  ls -la coolify/docker-compose-main.yml
  ls -la core/admin/port_management.py
  ls -la core/admin/admin_routes.py
  ls -la core/admin/background_tasks.py
  ls -la core/config/sms_settings.json
  ```

## 🚀 Deployment Steps

### Step 1: Stop Current Services
```bash
cd coolify
docker-compose down
```

### Step 2: Start Services
```bash
# Start all services
docker-compose -f docker-compose-main.yml up -d

# Wait for services to be ready
sleep 10

# Verify settings loaded
docker exec sms_receiver cat /app/config/sms_settings.json | grep -A 10 monitoring_ports
```

### Step 3: Update Configuration Files

**Create/Update sms_settings.json:**
```bash
cd core/config
# If file doesn't exist, copy from template
cp sms_settings.json.example sms_settings.json

# Verify monitoring_ports section exists
cat sms_settings.json | jq '.settings.monitoring_ports'
```

**Update Environment Variables:**
```bash
cd coolify
nano .env  # or vim .env
```

Add these lines if not present:
```bash
# Server IP (for monitoring connections)
SERVER_IP=your.actual.ip.address  # or "auto" for auto-detection

# Enable monitoring features
MONITORING_ENABLED=true
```

### Step 4: Start New Stack
```bash
cd coolify
docker-compose -f docker-compose-main.yml up -d
```

### Step 5: Verify Services
```bash
# Check all containers running
docker ps

# Expected containers:
# - sms_receiver
# - sms_postgres
# - sms_pgbouncer
# - sms_redis

# Check logs
docker logs sms_receiver

# Should see:
# - "Starting SMS Bridge v2.3.0"
# - "Monitoring routes mounted at /admin/monitoring"
# - "Monitoring background tasks started"
# - "Startup complete"
```

### Step 6: Test Admin UI
```bash
# Health check
curl -f http://localhost:8080/health

# Test admin login
curl -X POST http://localhost:8080/admin/login \
  -d "username=admin&password=your_password"

# Should redirect to admin dashboard
```

### Step 7: Test Monitoring Endpoints
```bash
# List monitoring services
curl http://localhost:8080/admin/monitoring/services \
  -H "Cookie: session=YOUR_SESSION_COOKIE"

# Should return monitoring services configuration
```

## 🔧 Post-Deployment Testing

### Test 1: Open a Port
1. Login to Admin UI: `http://your-domain.com/admin`
2. Navigate to Monitoring section
3. Click "Open Port" for metrics service
4. Duration: 30 minutes
5. Verify:
   - Connection info displayed
   - Port listed in active ports
   - Expiration time shown

### Test 2: Verify iptables Rule
```bash
# Check iptables rules (on host, not in container)
sudo iptables -L INPUT -n | grep 9100

# Should show ACCEPT rule for configured port
```

### Test 3: Close a Port
1. In Admin UI, click "Close Port"
2. Verify:
   - Port removed from active list
   - iptables rule removed

### Test 4: Export Prometheus Config
1. Navigate to Monitoring → Export Config
2. Download prometheus-remote.yml
3. Verify file contains correct server IP and ports

### Test 5: Background Task
1. Open a port with 1 minute duration
2. Wait 2 minutes
3. Check port status
4. Should be automatically closed

```bash
# Check port mappings file
docker exec sms_receiver cat /app/logs/port_mappings.json
# Should show empty or no expired entries
```

## 💻 Laptop Setup

### Step 1: Clone Repository on Laptop
```bash
git clone https://github.com/your-org/sms-bridge.git
cd sms-bridge/coolify-monitoring
```

### Step 2: Configure Laptop Monitoring
```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
# Set: SMS_BRIDGE_URL=https://your-domain.com
```

### Step 3: Download Prometheus Config
```bash
# From Admin UI or via curl
curl -u admin:password \
  https://your-domain.com/admin/monitoring/export-prometheus-config \
  -o config/prometheus-remote.yml
```

### Step 4: Test Monitoring Stack
```bash
# Start monitoring
./scripts/start-monitoring.sh

# Wait for services to start
sleep 30

# Check Prometheus
curl http://localhost:9090/-/healthy

# Check Grafana
curl http://localhost:3000/api/health

# View Prometheus targets
open http://localhost:9090/targets

# Access Grafana
open http://localhost:3000
# Login: admin/admin
```

## 🔍 Troubleshooting

### Issue: Containers won't start
**Solution:**
```bash
# Check logs
docker-compose -f docker-compose-main.yml logs

# Common issues:
# - Port 8080 already in use
# - Database migration not run
# - Environment variables missing
```

### Issue: Settings not loading
**Solution:**
```bash
# Verify settings file exists and is valid JSON
docker exec sms_receiver cat /app/config/sms_settings.json | jq .

# Check for syntax errors
docker exec sms_receiver python -c "import json; json.load(open('/app/config/sms_settings.json'))"

# Restart service to reload settings
docker restart sms_receiver
```

### Issue: Ports won't open
**Solution:**
```bash
# Check NET_ADMIN capability
docker inspect sms_receiver | grep -A 10 CapAdd

# Should show: "NET_ADMIN"

# Check iptables available in container
docker exec sms_receiver which iptables

# If missing, container needs rebuild with iptables installed
```

### Issue: Can't connect from laptop
**Solution:**
```bash
# 1. Verify port open on server
curl https://your-domain.com/admin/monitoring/port-status

# 2. Check firewall on server
sudo iptables -L -n | grep 9100

# 3. Check Prometheus config on laptop
cat coolify-monitoring/config/prometheus-remote.yml

# 4. Verify server IP is correct
ping YOUR_SERVER_IP

# 5. Check if server port is reachable
nc -zv YOUR_SERVER_IP 9100
```

### Issue: Monitoring routes not available
**Solution:**
```bash
# Check if monitoring enabled
docker exec sms_receiver env | grep MONITORING

# Check logs for mount message
docker logs sms_receiver | grep "Monitoring routes"

# Should see: "Monitoring routes mounted at /admin/monitoring"
```

## 📊 Verification Commands

### Settings & Configuration
```bash
# Check monitoring port configuration
docker exec sms_receiver cat /app/config/sms_settings.json | jq '.settings.monitoring_ports'

# View currently open ports from memory
docker exec sms_receiver cat /app/logs/port_mappings.json | jq .

# View settings history in database
docker exec sms_postgres psql -U postgres -d sms_bridge -c \
  "SELECT version_id, created_at, created_by, is_active FROM settings_history ORDER BY created_at DESC LIMIT 10;"
```

### Logs
```bash
# Application logs
docker exec sms_receiver cat /app/logs/sms_bridge.log | tail -50

# Check for monitoring events
docker logs sms_receiver | grep -i "monitoring\|port"
```

### Network
```bash
# Check container network
docker network inspect coolify_sms_bridge_network

# Check exposed ports
docker ps --format "table {{.Names}}\t{{.Ports}}"

# Should only show 8080 exposed for sms_receiver
```

## ✅ Success Criteria

- [ ] All containers running
- [ ] Database migration completed
- [ ] Monitoring routes accessible
- [ ] Can open/close ports via Admin UI
- [ ] iptables rules created/removed correctly
- [ ] Background auto-close task working
- [ ] Laptop monitoring stack connects successfully
- [ ] Prometheus scraping metrics
- [ ] Grafana displays data
- [ ] Audit trail records all events

## 🎯 Next Steps After Deployment

1. **Create Grafana Dashboards**
   - SMS request rates
   - Error rates
   - Queue depths
   - Database metrics

2. **Set Up Alerts**
   - High error rates
   - Queue backlog
   - Port left open too long

3. **Document Custom Procedures**
   - Team-specific workflows
   - Emergency procedures
   - Regular maintenance tasks

4. **Train Team**
   - How to open ports
   - How to start monitoring
   - How to interpret dashboards

## 📝 Rollback Procedure

If issues occur:

```bash
# Stop new stack
docker-compose -f docker-compose-main.yml down

# Restore old stack
docker-compose -f docker-compose.yml.backup up -d

# Restore database (if needed)
docker exec -i sms_postgres psql -U postgres sms_bridge < backup_pre_v2.3.sql

# Verify services
docker ps
curl http://localhost:8080/health
```

---

**Version**: 2.3.0  
**Date**: 2026-01-13  
**Status**: Ready for Deployment
