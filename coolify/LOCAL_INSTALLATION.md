# SMS Bridge - Local Installation (Running)

## ✅ Installation Complete

All services are running locally on your laptop using Docker Compose.

## 🌐 Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| **SMS Bridge API** | http://localhost:8080 | - |
| **Health Check** | http://localhost:8080/health | - |
| **Metrics** | http://localhost:8080/metrics | - |
| **Admin UI** | http://localhost:8080/admin | Create via settings |
| **Grafana** | http://localhost:3001 | admin / admin_local |
| **Prometheus** | http://localhost:9090 | - |

## 📊 Services Status

All 8 containers running:
- ✅ `sms_receiver` - SMS Bridge application (port 8080)
- ✅ `postgres` - PostgreSQL database
- ✅ `pgbouncer` - Connection pooler
- ✅ `redis` - Redis cache
- ✅ `prometheus` - Metrics collector (port 9090)
- ✅ `grafana` - Monitoring dashboards (port 3001)
- ✅ `postgres_exporter` - DB metrics
- ✅ `redis_exporter` - Redis metrics

## 🔧 Useful Commands

```bash
cd /home/shantanu/Documents/Software/SMS_Laptop_Setup/sms_bridge/coolify

# View all services
docker compose ps

# View logs
docker compose logs -f sms_receiver
docker compose logs -f postgres
docker compose logs -f redis

# Restart services
docker compose restart sms_receiver
docker compose restart

# Stop all services
docker compose down

# Stop and remove all data
docker compose down -v

# Rebuild after code changes
docker compose up -d --build sms_receiver
```

## 📝 Configuration

Environment variables in `.env`:
- Database: postgres/localdev_postgres_2026
- Redis password: localdev_redis_2026
- All secrets configured via Admin UI (Settings tab)

## 🔐 Default Settings

The application initialized with default settings from `schema.sql`:
- SMS Receiver Number: +919000000000
- Allowed Prefix: ONBOARD:
- Hash Length: 8
- TTL: 900 seconds (15 minutes)
- Sync Interval: 1 second
- Log Interval: 120 seconds

**⚠️ Update these via the Admin UI before use!**

## 🧪 Testing the API

```bash
# Health check
curl http://localhost:8080/health

# Root endpoint
curl http://localhost:8080/

# Metrics
curl http://localhost:8080/metrics

# Generate hash (test endpoint)
curl -X POST http://localhost:8080/onboarding/register \
  -H "Content-Type: application/json" \
  -d '{"mobile": "+919876543210"}'
```

## 🛠️ Database Access

```bash
# Connect to PostgreSQL
docker exec -it sms_postgres psql -U postgres -d sms_bridge

# Connect to Redis
docker exec -it sms_redis redis-cli -a localdev_redis_2026
```

## 📂 Files Changed

- ✅ Removed duplicate `coolify/init/schema.sql`
- ✅ Updated `docker-compose.yml` to mount root `schema.sql`
- ✅ Fixed environment variable naming (SMS_BRIDGE_ prefix)
- ✅ Fixed BlacklistMobile startup query
- ✅ Created `.env` for local development

## 🎯 Next Steps

1. Access Admin UI: http://localhost:8080/admin
2. Create admin user
3. Configure settings (SMS number, sync URL, etc.)
4. Test the onboarding flow
5. Monitor via Grafana: http://localhost:3001
