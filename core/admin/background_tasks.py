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
    4. Records events in database audit trail
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


async def sync_port_mappings_to_database_task():
    """
    Background task that syncs port mappings to database every 5 minutes
    
    This task:
    1. Reads current port mappings from file
    2. Ensures database audit trail is up to date
    3. Records any discrepancies
    """
    logger.info("Starting port mappings sync task")
    
    while True:
        try:
            # Wait 5 minutes between syncs
            await asyncio.sleep(300)
            
            from core.admin.port_management import active_port_mappings
            from core.database import get_db_context
            
            with get_db_context() as db:
                # Check for any open records in database that don't exist in memory
                # This would indicate a crash/restart scenario
                result = db.execute("""
                    SELECT service, external_port, opened_by, opened_at
                    FROM monitoring_port_access
                    WHERE action = 'opened' AND closed_at IS NULL
                """).fetchall()
                
                for row in result:
                    service = row[0]
                    if service not in active_port_mappings:
                        # Port was open in database but not in memory - close it
                        logger.warning(
                            f"SYNC: Found orphaned port record for {service}, closing..."
                        )
                        db.execute("""
                            UPDATE monitoring_port_access
                            SET closed_at = CURRENT_TIMESTAMP, action = 'closed'
                            WHERE service = %s AND closed_at IS NULL
                        """, (service,))
                        db.commit()
            
        except Exception as e:
            logger.error(f"Error in port sync task: {e}")
            await asyncio.sleep(300)


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
        
        # Start port sync task
        asyncio.create_task(sync_port_mappings_to_database_task())
        logger.info("✓ Started port mappings sync task")
    
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
