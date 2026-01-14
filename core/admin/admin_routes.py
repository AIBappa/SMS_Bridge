"""
SMS Bridge v2.3 - Admin Routes for Monitoring
API endpoints for port management and monitoring configuration
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field

from core.admin.port_management import (
    close_monitoring_port,
    get_active_ports,
    load_monitoring_config,
    open_monitoring_port,
    save_monitoring_config,
    scan_available_ports,
    validate_port_config,
)

logger = logging.getLogger(__name__)

# Create router
monitoring_router = APIRouter(prefix="/admin/monitoring", tags=["monitoring"])


# =============================================================================
# Request/Response Models
# =============================================================================

class OpenPortRequest(BaseModel):
    """Request to open a monitoring port"""
    service: str = Field(..., description="Service name (metrics, postgres, redis, pgbouncer)")
    duration_minutes: int = Field(60, ge=15, le=240, description="Duration in minutes (15-240)")


class PortConfigUpdate(BaseModel):
    """Request to update port configuration"""
    config: Dict[str, Dict] = Field(..., description="Complete monitoring port configuration")


class ClosePortRequest(BaseModel):
    """Request to close a monitoring port"""
    service: str = Field(..., description="Service name to close")


# =============================================================================
# Monitoring Service Endpoints
# =============================================================================

@monitoring_router.get("/services")
async def list_monitoring_services(request: Request):
    """
    List all available monitoring services and their current status
    
    Returns:
        - Service configuration from sms_settings.json
        - Currently active ports
        - Time remaining for each active port
    """
    try:
        config = load_monitoring_config()
        active = get_active_ports()
        
        return {
            "services": config,
            "active_ports": active,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to list monitoring services: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.post("/open-port")
async def open_port_endpoint(request: Request, body: OpenPortRequest):
    """
    Open a monitoring port for external access
    
    Args:
        service: Service name (metrics, postgres, redis, pgbouncer)
        duration_minutes: How long to keep port open (15-240 minutes)
    
    Returns:
        Port number, connection details, expiration time
        
    Security:
        - Only authenticated admin users can open ports
        - All actions logged with username and timestamp
        - Ports auto-close after expiration
    """
    # Get username from session (set by auth middleware)
    username = request.session.get("username", "unknown")
    
    try:
        result = open_monitoring_port(
            service=body.service,
            duration_minutes=body.duration_minutes,
            username=username
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to open port: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.post("/close-port")
async def close_port_endpoint(request: Request, body: ClosePortRequest):
    """
    Close an open monitoring port
    
    Args:
        service: Service name to close
        
    Returns:
        Confirmation of closure
        
    Security:
        - Only authenticated admin users can close ports
        - All actions logged
    """
    username = request.session.get("username", "unknown")
    
    try:
        result = close_monitoring_port(
            service=body.service,
            username=username
        )
        return result
    except Exception as e:
        logger.error(f"Failed to close port: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.get("/port-status")
async def port_status_endpoint(request: Request):
    """
    Get status of all monitoring ports
    
    Returns:
        Currently open ports with time remaining
        
    Note:
        Automatically closes expired ports
    """
    try:
        return get_active_ports()
    except Exception as e:
        logger.error(f"Failed to get port status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.post("/open-all")
async def open_all_ports(request: Request, duration_minutes: int = 60):
    """
    Open all enabled monitoring ports at once
    
    Args:
        duration_minutes: How long to keep ports open (15-240 minutes)
        
    Returns:
        Results for each service
        
    Use case:
        Quick setup for monitoring session
    """
    if not (15 <= duration_minutes <= 240):
        raise HTTPException(
            status_code=400,
            detail="Duration must be between 15 and 240 minutes"
        )
    
    username = request.session.get("username", "unknown")
    config = load_monitoring_config()
    results = {}
    
    for service, settings in config.items():
        if settings.get("enabled", False):
            try:
                result = open_monitoring_port(service, duration_minutes, username)
                results[service] = result
            except Exception as e:
                results[service] = {"error": str(e)}
    
    return {
        "status": "completed",
        "results": results,
        "timestamp": datetime.now().isoformat()
    }


@monitoring_router.post("/close-all")
async def close_all_ports(request: Request):
    """
    Close all open monitoring ports
    
    Returns:
        List of closed services
        
    Use case:
        Quick cleanup after monitoring session
    """
    username = request.session.get("username", "unknown")
    active = get_active_ports()
    closed = []
    errors = {}
    
    for service in active.keys():
        try:
            close_monitoring_port(service, username)
            closed.append(service)
        except Exception as e:
            logger.error(f"Failed to close {service}: {e}")
            errors[service] = str(e)
    
    return {
        "status": "completed",
        "closed": closed,
        "errors": errors if errors else None,
        "timestamp": datetime.now().isoformat()
    }


# =============================================================================
# Port Configuration Endpoints
# =============================================================================

@monitoring_router.get("/port-config")
async def get_port_config(request: Request):
    """
    Get current port configuration from sms_settings.json
    
    Returns:
        Complete monitoring port configuration
    """
    try:
        config = load_monitoring_config()
        active = get_active_ports()
        
        return {
            "current_config": config,
            "active_ports": list(active.keys()),
            "version": "2.3.0",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get port config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.post("/port-config")
async def update_port_config(request: Request, body: PortConfigUpdate):
    """
    Update port configuration in sms_settings.json
    
    Args:
        config: Complete monitoring port configuration
        
    Returns:
        Updated configuration
        
    Security:
        - Cannot update while ports are open
        - Configuration validated before saving
        - All changes logged
    """
    username = request.session.get("username", "unknown")
    
    # Check if any ports are currently open
    active = get_active_ports()
    if active:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Cannot change port configuration while ports are open",
                "active_ports": list(active.keys()),
                "action": "Close all ports first using /admin/monitoring/close-all"
            }
        )
    
    # Validate configuration
    is_valid, errors = validate_port_config(body.config)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail={"errors": errors}
        )
    
    try:
        # Save configuration
        save_monitoring_config(body.config)
        
        # Log change
        logger.warning(
            f"SECURITY: Port configuration updated - "
            f"User: {username}, "
            f"Timestamp: {datetime.now().isoformat()}"
        )
        
        return {
            "status": "success",
            "config": body.config,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to update port config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.post("/port-config/reset")
async def reset_port_config(request: Request):
    """
    Reset port configuration to defaults
    
    Returns:
        Default configuration
        
    Use case:
        Restore defaults if configuration becomes invalid
    """
    username = request.session.get("username", "unknown")
    
    # Check if any ports are currently open
    active = get_active_ports()
    if active:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Cannot reset configuration while ports are open",
                "active_ports": list(active.keys())
            }
        )
    
    default_config = {
        "metrics": {
            "port": 9100,
            "service": "sms_receiver",
            "description": "Prometheus metrics endpoint",
            "enabled": True
        },
        "postgres": {
            "port": 5433,
            "service": "postgres",
            "description": "PostgreSQL database access",
            "enabled": True
        },
        "pgbouncer": {
            "port": 6434,
            "service": "pgbouncer",
            "description": "PgBouncer connection pooler",
            "enabled": False
        },
        "redis": {
            "port": 6380,
            "service": "redis",
            "description": "Redis cache access",
            "enabled": True
        }
    }
    
    try:
        save_monitoring_config(default_config)
        
        logger.warning(
            f"SECURITY: Port configuration reset to defaults - "
            f"User: {username}"
        )
        
        return {
            "status": "reset",
            "config": default_config,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to reset port config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.get("/port-config/available-ports")
async def get_available_ports(
    request: Request,
    start: int = 9000,
    end: int = 9999,
    count: int = 10
):
    """
    Scan for available ports in specified range
    
    Args:
        start: Start of port range (default: 9000)
        end: End of port range (default: 9999)
        count: Number of ports to return (default: 10)
        
    Returns:
        List of available port numbers
        
    Use case:
        Find available ports when configuring monitoring
    """
    try:
        available = scan_available_ports(start, end, count)
        return {
            "available_ports": available,
            "scanned_range": f"{start}-{end}",
            "count": len(available)
        }
    except Exception as e:
        logger.error(f"Failed to scan ports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Export Configuration Endpoint
# =============================================================================

@monitoring_router.get("/export-prometheus-config")
async def export_prometheus_config(request: Request):
    """
    Export Prometheus configuration with current ports
    
    Returns:
        prometheus-remote.yml file with actual server IP and ports
        
    Use case:
        Download this file to your laptop for monitoring setup
        Save as: coolify-monitoring/config/prometheus-remote.yml
    """
    try:
        config = load_monitoring_config()
        server_ip = os.getenv("SERVER_IP", "your-server-ip")
        
        # Auto-detect server IP if set to "auto"
        if server_ip == "auto":
            from core.admin.port_management import get_server_ip
            server_ip = get_server_ip()
        
        metrics_port = config.get("metrics", {}).get("port", 9100)
        
        prometheus_config = f"""# Prometheus Remote Configuration
