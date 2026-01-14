"""
SMS Bridge v2.3 - Port Management Module
Handles dynamic opening/closing of monitoring ports with iptables
"""
import json
import logging
import os
import socket
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Port mappings persistent storage
PORT_MAPPINGS_FILE = Path("/app/logs/port_mappings.json")

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

# Service types for connection string generation
SERVICE_TYPES = {
    "metrics": "http",
    "postgres": "database",
    "pgbouncer": "database",
    "redis": "cache"
}

# Active port mappings (in-memory cache)
active_port_mappings: Dict[str, Dict] = {}


def load_monitoring_config() -> Dict:
    """Load monitoring port configuration from sms_settings.json"""
    try:
        settings_file = Path("/app/config/sms_settings.json")
        if not settings_file.exists():
            logger.warning("sms_settings.json not found, using defaults")
            return get_default_config()
        
        with open(settings_file) as f:
            config = json.load(f)
        
        monitoring_ports = config.get("settings", {}).get("monitoring_ports", {})
        if not monitoring_ports:
            logger.warning("No monitoring_ports in config, using defaults")
            return get_default_config()
        
        return monitoring_ports
    except Exception as e:
        logger.error(f"Failed to load monitoring config: {e}")
        return get_default_config()


def get_default_config() -> Dict:
    """Return default monitoring port configuration"""
    return {
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


def save_monitoring_config(monitoring_ports: Dict):
    """Save monitoring port configuration to sms_settings.json"""
    try:
        settings_file = Path("/app/config/sms_settings.json")
        temp_file = settings_file.with_suffix('.json.tmp')
        
        # Ensure config directory exists
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Read existing config
        with open(settings_file) as f:
            config = json.load(f)
        
        # Update monitoring ports section
        if "settings" not in config:
            config["settings"] = {}
        config["settings"]["monitoring_ports"] = monitoring_ports
        
        # Write to temp file first
        with open(temp_file, "w") as f:
            json.dump(config, f, indent=2)
        
        # Atomic rename
        temp_file.replace(settings_file)
        
        logger.info("Monitoring port configuration saved")
    except Exception as e:
        logger.exception("Failed to save monitoring config")
        raise


def load_port_mappings() -> Dict:
    """Load active port mappings from file"""
    try:
        if PORT_MAPPINGS_FILE.exists():
            with open(PORT_MAPPINGS_FILE) as f:
                data = json.load(f)
                # Convert ISO strings back to datetime
                for service in data.values():
                    service["opened_at"] = datetime.fromisoformat(service["opened_at"])
                    service["expires_at"] = datetime.fromisoformat(service["expires_at"])
                return data
    except Exception as e:
        logger.error(f"Failed to load port mappings: {e}")
    return {}


def save_port_mappings(mappings: Dict):
    """Save port mappings to file"""
    try:
        # Create logs directory if it doesn't exist
        PORT_MAPPINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        serializable = {}
        for service, data in mappings.items():
            serializable[service] = {
                **data,
                "opened_at": data["opened_at"].isoformat(),
                "expires_at": data["expires_at"].isoformat()
            }
        with open(PORT_MAPPINGS_FILE, "w") as f:
            json.dump(serializable, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save port mappings: {e}")


def validate_port_available(port: int) -> bool:
    """Check if port is available on the system"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('', port))
        sock.close()
        return True
    except OSError:
        return False


def validate_port_config(config: Dict) -> Tuple[bool, List[str]]:
    """Validate monitoring port configuration"""
    errors = []
    used_ports = set()
    
    for service, settings in config.items():
        external_port = settings.get("port")
        
        if not external_port:
            errors.append(f"{service}: Missing port configuration")
            continue
        
        # Range check
        if not (1024 <= external_port <= 65535):
            errors.append(f"{service}: Port {external_port} must be in range 1024-65535")
        
        # Uniqueness check
        if external_port in used_ports:
            errors.append(f"{service}: Port {external_port} already used by another service")
        used_ports.add(external_port)
        
        # Availability check (if enabled)
        if settings.get("enabled", False):
            if not validate_port_available(external_port):
                errors.append(f"{service}: Port {external_port} is already in use")
    
    return len(errors) == 0, errors


def scan_available_ports(start: int = 9000, end: int = 9999, count: int = 10) -> List[int]:
    """Scan for available ports in range"""
    available = []
    for port in range(start, end + 1):
        if len(available) >= count:
            break
        if validate_port_available(port):
            available.append(port)
    return available


def get_server_ip() -> str:
    """Get server IP address"""
    server_ip = os.getenv("SERVER_IP", "").strip()
    
    if not server_ip or server_ip == "auto":
        # Try to detect server IP
        try:
            # Get default route interface
            result = subprocess.run(
                ["ip", "route", "get", "1.1.1.1"],
                capture_output=True,
                text=True,
                check=True
            )
            # Parse output: "1.1.1.1 via X.X.X.X dev eth0 src Y.Y.Y.Y"
            for part in result.stdout.split():
                if part.startswith("src"):
                    idx = result.stdout.split().index(part)
                    server_ip = result.stdout.split()[idx + 1]
                    break
        except Exception as e:
            logger.warning(f"Could not detect server IP: {e}")
            server_ip = "your-server-ip"
    
    return server_ip


def open_monitoring_port(service: str, duration_minutes: int, username: str) -> Dict:
    """
    Open a monitoring port for external access
    - External port comes from sms_settings.json (configurable)
    - Internal port is fixed based on service type
    - Port is exposed via iptables rule
    - Automatically closes after duration
    - Logs who opened it and when
    """
    # Load current configuration
    config = load_monitoring_config()
    
    if service not in config:
        raise ValueError(f"Unknown service: {service}")
    
    service_config = config[service]
    
    if not service_config.get("enabled", False):
        raise ValueError(f"Service '{service}' is disabled in configuration")
    
    # External port from sms_settings.json (configurable)
    external_port = service_config["port"]
    
    # Internal port is fixed
    if service not in INTERNAL_PORTS:
        raise ValueError(f"No internal port mapping for service: {service}")
    
    internal_port = INTERNAL_PORTS[service]
    container_name = CONTAINER_NAMES.get(service, service)
    
    # Check if already open
    if service in active_port_mappings:
        return {
            "status": "already_open",
            "service": service,
            "port": external_port,
            "message": "Port is already open",
            **active_port_mappings[service]
        }
    
    # Validate port still available
    if not validate_port_available(external_port):
        raise ValueError(f"Port {external_port} is not available")
    
    # Get server IP
    server_ip = get_server_ip()
    
    # Add iptables rules to forward traffic to container
    try:
        # Get container IP address
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container_name],
            capture_output=True, text=True, check=True
        )
        container_ip = result.stdout.strip()
        
        if not container_ip:
            raise ValueError(f"Could not determine IP for container {container_name}")
        
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
    
    now = datetime.now()
    expires_at = now + timedelta(minutes=duration_minutes)
    
    # Generate connection information
    connection_info = generate_connection_string(service, external_port, server_ip)
    
    # Store mapping
    active_port_mappings[service] = {
        "external_port": external_port,
        "internal_port": internal_port,
        "container": container_name,
        "opened_at": now,
        "expires_at": expires_at,
        "opened_by": username,
        "connection_info": connection_info
    }
    
    # Persist to file
    save_port_mappings(active_port_mappings)
    
    # Log the action
    logger.warning(
        f"SECURITY: Monitoring port opened - "
        f"Service: {service}, Port: {external_port}, "
        f"User: {username}, Expires: {expires_at.isoformat()}"
    )
    
    return {
        "status": "opened",
        "service": service,
        "port": external_port,
        "opened_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "connection_info": connection_info
    }


def close_monitoring_port(service: str, username: str) -> Dict:
    """Close an open monitoring port"""
    if service not in active_port_mappings:
        return {"error": "Port not open", "service": service}
    
    mapping = active_port_mappings[service]
    external_port = mapping["external_port"]
    internal_port = mapping["internal_port"]
    container_name = mapping["container"]
    
    # Remove iptables rules
    try:
        # Get container IP address
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container_name],
            capture_output=True, text=True, check=False
        )
        container_ip = result.stdout.strip()
        
        if container_ip:
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
    
    # Log the action
    logger.warning(
        f"SECURITY: Monitoring port closed - "
        f"Service: {service}, Port: {external_port}, "
        f"User: {username}"
    )
    
    # Remove from active mappings
    del active_port_mappings[service]
    save_port_mappings(active_port_mappings)
    
    return {
        "status": "closed",
        "service": service,
        "port": external_port
    }


def generate_connection_string(service: str, port: int, server_ip: str) -> Dict:
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


def get_active_ports() -> Dict:
    """Get all currently active port mappings (read-only)"""
    now = datetime.now()
    return {
        service: {
            "port": data["external_port"],
            "opened_at": data["opened_at"].isoformat(),
            "expires_at": data["expires_at"].isoformat(),
            "opened_by": data["opened_by"],
            "time_remaining": str(data["expires_at"] - now),
            "connection_info": data["connection_info"],
            "expired": data["expires_at"] < now
        }
        for service, data in active_port_mappings.items()
    }


def close_expired_ports() -> List[str]:
    """Close all expired ports (called by background task)"""
    now = datetime.now()
    expired = [
        service for service, data in active_port_mappings.items()
        if data["expires_at"] < now
    ]
    
    closed = []
    for service in expired:
        try:
            logger.info("Auto-closing expired port for service: %s", service)
            close_monitoring_port(service, "system-auto-close")
            closed.append(service)
        except Exception as e:
            logger.error(f"Failed to auto-close {service}: {e}")
    
    return closed


# Initialize active port mappings on module load
active_port_mappings = load_port_mappings()
logger.info(f"Loaded {len(active_port_mappings)} active port mappings")
