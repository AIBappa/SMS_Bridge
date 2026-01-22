"""
SMS Bridge - HAProxy-Based Port Management Module
Controls monitoring ports via HAProxy stats socket (enable/disable backends)
No iptables required - simple TCP socket commands to HAProxy's internal port 9999
"""
import logging
import os
import socket
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# HAProxy backend/server mappings
HAPROXY_BACKENDS = {
    "postgres": {
        "backend": "postgres_monitor_back",
        "server": "pgbouncer",
        "port": int(os.getenv("POSTGRES_MONITOR_PORT", 9090)),
        "description": "PostgreSQL database access (via PgBouncer)"
    },
    "redis": {
        "backend": "redis_monitor_back",
        "server": "redis",
        "port": int(os.getenv("REDIS_MONITOR_PORT", 9091)),
        "description": "Redis cache access"
    }
}


def get_haproxy_connection() -> tuple:
    """Get HAProxy stats socket connection details"""
    host = os.getenv("HAPROXY_STATS_HOST", "sms_haproxy")
    port = int(os.getenv("HAPROXY_STATS_PORT", 9999))
    return host, port


def send_haproxy_command(command: str) -> str:
    """
    Send a command to HAProxy stats socket and return response.
    
    Args:
        command: HAProxy CLI command (e.g., "enable server backend/server")
    
    Returns:
        Response from HAProxy
    """
    host, port = get_haproxy_connection()
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5.0)
            sock.connect((host, port))
            sock.sendall(f"{command}\n".encode())
            
            # Read response
            response = b""
            while True:
                try:
                    data = sock.recv(4096)
                    if not data:
                        break
                    response += data
                except socket.timeout:
                    break
            
            return response.decode().strip()
    except socket.error as e:
        logger.error(f"HAProxy socket error: {e}")
        raise ConnectionError(f"Failed to connect to HAProxy stats socket: {e}")


def enable_backend_server(backend: str, server: str) -> bool:
    """Enable a server in a HAProxy backend"""
    command = f"enable server {backend}/{server}"
    try:
        response = send_haproxy_command(command)
        logger.info(f"HAProxy enable: {command} -> {response or 'OK'}")
        return True
    except Exception as e:
        logger.error(f"Failed to enable {backend}/{server}: {e}")
        raise


def disable_backend_server(backend: str, server: str) -> bool:
    """Disable a server in a HAProxy backend"""
    command = f"disable server {backend}/{server}"
    try:
        response = send_haproxy_command(command)
        logger.info(f"HAProxy disable: {command} -> {response or 'OK'}")
        return True
    except Exception as e:
        logger.error(f"Failed to disable {backend}/{server}: {e}")
        raise


def get_server_state(backend: str, server: str) -> Dict:
    """Get the current state of a server in a backend"""
    command = f"show servers state {backend}"
    try:
        response = send_haproxy_command(command)
        # Parse response - format: version\n<header>\n<data lines>
        lines = response.strip().split("\n")
        
        for line in lines:
            parts = line.split()
            # Format: be_id be_name srv_id srv_name srv_addr srv_op_state ...
            if len(parts) >= 6 and parts[3] == server:
                # srv_op_state: 0=stopped, 2=running
                op_state = int(parts[5]) if parts[5].isdigit() else 0
                return {
                    "backend": backend,
                    "server": server,
                    "enabled": op_state == 2,
                    "state_code": op_state
                }
        
        return {"backend": backend, "server": server, "enabled": False, "state_code": -1}
    except Exception as e:
        logger.error(f"Failed to get state for {backend}/{server}: {e}")
        return {"backend": backend, "server": server, "enabled": False, "error": str(e)}


def get_all_monitoring_states() -> List[Dict]:
    """Get current state of all monitoring backends"""
    states = []
    for service_name, config in HAPROXY_BACKENDS.items():
        state = get_server_state(config["backend"], config["server"])
        states.append({
            "service_name": service_name,
            "port": config["port"],
            "description": config["description"],
            "enabled": state.get("enabled", False),
            "backend": config["backend"],
            "server": config["server"]
        })
    return states


def get_server_ip() -> str:
    """Get server IP address for connection strings"""
    import subprocess
    
    server_ip = os.getenv("SERVER_IP", "").strip()
    
    if not server_ip or server_ip == "auto":
        try:
            result = subprocess.run(
                ["ip", "route", "get", "1.1.1.1"],
                capture_output=True, text=True, check=True
            )
            for i, part in enumerate(result.stdout.split()):
                if part == "src" and i + 1 < len(result.stdout.split()):
                    server_ip = result.stdout.split()[i + 1]
                    break
        except Exception as e:
            logger.warning(f"Could not detect server IP: {e}")
            server_ip = "your-server-ip"
    
    return server_ip


