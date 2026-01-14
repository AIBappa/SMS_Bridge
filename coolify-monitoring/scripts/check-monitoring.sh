#!/bin/bash
set -euo pipefail

# SMS Bridge Monitoring Stack - Status Check Script
# Usage: ./scripts/check-monitoring.sh

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🔍 Checking SMS Bridge Monitoring Stack Status..."
echo ""

cd "$PROJECT_DIR"

# Check if containers exist
if ! docker ps -a --format '{{.Names}}' | grep -q "monitoring_"; then
    echo "❌ No monitoring containers found"
    echo "   Run: ./scripts/start-monitoring.sh"
    exit 0
fi

# Check container status
echo "📦 Container Status:"
echo ""
docker ps -a --filter "name=monitoring_" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# Check if containers are running
PROMETHEUS_RUNNING=$(docker inspect -f '{{.State.Running}}' monitoring_prometheus 2>/dev/null || echo "false")
GRAFANA_RUNNING=$(docker inspect -f '{{.State.Running}}' monitoring_grafana 2>/dev/null || echo "false")

if [ "$PROMETHEUS_RUNNING" == "true" ] && [ "$GRAFANA_RUNNING" == "true" ]; then
    echo "✅ All services are running"
    echo ""
    
    # Check health status
    echo "🏥 Health Status:"
    PROMETHEUS_HEALTHY=$(docker inspect -f '{{.State.Health.Status}}' monitoring_prometheus 2>/dev/null || echo "unknown")
    GRAFANA_HEALTHY=$(docker inspect -f '{{.State.Health.Status}}' monitoring_grafana 2>/dev/null || echo "unknown")
    
    echo "  Prometheus: $PROMETHEUS_HEALTHY"
    echo "  Grafana:    $GRAFANA_HEALTHY"
    echo ""
    
    # Check if services are accessible
    echo "🌐 Network Accessibility:"
    if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
        echo "  ✓ Prometheus accessible at http://localhost:9090"
    else
        echo "  ❌ Prometheus not accessible"
    fi
    
    if curl -s http://localhost:3000/api/health > /dev/null 2>&1; then
        echo "  ✓ Grafana accessible at http://localhost:3000"
    else
        echo "  ❌ Grafana not accessible"
    fi
    echo ""
    
    # Check Prometheus targets
    echo "🎯 Prometheus Targets:"
    TARGETS=$(curl -s http://localhost:9090/api/v1/targets 2>/dev/null | grep -o '"health":"[^"]*"' | cut -d'"' -f4 | sort | uniq -c || echo "Unable to fetch")
    if [ "$TARGETS" != "Unable to fetch" ]; then
        echo "$TARGETS"
    else
        echo "  ⚠️  Unable to fetch target status"
    fi
    echo ""
    
    # Show resource usage
    echo "💾 Resource Usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" monitoring_prometheus monitoring_grafana
    echo ""
    
    # Show volume sizes
    echo "📊 Data Volume Sizes:"
    docker system df -v | grep "coolify-monitoring" || echo "  No volumes found"
    
else
    echo "⚠️  Some services are not running"
    echo ""
    echo "📋 Recent logs:"
    echo ""
    echo "=== Prometheus ==="
    docker logs --tail 10 monitoring_prometheus 2>/dev/null || echo "Container not found"
    echo ""
    echo "=== Grafana ==="
    docker logs --tail 10 monitoring_grafana 2>/dev/null || echo "Container not found"
fi

echo ""
echo "💡 Useful commands:"
echo "   Start:    ./scripts/start-monitoring.sh"
echo "   Stop:     ./scripts/stop-monitoring.sh"
echo "   Logs:     docker-compose -f docker-compose-monitoring.yml logs -f"
echo "   Restart:  docker-compose -f docker-compose-monitoring.yml restart"
