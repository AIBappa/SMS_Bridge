# SMS Bridge Best Practices

This document outlines best practices for operating and maintaining the SMS Bridge system, including cybersecurity, monitoring, and backup procedures.

## Cybersecurity Best Practices

### Credential Management
- Use Ansible Vault to encrypt sensitive credentials in `vault.yml`.
- Avoid hardcoding usernames, password#### Maintenance Operations
### Credential Management
- Use Ansible Vault to encrypt sensitive credentials and API keys in configuration files.
- Regularly rotate credentials and update the vault file.

### Database Security
- Implement custom database usernames instead of default users to reduce unauthorized access risks.
- Ensure proper privileges are granted to database users (e.g., sms_user) on required tables.
- Use PgBouncer for connection pooling to enhance security and performance.
- Disable or secure the default PostgreSQL user to prevent exploitation.

### General Security
- Run containers with minimal privileges and use Docker's security features.
- Implement network segmentation using Docker networks.
- Regularly update Docker images and dependencies to patch vulnerabilities.
- Monitor for suspicious activities using logs and alerts.

## Monitoring Best Practices

### Prometheus and Grafana Setup
- Use Prometheus to collect metrics from services like PostgreSQL, Redis, and the SMS receiver.
- Configure exporters (e.g., postgres_exporter, redis_exporter) for detailed monitoring.
- Set up Grafana dashboards for visualizing metrics, such as database performance, cache hits, and SMS processing rates.
- Define alerts in Prometheus for critical events, like high error rates or resource exhaustion.

#### Monitoring PostgreSQL with Prometheus and Grafana
- **Install postgres_exporter**: Deploy the postgres_exporter container to expose PostgreSQL metrics. Configure it with database credentials from Ansible Vault.
- **Prometheus Configuration**: Add a scrape job in prometheus.yml to target the postgres_exporter endpoint (e.g., `http://postgres_exporter:9187/metrics`).
- **Grafana Dashboards**: Import pre-built PostgreSQL dashboards (e.g., ID 9628) or create custom ones to visualize metrics like:
  - Active connections and connection pools.
  - Query execution time and slow queries.
  - Database size, table sizes, and index usage.
  - Transaction rates and lock waits.
- **Alerts in Prometheus**: Set up rules for alerts such as:
  - High number of active connections (e.g., >80% of max_connections).
  - Replication lag exceeding thresholds.
  - Increased error rates in queries.
  - Low disk space on database volumes.
- **Integration with PgBouncer**: Monitor connection pooling metrics to ensure efficient resource usage and detect bottlenecks.

#### Automated Grafana Setup (New in Setup Script)
The Ansible playbook now includes automated Grafana configuration:
- **Automatic Data Source**: Prometheus is automatically configured as the default data source.
- **Pre-built Dashboard**: A PostgreSQL monitoring dashboard is automatically imported showing database connections and size.
- **Access**: Open `http://localhost:3001`, log in with `admin` and your `grafana_admin_password` from vault.
- **Ready to Use**: No manual configuration needed - dashboards and data source are pre-configured.
- **Customization**: You can still import additional dashboards (like ID 9628) or create custom ones through the UI.

#### Deployment Status ✅
- **All Services Running**: PostgreSQL, Redis, Prometheus, Grafana, PgBouncer, and exporters are operational.
- **Health Checks**: SMS receiver health endpoint responds correctly at `http://localhost:8080/health`.
- **Metrics Available**: Both PostgreSQL (port 9187) and Redis (port 9121) exporters are providing metrics.
- **Grafana Ready**: Dashboard accessible at `http://localhost:3001` with automated configuration.
- **Database Schema**: All tables created successfully with `IF NOT EXISTS` protection against duplicates.

### Health Checks and Logging
- Implement health endpoints in services (e.g., /health in the SMS receiver) for automated monitoring.
- Use rotating log handlers in Python applications to manage log files efficiently.
- Mount host volumes for persistent logging to ensure logs are retained across container restarts.
- Monitor system health regularly to validate end-to-end SMS processing workflows.

### Key Metrics to Monitor
- Database connection pools and query performance.
- Redis cache hit/miss ratios and memory usage.
- SMS receiver throughput, error rates, and latency.
- Container resource usage (CPU, memory, disk).

