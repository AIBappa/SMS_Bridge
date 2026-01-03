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
- `cloudflare_tunnel/` - Cloudflare Tunnel configuration for secure remote access

### 📁 Additional Resources
- `docs/` - Documentation and examples
- `tests/` - Testing utilities and sample data
- `scripts/` - Utility scripts for initialization

## Concept

The idea is that older mobiles act as SMS receivers and the laptop aggregates all received SMSes in a PostgreSQL database. Duplicate SMSes are filtered and only unique SMS numbers are forwarded to the cloud database (example uses Cloudflare D1).

This method can verify mobile numbers that have been written to Cloudflare D1 via IP input. Users can send SMS to older mobile numbers to confirm their mobile numbers after submitting an onboarding application via IP/Ethernet network.

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

1. **Set up configuration**: Copy and customize configuration files
   ```bash
   cd coolify
   cp .env.example .env
   # Edit .env with your settings
   # IMPORTANT: Set SMS_BRIDGE_ADMIN_USERNAME and SMS_BRIDGE_ADMIN_PASSWORD
   ```

2. **Deploy with Docker Compose**:
   ```bash
   cd coolify
   docker-compose up -d
   ```
   
   Admin user will be **auto-created** on first startup from .env credentials.

3. **Verify**: Check that services are running
   ```bash
   docker-compose ps
   ```
   
   Login to Admin UI at: http://localhost:8080/admin/

## Service Access

Default service endpoints:
- **SMS Receiver**: http://localhost:8080
- **Grafana Dashboard**: http://localhost:3001
- **Prometheus Metrics**: http://localhost:9090

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

## Testing

See the `tests/` directory for testing utilities and sample data. 
