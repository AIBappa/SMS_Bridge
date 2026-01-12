# SMS Bridge Docker Deployment

This folder contains Ansible playbooks for deploying the SMS Bridge infrastructure using Docker containers.

## Files

- `setup_sms_bridge.yml` - Main deployment playbook using community.docker
- `restart_sms_bridge.yml` - Restart all Docker containers
- `stop_sms_bridge.yml` - Stop and remove all Docker containers
- `inventory.txt` - Ansible inventory file

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

### Deploy SMS Bridge with Docker
```bash
cd ansible-docker
ansible-playbook -i inventory.txt setup_sms_bridge.yml --ask-vault-pass
```

### Manage the Deployment
```bash
# Restart all containers
ansible-playbook -i inventory.txt restart_sms_bridge.yml

# Stop all containers
ansible-playbook -i inventory.txt stop_sms_bridge.yml
```

## Service Access

After deployment, services will be available at:

- **SMS Receiver**: http://localhost:8080
- **Grafana**: http://localhost:3001 (admin/your_grafana_password)
- **Prometheus**: http://localhost:9090

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