### Useful Docker Commands for Monitoring
- Check running containers: `docker ps`
- View container logs: `docker logs <container_name>`
- Monitor real-time resource usage: `docker stats`
- Inspect container details: `docker inspect <container_name>`
- Access container shell for debugging: `docker exec -it <container_name> /bin/bash`

## Backup Best Practices

### PostgreSQL Backups
- Use `pg_dump` for logical backups of the database schema and data.
- Schedule regular backups (e.g., daily) and store them securely off-site or in cloud storage.
- Test backup restoration procedures periodically to ensure data integrity.
- Consider point-in-time recovery (PITR) for critical data.

### Redis Backups
- Enable RDB snapshots for automatic backups of Redis data.
- Configure snapshot intervals based on data volatility (e.g., every 15 minutes).
- Store backups in persistent volumes or external storage.
- Use `redis-cli` commands for manual backups if needed.

## Redis Cache Management

### Viewing Redis Cache Contents

#### Docker Deployment - View Cache Contents
```bash
# Get Redis password from vault
REDIS_PASSWORD=$(ansible-vault view vault.yml | grep redis_password | cut -d':' -f2 | tr -d ' ')

# Connect to Redis and view all keys
docker exec redis redis-cli -a $REDIS_PASSWORD KEYS "*"

# View SMS numbers cache (main cache for duplicate prevention)
docker exec redis redis-cli -a $REDIS_PASSWORD SMEMBERS out_sms_numbers

# View cache statistics
docker exec redis redis-cli -a $REDIS_PASSWORD INFO

# Check specific key type and value
docker exec redis redis-cli -a $REDIS_PASSWORD TYPE out_sms_numbers
docker exec redis redis-cli -a $REDIS_PASSWORD SCARD out_sms_numbers  # Count members in set
```

#### K3s Deployment - View Cache Contents
```bash
# Get Redis password from Kubernetes secret
REDIS_PASSWORD=$(kubectl get secret sms-bridge-secrets -n sms-bridge -o jsonpath='{.data.redis-password}' | base64 -d)

# Connect to Redis pod and view all keys
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD KEYS "*"

# View SMS numbers cache
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SMEMBERS out_sms_numbers

# View cache statistics
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD INFO

# Check specific key details
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD TYPE out_sms_numbers
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SCARD out_sms_numbers
```

### Manual Redis Cache Cleaning and Updates

#### Clear Entire Cache (Use with Caution)
```bash
# Docker deployment
docker exec redis redis-cli -a $REDIS_PASSWORD FLUSHALL

# K3s deployment
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD FLUSHALL
```

#### Remove Specific Mobile Numbers from Cache
```bash
# Remove single number from duplicate prevention cache
MOBILE_NUMBER="99XXYYZZAA"

# Docker
docker exec redis redis-cli -a $REDIS_PASSWORD SREM out_sms_numbers $MOBILE_NUMBER

# K3s
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SREM out_sms_numbers $MOBILE_NUMBER
```

#### Bulk Remove Multiple Numbers
```bash
# Remove multiple numbers at once
MOBILE_NUMBERS="99XXYYZZAA 9876543210 9123456789"

# Docker
for number in $MOBILE_NUMBERS; do
  docker exec redis redis-cli -a $REDIS_PASSWORD SREM out_sms_numbers $number
done

# K3s
for number in $MOBILE_NUMBERS; do
  kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SREM out_sms_numbers $number
done
```

#### Add Numbers to Cache Manually
```bash
# Add single number to cache (useful for testing)
MOBILE_NUMBER="99XXYYZZAA"

# Docker
docker exec redis redis-cli -a $REDIS_PASSWORD SADD out_sms_numbers $MOBILE_NUMBER

# K3s
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SADD out_sms_numbers $MOBILE_NUMBER
```

### Redis Cache Maintenance and Troubleshooting

#### Check Cache Consistency with Database
```bash
# Compare Redis cache with database out_sms table
echo "=== Database SMS Numbers ==="
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT DISTINCT local_mobile FROM out_sms ORDER BY local_mobile;"

echo "=== Redis Cache Contents ==="
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SMEMBERS out_sms_numbers | sort
```

