"""
SMS Bridge v2.3 - Database-Backed Port Management Module
Handles dynamic opening/closing of monitoring ports with iptables
State stored in PostgreSQL for persistence and audit trail
"""
import json
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Internal ports are fixed in docker-compose.yml
INTERNAL_PORTS = {
    "metrics": 8080,      # sms_receiver container
    "postgres": 5432,     # postgres container
    "pgbouncer": 6432,    # pgbouncer container
    "redis": 6379         # redis container
}

# Container name mappings
CONTAINER_NAMES = {
    "metrics": "sms_receiver",
    "postgres": "sms_postgres",
    "pgbouncer": "sms_pgbouncer",
    "redis": "sms_redis"
}


def load_monitoring_config() -> Dict:
    """Load monitoring port configuration from sms_settings.json"""
    try:
        settings_file = Path("/app/config/sms_settings.json")
        if not settings_file.exists():
            # Fallback to workspace path for development
            settings_file = Path("core/config/sms_settings.json")
        
        with open(settings_file) as f:
            config = json.load(f)
        
        monitoring_config = config.get("settings", {}).get("monitoring_ports", {})
        if not monitoring_config:
            logger.warning("No monitoring_ports in config, using defaults")
            return get_default_config()
        
        return monitoring_config
    except Exception as e:
        logger.error(f"Failed to load monitoring config: {e}")
        return get_default_config()


def get_default_config() -> Dict:
    """Return default monitoring port configuration"""
    return {
        "default_duration_seconds": 3600,
        "max_duration_seconds": 86400,
        "auto_close_enabled": True,
        "available_services": {
            "metrics": {
                "port": 9100,
                "service": "sms_receiver",
                "description": "Prometheus metrics endpoint"
            },
            "postgres": {
                "port": 5433,
                "service": "postgres",
                "description": "PostgreSQL database access"
            },
            "pgbouncer": {
                "port": 6434,
                "service": "pgbouncer",
                "description": "PgBouncer connection pooler"
            },
            "redis": {
                "port": 6380,
                "service": "redis",
                "description": "Redis cache access"
            }
        }
    }


def get_server_ip() -> str:
    """Get server IP address"""
    server_ip = os.getenv("SERVER_IP", "").strip()
    
    if not server_ip or server_ip == "auto":
        # Try to detect server IP
        try:
            result = subprocess.run(
                ["ip", "route", "get", "1.1.1.1"],
                capture_output=True,
                text=True,
                check=True
            )
            for part in result.stdout.split():
                if part.startswith("src"):
                    idx = result.stdout.split().index(part)
                    server_ip = result.stdout.split()[idx + 1]
                    break
        except Exception as e:
            logger.warning(f"Could not detect server IP: {e}")
            server_ip = "your-server-ip"
    
    return server_ip


def execute_iptables_open(external_port: int, container_ip: str, internal_port: int):
    """Execute iptables commands to open a port"""
    try:
        # Add DNAT rule to forward external port to container's internal port
        subprocess.run([
            "iptables", "-t", "nat", "-A", "PREROUTING",
            "-p", "tcp", "--dport", str(external_port),
            "-j", "DNAT", "--to-destination", f"{container_ip}:{internal_port}"
        ], check=True, capture_output=True)
        
        # Add FORWARD rule to allow forwarded traffic
        subprocess.run([
            "iptables", "-A", "FORWARD",
            "-p", "tcp",
            "-d", container_ip,
            "--dport", str(internal_port),
            "-j", "ACCEPT"
        ], check=True, capture_output=True)
        
        logger.info(f"Added iptables rules for port {external_port} -> {container_ip}:{internal_port}")
    except subprocess.CalledProcessError as e:
        logger.exception(f"Failed to add iptables rules: {e}")
        raise ValueError(f"Failed to open port: {e}") from e


def execute_iptables_close(external_port: int, container_ip: str, internal_port: int):
    """Execute iptables commands to close a port"""
    try:
        # Remove FORWARD rule
        subprocess.run([
            "iptables", "-D", "FORWARD",
            "-p", "tcp",
            "-d", container_ip,
            "--dport", str(internal_port),
            "-j", "ACCEPT"
        ], check=False, capture_output=True)
        
        # Remove DNAT rule
        subprocess.run([
            "iptables", "-t", "nat", "-D", "PREROUTING",
            "-p", "tcp", "--dport", str(external_port),
            "-j", "DNAT", "--to-destination", f"{container_ip}:{internal_port}"
        ], check=False, capture_output=True)
        
        logger.info(f"Removed iptables rules for port {external_port}")
    except Exception as e:
        logger.exception(f"Failed to remove iptables rules: {e}")


