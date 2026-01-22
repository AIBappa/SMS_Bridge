"""
SMS Bridge v2.4.0 - Admin Routes for Monitoring
API endpoints for HAProxy-based port management and monitoring configuration
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from core.admin.haproxy_port_management import (
    open_monitoring_port,
    close_monitoring_port,
    get_port_states,
    get_port_history,
    get_available_services,
    get_all_monitoring_states,
    get_server_ip,
    HAPROXY_BACKENDS,
)

logger = logging.getLogger(__name__)

# Create router
monitoring_router = APIRouter(prefix="/admin/monitoring", tags=["monitoring"])


# =============================================================================
# Authentication Dependency
# =============================================================================

async def require_admin_auth(request: Request):
    """
    Dependency to require admin authentication for monitoring routes.
    Checks if user is authenticated via session (same as SQLAdmin).
    """
    is_authenticated = request.session.get("authenticated", False)
    if not is_authenticated:
        raise HTTPException(status_code=401, detail="Authentication required")
    return request.session.get("username", "unknown")


# =============================================================================
# Request/Response Models
# =============================================================================

class OpenPortRequest(BaseModel):
    """Request to open a monitoring port"""
    duration_seconds: int = Field(3600, ge=900, le=86400, description="Duration in seconds (15min-24h)")


class ClosePortRequest(BaseModel):
    """Request to close a monitoring port"""
    service: str = Field(..., description="Service name to close")


class PortConfigUpdate(BaseModel):
    """Request to update port configuration"""
    config: Dict = Field(..., description="Complete monitoring configuration")


# =============================================================================
# Monitoring Service Endpoints (Database-Backed)
# =============================================================================

@monitoring_router.get("/services")
async def list_monitoring_services(request: Request, username: str = Depends(require_admin_auth), db: Session = Depends(get_db)):
    """
    List all available monitoring services and their current status.
    
    Returns:
        - Available services configuration
        - Current state from database and HAProxy
        - Time remaining for each active port
    """
    try:
        config = get_available_services()
        states = get_port_states(db)
        
        return {
            "config": config,
            "states": states,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to list monitoring services: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.post("/ports/{service_name}/open")
async def open_port_endpoint(
    request: Request, 
    service_name: str,
    body: OpenPortRequest,
    username: str = Depends(require_admin_auth),
    db: Session = Depends(get_db)
):
    """
    Enable a monitoring port via HAProxy for external access.
    
    Args:
        service_name: Service name (postgres, redis)
        duration_seconds: How long to keep port open (900-86400 seconds / 15min-24h)
    
    Returns:
        Port number, connection details, expiration time
        
    Security:
        - Only authenticated admin users can open ports
        - All actions logged with username and timestamp
        - Ports auto-close after expiration
    """
    try:
        result = open_monitoring_port(
            db=db,
            service_name=service_name,
            username=username,
            duration_seconds=body.duration_seconds
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        logger.error(f"HAProxy connection failed: {e}")
        raise HTTPException(status_code=503, detail=f"HAProxy unavailable: {e}")
    except Exception as e:
        logger.error(f"Failed to open port: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.post("/ports/{service_name}/close")
async def close_port_endpoint(
    request: Request,
    service_name: str,
    username: str = Depends(require_admin_auth),
    db: Session = Depends(get_db)
):
    """
    Disable an open monitoring port via HAProxy.
    
    Args:
        service_name: Service name to close
        
    Returns:
        Confirmation of closure
        
    Security:
        - Only authenticated admin users can close ports
        - All actions logged
    """
    try:
        result = close_monitoring_port(
            db=db,
            service_name=service_name,
            username=username,
            reason='manual'
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        logger.error(f"HAProxy connection failed: {e}")
        raise HTTPException(status_code=503, detail=f"HAProxy unavailable: {e}")
    except Exception as e:
        logger.error(f"Failed to close port: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.get("/port-states")
async def port_states_endpoint(request: Request, username: str = Depends(require_admin_auth), db: Session = Depends(get_db)):
    """
    Get current state of all monitoring ports from database and HAProxy.
    
    Returns:
        List of all ports with their current state
    """
    try:
        states = get_port_states(db)
        return {
            "states": states,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get port states: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.get("/port-history")
async def port_history_endpoint(
    request: Request,
    service_name: Optional[str] = None,
    limit: int = 50,
    username: str = Depends(require_admin_auth),
    db: Session = Depends(get_db)
):
    """
    Get history of port operations from database.
    
    Args:
        service_name: Filter by service (optional)
        limit: Max number of records to return
        
    Returns:
        List of historical port operations
    """
    try:
        history = get_port_history(db, service_name, limit)
        return {
            "history": history,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get port history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.get("/ports")
async def monitoring_ports_page(request: Request, username: str = Depends(require_admin_auth)):
    """
    Serve the monitoring ports management page
    
    Returns:
        HTML page for port management interface
    """
    try:
        # Read the HTML template
        template_path = Path("/app/core/templates/monitoring_ports.html")
        if not template_path.exists():
            # Fallback for development
            template_path = Path("core/templates/monitoring_ports.html")
        
        with open(template_path, 'r') as f:
            html_content = f.read()
        
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Failed to serve monitoring ports page: {e}")
        raise HTTPException(status_code=500, detail="Failed to load monitoring ports page")


@monitoring_router.post("/open-all")
async def open_all_ports(request: Request, duration_minutes: int = 60, username: str = Depends(require_admin_auth), db: Session = Depends(get_db)):
    """
    Enable all monitoring ports via HAProxy at once.
    
    Args:
        duration_minutes: How long to keep ports open (15-240 minutes)
        db: Database session
        
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
    
    results = {}
    
    for service_name in HAPROXY_BACKENDS.keys():
        try:
            result = open_monitoring_port(
                db=db,
                service_name=service_name,
                username=username,
                duration_seconds=duration_minutes * 60
            )
            results[service_name] = result
        except Exception as e:
            results[service_name] = {"error": str(e)}
    
    return {
        "status": "completed",
        "results": results,
        "timestamp": datetime.now().isoformat()
    }