#### Rebuild Cache from Database (if cache is corrupted)
```bash
# Clear current cache
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD DEL out_sms_numbers

# Rebuild from database
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT DISTINCT local_mobile FROM out_sms;" | tail -n +3 | head -n -2 | \
  xargs -I {} kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SADD out_sms_numbers {}
```

#### Monitor Cache Performance
```bash
# View cache hit/miss statistics
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD INFO stats | grep -E "keyspace_hits|keyspace_misses"

# Calculate hit rate
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD INFO stats | \
  awk '/keyspace_hits/{hits=$2} /keyspace_misses/{misses=$2} END{total=hits+misses; if(total>0) print "Hit Rate:", (hits/total)*100 "%"}'
```

#### Redis Memory Management
```bash
# Check memory usage
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD INFO memory | grep -E "used_memory|used_memory_human"

# View largest keys (potential memory hogs)
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD --bigkeys

# Check memory fragmentation
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD INFO memory | grep -E "mem_fragmentation_ratio"
```

#### Redis Connectivity and Health Checks
```bash
# Test basic connectivity
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD PING

# Check connected clients
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD INFO clients | grep connected_clients

# View slow queries (if any)
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SLOWLOG GET 10

# Check for blocked clients
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD CLIENT LIST | grep -c "flags=b"
```

### Advanced Redis Operations

#### Export Cache Contents for Backup/Analysis
```bash
# Export all cache contents to file
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD --scan --pattern "*" > redis_keys_backup.txt

# Export SMS numbers specifically
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SMEMBERS out_sms_numbers > sms_numbers_backup.txt
```

#### Import Cache Contents from Backup
```bash
# Import SMS numbers from backup file
kubectl exec -n sms-bridge deployment/redis -- bash -c "
REDIS_PASSWORD=\$(cat /run/secrets/redis-password)
cat /tmp/sms_numbers_backup.txt | xargs -I {} redis-cli -a \$REDIS_PASSWORD SADD out_sms_numbers {}
"
```

#### Redis Configuration Inspection
```bash
# View current Redis configuration
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD CONFIG GET "*"

# Check specific configuration values
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD CONFIG GET maxmemory
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD CONFIG GET tcp-keepalive
```

### Common Redis Issues and Solutions

#### Cache Inconsistency Issues
**Problem**: Redis cache doesn't match database contents
**Solution**:
```bash
# Rebuild cache from database
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT string_agg(DISTINCT local_mobile, ' ') FROM out_sms;" | \
  xargs kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD DEL out_sms_numbers && \
  kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT DISTINCT local_mobile FROM out_sms;" | tail -n +3 | head -n -2 | \
  xargs -I {} kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD SADD out_sms_numbers {}
```

#### Memory Issues
**Problem**: Redis using too much memory
**Solution**:
```bash
# Check memory usage and largest keys
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD INFO memory
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD --bigkeys

# If needed, clear old/unused data (be careful!)
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD DEL out_sms_numbers
```

#### Connection Issues
**Problem**: SMS receiver can't connect to Redis
**Solution**:
```bash
# Check Redis connectivity from SMS receiver
kubectl exec -n sms-bridge deployment/sms-receiver -- redis-cli -h redis -a $REDIS_PASSWORD PING

# Check Redis pod status
kubectl get pods -n sms-bridge | grep redis

# View Redis logs
kubectl logs -n sms-bridge deployment/redis --tail=20
```

### General Backup Guidelines
- Automate backups using cron jobs or Ansible playbooks.
- Encrypt backups to protect sensitive data.
- Document backup and restoration processes in runbooks.
- Monitor backup success and alert on failures.

### Useful Docker Commands for Backup
- Backup PostgreSQL database: `docker exec <postgres_container> pg_dump -U <username> -h localhost <database> > backup.sql`
- Backup Redis data: `docker exec <redis_container> redis-cli save`
- Backup a Docker volume: `docker run --rm -v <volume_name>:/data -v $(pwd):/backup alpine tar czf /backup/backup.tar.gz -C /data .`
- Restore PostgreSQL from backup: `docker exec -i <postgres_container> psql -U <username> -d <database> < backup.sql`
- Restore Redis from RDB file: Copy the RDB file to the Redis container and restart.

## Additional Recommendations

- Regularly review and update Ansible playbooks for infrastructure changes.
- Perform security audits and penetration testing on the system.
- Document incident response procedures for handling breaches or failures.
- Ensure high availability by considering load balancers and failover mechanisms for production deployments.

