#!/bin/bash
set -euo pipefail

# SMS Bridge Monitoring Stack - Stop Script
# Usage: ./scripts/stop-monitoring.sh

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🛑 Stopping SMS Bridge Monitoring Stack..."
echo ""

cd "$PROJECT_DIR"

# Check if containers are running
if ! docker ps --format '{{.Names}}' | grep -q "monitoring_"; then
    echo "ℹ️  No monitoring containers are running"
    exit 0
fi

# Stop the stack
docker-compose -f docker-compose-monitoring.yml down

echo ""
echo "✅ Monitoring stack stopped successfully"
echo ""
echo "💡 Your data is preserved in Docker volumes:"
echo "   - Grafana dashboards: coolify-monitoring_grafana_data"
echo "   - Prometheus metrics: coolify-monitoring_prometheus_data"
echo ""
echo "🚀 To start again: ./scripts/start-monitoring.sh"
echo "🗑️  To remove all data: docker-compose -f docker-compose-monitoring.yml down -v"