def generate_connection_info(service_name: str, port: int) -> Dict:
    """Generate connection information for a monitoring service"""
    server_ip = get_server_ip()
    
    if service_name == "postgres":
        db_name = os.getenv("POSTGRES_DB", os.getenv("SMS_BRIDGE_DATABASE__NAME", "sms_bridge"))
        db_user = os.getenv("POSTGRES_USER", os.getenv("SMS_BRIDGE_DATABASE__USER", "postgres"))
        return {
            "type": "postgresql",
            "host": server_ip,
            "port": port,
            "database": db_name,
            "username": db_user,
            "connection_string": f"postgresql://{db_user}:****@{server_ip}:{port}/{db_name}",
            "note": "Password from POSTGRES_PASSWORD environment variable"
        }
    elif service_name == "redis":
        return {
            "type": "redis",
            "host": server_ip,
            "port": port,
            "connection_string": f"redis://:****@{server_ip}:{port}/0",
            "note": "Password from REDIS_PASSWORD environment variable"
        }
    return {"host": server_ip, "port": port}


# =============================================================================
# Database-Backed Port Management Functions
# =============================================================================

def open_monitoring_port(db: Session, service_name: str, username: str, duration_seconds: int = 3600) -> Dict:
    """
    Enable a monitoring port via HAProxy and record in database.
    
    Args:
        db: Database session
        service_name: Service to enable (postgres, redis)
        username: User enabling the port
        duration_seconds: How long to keep port open
    
    Returns:
        Dict with port info and connection details
    """
    from core.models import MonitoringPortState, MonitoringPortHistory
    
    if service_name not in HAPROXY_BACKENDS:
        raise ValueError(f"Unknown service: {service_name}. Available: {list(HAPROXY_BACKENDS.keys())}")
    
    config = HAPROXY_BACKENDS[service_name]
    backend = config["backend"]
    server = config["server"]
    port = config["port"]
    
    # Check current state in database
    state = db.query(MonitoringPortState).filter(
        MonitoringPortState.service_name == service_name
    ).first()
    
    if state and state.is_open:
        return {
            "status": "already_open",
            "service": service_name,
            "port": port,
            "opened_at": state.opened_at.isoformat() if state.opened_at else None,
            "opened_by": state.opened_by,
            "scheduled_close_at": state.scheduled_close_at.isoformat() if state.scheduled_close_at else None,
            "message": "Port is already open"
        }
    
    # Enable the server in HAProxy
    enable_backend_server(backend, server)
    
    # Calculate times
    now = datetime.utcnow()
    scheduled_close = now + timedelta(seconds=duration_seconds)
    
    # Generate connection info
    connection_info = generate_connection_info(service_name, port)
    
    # Update or create state in database
    if state:
        state.is_open = True
        state.port = port
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
            port=port,
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
        port=port,
        action='opened',
        action_by=username,
        duration_seconds=duration_seconds
    )
    db.add(history)
    
    db.commit()
    
    # Security log
    logger.warning(
        f"SECURITY: Monitoring port opened via HAProxy - "
        f"Service: {service_name}, Port: {port}, "
        f"User: {username}, Expires: {scheduled_close.isoformat()}"
    )
    
    return {
        "status": "opened",
        "service": service_name,
        "port": port,
        "opened_at": now.isoformat(),
        "scheduled_close_at": scheduled_close.isoformat(),
        "opened_by": username,
        "connection_info": connection_info
    }