For more details on the system setup, refer to the Ansible playbooks in `ansible-k3s/` (production) or `ansible-docker/` (development) folders and configuration files.

## Access and Credentials

### Service Ports and Access Links
- **PostgreSQL Database**: Port 5432, access via `localhost:5432` (user: `postgres`, password: `pg_password` from vault).
- **PgBouncer**: Port 6432, access via `localhost:6432` (user: `postgres`, password: `pg_password` from vault).
- **Redis Cache**: Port 6379, access via `localhost:6379` (password: `redis_password` from vault).
- **Prometheus**: Port 9090, access via `http://localhost:9090` (no password).
- **Grafana**: Port 3001, access via `http://localhost:3001` (admin user: `admin`, password: `grafana_admin_password` from vault).
- **Python SMS Receiver**: Port 8080, access via `http://localhost:8080` (API key: `cf_api_key` from vault for external forwarding).
- **Postgres Exporter**: Port 9187, metrics at `http://localhost:9187/metrics`.
- **Redis Exporter**: Port 9121, metrics at `http://localhost:9121/metrics`.

### Retrieving Passwords from Vault
All passwords are encrypted in `vault.yml`. To access:
- Run `ansible-vault view vault.yml` to view decrypted contents in the terminal.
- Alternatively, use `ansible-vault edit vault.yml` to open the file in your default text editor (e.g., vim) for viewing/editing; it will decrypt temporarily and re-encrypt on save.
- Use the vault password you set during creation.
- Key variables: `pg_password`, `redis_password`, `grafana_admin_password`, `cf_api_key`, `cf_backend_url`, `hash_secret_key`.

#### Setting Up Default Text Editor
- **On Linux (Bash)**: Ansible uses the `EDITOR` environment variable. Set it temporarily with `export EDITOR=vim` or permanently by adding `export EDITOR=vim` to `~/.bashrc`. Common editors: `vim`, `nano`, `emacs`, `gedit`.
- **On Windows**: If using WSL, Git Bash, or Cygwin, set `export EDITOR=notepad` or `export EDITOR="C:/Program Files/Notepad++/notepad++.exe"`. Common editors: Notepad, Notepad++, VS Code. Note: Direct Windows Ansible may require adjustments.

## Testing and Validation

### Key Endpoint Tests
Use these curl commands to test all system endpoints and validate functionality:

#### 1. Health Check
```bash
curl -s http://localhost:8080/health
# Expected response: {"status":"healthy"}
```

#### 2. SMS Receiver - Send Test SMS
```bash
curl -X POST http://localhost:8080/sms/receive \
  -H "Content-Type: application/json" \
  -d '{
    "sender_number": "+1234567890",
    "sms_message": "This is a test SMS message from mobile 9876543210",
    "received_timestamp": "2025-09-06T12:00:00Z"
  }'
# Expected response: {"status":"received"}
```

#### 3. Prometheus Metrics
```bash
# Check if Prometheus is collecting metrics
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job, health}'

# Check specific PostgreSQL metrics
curl -s http://localhost:9187/metrics | grep -E "pg_stat_database|pg_up"

# Check Redis metrics
curl -s http://localhost:9121/metrics | grep -E "redis_up|redis_connected_clients"
```

#### 4. Database Connectivity Tests
```bash
# Test PostgreSQL direct connection
docker exec postgres psql -U postgres -d sms_bridge -c "SELECT COUNT(*) FROM input_sms;"

# Test PgBouncer connection
docker exec postgres psql -U postgres -h localhost -p 6432 -d sms_bridge -c "SELECT setting_key, setting_value FROM system_settings LIMIT 5;"
```

#### 5. Redis Connectivity Test
```bash
# Test Redis connection and check SMS numbers cache
# Note: You'll need to get the Redis password from vault manually
echo "Use 'ansible-vault view vault.yml' to get redis_password, then:"
echo "docker exec redis redis-cli -a <redis_password> SMEMBERS out_sms_numbers"

# Alternative: Get password and test in one command
REDIS_PASSWORD=$(ansible-vault view vault.yml | grep redis_password | cut -d':' -f2 | tr -d ' ')
docker exec redis redis-cli -a $REDIS_PASSWORD SMEMBERS out_sms_numbers

# Check Redis connectivity and basic info
docker exec redis redis-cli -a $REDIS_PASSWORD INFO | head -20

# Test cache operations
docker exec redis redis-cli -a $REDIS_PASSWORD SCARD out_sms_numbers  # Count cached numbers
docker exec redis redis-cli -a $REDIS_PASSWORD SISMEMBER out_sms_numbers "99XXYYZZAA"  # Check specific number
```

