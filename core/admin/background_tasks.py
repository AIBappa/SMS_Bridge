"""
SMS Bridge v2.3 - Background Tasks
Periodic tasks for monitoring port management and system maintenance
"""
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def auto_close_expired_ports_task():
    """
    Background task that runs every minute to close expired monitoring ports
    
    This task:
    1. Checks for expired ports every 60 seconds
    2. Closes any ports that have exceeded their duration
    3. Logs all auto-close actions
    """
    from core.admin.port_management import close_expired_ports
    
    logger.info("Starting auto-close expired ports task")
    
    while True:
        try:
            # Wait 60 seconds between checks
            await asyncio.sleep(60)
            
            # Close expired ports
            closed = close_expired_ports()
            
            if closed:
                logger.warning(
                    f"AUTO-CLOSE: Closed {len(closed)} expired port(s): {', '.join(closed)}"
                )
            
        except Exception as e:
            logger.error(f"Error in auto-close task: {e}")
            # Continue running even if there's an error
            await asyncio.sleep(60)


def start_background_tasks(app):
    """
    Start all background tasks
    
    Called from main application startup
    """
    @app.on_event("startup")
    async def startup_tasks():
        """Start background tasks on application startup"""
        # Start auto-close task
        asyncio.create_task(auto_close_expired_ports_task())
        logger.info("✓ Started auto-close expired ports task")
    
    @app.on_event("shutdown")
    async def shutdown_tasks():
        """Cleanup on application shutdown"""
        logger.info("Shutting down background tasks...")
        
        # Close all open ports on shutdown (optional - for security)
        try:
            from core.admin.port_management import active_port_mappings, close_monitoring_port
            
            for service in list(active_port_mappings.keys()):
                try:
                    close_monitoring_port(service, "system-shutdown")
                    logger.info(f"Closed {service} port on shutdown")
                except Exception as e:
                    logger.error(f"Failed to close {service} on shutdown: {e}")
        except Exception as e:
            logger.error(f"Error during shutdown cleanup: {e}")
