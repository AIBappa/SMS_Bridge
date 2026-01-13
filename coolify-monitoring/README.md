# SMS Bridge Monitoring Stack (Laptop)

**On-demand monitoring for SMS Bridge v2.3** - Run Prometheus and Grafana locally to monitor your remote server.

---

## Quick Start

### 1. First-Time Setup

```bash
# Copy environment template
cp .env.example .env

# Edit with your server URL
nano .env
# Set: SMS_BRIDGE_URL=https://your-domain.com
```

### 2. Download Prometheus Config

**Option A: Via Admin UI (Recommended)**
1. Login to Admin UI: `https://your-domain.com/admin`
2. Go to: **Monitoring → Export Config**
3. Save as: `config/prometheus-remote.yml`

**Option B: Via Command Line**
```bash
curl -u admin:password \
  https://your-domain.com/admin/monitoring/export-prometheus-config \
  -o config/prometheus-remote.yml
```

### 3. Start Monitoring

```bash
./scripts/start-monitoring.sh
```

### 4. Open Ports on Server

1. Login to Admin UI: `https://your-domain.com/admin`
2. Go to: **Monitoring → Port Configuration**
3. Click: **"Open Port"** for the services you want to monitor
4. Choose duration (15 min - 4 hours)

### 5. Access Dashboards

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

---

## Daily Workflow

```bash
# Check status
./scripts/check-monitoring.sh

# Start monitoring (if not running)
./scripts/start-monitoring.sh

# Open ports on server via Admin UI
# https://your-domain.com/admin

# Access Grafana
# http://localhost:3000

# When done, stop monitoring
./scripts/stop-monitoring.sh
```

---

## Folder Structure

```
coolify-monitoring/
├── docker-compose-monitoring.yml    # Monitoring stack definition
├── .env.example                     # Environment template
├── .env                            # Your configuration (git-ignored)
├── config/
│   ├── prometheus-remote.yml       # Downloaded from server
│   ├── prometheus-remote.yml.template
│   └── grafana-datasources.yml     # Grafana data source config
├── scripts/
│   ├── start-monitoring.sh         # Start stack
│   ├── stop-monitoring.sh          # Stop stack
│   └── check-monitoring.sh         # Check status
└── README.md                        # This file
```

---

## What Gets Monitored?

| Service | Metrics | Port (on server) |
|---------|---------|------------------|
| **SMS Bridge** | Request rates, errors, latency | 9100 |
| **PostgreSQL** | Connections, queries, performance | 5433 |
| **Redis** | Memory, commands, hit rate | 6380 |

---

## Security Notes

- ✅ Ports only open when you need them
- ✅ Auto-close after timeout (15 min - 4 hours)
- ✅ All actions logged in audit trail
- ✅ Only admins can open ports

---

## Troubleshooting

### Services won't start
```bash
# Check Docker
docker --version
docker info

# Check logs
docker-compose -f docker-compose-monitoring.yml logs
```

### Can't access Grafana
```bash
# Check if running
docker ps | grep monitoring

# Check port binding
netstat -tlnp | grep 3000
```

### Prometheus not scraping
1. Ensure ports are open on server (via Admin UI)
2. Check Prometheus targets: http://localhost:9090/targets
3. Verify `prometheus-remote.yml` has correct IP/ports

### Need to update config
```bash
# Stop stack
./scripts/stop-monitoring.sh

# Update config files
nano config/prometheus-remote.yml

# Restart
./scripts/start-monitoring.sh
```

---

## Data Persistence

Your dashboards and metrics are preserved in Docker volumes:
- `coolify-monitoring_grafana_data` - Grafana dashboards
- `coolify-monitoring_prometheus_data` - Prometheus metrics (7 days)

To remove all data:
```bash
docker-compose -f docker-compose-monitoring.yml down -v
```

---

## Advanced Usage

### Connect DBeaver to PostgreSQL
1. Open port via Admin UI
2. Use connection details from Admin UI
3. Configure DBeaver with provided host:port

### Connect Redis Desktop Manager
1. Open Redis port via Admin UI
2. Use connection details from Admin UI
3. Configure Redis client with provided host:port

### Custom Grafana Dashboards
1. Access Grafana: http://localhost:3000
2. Create → Dashboard
3. Add panels with Prometheus queries
4. Save dashboard (persists across restarts)

---

## More Information

- **Full Setup Guide**: `docs/core/MONITORING_SETUP.md`
- **Technical Spec**: `docs/core/SMS_Bridge_monitoring_spec_v2.3.md`
- **Code Examples**: `docs/core/SMS_Bridge_monitoring_snippets_v2.3.md`

---

## Support

Need help? Check the documentation or logs:
- Logs: `docker-compose -f docker-compose-monitoring.yml logs -f`
- Status: `./scripts/check-monitoring.sh`