#### 6. SMS Processing Workflow Test
```bash
# Send multiple test SMS messages
for i in {1..3}; do
  curl -X POST http://localhost:8080/sms/receive \
    -H "Content-Type: application/json" \
    -d "{
      \"sender_number\": \"+12345678$i$i\",
      \"sms_message\": \"Test message $i with mobile 987654321$i\",
      \"received_timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }"
  echo " - SMS $i sent"
  sleep 2
done

# Check if messages were processed
echo "Checking processed messages..."
docker exec postgres psql -U postgres -d sms_bridge -c "SELECT COUNT(*) as total_input FROM input_sms;"
docker exec postgres psql -U postgres -d sms_bridge -c "SELECT COUNT(*) as total_output FROM out_sms;"
docker exec postgres psql -U postgres -d sms_bridge -c "SELECT overall_status, COUNT(*) FROM sms_monitor GROUP BY overall_status;"
```

#### 7. Grafana Dashboard Access
```bash
# Open Grafana in browser (manual step)
echo "Open http://localhost:3001 in your browser"
echo "Login: admin"
echo "Password: Use 'ansible-vault view vault.yml' to get grafana_admin_password"
```

### Validation Checklist
After running the tests above, verify:
- [ ] Health endpoint responds with 200 status
- [ ] SMS messages are accepted and stored in `input_sms` table
- [ ] Validation checks process messages (check `sms_monitor` table)
- [ ] Valid messages appear in `out_sms` table and Redis cache
- [ ] Prometheus scrapes metrics from all exporters
- [ ] Grafana displays PostgreSQL dashboard with live data
- [ ] All containers remain healthy after processing load

### Troubleshooting Commands
```bash
# Check container status
docker ps

# View recent logs for specific services
docker logs sms_receiver --tail=50
docker logs postgres --tail=50
docker logs redis --tail=50
docker logs grafana --tail=50

# Monitor real-time resource usage
docker stats

# Restart specific service using Ansible (secure method)
ansible-playbook ansible-docker/restart_sms_bridge.yml --ask-vault-pass

# Check individual container status
docker inspect sms_receiver
docker inspect postgres
```

## Deployment Management

The SMS Bridge system supports two deployment methods:
1. **K3s-based deployment** (Recommended for production)
2. **Docker Compose deployment** (For development/testing)

### K3s Deployment (Production - Recommended)

The K3s deployment provides a complete Kubernetes-based SMS Bridge infrastructure with proper scaling, monitoring, and management capabilities.

#### Available Scripts in `ansible-k3s/` folder:

**Installation Scripts:**
- `install_k3s.yml` - Install K3s Kubernetes cluster
- `setup_sms_bridge_k3s.yml` - Complete fresh SMS Bridge deployment
- `uninstall_k3s.yml` - Remove K3s cluster entirely

**Management Scripts:**
- `upgrade_sms_bridge_k3s.yml` - Apply code/schema updates (preserves data)
- `restart_sms_bridge_k3s.yml` - Restart services only (no code changes)
- `stop_sms_bridge_k3s.yml` - Complete shutdown (destroys data)

#### K3s Quick Start Commands:
```bash
# Navigate to project directory
cd /home/<user>/Documents/Software/SMS_Laptop_Setup/sms_bridge

# 1. Install K3s cluster (one-time setup)
ansible-playbook ansible-k3s/install_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass

# 2. Deploy SMS Bridge infrastructure (fresh installation)
ansible-playbook ansible-k3s/setup_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass

# 3. Apply updates to running system (recommended for updates)
ansible-playbook ansible-k3s/upgrade_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass

# 4. Restart services only (troubleshooting)
ansible-playbook ansible-k3s/restart_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass

# 5. Complete shutdown (destroys all data)
ansible-playbook ansible-k3s/stop_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass
```

