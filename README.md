# SMS Bridge Consolidator

This software is an SMS Bridge Consolidator that works on a laptop connected to various older mobile devices on the same local Wi-Fi network.

## Project Structure

### 📁 Core Application
- `core/` - **Core application package** (Python code)
  - `sms_server_v2.py` - Main SMS processing application
  - `redis_v2.py` - Async Redis client with pooling
  - `workers.py` - Background workers for abuse detection and monitoring
  - `requirements.txt` - Python dependencies
  - `config.py` - Configuration management
  - `database.py` - Database connection management
  - `services/` - Validation and utility modules
  - `observability/` - Prometheus metrics and monitoring
  - `models/` - Database models and schemas
  - `admin/` - Admin interface

### 📁 Deployment Options
- `coolify/` - Coolify deployment with Docker Compose
  - Includes Supabase integration
  - Monitoring stack (Prometheus, Grafana)
  - `Dockerfile` - SMS Bridge application container image
  - `init/schema.sql` - Database schema
  - `config/` - Grafana and Prometheus configuration

**Note:** Cloudflare Tunnel is managed via Cloudflare Zero Trust Dashboard for secure remote access.

### 📁 Additional Resources
- `docs/` - Documentation and examples

## Concept

The idea is that older mobiles act as SMS receivers and the laptop aggregates all received SMS messages in a PostgreSQL database. Duplicate SMS messages are filtered and only unique SMS numbers are forwarded to the external backend.

This method can verify mobile numbers via SMS. Users can send SMS to older mobile numbers to confirm their mobile numbers after submitting an onboarding application via IP/Ethernet network.

## Deployment

### Using Coolify
See [coolify/README.md](coolify/README.md) for detailed deployment instructions using Coolify.

### Using Docker Compose
```bash
docker-compose -f coolify/docker-compose.yml up -d
```

## Prerequisites

- Linux laptop (tested on Ubuntu/Debian) or WSL environment
- Docker and Docker Compose
- Python 3.9+ (for local development)
- Git (for cloning)

## Quick Start

### Production Deployment (Coolify/Docker Compose)

1. **Run setup script**: Prepares directories and configuration
   ```bash
   cd coolify
   ./setup.sh
   ```

2. **Configure environment**: Edit `.env` with your secure credentials
   ```bash
   nano .env
   # IMPORTANT: Set all passwords and secrets (look for CHANGE_ME)
   ```

3. **Deploy services**:
   ```bash
   docker-compose up -d
   ```
   
   Admin user will be **auto-created** on first startup from .env credentials.

4. **Verify deployment**: Check that services are running
   ```bash
   docker-compose ps
   docker-compose logs -f sms_receiver
   ```

See [coolify/README.md](coolify/README.md) for detailed deployment options and troubleshooting.

### Local Development

For local testing without full deployment:

```bash
# Install Python dependencies
pip install -r core/requirements.txt

# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_DB=sms_bridge
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=your_password
export REDIS_HOST=localhost
export REDIS_PASSWORD=your_redis_password

# Run the application
python -m core.sms_server_v2
```

**Database Setup for Local Development:**

```bash
# Create database and run schema
psql -U postgres -c "CREATE DATABASE sms_bridge;"
psql -U postgres -d sms_bridge -f coolify/init/schema.sql
```

**Access Points:**
- SMS Bridge API: <http://localhost:8080>
- Health Check: <http://localhost:8080/health>
- Metrics: <http://localhost:8080/metrics>
- Admin UI: <http://localhost:8080/admin/>

**Useful Commands:**

```bash
# View logs
docker-compose logs -f sms_receiver

# Restart service
docker-compose restart sms_receiver

# Stop all services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build sms_receiver

# Database access
docker-compose exec postgres psql -U postgres -d sms_bridge

# Redis access
docker-compose exec redis redis-cli -a YOUR_REDIS_PASSWORD
```

## API Endpoints

### Inbound Endpoints (SMS Bridge receives)

- **POST `http://localhost:8080/onboarding/register`** - Generate or return onboarding hash for mobile number
- **GET `http://localhost:8080/health`** - Health status of SMS Bridge service
- **POST `http://localhost:8080/sms/receive`** - Receive webhook from mobile device for incoming SMS data
  - *This is where the SMS Receiver (mobile) sends received SMS data*
- **POST `http://localhost:8080/pin-setup`** - Submit PIN after mobile verification

### Admin Endpoints

- **POST `http://localhost:8080/admin/trigger-recovery`** - Trigger manual recovery sync to backend (Admin only)

### Metrics & Monitoring

- **GET `http://localhost:8080/metrics`** - Prometheus metrics endpoint for scraping by Prometheus. This is an internal observability endpoint and is intentionally **not** included in `docs/core/integration_openapi.yaml` because it does not follow the same authentication/usage pattern as the public application API.

### Outbound Webhook Contract (External backend receives)

- **POST `{sync_url_from_settings}`** - Receive validated SMS data in format: `{mobile_number, pin, hash}`

### Service Access

Default service endpoints:
- **SMS Bridge API**: <http://localhost:8080>
- **Grafana Dashboard**: <http://localhost:3001>
- **Prometheus Metrics**: <http://localhost:9090>
- **Admin UI**: <http://localhost:8080/admin/>

## Mobile Setup Required

- Install SMS_Gateway app on older Android devices
- May require rooted device or developer mode
- Configure to send SMSes to laptop endpoint (configured in application settings)

## Planned Updates

- Support for multiple mobile devices
- Enhanced filtering and validation
- Mobile app improvements
- Cloud backend integration enhancements

## Documentation

- [Admin Security Guide](docs/ADMIN_SECURITY.md) - **Important security information for admin users**
- [Technical Specification](docs/core/SMS_Bridge_tech_spec_v2.2.md)
- [Monitoring Specification](docs/core/SMS_Bridge_monitoring_spec_v2.2.md)
- [Coolify Deployment](coolify/README.md) 
