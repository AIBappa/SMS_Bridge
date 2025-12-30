# SMS Bridge Best Practices

This document outlines best practices for deploying, operating, and maintaining the SMS Bridge system. For application-specific details (API endpoints, Redis keys, database schema), refer to `SMS_Bridge_tech_spec_v2.2.md`.

## Cybersecurity Best Practices

### Credential Management
- Use Ansible Vault to encrypt sensitive credentials and API keys in configuration files.
- Regularly rotate credentials and update the vault file.

### Database Security
- Implement custom database usernames instead of default users to reduce unauthorized access risks.
- Ensure proper privileges are granted to database users on required tables.
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
- **Grafana Dashboards**: Import pre-built PostgreSQL dashboards (e.g., ID 9628) or create custom ones.
- **Alerts in Prometheus**: Set up rules for alerts such as high connection count, replication lag, query errors, low disk space.
- **Integration with PgBouncer**: Monitor connection pooling metrics to ensure efficient resource usage.

#### Automated Grafana Setup
The Ansible playbook includes automated Grafana configuration:
- **Automatic Data Source**: Prometheus is automatically configured as the default data source.
- **Pre-built Dashboard**: A PostgreSQL monitoring dashboard is automatically imported.
- **Access**: Open `http://localhost:3001`, log in with `admin` and your `grafana_admin_password` from vault.
- **Ready to Use**: No manual configuration needed - dashboards and data source are pre-configured.

### Health Checks and Logging
- Implement health endpoints in services (e.g., /health in the SMS receiver) for automated monitoring.
- Use rotating log handlers in Python applications to manage log files efficiently.
- Mount host volumes for persistent logging to ensure logs are retained across container restarts.

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

## Redis Operations (Generic)

### Viewing Redis Contents
```bash
# Docker deployment
REDIS_PASSWORD=$(ansible-vault view vault.yml | grep redis_password | cut -d':' -f2 | tr -d ' ')
docker exec redis redis-cli -a $REDIS_PASSWORD KEYS "*"
docker exec redis redis-cli -a $REDIS_PASSWORD INFO

# K3s deployment
REDIS_PASSWORD=$(kubectl get secret sms-bridge-secrets -n sms-bridge -o jsonpath='{.data.redis-password}' | base64 -d)
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD KEYS "*"
kubectl exec -n sms-bridge deployment/redis -- redis-cli -a $REDIS_PASSWORD INFO
```

### Redis Health and Performance
```bash
# Test connectivity
redis-cli -a $REDIS_PASSWORD PING

# Check memory usage
redis-cli -a $REDIS_PASSWORD INFO memory | grep -E "used_memory|used_memory_human"

# Check connected clients
redis-cli -a $REDIS_PASSWORD INFO clients | grep connected_clients

# View slow queries
redis-cli -a $REDIS_PASSWORD SLOWLOG GET 10
```

## Access and Credentials

### Service Ports and Access Links
- **PostgreSQL Database**: Port 5432
- **PgBouncer**: Port 6432
- **Redis Cache**: Port 6379
- **Prometheus**: Port 9090
- **Grafana**: Port 3001
- **SMS Bridge API**: Port 8000
- **SMS Bridge Admin UI**: http://localhost:8000/admin
- **Postgres Exporter**: Port 9187
- **Redis Exporter**: Port 9121

### SMS Bridge Admin UI Setup

The Admin UI is accessible at `http://localhost:8000/admin` after deployment.

#### Creating Initial Admin User

After deploying the application, create the first admin user:

```bash
# Using the init script (interactive mode)
cd /home/<user>/Documents/Software/SMS_Laptop_Setup/sms_bridge
python scripts/init_sms_bridge.py -i

# Or with command-line arguments
python scripts/init_sms_bridge.py --create-admin --username admin --password <your-password> --email admin@example.com

# Initialize database and create default settings
python scripts/init_sms_bridge.py --init-db --create-settings
```

#### Admin UI Features
- **Settings History**: View and create configuration versions (append-only)
- **Logs**: View SMS Bridge audit logs
- **Blacklist**: Manage blacklisted mobile numbers
- **Backup Users**: View fallback mode entries
- **Admin Users**: Manage admin accounts

### Retrieving Passwords from Vault
All passwords are encrypted in `vault.yml`. To access:
- Run `ansible-vault view vault.yml` to view decrypted contents in the terminal.
- Alternatively, use `ansible-vault edit vault.yml` to open the file in your default text editor.
- Key variables: `pg_password`, `redis_password`, `grafana_admin_password`, `cf_api_key`, `hmac_secret`.

#### Setting Up Default Text Editor
- **On Linux (Bash)**: Set `export EDITOR=vim` or permanently add to `~/.bashrc`.
- **On Windows**: If using WSL, set `export EDITOR=notepad` or path to preferred editor.

## Deployment Management

The SMS Bridge system supports two deployment methods:
1. **K3s-based deployment** (Recommended for production)
2. **Docker Compose deployment** (For development/testing)

### K3s Deployment (Production - Recommended)