### Docker Compose Deployment (Development)

For development and testing, a simpler Docker Compose deployment is available.

#### Available Scripts in `ansible-docker/` folder:

- `setup_sms_bridge.yml` - Deploy using Docker Compose
- `restart_sms_bridge.yml` - Restart Docker containers
- `stop_sms_bridge.yml` - Stop Docker containers

#### Docker Deployment Commands:
```bash
# Navigate to project directory
cd /home/<user>/Documents/Software/SMS_Laptop_Setup/sms_bridge

# Deploy SMS Bridge with Docker Compose
ansible-playbook ansible-docker/setup_sms_bridge.yml --ask-vault-pass

# Restart services
ansible-playbook ansible-docker/restart_sms_bridge.yml --ask-vault-pass

# Stop services  
ansible-playbook ansible-docker/stop_sms_bridge.yml
```

### Script Details

#### K3s Scripts (`ansible-k3s/` folder):

| Script | Purpose | Data Safety | Use Case |
|--------|---------|-------------|----------|
| `install_k3s.yml` | Install K3s cluster | ✅ Safe | One-time cluster setup |
| `setup_sms_bridge_k3s.yml` | Fresh deployment | ⚠️ Destroys data | Initial installation |
| `upgrade_sms_bridge_k3s.yml` | Apply updates | ✅ Preserves data | Deploy new code/schema |
| `restart_sms_bridge_k3s.yml` | Restart pods | ✅ Safe | Troubleshooting |
| `stop_sms_bridge_k3s.yml` | Complete shutdown | ⚠️ Destroys data | Maintenance/cleanup |
| `uninstall_k3s.yml` | Remove K3s | ⚠️ Destroys everything | Complete removal |

#### Docker Scripts (`ansible-docker/` folder):

| Script | Purpose | Data Safety | Use Case |
|--------|---------|-------------|----------|
| `setup_sms_bridge.yml` | Docker deployment | ⚠️ Recreates containers | Development setup |
| `restart_sms_bridge.yml` | Restart containers | ✅ Preserves data | Development restart |
| `stop_sms_bridge.yml` | Stop containers | ✅ Safe stop | Development shutdown |

### Quick Reference Commands

#### K3s SMS Bridge Operations
```bash
# Navigate to project directory first
cd /home/<user>/Documents/Software/SMS_Laptop_Setup/sms_bridge

# === Fresh Installation ===
ansible-playbook ansible-k3s/setup_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass

# === Apply Code/Schema Updates (Recommended for updates) ===
ansible-playbook ansible-k3s/upgrade_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass

# === Restart Services (No code changes) ===
ansible-playbook ansible-k3s/restart_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass

# === Complete Shutdown ===
ansible-playbook ansible-k3s/stop_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass

# === K3s Monitoring Commands ===
# Check pod status
k3s kubectl get pods -n sms-bridge

# View service endpoints  
k3s kubectl get services -n sms-bridge

# Check deployment status
k3s kubectl get deployments -n sms-bridge

# View logs from specific services
k3s kubectl logs -f deployment/sms-receiver -n sms-bridge
k3s kubectl logs -f deployment/postgres -n sms-bridge

# Access database shell
k3s kubectl exec -it deployment/postgres -n sms-bridge -- psql -U postgres -d sms_bridge
```

#### Maintenance Operations
```bash
# === K3s Maintenance ===
# Check cluster status
k3s kubectl cluster-info

# Check node status  
k3s kubectl get nodes

# Check all resources in SMS Bridge namespace
k3s kubectl get all -n sms-bridge

# View detailed pod information
k3s kubectl describe pods -n sms-bridge

# === Docker Maintenance ===
# Clean up unused Docker resources
docker system prune -f

# Check Docker images for SMS Bridge
docker images | grep sms_receiver

# Backup database before maintenance (K3s)
k3s kubectl exec deployment/postgres -n sms-bridge -- pg_dump -U postgres sms_bridge > backup_$(date +%Y%m%d_%H%M%S).sql

# Update individual container images
docker pull postgres:15
docker pull redis:7-alpine
docker pull grafana/grafana
```

## Summary: When to Use Which Script

### 🎯 **Recommended Production Workflow (K3s)**