def close_monitoring_port(db: Session, service_name: str, username: Optional[str] = None, reason: str = 'manual') -> Dict:
    """
    Disable a monitoring port via HAProxy.
    
    Args:
        db: Database session
        service_name: Service to disable
        username: User disabling the port (None for system/auto)
        reason: Reason for closing (manual, auto_expired, system_shutdown)
    
    Returns:
        Dict with confirmation
    """
    from core.models import MonitoringPortState, MonitoringPortHistory
    
    if service_name not in HAPROXY_BACKENDS:
        raise ValueError(f"Unknown service: {service_name}. Available: {list(HAPROXY_BACKENDS.keys())}")
    
    config = HAPROXY_BACKENDS[service_name]
    backend = config["backend"]
    server = config["server"]
    port = config["port"]
    
    # Get current state from database
    state = db.query(MonitoringPortState).filter(
        MonitoringPortState.service_name == service_name
    ).first()
    
    if state and not state.is_open:
        return {
            "status": "already_closed",
            "service": service_name,
            "port": port,
            "message": "Port is already closed"
        }
    
    # Disable the server in HAProxy
    try:
        disable_backend_server(backend, server)
    except Exception as e:
        logger.error(f"Failed to disable HAProxy backend for {service_name}: {e}")
        # Continue anyway to update database state
    
    # Update database state
    now = datetime.utcnow()
    closed_by = username if username else 'auto_close'
    
    if state:
        state.is_open = False
        state.closed_at = now
        state.closed_by = closed_by
        state.close_reason = reason
        state.updated_at = now
    else:
        # Create a closed state if none exists
        state = MonitoringPortState(
            service_name=service_name,
            port=port,
            is_open=False,
            closed_at=now,
            closed_by=closed_by,
            close_reason=reason
        )
        db.add(state)
    
    # Log to history
    history = MonitoringPortHistory(
        service_name=service_name,
        port=port,
        action='closed',
        action_by=closed_by,
        reason=reason
    )
    db.add(history)
    
    db.commit()
    
    # Security log
    logger.warning(
        f"SECURITY: Monitoring port closed via HAProxy - "
        f"Service: {service_name}, Port: {port}, "
        f"User: {closed_by}, Reason: {reason}"
    )
    
    return {
        "status": "closed",
        "service": service_name,
        "port": port,
        "closed_at": now.isoformat(),
        "closed_by": closed_by,
        "reason": reason
    }


def get_port_states(db: Session) -> List[Dict]:
    """Get current state of all monitoring ports from database + HAProxy"""
    from core.models import MonitoringPortState
    
    # Get HAProxy live states
    haproxy_states = {s["service_name"]: s for s in get_all_monitoring_states()}
    
    result = []
    for service_name, config in HAPROXY_BACKENDS.items():
        # Database state
        db_state = db.query(MonitoringPortState).filter(
            MonitoringPortState.service_name == service_name
        ).first()
        
        # HAProxy state
        haproxy_state = haproxy_states.get(service_name, {})
        
        port_info = {
            "service_name": service_name,
            "port": config["port"],
            "description": config["description"],
            "is_open": db_state.is_open if db_state else False,
            "haproxy_enabled": haproxy_state.get("enabled", False),
            "opened_at": db_state.opened_at.isoformat() if db_state and db_state.opened_at else None,
            "opened_by": db_state.opened_by if db_state else None,
            "scheduled_close_at": db_state.scheduled_close_at.isoformat() if db_state and db_state.scheduled_close_at else None,
            "duration_seconds": db_state.duration_seconds if db_state else None,
        }
        
        # Calculate time remaining if open
        if db_state and db_state.is_open and db_state.scheduled_close_at:
            now = datetime.utcnow()
            remaining = (db_state.scheduled_close_at - now).total_seconds()
            port_info["time_remaining_seconds"] = max(0, int(remaining))
        
        result.append(port_info)
    
    return result


def get_port_history(db: Session, service_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Get history of port operations from database"""
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


def get_available_services() -> Dict:
    """Return configuration of available monitoring services"""
    return {
        "services": HAPROXY_BACKENDS,
        "default_duration_seconds": 3600,
        "max_duration_seconds": 86400,
        "auto_close_enabled": True
    }


def sync_haproxy_with_database(db: Session) -> Dict:
    """
    Synchronize HAProxy state with database state.
    Called on application startup to ensure consistency.
    
    Returns:
        Dict with sync results
    """
    from core.models import MonitoringPortState
    
    results = {"enabled": [], "disabled": [], "errors": []}
    
    for service_name, config in HAPROXY_BACKENDS.items():
        try:
            db_state = db.query(MonitoringPortState).filter(
                MonitoringPortState.service_name == service_name
            ).first()
            
            backend = config["backend"]
            server = config["server"]
            
            # If database says open and not expired, enable in HAProxy
            if db_state and db_state.is_open:
                now = datetime.utcnow()
                if db_state.scheduled_close_at and db_state.scheduled_close_at > now:
                    enable_backend_server(backend, server)
                    results["enabled"].append(service_name)
                else:
                    # Expired - disable and update database
                    disable_backend_server(backend, server)
                    close_monitoring_port(db, service_name, reason='auto_expired')
                    results["disabled"].append(service_name)
            else:
                # Ensure disabled in HAProxy
                disable_backend_server(backend, server)
                results["disabled"].append(service_name)
                
        except Exception as e:
            logger.error(f"Failed to sync {service_name}: {e}")
            results["errors"].append(f"{service_name}: {e}")
    
    logger.info(f"HAProxy sync completed: {results}")
    return results
