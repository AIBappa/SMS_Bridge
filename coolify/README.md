# SMS Bridge - Coolify Deployment on Hetzner

This folder contains everything needed to deploy SMS Bridge via **Coolify** on your Hetzner VM.

## Deployment Options

### Option A: Existing Supabase + Dragonfly Setup (Recommended)

If you already have **Supabase** (PostgreSQL) and **Dragonfly** (Redis-compatible) running on Hetzner, you only need to deploy the **SMS Receiver Python container**.

### Option B: Full Stack Deployment

Deploy everything including PostgreSQL, Redis, and monitoring. See [Full Stack Deployment](#full-stack-deployment) section below.

---

## Option A: Connect to Existing Supabase + Dragonfly

### Prerequisites

- **Supabase** running on Hetzner (provides PostgreSQL)
- **Dragonfly** running on Hetzner (Redis-compatible)
- **Coolify** installed on Hetzner

### What You Need from Supabase

1. **Database Host**: Usually `localhost` or Supabase container name (e.g., `supabase-db`)
2. **Database Port**: Default `5432` (or pooler port `6543` if using Supavisor)
3. **Database Name**: Create a new database `sms_bridge` or use existing
4. **Database User/Password**: From your Supabase configuration

### What You Need from Dragonfly

1. **Host**: Usually `localhost` or Dragonfly container name (e.g., `dragonfly`)
2. **Port**: Default `6379`
3. **Password**: Your Dragonfly password (if set)

### Step 1: Initialize Database Schema

Run the schema on your Supabase PostgreSQL:

```bash
# Connect to Supabase PostgreSQL and run schema
psql -h <SUPABASE_DB_HOST> -U postgres -d sms_bridge -f coolify/init/schema.sql
```

Or via Supabase SQL Editor, copy contents of `coolify/init/schema.sql`.

### Step 2: Deploy SMS Receiver Only

Use the simplified compose file for just the Python app:

```yaml
# docker-compose.supabase.yml
version: "3.8"

services:
  sms_receiver:
    build:
      context: ..
      dockerfile: coolify/Dockerfile
    container_name: sms_receiver
    restart: unless-stopped
    ports:
      - "${SMS_RECEIVER_PORT:-8080}:8080"
    volumes:
      - ./logs:/app/logs:rw
    environment:
      # Backend Integration
      CF_API_KEY: ${CF_API_KEY}
      CF_BACKEND_URL: ${CF_BACKEND_URL}
      # Supabase PostgreSQL Connection
      POSTGRES_HOST: ${SUPABASE_DB_HOST:-supabase-db}
      POSTGRES_DB: ${POSTGRES_DB:-sms_bridge}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_PORT: ${POSTGRES_PORT:-5432}
      # Dragonfly (Redis-compatible) Connection
      REDIS_HOST: ${DRAGONFLY_HOST:-dragonfly}
      REDIS_PORT: ${DRAGONFLY_PORT:-6379}
      REDIS_PASSWORD: ${DRAGONFLY_PASSWORD:-}
      # Security
      HASH_SECRET_KEY: ${HASH_SECRET_KEY}
      # Logging
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      LOG_DIR: /app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    # Connect to existing Docker network where Supabase/Dragonfly run
    networks:
      - supabase_default  # Change to your Supabase network name

networks:
  supabase_default:
    external: true  # Use existing network
```

### Step 3: Environment Variables for Supabase + Dragonfly

Create `.env` file:

```bash
# ===========================================
# Supabase PostgreSQL Connection
# ===========================================
SUPABASE_DB_HOST=supabase-db          # Or 'localhost' if same host
POSTGRES_PORT=5432                     # Or 6543 for Supavisor pooler
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_supabase_db_password
POSTGRES_DB=sms_bridge

# ===========================================
# Dragonfly (Redis-compatible) Connection
# ===========================================
DRAGONFLY_HOST=dragonfly              # Or 'localhost' if same host
DRAGONFLY_PORT=6379
DRAGONFLY_PASSWORD=your_dragonfly_password  # Leave empty if no auth

# ===========================================
# SMS Receiver Application
# ===========================================
CF_API_KEY=your_backend_api_key
CF_BACKEND_URL=https://your-backend.com/api
HASH_SECRET_KEY=your_hmac_secret_key
LOG_LEVEL=INFO
SMS_RECEIVER_PORT=8080
```

### Step 4: Find Your Docker Network

```bash
# List networks to find Supabase network name
docker network ls

# Common names:
# - supabase_default
# - supabase_network
# - coolify_<project-id>
```

Update `networks:` section in compose file with correct network name.

### Step 5: Deploy via Coolify

1. In Coolify, create new **Docker Compose** service
2. Point to `coolify/docker-compose.supabase.yml` (or create this file)
3. Add environment variables
4. Deploy!

### Alternative: Direct Docker Run

```bash
docker build -t sms_receiver -f coolify/Dockerfile ..

docker run -d \
  --name sms_receiver \
  --network supabase_default \
  -p 8080:8080 \
  -e POSTGRES_HOST=supabase-db \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=sms_bridge \
  -e REDIS_HOST=dragonfly \
  -e REDIS_PORT=6379 \
  -e REDIS_PASSWORD=your_redis_password \
  -e CF_API_KEY=your_api_key \
  -e CF_BACKEND_URL=https://your-backend.com/api \
  -e HASH_SECRET_KEY=your_secret \
  sms_receiver
```

---

## Full Stack Deployment

If you don't have existing Supabase/Dragonfly and want to deploy everything from scratch (PostgreSQL, Redis, monitoring):

### Folder Structure

```
coolify/
├── docker-compose.yml     # Main compose file for Coolify
├── Dockerfile             # SMS Receiver application image
├── .env.example           # Environment variables template
├── init/
│   ├── init.sql           # PostgreSQL initialization
│   └── schema.sql         # Database schema
└── config/
    ├── prometheus.yml     # Prometheus scrape config
    └── grafana/
        └── provisioning/
            ├── datasources/prometheus.yml
            └── dashboards/dashboards.yml
```

## Deployment Steps

### 1. Push to Git Repository

Make sure this `coolify/` folder is committed and pushed to your Git repository.

```bash
git add coolify/
git commit -m "Add Coolify deployment configuration"
git push origin main
```

### 2. Configure Coolify

1. **Login to Coolify** on your Hetzner VM
2. **Create new Service** → Select "Docker Compose"
3. **Connect your Git repository**
4. **Set Build Path** to: `coolify/` (the docker-compose.yml location)
5. **Note**: The build context uses parent directory (`..`) to access `core/` folder
6. **Add Environment Variables** (copy from `.env.example`):

   | Variable | Description | Example |
   |----------|-------------|---------|
   | `POSTGRES_PASSWORD` | Database password | `secure_password_123` |
   | `REDIS_PASSWORD` | Redis password | `redis_secure_456` |
   | `CF_API_KEY` | Backend API key | `your_api_key` |
   | `CF_BACKEND_URL` | Backend URL | `https://your-backend.com/api` |
   | `HASH_SECRET_KEY` | HMAC secret | `your_hmac_secret` |
   | `GRAFANA_ADMIN_PASSWORD` | Grafana admin pass | `grafana_admin_123` |

### 3. Deploy

Click **Deploy** in Coolify. The following will happen automatically:
- Build the SMS Receiver Docker image
- Pull PostgreSQL, Redis, PgBouncer, Prometheus, Grafana images
- Initialize the database with schema
- Start all services with health checks
- Configure monitoring stack

### 4. Configure Domain (Optional)

In Coolify:
1. Go to your service settings
2. Add domain for `sms_receiver` service (port 8080)
3. Enable HTTPS with Let's Encrypt

## Services & Ports

| Service | Internal Port | Default External Port | Description |
|---------|---------------|----------------------|-------------|
| sms_receiver | 8080 | 8080 | Main SMS Bridge API |
| postgres | 5432 | - | PostgreSQL Database |
| pgbouncer | 6432 | - | Connection Pooler |
| redis | 6379 | - | Redis Cache |
| prometheus | 9090 | 9090 | Metrics Collection |
| grafana | 3000 | 3001 | Monitoring Dashboard |

## Accessing Services

After deployment:

- **SMS Bridge API**: `http://your-domain:8080` or `http://your-ip:8080`
- **Grafana Dashboard**: `http://your-domain:3001` (admin / your GRAFANA_ADMIN_PASSWORD)
- **Prometheus**: `http://your-domain:9090`

## Health Checks

The SMS Receiver includes a health endpoint:
```bash
curl http://your-domain:8080/health
```

## Logs

Logs are persisted in the `./logs` volume. Access via Coolify logs viewer or:
```bash
docker logs sms_receiver
```

## Updating

1. Push changes to your Git repository
2. In Coolify, click **Redeploy**
3. Coolify will rebuild and restart services

## Troubleshooting

### Database Connection Issues
- Check PostgreSQL logs: `docker logs sms_postgres`
- Verify PgBouncer is healthy: `docker logs sms_pgbouncer`

### Redis Connection Issues
- Check Redis logs: `docker logs sms_redis`
- Verify password is correct in environment variables

### Application Errors
- Check SMS Receiver logs: `docker logs sms_receiver`
- Verify all environment variables are set correctly

## Manual Docker Compose (Alternative)

If not using Coolify, you can deploy manually:

```bash
cd coolify/
cp .env.example .env
# Edit .env with your values
docker compose up -d
```

## Security Notes

- Change all default passwords in production
- Use HTTPS with a proper domain
- Consider restricting Prometheus/Grafana ports to internal network
- Regularly update Docker images for security patches
