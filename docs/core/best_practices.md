# SMS Bridge Best Practices

This document outlines best practices for deploying, operating, and maintaining the SMS Bridge system. For application-specific details (API endpoints, Redis keys, database schema), refer to `SMS_Bridge_tech_spec_v2.2.md`.

## Cybersecurity Best Practices

### Credential Management
- Store sensitive credentials and API keys in secure configuration files with appropriate file permissions (600).
- Use environment variables or encrypted configuration management for production deployments.
- Regularly rotate credentials and update configuration files.

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
- **Install postgres_exporter**: Deploy the postgres_exporter container to expose PostgreSQL metrics.
- **Prometheus Configuration**: Add a scrape job in prometheus.yml to target the postgres_exporter endpoint (e.g., `http://postgres_exporter:9187/metrics`).
- **Grafana Dashboards**: Import pre-built PostgreSQL dashboards (e.g., ID 9628) or create custom ones.
- **Alerts in Prometheus**: Set up rules for alerts such as high connection count, replication lag, query errors, low disk space.
- **Integration with PgBouncer**: Monitor connection pooling metrics to ensure efficient resource usage.

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
- Automate backups using cron jobs or scheduled scripts.
- Encrypt backups to protect sensitive data.
- Document backup and restoration processes in runbooks.
- Monitor backup success and alert on failures.

### Useful Docker Commands for Backup
- Backup PostgreSQL database: `docker exec <postgres_container> pg_dump -U <username> -h localhost <database> > backup.sql`
- Backup Redis data: `docker exec <redis_container> redis-cli save`
- Backup a Docker volume: `docker run --rm -v <volume_name>:/data -v $(pwd):/backup alpine tar czf /backup/backup.tar.gz -C /data .`
- Restore PostgreSQL from backup: `docker exec -i <postgres_container> psql -U <username> -d <database> < backup.sql`
- Restore Redis from RDB file: Copy the RDB file to the Redis container and restart.


## Redis Operations

### Viewing Redis Contents
```bash
# Using Docker
docker exec redis redis-cli -a <password> KEYS "*"
docker exec redis redis-cli -a <password> INFO
```

### Redis Health and Performance
```bash
# Test connectivity
redis-cli -a <password> PING

# Check memory usage
redis-cli -a <password> INFO memory | grep -E "used_memory|used_memory_human"

# Check connected clients
redis-cli -a <password> INFO clients | grep connected_clients

# View slow queries
redis-cli -a <password> SLOWLOG GET 10
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

Admin users are automatically created from environment variables on startup:

```bash
# In your .env file, set:
SMS_BRIDGE_ADMIN_USERNAME=admin
SMS_BRIDGE_ADMIN_PASSWORD=YourSecurePassword123

# Then start/restart the application
docker-compose up -d
```

# To ensure that docker-compose allows building again if code changes.
If python build is required or haproxy build required based on code changes,
ensure existing docker-compose containers are stopped. Then build the containers again without any cache impacting the build.

docker-compose down -v (Stop containers and remove volume)

docker-compose build --no-cache

docker-compose up -d


The admin user will be created automatically on first startup if the credentials are set in `.env` and the user doesn't already exist.

#### Database Initialization

Database tables and default settings are automatically created when you deploy:

- **Docker/Coolify**: `coolify/init/schema.sql` runs automatically on first startup
- **Manual setup**: Run the schema manually:
  ```bash
  psql -h localhost -U postgres -d sms_bridge -f coolify/init/schema.sql
  ```

#### Admin UI Features
- **Settings History**: View and create configuration versions (append-only)
- **Logs**: View SMS Bridge audit logs
- **Blacklist**: Manage blacklisted mobile numbers
- **Backup Users**: View fallback mode entries
- **Admin Users**: Manage admin accounts

### Managing Configuration
All configuration is stored in environment variables (`.env` files in coolify/).
- Key variables: `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`, `CF_API_KEY`, `HMAC_SECRET`.
- Ensure proper file permissions (600) for .env files containing secrets.

## Deployment Management

The SMS Bridge system supports Docker Compose deployment for local development and production use.

### Docker Compose Deployment

#### Starting Services
```bash
cd coolify
docker-compose up -d
```

#### Monitoring Services
```bash
# Check container status
docker-compose ps

# View logs for all services
docker-compose logs -f

# View logs for specific service
docker-compose logs -f sms-receiver
docker-compose logs -f postgres
docker-compose logs -f redis
```

#### Stopping Services
```bash
# Stop all services
docker-compose down

# Stop and remove volumes (destroys data)
docker-compose down -v
```

## Common Troubleshooting Commands

```bash
# Check container status
docker ps

# View recent logs for specific services
docker logs sms_receiver --tail=50
docker logs postgres --tail=50
docker logs redis --tail=50

# Monitor real-time resource usage
docker stats

# Restart specific service
docker-compose restart sms-receiver

# Access container shell for debugging
docker exec -it sms_receiver /bin/bash
```

### Database Connection Issues
- Verify PgBouncer is running and accessible
- Check PostgreSQL container logs for connection errors
- Ensure proper credentials in configuration files

### System Health Checks
```bash
# Check all running containers
docker ps

# Check service health endpoints
curl http://localhost:8000/health
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:3001/api/health  # Grafana

# Check database connectivity
docker exec postgres psql -U postgres -c "SELECT 1"

# Check Redis connectivity
docker exec redis redis-cli -a <password> PING
```

## Additional Recommendations

- Regularly review and update Docker Compose configurations for infrastructure changes.
- Perform security audits and penetration testing on the system.
- Document incident response procedures for handling breaches or failures.
- Ensure high availability by considering load balancers and failover mechanisms for production deployments.
- Use Coolify or similar platforms for production deployments with proper monitoring and scaling capabilities.

For deployment details, refer to [coolify/README.md](../../coolify/README.md).
