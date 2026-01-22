"""
SMS Bridge v2.3 - Main FastAPI Application
API endpoints per tech spec Section 4.
"""
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from core.config import get_settings
from core.database import get_db, check_db_health, init_db, dispose_engine
from core import redis_v2 as redis_client
from core.models import (
    # Pydantic schemas
    OnboardRegisterRequest,
    OnboardRegisterResponse,
    SMSReceiveRequest,
    SMSReceiveResponse,
    PinSetupRequest,
    PinSetupResponse,
    HealthResponse,
    HealthChecks,
    TriggerRecoveryResponse,
    ErrorResponse,
)
from core.services import (
    generate_onboarding_hash,
    run_validation_pipeline,
    extract_hash_from_message,
)
from core.admin.admin import setup_admin

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# FastAPI app
settings = get_settings()
app = FastAPI(
    title="SMS Bridge",
    version=settings.version,
    description="SMS verification service for user onboarding",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Add SessionMiddleware for admin authentication
# MUST be added before admin UI setup
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.admin_secret_key,
    session_cookie="sms_bridge_session",
    max_age=3600,  # 1 hour
    same_site="lax",  # IMPORTANT: "lax" allows cookies in GET redirects
    https_only=False,  # Set to True in production with HTTPS
    path="/",  # Cookie available for all paths
    domain=None,  # Don't restrict domain - works for localhost and IP addresses
)


# Mount static files for admin interface
from starlette.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="core/static"), name="static")


# =============================================================================
# Security Dependencies
# =============================================================================