The K3s deployment provides a complete Kubernetes-based SMS Bridge infrastructure with proper scaling, monitoring, and management capabilities.

#### Available Scripts in `ansible-k3s/` folder:

| Script | Purpose | Data Safety | Use Case |
|--------|---------|-------------|----------|
| `install_k3s.yml` | Install K3s cluster | ✅ Safe | One-time cluster setup |
| `setup_sms_bridge_k3s.yml` | Fresh deployment | ⚠️ Destroys data | Initial installation |
| `upgrade_sms_bridge_k3s.yml` | Apply updates | ✅ Preserves data | Deploy new code/schema |
| `restart_sms_bridge_k3s.yml` | Restart pods | ✅ Safe | Troubleshooting |
| `stop_sms_bridge_k3s.yml` | Complete shutdown | ⚠️ Destroys data | Maintenance/cleanup |
| `uninstall_k3s.yml` | Remove K3s | ⚠️ Destroys everything | Complete removal |

#### K3s Quick Start Commands:
```bash
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

#### K3s Monitoring Commands:
```bash
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

### Docker Compose Deployment (Development)

For development and testing, a simpler Docker Compose deployment is available.

#### Available Scripts in `ansible-docker/` folder:

| Script | Purpose | Data Safety | Use Case |
|--------|---------|-------------|----------|
| `setup_sms_bridge.yml` | Docker deployment | ⚠️ Recreates containers | Development setup |
| `restart_sms_bridge.yml` | Restart containers | ✅ Preserves data | Development restart |
| `stop_sms_bridge.yml` | Stop containers | ✅ Safe stop | Development shutdown |

#### Docker Deployment Commands:
```bash
cd /home/<user>/Documents/Software/SMS_Laptop_Setup/sms_bridge

# Deploy SMS Bridge with Docker Compose
ansible-playbook ansible-docker/setup_sms_bridge.yml --ask-vault-pass

# Restart services
ansible-playbook ansible-docker/restart_sms_bridge.yml --ask-vault-pass

# Stop services  
ansible-playbook ansible-docker/stop_sms_bridge.yml
```

## Recommended Workflows

### 🎯 Production Workflow (K3s)

1. **First-time setup:**
   ```bash
   ansible-playbook ansible-k3s/install_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass
   ansible-playbook ansible-k3s/setup_sms_bridge_k3s.yml -i ansible-k3s/inventory.txt --ask-become-pass --ask-vault-pass
   ```

   **If re-running setup after previous deployment:**
   ```bash
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

### 🧪 Development Workflow (Docker)

```bash
ansible-playbook ansible-docker/setup_sms_bridge.yml --ask-vault-pass
ansible-playbook ansible-docker/restart_sms_bridge.yml --ask-vault-pass
ansible-playbook ansible-docker/stop_sms_bridge.yml
```

## ⚠️ Critical Notes

- **Always use `upgrade_sms_bridge_k3s.yml` for code updates** - it preserves data while applying changes
- **Never use `setup_sms_bridge_k3s.yml` on existing systems** - it will destroy data
- **Test in development first** using Docker scripts before applying to K3s production
- **All scripts require vault password** except stop operations

## Lessons Learnt

### Build Marker Issues
If scripts fail to rebuild Docker images or apply code changes, the build marker may be preventing updates:

```bash
# Remove build marker to force complete rebuild
rm -f /home/$USER/sms_bridge/.image_built
```

**When to remove the marker:**
- Code changes not appearing after deployment
- Schema migrations not being applied
- Docker image not rebuilding with latest code
- Service fails to start after code update

### Database Connection Issues
- Verify PgBouncer is running and accessible
- Check PostgreSQL pod logs for connection errors
- Ensure proper credentials in vault.yml

### Common Troubleshooting Commands
```bash
# Check container status
docker ps

# View recent logs for specific services
docker logs sms_receiver --tail=50
docker logs postgres --tail=50
docker logs redis --tail=50

# Monitor real-time resource usage
docker stats

# Restart specific service using Ansible (secure method)
ansible-playbook ansible-docker/restart_sms_bridge.yml --ask-vault-pass

# K3s: Check all resources in SMS Bridge namespace
k3s kubectl get all -n sms-bridge

# K3s: View detailed pod information
k3s kubectl describe pods -n sms-bridge
```

### System Health Checks
```bash
# K3s: Verify all services are running
kubectl get pods -n sms-bridge
kubectl get services -n sms-bridge
kubectl get deployments -n sms-bridge

# Check for any failing pods
kubectl get pods -n sms-bridge | grep -v Running

# Pod resource usage
kubectl top pods -n sms-bridge

# Check pod logs for errors
kubectl logs -n sms-bridge deployment/sms-receiver --previous
```

## Additional Recommendations

- Regularly review and update Ansible playbooks for infrastructure changes.
- Perform security audits and penetration testing on the system.
- Document incident response procedures for handling breaches or failures.
- Ensure high availability by considering load balancers and failover mechanisms for production deployments.

For more details on the system setup, refer to the Ansible playbooks in `ansible-k3s/` (production) or `ansible-docker/` (development) folders.