def get_container_ip(container_name: str) -> str:
    """Get IP address of a Docker container"""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container_name],
            capture_output=True, text=True, check=True
        )
        container_ip = result.stdout.strip()
        
        if not container_ip:
            raise ValueError(f"Could not determine IP for container {container_name}")
        
        return container_ip
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to get container IP: {e}") from e


def generate_connection_info(service: str, port: int, server_ip: str) -> Dict:
    """Generate connection information for a service"""
    if service in ["postgres", "pgbouncer"]:
        db_name = os.getenv("POSTGRES_DB", "sms_bridge")
        db_user = os.getenv("POSTGRES_USER", "postgres")
        return {
            "host": server_ip,
            "port": port,
            "database": db_name,
            "username": db_user,
            "connection_string": f"postgresql://{db_user}:****@{server_ip}:{port}/{db_name}",
            "note": "Get password from environment variables"
        }
    elif service == "redis":
        return {
            "host": server_ip,
            "port": port,
            "connection_string": f"redis://:****@{server_ip}:{port}/0",
            "note": "Get password from environment variables"
        }
    elif service == "metrics":
        return {
            "url": f"http://{server_ip}:{port}/metrics",
            "health": f"http://{server_ip}:{port}/health",
            "prometheus_target": f"{server_ip}:{port}"
        }
    return {}


# =============================================================================
# Database-Backed Port Management Functions
# =============================================================================

def open_monitoring_port(db: Session, service_name: str, username: str, duration_seconds: int = 3600) -> Dict:
    """
    Open a monitoring port and record in database
    
    Args:
        db: Database session
        service_name: Service to open (metrics, postgres, redis, pgbouncer)
        username: User opening the port
        duration_seconds: How long to keep port open
    
    Returns:
        Dict with port info and connection details
    """
    from core.models import MonitoringPortState, MonitoringPortHistory
    
    # Load configuration
    config = load_monitoring_config()
    available_services = config.get("available_services", {})
    
    if service_name not in available_services:
        raise ValueError(f"Unknown service: {service_name}")
    
    service_config = available_services[service_name]
    external_port = service_config["port"]
    
    # Check if service has internal port mapping
    if service_name not in INTERNAL_PORTS:
        raise ValueError(f"No internal port mapping for service: {service_name}")
    
    internal_port = INTERNAL_PORTS[service_name]
    container_name = CONTAINER_NAMES.get(service_name, service_name)
    
    # Check current state in database
    state = db.query(MonitoringPortState).filter(
        MonitoringPortState.service_name == service_name
    ).first()
    
    if state and state.is_open:
        # Port already open
        return {
            "status": "already_open",
            "service": service_name,
            "port": external_port,
            "opened_at": state.opened_at.isoformat() if state.opened_at else None,
            "opened_by": state.opened_by,
            "scheduled_close_at": state.scheduled_close_at.isoformat() if state.scheduled_close_at else None,
            "message": "Port is already open"
        }
    
    # Get container IP and open iptables
    container_ip = get_container_ip(container_name)
    execute_iptables_open(external_port, container_ip, internal_port)
    
    # Calculate times
    now = datetime.utcnow()
    scheduled_close = now + timedelta(seconds=duration_seconds)
    
    # Generate connection info
    server_ip = get_server_ip()
    connection_info = generate_connection_info(service_name, external_port, server_ip)
    
    # Update or create state in database
    if state:
        state.is_open = True
        state.opened_at = now
        state.opened_by = username
        state.scheduled_close_at = scheduled_close
        state.duration_seconds = duration_seconds
        state.closed_at = None
        state.closed_by = None
        state.close_reason = None
        state.updated_at = now
    else:
        state = MonitoringPortState(
            service_name=service_name,
            port=external_port,
            is_open=True,
            opened_at=now,
            opened_by=username,
            scheduled_close_at=scheduled_close,
            duration_seconds=duration_seconds
        )
        db.add(state)
    
    # Log to history
    history = MonitoringPortHistory(
        service_name=service_name,
        port=external_port,
        action='opened',
        action_by=username,
        duration_seconds=duration_seconds
    )
    db.add(history)
    
    db.commit()
    
    # Security log
    logger.warning(
        f"SECURITY: Monitoring port opened - "
        f"Service: {service_name}, Port: {external_port}, "
        f"User: {username}, Expires: {scheduled_close.isoformat()}"
    )
    
    return {
        "status": "opened",
        "service": service_name,
        "port": external_port,
        "opened_at": now.isoformat(),
        "scheduled_close_at": scheduled_close.isoformat(),
        "opened_by": username,
        "connection_info": connection_info
    }


