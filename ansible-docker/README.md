# SMS Bridge Docker Deployment

This folder contains Ansible playbooks for deploying the SMS Bridge infrastructure using Docker containers.

## 🚀 Production_2 Quick Start

**NEW**: One-command deployment with automated migration!

```bash
cd ansible-docker
./deploy_production_2.sh
```

This interactive script offers:
1. **Automated Migration** (RECOMMENDED) - Migrates existing system to Production_2 with data preservation
2. **Fresh Install** - Clean Production_2 installation (destroys existing data)
3. **Manual Backup** - Backup current system without deployment

📖 **For detailed deployment guide**: See [DEPLOYMENT_PRODUCTION_2.md](DEPLOYMENT_PRODUCTION_2.md)

---

## Files

### Deployment Playbooks
- `migrate_to_production_2.yml` - **NEW** - Production_2 migration with schema update and data preservation
- `setup_sms_bridge.yml` - Main deployment playbook using community.docker
- `restart_sms_bridge.yml` - Restart all Docker containers
- `stop_sms_bridge.yml` - Stop and remove all Docker containers

### Deployment Scripts & Guides
- `deploy_production_2.sh` - **NEW** - Interactive deployment script (one-command deployment)
- `DEPLOYMENT_PRODUCTION_2.md` - **NEW** - Comprehensive Production_2 deployment guide
- `inventory.txt` - Ansible inventory file
- `README.md` - This file

## Shared Files (from parent directory)

The playbooks reference these shared files from the parent directory:
- `../vault.yml` - Encrypted secrets file
- `../schema.sql` - Database schema
- `../sms_server.py` - Main SMS processing application
- `../checks/` - Validation check modules

## Prerequisites

1. **Docker**: Ensure Docker is installed and running
2. **Ansible Collections**: Install required collections
   ```bash
   ansible-galaxy collection install community.docker
   ```
3. **Python Docker Library**: Install the Python Docker library
   ```bash
   pip install docker
   ```
4. **Vault File**: Ensure `../vault.yml` contains required secrets

## Quick Start

### Production_2 Deployment (Recommended)

#### Option 1: Interactive Script (Easiest)
```bash
cd ansible-docker
./deploy_production_2.sh
```

#### Option 2: Direct Ansible (Advanced)
```bash
# Automated migration (preserves data)
ansible-playbook -i inventory.txt migrate_to_production_2.yml --ask-vault-pass

# OR Fresh install (destroys data)
ansible-playbook -i inventory.txt stop_sms_bridge.yml --ask-vault-pass
docker volume rm pg_data
ansible-playbook -i inventory.txt setup_sms_bridge.yml --ask-vault-pass
```

### Legacy Deployment

#### Deploy SMS Bridge with Docker
```bash
cd ansible-docker
ansible-playbook -i inventory.txt setup_sms_bridge.yml --ask-vault-pass
```

#### Manage the Deployment
```bash
# Restart all containers
ansible-playbook -i inventory.txt restart_sms_bridge.yml

# Stop all containers
ansible-playbook -i inventory.txt stop_sms_bridge.yml
```

## Service Access

After deployment, services will be available at:

### Application Services
- **SMS Bridge API**: http://localhost:8080
  - Health check: http://localhost:8080/health
  - **NEW** Admin UI: http://localhost:8080/admin/settings/ui (Production_2)
  - Metrics: http://localhost:8080/metrics

### Monitoring Services
- **Grafana**: http://localhost:3001 (admin/your_grafana_password)
- **Prometheus**: http://localhost:9090
- **Postgres Exporter**: http://localhost:9187/metrics
- **Redis Exporter**: http://localhost:9121/metrics

### Database Services
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **PgBouncer**: localhost:6432

## Docker Management

You can also manage containers directly with Docker commands:

```bash
# View container status
docker ps

# View logs
docker logs sms_receiver
docker logs postgres
docker logs redis

# Access container shell
docker exec -it sms_receiver /bin/bash

# View network
docker network ls
docker network inspect sms_bridge_network
```

## Architecture

The Docker deployment creates:

### Network
- `sms_bridge_network` - Custom bridge network for container communication

### Volumes
- `pg_data` - PostgreSQL data persistence

### Containers
- `postgres` - PostgreSQL database (port 5432)
- `redis` - Redis cache (port 6379)
- `pgbouncer` - PostgreSQL connection pooler (port 6432)
- `prometheus` - Metrics collection (port 9090)
- `grafana` - Monitoring dashboard (port 3001)
- `postgres_exporter` - PostgreSQL metrics (port 9187)
- `redis_exporter` - Redis metrics (port 9121)
- `sms_receiver` - Main SMS processing application (port 8080)

## Troubleshooting

### Check Container Status
```bash
docker ps -a
docker logs <container_name>
```

### Common Issues

1. **Port conflicts**: Check if ports are already in use
   ```bash
   sudo netstat -tulpn | grep -E ':(5432|6379|6432|8080|9090|3001)'
   ```

2. **Permission issues**: Ensure Docker daemon is running and user has permissions
   ```bash
   sudo systemctl status docker
   sudo usermod -aG docker $USER
   ```

3. **Build failures**: Check Dockerfile and build context
   ```bash
   cd ~/sms_bridge
   docker build -t sms_receiver_image .
   ```