@monitoring_router.post("/close-all")
async def close_all_ports(request: Request, username: str = Depends(require_admin_auth), db: Session = Depends(get_db)):
    """
    Disable all open monitoring ports via HAProxy.
    
    Args:
        db: Database session
        
    Returns:
        List of closed services
        
    Use case:
        Quick cleanup after monitoring session
    """
    states = get_port_states(db)
    active = {s["service_name"]: s for s in states if s.get("is_open")}
    closed = []
    errors = {}
    
    for service_name in active.keys():
        try:
            close_monitoring_port(db=db, service_name=service_name, username=username, reason='manual')
            closed.append(service_name)
        except Exception as e:
            logger.error(f"Failed to close {service_name}: {e}")
            errors[service_name] = str(e)
    
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
async def get_port_config(request: Request, username: str = Depends(require_admin_auth), db: Session = Depends(get_db)):
    """
    Get current port configuration.
    
    Returns:
        Available services and current states
    """
    try:
        config = get_available_services()
        states = get_port_states(db)
        active = [s["service_name"] for s in states if s.get("is_open")]
        
        return {
            "current_config": config,
            "active_ports": active,
            "version": "2.4.0",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get port config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitoring_router.get("/haproxy-status")
async def haproxy_status(request: Request, username: str = Depends(require_admin_auth)):
    """
    Get live HAProxy backend status.
    
    Returns:
        Current state of all monitoring backends from HAProxy
        
    Use case:
        Debug HAProxy connectivity and verify backend states
    """
    try:
        states = get_all_monitoring_states()
        return {
            "haproxy_backends": states,
            "timestamp": datetime.now().isoformat()
        }
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"HAProxy unavailable: {e}")
    except Exception as e:
        logger.error(f"Failed to get HAProxy status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Export Configuration Endpoint
# =============================================================================

@monitoring_router.get("/export-prometheus-config")
async def export_prometheus_config(request: Request, username: str = Depends(require_admin_auth)):
    """
    Export Prometheus configuration with current ports.
    
    Returns:
        prometheus-remote.yml file with actual server IP and ports
        
    Use case:
        Download this file to your laptop for monitoring setup
    """
    try:
        server_ip = get_server_ip()
        
        postgres_port = HAPROXY_BACKENDS["postgres"]["port"]
        redis_port = HAPROXY_BACKENDS["redis"]["port"]
        
        prometheus_config = f"""# SMS Bridge Monitoring Configuration
# Generated: {datetime.now().isoformat()}
# Server: {server_ip}
# 
# Monitoring Ports (HAProxy):
#   PostgreSQL: {postgres_port}
#   Redis: {redis_port}
#
# Note: Enable ports via Admin UI before connecting

global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    monitor: 'sms-bridge-remote'
    environment: 'production'

scrape_configs:
  # SMS Bridge Application (via HAProxy main port)
  - job_name: 'sms_bridge'
    static_configs:
      - targets: ['{server_ip}:8080']
    metrics_path: '/health'
    scrape_interval: 30s
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
async def list_logs(request: Request, username: str = Depends(require_admin_auth)):
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
async def download_logs(request: Request, service: str, username: str = Depends(require_admin_auth)):
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