1. **First-time setup:**
   ```bash
   ansible-playbook ansible-k3s/install_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass
   ansible-playbook ansible-k3s/setup_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass
   ```

   **If re-running setup after previous deployment:**
   ```bash
   # Remove build marker to force image rebuild with updated code
   rm -f /home/$USER/sms_bridge/.image_built
   ansible-playbook ansible-k3s/setup_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass
   ```

2. **Regular updates/new features:**
   ```bash
   ansible-playbook ansible-k3s/upgrade_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass
   ```

3. **Troubleshooting/restart:**
   ```bash
   ansible-playbook ansible-k3s/restart_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass
   ```

4. **Complete shutdown:**
   ```bash
   ansible-playbook ansible-k3s/stop_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass
   ```

### 🧪 **Development Workflow (Docker)**

Use `ansible-docker/` scripts for local development and testing:
```bash
ansible-playbook ansible-docker/setup_sms_bridge.yml --ask-vault-pass
ansible-playbook ansible-docker/restart_sms_bridge.yml --ask-vault-pass
ansible-playbook ansible-docker/stop_sms_bridge.yml
```

### ⚠️ **Critical Notes**

- **Always use `upgrade_sms_bridge_k3s.yml` for code updates** - it preserves data while applying changes
- **Never use `setup_sms_bridge_k3s.yml` on existing systems** - it will destroy data
- **Test in development first** using Docker scripts before applying to K3s production
- **All scripts require vault password** except stop operations

### 🔧 **Troubleshooting**

#### Build Marker Issues
If scripts fail to rebuild Docker images or apply code changes, the build marker may be preventing updates:

```bash
# Remove build marker to force complete rebuild
rm -f /home/$USER/sms_bridge/.image_built

# Then re-run the appropriate script
ansible-playbook ansible-k3s/upgrade_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass
```

**When to remove the marker:**
- SMS server fails to start with "column does not exist" errors
- Code changes not appearing after deployment
- Schema migrations not being applied
- Docker image not rebuilding with latest code

#### Database Schema Issues
If the SMS receiver fails with database column errors:
1. Check if upgrade script completed successfully
2. Remove build marker and re-run upgrade script
3. Verify all tables have required columns using kubectl exec

### 🔍 **Investigation & Debugging**

#### SMS Processing Investigation

**Check SMS Reception and Processing:**
```bash
# Monitor real-time logs from SMS receiver
kubectl logs -n sms-bridge deployment/sms-receiver --tail=20 -f

# Check specific SMS in input_sms table
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT uuid, sender_number, sms_message, received_timestamp FROM input_sms WHERE sender_number LIKE '%PHONE_NUMBER%' ORDER BY received_timestamp DESC;"

# Check SMS processing status in sms_monitor
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT uuid, overall_status, failed_at_check, processing_completed_at FROM sms_monitor WHERE uuid IN (SELECT uuid FROM input_sms WHERE sender_number LIKE '%PHONE_NUMBER%');"

# Check if SMS made it to out_sms table
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT uuid, sender_number, sms_message FROM out_sms WHERE sender_number LIKE '%PHONE_NUMBER%';"
```

**Check for Duplicate SMS Detection:**
```bash
# Check Redis out_sms_numbers set (duplicate prevention)
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a \
  $(kubectl get secret sms-bridge-secrets -n sms-bridge -o jsonpath='{.data.redis-password}' | base64 -d) \
  SMEMBERS out_sms_numbers

# Check if specific number is in duplicate prevention set
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a \
  $(kubectl get secret sms-bridge-secrets -n sms-bridge -o jsonpath='{.data.redis-password}' | base64 -d) \
  SISMEMBER out_sms_numbers "PHONE_NUMBER"

# View Redis cache statistics
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a \
  $(kubectl get secret sms-bridge-secrets -n sms-bridge -o jsonpath='{.data.redis-password}' | base64 -d) \
  INFO | grep -E "connected_clients|used_memory|keyspace"
```

#### Batch Processor Debugging

**Check Batch Processing Settings:**
```bash
# View current batch processor configuration
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT setting_key, setting_value FROM system_settings WHERE setting_key IN ('batch_size', 'batch_timeout', 'last_processed_uuid', 'permitted_headers') ORDER BY setting_key;"
```

