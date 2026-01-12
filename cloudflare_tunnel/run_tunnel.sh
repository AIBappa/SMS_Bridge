#!/usr/bin/env bash
# Helper script to start/stop the cloudflared tunnel using docker-compose
# Usage: ./run_tunnel.sh up|down|status
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

cmd=${1:-up}
case "$cmd" in
  up)
    echo "Starting cloudflared tunnel..."
    docker compose up -d
    docker logs -f cloudflared-tunnel || true
    ;;
  down)
    echo "Stopping cloudflared tunnel..."
    docker compose down
    ;;
  status)
    docker ps --filter name=cloudflared-tunnel
    ;;
  *)
    echo "Usage: $0 up|down|status"
    exit 1
    ;;
esac