# Generated: {datetime.now().isoformat()}
# Server: {server_ip}
# 
# Save this file as: coolify-monitoring/config/prometheus-remote.yml
# Then start monitoring: ./scripts/start-monitoring.sh

global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    monitor: 'sms-bridge-remote'
    environment: 'production'

scrape_configs:
  # SMS Bridge Application Metrics
  - job_name: 'sms_receiver'
    static_configs:
      - targets: ['{server_ip}:{metrics_port}']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s

  # Prometheus Self-Monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
"""
        
        return Response(
            content=prometheus_config,
            media_type="text/yaml",
            headers={
                "Content-Disposition": "attachment; filename=prometheus-remote.yml"
            }
        )
    except Exception as e:
        logger.error(f"Failed to export prometheus config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Log Management Endpoints
# =============================================================================

@monitoring_router.get("/logs/list")
async def list_logs(request: Request):
    """
    List available log files
    
    Returns:
        Dictionary of available log files with sizes
    """
    try:
        logs_dir = Path("/app/logs")
        log_files = {}
        
        # Application logs
        app_log = logs_dir / "sms_bridge.log"
        if app_log.exists():
            log_files["application"] = {
                "path": str(app_log),
                "size": app_log.stat().st_size,
                "modified": datetime.fromtimestamp(app_log.stat().st_mtime).isoformat()
            }
        
        # PostgreSQL logs
        postgres_dir = logs_dir / "postgres"
        if postgres_dir.exists():
            postgres_logs = list(postgres_dir.glob("postgresql-*.log"))
            if postgres_logs:
                latest = max(postgres_logs, key=lambda p: p.stat().st_mtime)
                log_files["postgres"] = {
                    "path": str(latest),
                    "size": latest.stat().st_size,
                    "modified": datetime.fromtimestamp(latest.stat().st_mtime).isoformat()
                }
        
        # Redis logs
        redis_log = logs_dir / "redis" / "redis.log"
        if redis_log.exists():
            log_files["redis"] = {
                "path": str(redis_log),
                "size": redis_log.stat().st_size,
                "modified": datetime.fromtimestamp(redis_log.stat().st_mtime).isoformat()
            }
        
        return {
            "logs": log_files,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to list logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.get("/logs/download/{service}")
async def download_logs(request: Request, service: str):
    """
    Download logs for a specific service
    
    Args:
        service: Service name (application, postgres, redis)
        
    Returns:
        Log file download
    """
    try:
        logs_dir = Path("/app/logs")
        
        if service == "application":
            log_path = logs_dir / "sms_bridge.log"
        elif service == "postgres":
            postgres_dir = logs_dir / "postgres"
            postgres_logs = list(postgres_dir.glob("postgresql-*.log"))
            if not postgres_logs:
                raise HTTPException(status_code=404, detail="No PostgreSQL logs found")
            log_path = max(postgres_logs, key=lambda p: p.stat().st_mtime)
        elif service == "redis":
            log_path = logs_dir / "redis" / "redis.log"
        else:
            raise HTTPException(status_code=400, detail="Invalid service")
        
        if not log_path.exists():
            raise HTTPException(status_code=404, detail="Log file not found")
        
        return FileResponse(
            log_path,
            media_type="text/plain",
            filename=f"{service}-{datetime.now().strftime('%Y%m%d')}.log"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
