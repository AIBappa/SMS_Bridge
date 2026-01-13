#!/bin/bash
set -euo pipefail

# SMS Bridge Monitoring Stack - Start Script
# Usage: ./scripts/start-monitoring.sh

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 Starting SMS Bridge Monitoring Stack..."
echo ""

# Check prerequisites
echo "✓ Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ ERROR: Docker is not installed"
    echo "   Install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ ERROR: Docker Compose is not installed"
    echo "   Install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo "❌ ERROR: Docker daemon is not running"
    echo "   Start Docker and try again"
    exit 1
fi

echo "  ✓ Docker is installed and running"

# Check if .env file exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚠️  WARNING: .env file not found"
    echo "   Creating from template..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo ""
    echo "📝 Please edit .env and update SMS_BRIDGE_URL with your server URL"
    echo "   File location: $PROJECT_DIR/.env"
    echo ""
    read -p "Press Enter to continue after editing .env file..."
fi

# Check if prometheus config exists
if [ ! -f "$PROJECT_DIR/config/prometheus-remote.yml" ]; then
    echo "⚠️  WARNING: Prometheus config not found"
    echo ""
    echo "📥 You need to download the config from Admin UI:"
    echo "   1. Go to: https://your-domain.com/admin"
    echo "   2. Navigate to: Monitoring → Export Config"
    echo "   3. Save as: $PROJECT_DIR/config/prometheus-remote.yml"
    echo ""
    echo "   Or use the template:"
    if [ -f "$PROJECT_DIR/config/prometheus-remote.yml.template" ]; then
        cp "$PROJECT_DIR/config/prometheus-remote.yml.template" "$PROJECT_DIR/config/prometheus-remote.yml"
        echo "   ✓ Copied template to prometheus-remote.yml"
        echo "   ⚠️  Remember to update the IP and ports in the file"
    fi
    echo ""
    read -p "Press Enter to continue..."
fi

# Load environment variables
source "$PROJECT_DIR/.env"

# Validate SMS_BRIDGE_URL
if [ -z "${SMS_BRIDGE_URL:-}" ] || [ "$SMS_BRIDGE_URL" == "https://your-domain.com" ]; then
    echo "❌ ERROR: SMS_BRIDGE_URL not configured in .env"
    echo "   Please edit .env and set your actual server URL"
    exit 1
fi

echo "  ✓ Configuration files present"
echo ""

# Start the stack
echo "🐳 Starting Docker containers..."
cd "$PROJECT_DIR"
docker-compose -f docker-compose-monitoring.yml up -d

# Wait for services to be healthy
echo ""
echo "⏳ Waiting for services to start..."
sleep 5

# Check if services are running
PROMETHEUS_RUNNING=$(docker inspect -f '{{.State.Running}}' monitoring_prometheus 2>/dev/null || echo "false")
GRAFANA_RUNNING=$(docker inspect -f '{{.State.Running}}' monitoring_grafana 2>/dev/null || echo "false")

if [ "$PROMETHEUS_RUNNING" == "true" ] && [ "$GRAFANA_RUNNING" == "true" ]; then
    echo ""
    echo "✅ Monitoring stack started successfully!"
    echo ""
    echo "📊 Access your dashboards:"
    echo "   Prometheus: http://localhost:9090"
    echo "   Grafana:    http://localhost:3000"
    echo ""
    echo "🔐 Grafana credentials:"
    echo "   Username: ${GRAFANA_ADMIN_USER:-admin}"
    echo "   Password: ${GRAFANA_ADMIN_PASSWORD:-admin}"
    echo ""
    echo "💡 Next steps:"
    echo "   1. Open ports on server via Admin UI"
    echo "   2. Open Grafana and create dashboards"
    echo "   3. View real-time metrics from your server"
    echo ""
    echo "🛑 To stop monitoring: ./scripts/stop-monitoring.sh"
else
    echo ""
    echo "❌ ERROR: Failed to start some services"
    echo "   Check logs: docker-compose -f docker-compose-monitoring.yml logs"
    exit 1
fi
