"""
SMS Bridge v2.3 - Background Tasks
Periodic tasks for HAProxy-based monitoring port management and system maintenance
"""
import asyncio
import logging


logger = logging.getLogger(__name__)

# Module-level variable to track background tasks
_background_tasks: list = []


async def auto_close_expired_ports_task():
    """
    Background task that runs every minute to close expired monitoring ports.
    Uses HAProxy stats socket to disable backends and database to track state.
    
    This task:
    1. Checks for expired ports every 60 seconds
    2. Disables HAProxy backends for any expired ports
    3. Logs all auto-close actions
    """
    from core.admin.haproxy_port_management import close_expired_ports
    from core.database import get_db_context
    
    logger.info("Starting auto-close expired ports task (HAProxy-backed)")
    
    while True:
        try:
            # Wait 60 seconds between checks
            await asyncio.sleep(60)
            
            # Close expired ports via HAProxy
            with get_db_context() as db:
                closed = close_expired_ports(db)
                
                if closed:
                    logger.warning(
                        f"AUTO-CLOSE: Closed {len(closed)} expired port(s): {', '.join(closed)}"
                    )
            
        except Exception as e:
            logger.error(f"Error in auto-close task: {e}")
            # Continue running even if there's an error
            await asyncio.sleep(60)


async def sync_haproxy_on_startup():
    """
    Synchronize HAProxy backend states with database on startup.
    Ensures consistency after container restarts.
    """
    from core.admin.haproxy_port_management import sync_haproxy_with_database
    from core.database import get_db_context
    
    try:
        # Wait a bit for HAProxy to be ready
        await asyncio.sleep(5)
        
        with get_db_context() as db:
            results = sync_haproxy_with_database(db)
            logger.info(f"HAProxy sync completed: enabled={results['enabled']}, disabled={results['disabled']}")
    except Exception as e:
        logger.error(f"Failed to sync HAProxy on startup: {e}")


def start_background_tasks(app):
    """
    Start all background tasks.
    
    Called from main application startup.
    """
    
    @app.on_event("startup")
    async def startup_tasks() -> None:
        """Start background tasks on application startup"""
        # Sync HAProxy state with database
        asyncio.create_task(sync_haproxy_on_startup())
        
        # Start auto-close task
        task = asyncio.create_task(auto_close_expired_ports_task())
        _background_tasks.append(task)
        logger.info("✓ Started auto-close expired ports task (HAProxy)")
    
    @app.on_event("shutdown")
    async def shutdown_tasks() -> None:
        """Cleanup on application shutdown"""
        logger.info("Shutting down background tasks...")
        
        # Cancel background tasks gracefully
        for task in _background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Close all open ports on shutdown via HAProxy
        try:
            from core.admin.haproxy_port_management import (
                close_monitoring_port, 
                get_port_states,
                HAPROXY_BACKENDS
            )
            from core.database import get_db_context
            
            with get_db_context() as db:
                states = get_port_states(db)
                for state in states:
                    if state.get("is_open"):
                        try:
                            close_monitoring_port(db, state["service_name"], reason="system_shutdown")
                            logger.info(f"Closed {state['service_name']} port on shutdown")
                        except Exception as e:
                            logger.error(f"Failed to close {state['service_name']} on shutdown: {e}")
        except Exception as e:
            logger.error(f"Error during shutdown cleanup: {e}")