async def verify_sms_api_key(apiKey: Optional[str] = Query(None, description="API key for authentication")):
    """
    Validate API key from query parameter for /sms/receive endpoint.
    Reads expected key from Redis config:current.
    If sms_receive_api_key is configured in settings, it must match.
    If not configured, access is allowed (backward compatibility).
    """
    config = redis_client.get_config_current()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not configured"
        )
    
    expected_key = config.get("sms_receive_api_key")
    
    # If API key is configured in settings, enforce it
    if expected_key:
        if not apiKey:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing apiKey query parameter"
            )
        
        if not secrets.compare_digest(apiKey, expected_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
    
    # If not configured, allow access (backward compatibility)
    return True


# =============================================================================
# Startup / Shutdown Events
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """
    Startup sequence per tech spec Section 7.1:
    1. Initialize database connection
    2. Initialize Redis connection
    3. Load active settings from Postgres to Redis (if enabled)
    4. Restore from power_down_store (if entries exist)
    5. Load blacklist from database
    6. Start background workers
    7. Setup Admin UI and monitoring routes
    8. Start monitoring background tasks (v2.3)
    """
    logger.info(f"Starting SMS Bridge v{settings.version}")
    
    # 1. Initialize database
    init_db()
    logger.info("Database initialized")
    
    # 2. Test Redis connection
    redis_health = redis_client.check_redis_health()
    if redis_health != "healthy":
        logger.error("Redis connection failed on startup")
        raise RuntimeError("Redis unavailable")
    logger.info("Redis connection verified")
    
    # 3. Load active settings to Redis (if enabled)
    if settings.load_settings_to_redis:
        from core.database import get_db_context
        from core.models import SettingsHistory
        
        with get_db_context() as db:
            active_settings = db.query(SettingsHistory).filter(
                SettingsHistory.is_active == True
            ).first()
            
            if active_settings:
                redis_client.set_config_current(active_settings.payload)
                logger.info("Loaded active settings to Redis config:current")
            else:
                logger.warning("No active settings found in database")
    
    # 4. Restore from power_down_store
    from core.database import get_db_context
    from core.models import PowerDownStore
    
    with get_db_context() as db:
        power_down_count = db.query(PowerDownStore).count()
        if power_down_count > 0:
            redis_client.restore_from_power_down_store(db)
            logger.info(f"Restored {power_down_count} entries from power_down_store")
    
    # 5. Load blacklist from database
    from core.database import get_db_context
    from core.models import BlacklistMobile
    
    with get_db_context() as db:
        blacklist = db.query(BlacklistMobile).all()
        mobiles = [b.mobile for b in blacklist]
        redis_client.load_blacklist_from_db(mobiles)
        logger.info(f"Loaded {len(mobiles)} blacklisted numbers")
    
    # 6. Auto-create admin user from environment (if configured)
    from core.admin.admin import ensure_admin_from_env
    ensure_admin_from_env()
    
    # 7. Setup Admin UI (if enabled)
    if settings.admin_enabled:
        setup_admin(app)
        logger.info(f"Admin UI mounted at {settings.admin_path}")
    
    # 8. Mount monitoring routes (v2.3)
    if settings.monitoring_enabled:
        from core.admin.admin_routes import monitoring_router
        app.include_router(monitoring_router)
        logger.info("Monitoring routes mounted at /admin/monitoring")
    
    # 9. Start background workers (if enabled)
    if settings.sync_worker_enabled or settings.audit_worker_enabled:
        from core.workers import start_workers
        start_workers()
        logger.info("Background workers started")
    
    # 10. Start monitoring background tasks (v2.3)
    if settings.monitoring_worker_enabled:
        import asyncio
        from core.admin.background_tasks import auto_close_expired_ports_task
        
        # Create tasks directly instead of registering event handlers
        asyncio.create_task(auto_close_expired_ports_task())
        logger.info("Monitoring background tasks started")
    
    logger.info("Startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Shutdown sequence per tech spec Section 7.2:
    1. Stop accepting new requests
    2. Drain sync_queue
    3. Flush audit_buffer to Postgres
    4. Backup Redis keys to power_down_store
    5. Close monitoring ports (v2.3)
    6. Close connections
    """
    logger.info("Initiating graceful shutdown")
    
    # Stop background workers
    try:
        from core.workers import stop_workers
        stop_workers()
        logger.info("Background workers stopped")
    except Exception as e:
        logger.error(f"Error stopping workers: {e}")
    
    # Close all open monitoring ports via HAProxy (v2.4)
    if settings.monitoring_enabled:
        try:
            from core.admin.haproxy_port_management import close_monitoring_port, get_port_states
            from core.database import get_db_context as get_db_ctx
            with get_db_ctx() as db:
                states = get_port_states(db)
                for state in states:
                    if state.get("is_open"):
                        try:
                            close_monitoring_port(db, state["service_name"], reason="system_shutdown")
                            logger.info(f"Closed {state['service_name']} port on shutdown")
                        except Exception as e:
                            logger.error(f"Failed to close {state['service_name']} on shutdown: {e}")
        except Exception as e:
            logger.error(f"Error closing monitoring ports: {e}")
    
    # Backup Redis state to Postgres
    try:
        from core.database import get_db_context
        with get_db_context() as db:
            redis_client.backup_to_power_down_store(db, None)
        logger.info("Redis state backed up")
    except Exception as e:
        logger.exception("Error backing up Redis state")
    
    # Close connections
    redis_client.close_redis()
    dispose_engine()
    
    logger.info("Shutdown complete")


# =============================================================================
# API Endpoints
# =============================================================================

@app.post(
    "/onboarding/register",
    response_model=OnboardRegisterResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    tags=["Onboarding"],
    summary="Register mobile for onboarding",
)
def register_onboarding(
    request: OnboardRegisterRequest,
    db: Session = Depends(get_db),
) -> OnboardRegisterResponse:
    """
    Register mobile number for onboarding verification.
    
    Logic (per tech spec Section 4.1):
    1. Load settings from Redis config:current
    2. Validate mobile format
    3. Validate country code (foreign_number_check)
    4. Check rate limit (count_check)
    5. Check blacklist (blacklist_check)
    6. Generate hash: Base32(HMAC-SHA256(Mobile + Timestamp, secret))[:hash_length]
    7. Store in Redis: active_onboarding:{hash} with TTL
    8. Log HASH_GEN to audit_buffer
    9. Return hash and deadlines
    """
    # 1. Load settings
    config = redis_client.get_config_current()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not configured"
        )
    
    # 2. Validate mobile format (basic validation)
    mobile = request.mobile_number
    if not mobile.startswith("+") or len(mobile) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mobile number format"
        )
    
    # 3. Foreign number check
    checks_config = config.get("checks", {})
    if checks_config.get("foreign_number_check_enabled", True):
        allowed_countries = config.get("allowed_countries", ["+91", "+44"])
        # Extract country code
        country_code = None
        for cc in allowed_countries:
            if mobile.startswith(cc):
                country_code = cc
                break
        if country_code is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Country not supported"
            )
    
    # 4. Rate limit check
    if checks_config.get("count_check_enabled", True):
        threshold = config.get("count_threshold", 5)
        count = redis_client.incr_rate(mobile, ttl_seconds=60)
        if count > threshold:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({count}/{threshold})"
            )
    
    # 5. Blacklist check
    if checks_config.get("blacklist_check_enabled", True):
        if redis_client.sismember_blacklist(mobile):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Mobile number is blocked"
            )
    
    # 6. Generate hash
    secrets_config = config.get("secrets", {})
    hmac_secret = secrets_config.get("hmac_secret", "default-secret")
    hash_length = config.get("hash_length", 8)
    ttl_seconds = config.get("ttl_hash_seconds", 900)
    
    hash_val, gen_ts = generate_onboarding_hash(mobile, hmac_secret, hash_length)
    
    # 7. Store in Redis
    redis_client.set_active_onboarding(
        hash_val=hash_val,
        mobile=mobile,
        gen_ts=gen_ts,
        email=request.email,
        device_id=request.device_id,
        ttl_seconds=ttl_seconds,
    )
    
    # 8. Log to audit buffer
    redis_client.lpush_audit_event("HASH_GEN", {
        "mobile": mobile[-4:],  # Only last 4 digits for privacy
        "hash": hash_val[:4],   # Only first 4 chars
    })
    
    # 9. Build response
    user_timelimit = 300  # 5 minutes for user display
    user_deadline = gen_ts + timedelta(seconds=user_timelimit)
    
    return OnboardRegisterResponse(
        status="success",
        sms_receiving_number=config.get("sms_receiver_number", ""),
        hash=hash_val,
        generated_at=gen_ts,
        user_deadline=user_deadline,
        user_timelimit_seconds=user_timelimit,
    )


@app.post(
    "/sms/receive",
    response_model=SMSReceiveResponse,
    tags=["SMS"],
    summary="Receive SMS from gateway",
)
def receive_sms(
    request: SMSReceiveRequest,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_sms_api_key),
) -> SMSReceiveResponse:
    """
    Receive SMS from gateway or Test Lab.
    
    Logic (per tech spec Section 4.2):
    1. Load settings from Redis
    2. Run validation pipeline (4 checks)
    3. On all pass: atomically DELETE active_onboarding:{hash}, SET verified:{mobile}
    4. Log SMS_VERIFIED to audit_buffer
    5. Return status
    """
    # Generate message ID for tracking
    msg_id = str(uuid.uuid4())
    
    # 1. Load settings
    config = redis_client.get_config_current()
    if config is None:
        return SMSReceiveResponse(
            status="failed",
            message_id=msg_id,
            queued_for_processing=False,
        )
    
    # 2. Run validation pipeline
    all_passed, results = run_validation_pipeline(
        message=request.message,
        mobile_number=request.mobile_number,
        config=config,
    )
    
    if not all_passed:
        # Log validation failure
        failed_checks = [
            name for name, (status, _) in results.items() if status == 2
        ]
        logger.warning(f"SMS validation failed: {failed_checks} for msg_id={msg_id}")
        
        redis_client.lpush_audit_event("SMS_FAILED", {
            "msg_id": msg_id,
            "mobile": request.mobile_number[-4:],
            "failed_checks": failed_checks,
        })
        
        return SMSReceiveResponse(
            status="failed",
            message_id=msg_id,
            queued_for_processing=False,
        )
    
    # 3. Extract hash and perform atomic operation
    allowed_prefix = config.get("allowed_prefix", "ONBOARD:")
    hash_val = extract_hash_from_message(request.message, allowed_prefix)
    
    if hash_val:
        # Atomic: DELETE active_onboarding:{hash} and SET verified:{mobile}
        r = redis_client.get_redis()
        pipe = r.pipeline()
        pipe.delete(f"active_onboarding:{hash_val}")
        pipe.setex(
            f"verified:{request.mobile_number}",
            3600,  # 1 hour TTL
            f'{{"mobile": "{request.mobile_number}", "hash": "{hash_val}", "verified_ts": "{datetime.utcnow().isoformat()}"}}'
        )
        pipe.execute()
    
    # 4. Log success
    redis_client.lpush_audit_event("SMS_VERIFIED", {
        "msg_id": msg_id,
        "mobile": request.mobile_number[-4:],
        "hash": hash_val[:4] if hash_val else "N/A",
    })
    
    logger.info(f"SMS verified: msg_id={msg_id}")
    
    return SMSReceiveResponse(
        status="received",
        message_id=msg_id,
        queued_for_processing=True,
    )


@app.post(
    "/pin-setup",
    response_model=PinSetupResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    tags=["PIN"],
    summary="Set up PIN for verified mobile",
)
def setup_pin(
    request: PinSetupRequest,
    db: Session = Depends(get_db),
) -> PinSetupResponse:
    """
    Collect PIN for verified mobile.
    
    Logic (per tech spec Section 4.4):
    1. Verify mobile exists in verified:{mobile}
    2. Validate hash matches
    3. Push to sync_queue for backend delivery
    4. Delete verified:{mobile}
    5. Log PIN_COLLECTED to audit_buffer
    """
    # 1. Check verified entry
    verified_data = redis_client.get_verified(request.mobile_number)
    if verified_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mobile not found in verified entries"
        )
    
    # 2. Validate hash
    if verified_data.get("hash") != request.hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hash mismatch"
        )
    
    # 3. Push to sync_queue
    outbound = {
        "mobile": request.mobile_number,
        "pin": request.pin,
        "hash": request.hash,
    }
    redis_client.lpush_sync_queue(outbound)
    
    # 4. Delete verified entry
    redis_client.delete_verified(request.mobile_number)
    
    # 5. Log audit event
    redis_client.lpush_audit_event("PIN_COLLECTED", {
        "mobile": request.mobile_number[-4:],
    })
    
    logger.info(f"PIN collected for mobile ending {request.mobile_number[-4:]}")
    
    return PinSetupResponse(
        status="success",
        message="PIN accepted, account creation in progress",
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check endpoint",
    responses={
        200: {"description": "Service healthy"},
        503: {"description": "Service degraded or unhealthy"},
    },
)
def health_check():
    """
    Health check per tech spec Section 4.3.
    Checks database, Redis, and batch processor status.
    Returns HTTP 200 when healthy, HTTP 503 when degraded or unhealthy.
    """
    # Check database
    db_status = check_db_health()
    
    # Check Redis
    redis_status = redis_client.check_redis_health()
    
    # Check batch processor (sync worker)
    try:
        from core.workers import get_worker_status
        worker_status = get_worker_status()
    except Exception:
        worker_status = "unknown"
    
    # Overall status
    if db_status == "unhealthy" or redis_status == "unhealthy":
        overall = "unhealthy"
    elif db_status == "degraded" or redis_status == "degraded" or worker_status != "running":
        overall = "degraded"
    else:
        overall = "healthy"
    
    # Prepare response body
    response_body = HealthResponse(
        status=overall,
        service=settings.app_name,
        version=settings.version,
        timestamp=datetime.utcnow(),
        checks=HealthChecks(
            database=db_status,
            redis=redis_status,
            batch_processor=worker_status,
        ),
    )
    
    # Return appropriate HTTP status code
    if overall == "healthy":
        return JSONResponse(
            status_code=200,
            content=response_body.model_dump(mode='json')
        )
    else:
        # degraded or unhealthy = 503 Service Unavailable
        return JSONResponse(
            status_code=503,
            content=response_body.model_dump(mode='json')
        )


@app.post(
    "/admin/trigger-recovery",
    response_model=TriggerRecoveryResponse,
    tags=["Admin"],
    summary="Trigger recovery process",
)
def trigger_recovery(db: Session = Depends(get_db)) -> TriggerRecoveryResponse:
    """
    Trigger recovery process per tech spec Section 4.5.
    Collects all failed users from sync_queue and sends to recovery_url as batch.
    """
    import httpx
    
    config = redis_client.get_config_current()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not configured"
        )
    
    recovery_url = config.get("recovery_url")
    if not recovery_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recovery URL not configured"
        )
    
    triggered_at = datetime.utcnow()
    
    # Collect all failed users from sync_queue
    failed_users = []
    queue_length = redis_client.llen_sync_queue()
    
    if queue_length == 0:
        return TriggerRecoveryResponse(
            status="success",
            triggered_at=triggered_at,
            message="No failed users to recover (sync_queue is empty)",
        )
    
    # Pop all items from queue
    while True:
        item = redis_client.rpop_sync_queue()
        if item is None:
            break
        failed_users.append(item)
    
    if not failed_users:
        return TriggerRecoveryResponse(
            status="success",
            triggered_at=triggered_at,
            message="No failed users to recover",
        )
    
    # Prepare batch payload
    hmac_secret = config.get("secrets", {}).get("hmac_secret")
    payload = {
        "users": failed_users,
        "batch_size": len(failed_users),
        "triggered_at": triggered_at.isoformat(),
        "triggered_by": "admin"
    }
    
    # Sign the payload if hmac_secret is configured
    if hmac_secret:
        import hmac
        import hashlib
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            hmac_secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        payload["signature"] = signature
    
    # Send to recovery_url
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(recovery_url, json=payload)
            response.raise_for_status()
            
        logger.info(f"Recovery sent {len(failed_users)} users to {recovery_url}")
        
    except httpx.HTTPError as e:
        # On failure, put users back in queue
        for user in reversed(failed_users):  # Reverse to maintain order
            redis_client.lpush_sync_queue(user)
        
        logger.error(f"Recovery trigger failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Recovery endpoint error: {str(e)}"
        )
    
    # Log audit event
    redis_client.lpush_audit_event("RECOVERY_TRIGGERED", {
        "triggered_at": triggered_at.isoformat(),
        "users_sent": len(failed_users),
        "recovery_url": recovery_url,
    })
    
    return TriggerRecoveryResponse(
        status="success",
        triggered_at=triggered_at,
        message=f"Recovery completed: {len(failed_users)} users sent to recovery endpoint",
    )


@app.get(
    "/metrics",
    response_class=PlainTextResponse,
    tags=["Metrics"],
    summary="Prometheus metrics",
)
def get_metrics():
    """
    Prometheus metrics endpoint per monitoring spec.
    Returns metrics in Prometheus text format.
    """
    if not settings.metrics_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metrics disabled"
        )
    
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return PlainTextResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# =============================================================================
# Landing Page
# =============================================================================

@app.get("/", include_in_schema=False)
def landing_page():
    """Landing page redirect to docs or simple response"""
    if settings.debug:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/docs")
    return JSONResponse({
        "service": settings.app_name,
        "version": settings.version,
        "status": "running",
    })


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "core.sms_server_v2:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        reload=settings.debug,
    )