**Reset Batch Processing (if stuck):**
```bash
# Reset last_processed_uuid to reprocess all SMS
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "UPDATE system_settings SET setting_value = '00000000-0000-0000-0000-000000000000' WHERE setting_key = 'last_processed_uuid';"

# Check batch processor logs
kubectl logs -n sms-bridge deployment/sms-receiver | grep -i "batch\|processing\|timeout"
```

#### Network Traffic Monitoring

**Monitor SMS Traffic with tcpdump:**
```bash
# Basic traffic monitoring on SMS port (30080)
sudo tcpdump -i any -n port 30080

# Detailed HTTP content capture (shows actual SMS data)
sudo tcpdump -i any -n -A -s 0 'port 30080 and (((ip[2:2] - ((ip[0]&0xf)<<2)) - ((tcp[12]&0xf0)>>2)) != 0)'

# Monitor specific IP (e.g., mobile device)
sudo tcpdump -i any -n -A host 192.168.1.27 and port 30080
```

#### Database Deep Dive

**Check Complete SMS Processing Pipeline:**
```bash
# Full SMS processing trace for specific UUID
SMS_UUID="YOUR_SMS_UUID_HERE"
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT 'input_sms' as table_name, uuid, sender_number, sms_message, received_timestamp, country_code, local_mobile FROM input_sms WHERE uuid = '$SMS_UUID'
   UNION ALL
   SELECT 'sms_monitor' as table_name, uuid::text, overall_status, failed_at_check, processing_completed_at::text, '' as country_code, '' as local_mobile FROM sms_monitor WHERE uuid = '$SMS_UUID'
   UNION ALL  
   SELECT 'out_sms' as table_name, uuid::text, sender_number, sms_message, '' as received_timestamp, country_code, local_mobile FROM out_sms WHERE uuid = '$SMS_UUID';"

# Check onboarding records for mobile number
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT mobile_number, salt, hash, request_timestamp, is_active FROM onboarding_mobile WHERE mobile_number = 'PHONE_NUMBER';"

# View recent SMS processing activity
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT i.uuid, i.sender_number, i.sms_message, i.received_timestamp, m.overall_status, m.failed_at_check 
   FROM input_sms i 
   LEFT JOIN sms_monitor m ON i.uuid = m.uuid 
   ORDER BY i.received_timestamp DESC LIMIT 10;"
```

#### System Health Checks

**Verify All Services are Running:**
```bash
# Check all pods status
kubectl get pods -n sms-bridge

# Check services and ports
kubectl get services -n sms-bridge

# Check deployment status
kubectl get deployments -n sms-bridge

# Check for any failing pods
kubectl get pods -n sms-bridge | grep -v Running
```

**Check Resource Usage:**
```bash
# Pod resource usage
kubectl top pods -n sms-bridge

# Node resource usage
kubectl top nodes

# Check pod logs for errors
kubectl logs -n sms-bridge deployment/sms-receiver --previous
```

#### Configuration Validation

**Verify Settings and Secrets:**
```bash
# Check all system settings
kubectl exec -n sms-bridge deployment/postgres -- psql -U postgres -d sms_bridge -c \
  "SELECT setting_key, setting_value FROM system_settings ORDER BY setting_key;"

# Verify secrets are properly configured
kubectl get secrets -n sms-bridge
kubectl describe secret sms-bridge-secrets -n sms-bridge

# Check environment variables in SMS receiver pod
kubectl exec -n sms-bridge deployment/sms-receiver -- env | grep -E "POSTGRES|REDIS|CF_|HASH"
```

#### Common Issue Patterns

**Form Parsing Errors:**
- Look for "python-multipart" errors in logs
- Indicates missing dependency in Docker image

**UUID Comparison Issues:**
- Check if `last_processed_uuid` is preventing new SMS processing
- Reset UUID to `00000000-0000-0000-0000-000000000000` if needed

**Duplicate Detection:**
- SMS failing at "duplicate" check means mobile number already processed
- Check Redis `out_sms_numbers` set for existing numbers

**Header Validation Failures:**
- Verify `permitted_headers` setting contains expected headers (e.g., "ONBOARD")
- Check SMS message format matches `HEADER:hash` pattern

**Database Connection Issues:**
- Verify PgBouncer is running and accessible
- Check PostgreSQL pod logs for connection errors