def close_monitoring_port(db: Session, service_name: str, username: Optional[str] = None, reason: str = 'manual') -> Dict:
    """
    Close a monitoring port
    
    Args:
        db: Database session
        service_name: Service to close
        username: User closing the port (None for system)
        reason: Reason for closing (manual, auto_expired, system_shutdown)
    
    Returns:
        Dict with confirmation
    """
    from core.models import MonitoringPortState, MonitoringPortHistory
    
    # Get current state
    state = db.query(MonitoringPortState).filter(
        MonitoringPortState.service_name == service_name
    ).first()
    
    if not state:
        raise ValueError(f"Service {service_name} not found in database")
    
    if not state.is_open:
        return {
            "status": "already_closed",
            "service": service_name,
            "port": state.port,
            "message": "Port is already closed"
        }
    
    external_port = state.port
    internal_port = INTERNAL_PORTS.get(service_name)
    container_name = CONTAINER_NAMES.get(service_name, service_name)
    
    # Close iptables
    try:
        container_ip = get_container_ip(container_name)
        execute_iptables_close(external_port, container_ip, internal_port)
    except Exception as e:
        logger.error(f"Failed to close iptables for {service_name}: {e}")
        # Continue anyway to update database state
    
    # Update database state
    now = datetime.utcnow()
    closed_by = username if username else 'auto_close'
    
    state.is_open = False
    state.closed_at = now
    state.closed_by = closed_by
    state.close_reason = reason
    state.updated_at = now
    
    # Log to history
    history = MonitoringPortHistory(
        service_name=service_name,
        port=external_port,
        action='closed',
        action_by=closed_by,
        reason=reason
    )
    db.add(history)
    
    db.commit()
    
    # Security log
    logger.warning(
        f"SECURITY: Monitoring port closed - "
        f"Service: {service_name}, Port: {external_port}, "
        f"User: {closed_by}, Reason: {reason}"
    )
    
    return {
        "status": "closed",
        "service": service_name,
        "port": external_port,
        "closed_at": now.isoformat(),
        "closed_by": closed_by,
        "reason": reason
    }


def get_port_states(db: Session) -> List[Dict]:
    """Get current state of all monitoring ports"""
    from core.models import MonitoringPortState
    
    states = db.query(MonitoringPortState).order_by(MonitoringPortState.service_name).all()
    
    # Also load config to get descriptions
    config = load_monitoring_config()
    available_services = config.get("available_services", {})
    
    result = []
    for state in states:
        service_config = available_services.get(state.service_name, {})
        
        port_info = {
            "service_name": state.service_name,
            "port": state.port,
            "description": service_config.get("description", ""),
            "is_open": state.is_open,
            "opened_at": state.opened_at.isoformat() if state.opened_at else None,
            "opened_by": state.opened_by,
            "scheduled_close_at": state.scheduled_close_at.isoformat() if state.scheduled_close_at else None,
            "duration_seconds": state.duration_seconds,
        }
        
        # Calculate time remaining if open
        if state.is_open and state.scheduled_close_at:
            now = datetime.utcnow()
            remaining = (state.scheduled_close_at - now).total_seconds()
            port_info["time_remaining_seconds"] = max(0, int(remaining))
        
        result.append(port_info)
    
    return result


def get_port_history(db: Session, service_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Get history of port operations"""
    from core.models import MonitoringPortHistory
    
    query = db.query(MonitoringPortHistory)
    
    if service_name:
        query = query.filter(MonitoringPortHistory.service_name == service_name)
    
    history = query.order_by(MonitoringPortHistory.timestamp.desc()).limit(limit).all()
    
    return [
        {
            "id": h.id,
            "service_name": h.service_name,
            "port": h.port,
            "action": h.action,
            "action_by": h.action_by,
            "reason": h.reason,
            "duration_seconds": h.duration_seconds,
            "timestamp": h.timestamp.isoformat()
        }
        for h in history
    ]


def close_expired_ports(db: Session) -> List[str]:
    """Close all expired ports (called by background task)"""
    from core.models import MonitoringPortState
    
    now = datetime.utcnow()
    
    # Find expired open ports
    expired_states = db.query(MonitoringPortState).filter(
        MonitoringPortState.is_open == True,
        MonitoringPortState.scheduled_close_at <= now
    ).all()
    
    closed = []
    for state in expired_states:
        try:
            logger.info(f"Auto-closing expired port for service: {state.service_name}")
            close_monitoring_port(db, state.service_name, username=None, reason='auto_expired')
            closed.append(f"{state.service_name}:{state.port}")
        except Exception as e:
            logger.error(f"Failed to auto-close {state.service_name}: {e}")
    
    return closed
