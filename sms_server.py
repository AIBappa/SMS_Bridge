import os
import json
import asyncio
import logging
import secrets
import hashlib
import uuid as uuid_module
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional
import asyncpg
import redis
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Header, Depends
from fastapi.routing import APIRoute
from pydantic import BaseModel
import requests
from redis_client import redis_pool  # Async Redis pool for Redis-first architecture

# Observability ASGI metrics mount (exposes /metrics) will be mounted after app is created

# Pydantic models
class SMSInput(BaseModel):
    sender_number: str
    sms_message: str
    received_timestamp: datetime

class BatchSMSData(BaseModel):
    uuid: str
    sender_number: str
    sms_message: str
    received_timestamp: datetime
    country_code: Optional[str] = None
    local_mobile: Optional[str] = None

# New models for onboarding functionality
class OnboardingRequest(BaseModel):
    mobile_number: str

class OnboardingResponse(BaseModel):
    mobile_number: str
    hash: str
    message: str

# Response model for GeoPrasidh compatible format
class GeoPrasidhOnboardingResponse(BaseModel):
    mobile_number: str
    hash: str
    expires_at: str
    status: str

# Load configuration
CONFIG_FILE = os.path.expanduser('~/sms_bridge_config.json')
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    config = {}

CF_BACKEND_URL = os.getenv('CF_BACKEND_URL', config.get('cf_endpoint', 'https://default-url-if-not-set'))
API_KEY = os.getenv('CF_API_KEY', config.get('cf_api_key', ''))

HASH_SECRET_KEY = os.getenv('HASH_SECRET_KEY', '')  # Added for hash validation

# API Key for incoming requests from GeoPrasidh (redacted placeholder)
GEOPRASIDH_API_KEY = os.getenv('GEOPRASIDH_API_KEY', 'dev-api-key-REDACTED')

# Authentication dependency
def verify_api_key(authorization: str = Header(None)):
    """Verify the API key from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    if not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    token = authorization.replace('Bearer ', '')
    if token != GEOPRASIDH_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    return token

def normalize_mobile_number(mobile: str) -> str:
    """Normalize mobile number to remove + and extract digits"""
    # Remove + and any spaces/dashes
    normalized = mobile.replace('+', '').replace('-', '').replace(' ', '')
    
    # Remove country code if present (assuming +91 for India)
    if normalized.startswith('91') and len(normalized) == 12:
        normalized = normalized[2:]  # Remove '91' prefix
    
    return normalized

# Load configuration

POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'database': os.getenv('POSTGRES_DB', 'sms_bridge'),
    'user': os.getenv('POSTGRES_USER', 'sms_user'),
    'password': os.getenv('POSTGRES_PASSWORD', ''),
    'port': int(os.getenv('POSTGRES_PORT', 6432)),  # pgbouncer port
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'password': os.getenv('REDIS_PASSWORD', None),
    'db': 0,
}

app = FastAPI()
redis_client = redis.StrictRedis(**REDIS_CONFIG)
pool = None

# Try to mount observability ASGI app at /metrics (optional)
try:
    from observability.asgi_metrics import app as metrics_asgi_app
    app.mount('/metrics', metrics_asgi_app)
except Exception:
    logging.getLogger(__name__).debug('Observability ASGI app not available; /metrics not mounted')

# Logging setup with file handlers for persistent logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_DIR = os.getenv('LOG_DIR', '/app/logs')

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging with both file and console handlers
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Console output for Docker logs
    ]
)

# Add rotating file handlers for persistent logging
from logging.handlers import RotatingFileHandler

# Create rotating file handler for general logs
rotating_handler = RotatingFileHandler(
    f'{LOG_DIR}/sms_server.log',
    maxBytes=50*1024*1024,  # 50MB
    backupCount=5
)
rotating_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Create rotating file handler for errors
error_handler = RotatingFileHandler(
    f'{LOG_DIR}/sms_server_errors.log',
    maxBytes=50*1024*1024,  # 50MB
    backupCount=5
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Add handlers to root logger
logging.getLogger().addHandler(rotating_handler)
logging.getLogger().addHandler(error_handler)

logger = logging.getLogger(__name__)
logger.info(f"SMS Server starting with log level: {LOG_LEVEL}")
logger.info(f"Logs will be written to: {LOG_DIR}")

async def get_db_pool():
    global pool
    if pool is None:
        # Disable statement cache for PgBouncer compatibility
        pool = await asyncpg.create_pool(**POSTGRES_CONFIG, min_size=1, max_size=10, statement_cache_size=0)
    return pool

async def get_setting(key: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT setting_value FROM system_settings WHERE setting_key = $1", key)
        if result is None:
            return None
        # Try to parse as JSON, if it fails return as string
        try:
            return json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return result

async def run_validation_checks(batch_sms_data: List[BatchSMSData]):
    check_sequence = await get_setting('check_sequence')
    check_enabled = await get_setting('check_enabled')
    pool = await get_db_pool()
    
    for sms in batch_sms_data:
        # REDIS-FIRST EARLY CHECKS (before DB validation pipeline)
        
        # 1. Check blacklist in Redis (instant, no DB I/O)
        if await redis_pool.sismember('blacklist_mobiles', sms.local_mobile):
            logger.info(f"SMS from {sms.local_mobile} blocked - blacklisted")
            await redis_pool.lpush("sms_monitor_queue", {
                "uuid": sms.uuid,
                "mobile": sms.local_mobile,
                "status": "invalid",
                "reason": "blacklist",
                "country_code": sms.country_code
            })
            # Skip this SMS entirely - continue to next
            continue
        
        # 2. Increment abuse counter (non-blocking, never delays good users)
        try:
            await redis_pool.incr(f'abuse_counter:{sms.local_mobile}')
            await redis_pool.expire(f'abuse_counter:{sms.local_mobile}', 86400)  # 24h TTL
        except Exception as e:
            logger.warning(f"Failed to increment abuse counter for {sms.local_mobile}: {e}")
        
        # Initialize all check results to 0 (not run)
        results = {
            'blacklist_check': 0,
            'duplicate_check': 0,
            'foreign_number_check': 0,
            'header_hash_check': 0,
            'mobile_check': 0,
            'time_window_check': 0
        }
        overall_status = 'valid'
        failed_check = None
        
        for check_name in check_sequence:
            if not check_enabled.get(check_name, False):
                results[f'{check_name}_check'] = 3  # skipped
                continue
            
            # Use explicit function mapping instead of globals() to prevent code injection
            if check_name not in VALIDATION_FUNCTIONS:
                logger.error(f"Unknown validation check: {check_name}")
                results[f'{check_name}_check'] = 2  # fail
                overall_status = 'invalid'
                failed_check = check_name
                break
            
            check_func = VALIDATION_FUNCTIONS[check_name]
            result = await check_func(sms, pool)
            results[f'{check_name}_check'] = result
            
            if result == 2:  # fail
                overall_status = 'invalid'
                failed_check = check_name
                break
            elif result == 3:  # skipped
                continue
        
        # Log to Redis monitor queue (async, non-blocking)
        await redis_pool.lpush("sms_monitor_queue", {
            "uuid": sms.uuid,
            "mobile": sms.local_mobile,
            "status": overall_status,
            "reason": failed_check or "",
            "country_code": sms.country_code
        })
        
        # Also update sms_monitor table directly (keep existing behavior)
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO sms_monitor (uuid, overall_status, failed_at_check, processing_completed_at, 
                                         blacklist_check, duplicate_check, foreign_number_check, header_hash_check, 
                                         mobile_check, time_window_check, country_code, local_mobile)
                VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (uuid) DO UPDATE SET 
                    overall_status = EXCLUDED.overall_status,
                    failed_at_check = EXCLUDED.failed_at_check,
                    processing_completed_at = EXCLUDED.processing_completed_at,
                    blacklist_check = EXCLUDED.blacklist_check,
                    duplicate_check = EXCLUDED.duplicate_check,
                    foreign_number_check = EXCLUDED.foreign_number_check,
                    header_hash_check = EXCLUDED.header_hash_check,
                    mobile_check = EXCLUDED.mobile_check,
                    time_window_check = EXCLUDED.time_window_check,
                    country_code = EXCLUDED.country_code,
                    local_mobile = EXCLUDED.local_mobile
            """, sms.uuid, overall_status, failed_check, *results.values(), sms.country_code, sms.local_mobile)
        
        if overall_status == 'valid':
            # Insert to out_sms and Redis using structured mobile data
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO out_sms (uuid, sender_number, sms_message, country_code, local_mobile) 
                    VALUES ($1, $2, $3, $4, $5)
                """, sms.uuid, sms.sender_number, sms.sms_message, sms.country_code, sms.local_mobile)
            redis_client.sadd('out_sms_numbers', sms.local_mobile)
            await redis_pool.sadd('out_sms_numbers', sms.local_mobile)  # Also add to async Redis
            
            # Forward to cloud backend only after validation passes
            if CF_BACKEND_URL and API_KEY:
                try:
                    # Convert datetime to string for JSON serialization
                    sms_dict = {
                        'sender_number': sms.sender_number,
                        'sms_message': sms.sms_message,
                        'received_timestamp': sms.received_timestamp.isoformat()
                    }
                    response = requests.post(CF_BACKEND_URL, json=sms_dict, headers={'Authorization': f'Bearer {API_KEY}'}, timeout=5)
                    logger.info(f"Forwarded validated SMS to cloud, status: {response.status_code}")
                except Exception as e:
                    logger.warning(f"Cloud forwarding failed for validated SMS: {e}")


async def batch_processor():
    """
    Advanced batch processor with timeout-based batching logic.
    
    Process flow:
    1. Read batch size and timeout settings from the settings table
    2. Query input_sms for new rows where uuid > last processed UUID
    3. If rows < batch_size: wait for batch_timeout or more rows
    4. Process available batch (1 to batch_size rows)
    5. Update last processed UUID and repeat
    """
    logger.info("Starting advanced batch processor...")
    
    while True:
        try:
            pool = await get_db_pool()
            
            # Read batch size and timeout settings
            try:
                batch_size = int(await get_setting('batch_size'))
                try:
                    batch_timeout = float(await get_setting('batch_timeout'))
                except:
                    # Default timeout if not set
                    batch_timeout = 2.0
                    logger.warning(f"batch_timeout not found in settings, using default: {batch_timeout}s")
                    # Insert default batch_timeout setting
                    async with pool.acquire() as conn:
                        await conn.execute("""
                            INSERT INTO system_settings (setting_key, setting_value) 
                            VALUES ('batch_timeout', '2.0') 
                            ON CONFLICT (setting_key) DO UPDATE SET setting_value = '2.0'
                        """)
                
                last_uuid = await get_setting('last_processed_uuid')
            except Exception as e:
                logger.error(f"Failed to read batch processor settings: {e}")
                await asyncio.sleep(5)
                continue
            
            logger.debug(f"Batch processor config: size={batch_size}, timeout={batch_timeout}s, last_uuid={last_uuid}")
            
            # Query for new rows
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT uuid, sender_number, sms_message, received_timestamp, country_code, local_mobile 
                    FROM input_sms 
                    WHERE uuid > $1::uuid
                    ORDER BY uuid 
                    LIMIT $2
                """, last_uuid, batch_size)
            
            initial_row_count = len(rows)
            logger.debug(f"Found {initial_row_count} new SMS messages to process")
            
            # If no rows, wait and continue
            if initial_row_count == 0:
                logger.debug("No new SMS messages found, waiting...")
                await asyncio.sleep(batch_timeout)
                continue
            
            # If we have fewer rows than batch_size, wait for timeout
            if initial_row_count < batch_size:
                logger.debug(f"Only {initial_row_count}/{batch_size} rows available, starting {batch_timeout}s timeout...")
                
                timeout_start = asyncio.get_event_loop().time()
                
                # Poll during timeout period
                while True:
                    current_time = asyncio.get_event_loop().time()
                    elapsed = current_time - timeout_start
                    
                    if elapsed >= batch_timeout:
                        logger.debug(f"Timeout ({batch_timeout}s) reached, proceeding with {len(rows)} rows")
                        break
                    
                    # Check for new rows during timeout
                    async with pool.acquire() as conn:
                        updated_rows = await conn.fetch("""
                            SELECT uuid, sender_number, sms_message, received_timestamp, country_code, local_mobile 
                            FROM input_sms 
                            WHERE uuid > $1::uuid
                            ORDER BY uuid 
                            LIMIT $2
                        """, last_uuid, batch_size)
                    
                    if len(updated_rows) >= batch_size:
                        logger.debug(f"Batch size ({batch_size}) reached during timeout, proceeding immediately")
                        rows = updated_rows
                        break
                    elif len(updated_rows) > len(rows):
                        logger.debug(f"New SMS arrived during timeout: {len(updated_rows)} total")
                        rows = updated_rows
                    
                    # Short sleep to avoid tight polling
                    await asyncio.sleep(0.1)
            
            # Process the batch if we have any rows
            if rows:
                logger.info(f"Processing batch of {len(rows)} SMS messages")
                
                # Convert UUID objects to strings for Pydantic model
                batch_data = []
                for row in rows:
                    row_dict = dict(row)
                    row_dict['uuid'] = str(row_dict['uuid'])  # Convert UUID to string
                    batch_data.append(BatchSMSData(**row_dict))
                
                # Run validation checks
                await run_validation_checks(batch_data)
                
                # Update last_processed_uuid to the highest UUID in this batch
                new_last_uuid = rows[-1]['uuid']
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE system_settings SET setting_value = $1 WHERE setting_key = 'last_processed_uuid'
                    """, str(new_last_uuid))
                
                logger.info(f"Batch processing completed. Updated last_processed_uuid to: {new_last_uuid}")
            
            # Brief pause before next iteration
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error in batch processor: {e}")
            await asyncio.sleep(5)  # Wait longer on error

@app.on_event("startup")
async def startup_event():
    """Initialize services and start background workers"""
    # Initialize async Redis pool (Redis-first architecture)
    await redis_pool.init()
    logger.info("Async Redis pool initialized")
    
    # Start background workers for abuse detection and monitoring
    try:
        from background_workers import start_background_workers
        await start_background_workers()
        logger.info("Background workers started successfully")
    except Exception as e:
        logger.error(f"Failed to start background workers: {e}")
    
    # Cache warmup: Load existing validated numbers into Redis
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        numbers = await conn.fetch("SELECT local_mobile FROM out_sms WHERE local_mobile IS NOT NULL")
        for row in numbers:
            # Use both sync (for backward compat) and async Redis
            redis_client.sadd('out_sms_numbers', row['local_mobile'])
            await redis_pool.sadd('out_sms_numbers', row['local_mobile'])
    logger.info(f"Redis cache warmed up with {len(numbers)} validated numbers")

    
    # Start batch processor
    asyncio.create_task(batch_processor())

@app.post("/sms/receive")
async def receive_sms(request: Request, background_tasks: BackgroundTasks):
    """
    Handle SMS reception from both JSON and form-encoded data
    """
    content_type = request.headers.get("content-type", "").lower()
    
    try:
        if "application/json" in content_type:
            # Handle JSON data (existing format)
            json_data = await request.json()
            sms_data = SMSInput(**json_data)
        elif "application/x-www-form-urlencoded" in content_type:
            # Handle form-encoded data from mobile app
            form_data = await request.form()
            logger.info(f"=== FORM DATA RECEIVED ===")
            logger.info(f"Raw form data: {dict(form_data)}")
            
            # Convert form fields to expected format
            sender_number = form_data.get("number", "")
            sms_message = form_data.get("message", "")
            timestamp_str = form_data.get("timestamp", "0")
            
            # Convert Unix timestamp (milliseconds) to datetime
            try:
                timestamp_ms = int(timestamp_str)
                received_timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            except (ValueError, TypeError):
                received_timestamp = datetime.now(timezone.utc)
                logger.warning(f"Invalid timestamp '{timestamp_str}', using current time")
            
            sms_data = SMSInput(
                sender_number=sender_number,
                sms_message=sms_message,
                received_timestamp=received_timestamp
            )
            logger.info(f"=== CONVERTED TO SMS DATA ===")
        else:
            logger.error(f"Unsupported content type: {content_type}")
            raise HTTPException(status_code=400, detail="Content-Type must be application/json or application/x-www-form-urlencoded")
        
        # Extract country code and local mobile for structured storage
        from checks.mobile_utils import normalize_mobile_number
        pool = await get_db_pool()
        country_code, local_mobile = await normalize_mobile_number(sms_data.sender_number, pool)
        
        # Log the processed SMS data
        logger.info(f"=== SMS RECEIVED ===")
        logger.info(f"Sender Number: {sms_data.sender_number}")
        logger.info(f"Country Code: {country_code}")
        logger.info(f"Local Mobile: {local_mobile}")
        logger.info(f"SMS Message: {sms_data.sms_message}")
        logger.info(f"Received Timestamp: {sms_data.received_timestamp}")
        logger.info(f"=== END SMS DATA ===")
        
        # Insert to database with structured mobile data
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO input_sms (sender_number, sms_message, received_timestamp, country_code, local_mobile) 
                VALUES ($1, $2, $3, $4, $5)
            """, sms_data.sender_number, sms_data.sms_message, sms_data.received_timestamp, country_code, local_mobile)
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"Error processing SMS: {e}")
        raise HTTPException(status_code=400, detail=f"Error processing SMS: {str(e)}")

@app.post("/onboarding/register", response_model=OnboardingResponse)
async def register_mobile(request: OnboardingRequest):
    """
    Register a mobile number for onboarding and generate hash.
    Returns the mobile number, hash, and instruction message.
    """
    try:
        pool = await get_db_pool()
        mobile_number = request.mobile_number.strip()
        
        # Validate mobile number format
        import re
        if not re.match(r'^\d{10,15}$', mobile_number):
            raise HTTPException(status_code=400, detail="Invalid mobile number format")
        
        # Generate salt (use a sensible default if the setting is missing)
        async with pool.acquire() as conn:
            salt_val = await conn.fetchval(
                "SELECT setting_value FROM system_settings WHERE setting_key = 'hash_salt_length'"
            )
        # If the DB value is missing or empty, default to 16 (bytes -> 32 hex chars)
        try:
            salt_length = int(salt_val or 16)
        except (TypeError, ValueError):
            salt_length = 16

        salt = secrets.token_hex(salt_length // 2)  # hex gives 2 chars per byte
        
        # Check if mobile number already exists and is active
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT mobile_number, is_active FROM onboarding_mobile WHERE mobile_number = $1",
                mobile_number
            )
            
            if existing and existing['is_active']:
                raise HTTPException(status_code=409, detail="Mobile number already registered and active")
            
            # Insert or update onboarding record
            if existing:
                # Reactivate existing record with new salt
                await conn.execute("""
                    UPDATE onboarding_mobile 
                    SET salt = $1, request_timestamp = NOW(), is_active = true 
                    WHERE mobile_number = $2
                """, salt, mobile_number)
            else:
                # Create new record
                await conn.execute("""
                    INSERT INTO onboarding_mobile (mobile_number, salt, hash) 
                    VALUES ($1, $2, $3)
                """, mobile_number, salt, "")  # hash will be computed below
        
        # Get permitted header from settings (use first one for generation)
        async with pool.acquire() as conn:
            permitted_headers_str = await conn.fetchval(
                "SELECT setting_value FROM system_settings WHERE setting_key = 'permitted_headers'"
            )
        
        if not permitted_headers_str:
            raise HTTPException(status_code=500, detail="No permitted headers configured in system settings")
        
        # Use the first permitted header for hash generation
        demo_header = permitted_headers_str.split(',')[0].strip()
        data_to_hash = f"{demo_header}{mobile_number}{salt}"
        computed_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
        
        # Update the hash in database
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE onboarding_mobile SET hash = $1 WHERE mobile_number = $2",
                computed_hash, mobile_number
            )
        
        message = f"{demo_header}:{computed_hash}"
        
        return OnboardingResponse(
            mobile_number=mobile_number,
            hash=computed_hash,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in register_mobile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/onboard/register/{mobile_number}", response_model=GeoPrasidhOnboardingResponse)
async def register_mobile_geoprasidh(mobile_number: str, api_key: str = Depends(verify_api_key)):
    """
    GeoPrasidh-compatible endpoint for mobile registration (Redis-first).
    Accepts mobile number with + prefix and returns hash with expiry.
    NO database I/O in hot path - uses Redis exclusively.
    """
    try:
        # Normalize mobile number (remove + and country code)
        normalized_mobile = normalize_mobile_number(mobile_number)
        
        # Validate mobile number format (10 digits after normalization)
        if not re.match(r'^\d{10}$', normalized_mobile):
            raise HTTPException(status_code=400, detail="Invalid mobile number format")
        
        # REDIS-FIRST CHECKS (no DB I/O)
        
        # Check if already onboarded (Redis only)
        if await redis_pool.sismember('out_sms_numbers', normalized_mobile):
            raise HTTPException(status_code=409, detail="Mobile number already onboarded and validated")
        
        # Check if blacklisted (Redis only)
        if await redis_pool.sismember('blacklist_mobiles', normalized_mobile):
            raise HTTPException(status_code=403, detail="Mobile number is blacklisted")
        
        # Check if hash already exists in Redis (within 24h window)
        existing_hash = await redis_pool.get(f'onboard_hash:{normalized_mobile}')
        if existing_hash:
            # Return existing hash (still valid)
            expires_at = (datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).replace(hour=datetime.now(timezone.utc).hour + 1)).isoformat().replace('+00:00', 'Z')
            logger.info(f"Returning existing onboard hash for {normalized_mobile}")
            return GeoPrasidhOnboardingResponse(
                mobile_number=mobile_number,
                hash=existing_hash,
                expires_at=expires_at,
                status="pending"
            )
        
        # Generate new hash (minimal DB reads for config only)
        pool = await get_db_pool()
        
        # Get salt length from settings
        async with pool.acquire() as conn:
            salt_length = int(await conn.fetchval(
                "SELECT setting_value FROM system_settings WHERE setting_key = 'hash_salt_length'"
            ) or 16)
        
        salt = secrets.token_hex(salt_length // 2)
        
        # Get permitted header from settings
        async with pool.acquire() as conn:
            permitted_headers_str = await conn.fetchval(
                "SELECT setting_value FROM system_settings WHERE setting_key = 'permitted_headers'"
            )
        
        if not permitted_headers_str:
            raise HTTPException(status_code=500, detail="No permitted headers configured in system settings")
        
        # Use the first permitted header for hash generation
        demo_header = permitted_headers_str.split(',')[0].strip()
        data_to_hash = f"{demo_header}{normalized_mobile}{salt}"
        computed_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
        
        # Store hash in Redis with 24h TTL (hot path - no DB write)
        await redis_pool.setex(f'onboard_hash:{normalized_mobile}', 86400, computed_hash)
        # Increment onboarding Prometheus counter if available
        try:
            from observability.metrics import SMS_ONBOARD_REQUESTS
            SMS_ONBOARD_REQUESTS.inc()
        except Exception:
            pass
        logger.info(f"Stored onboard hash in Redis for {normalized_mobile} (TTL: 24h)")
        
        # Log to monitor queue for async audit (non-blocking)
        await redis_pool.lpush("sms_monitor_queue", {
            "uuid": str(uuid_module.uuid4()),
            "mobile": normalized_mobile,
            "status": "onboard_requested",
            "reason": "",
            "country_code": "91"
        })
        
        # Generate expires_at timestamp (1 hour from now, rounded to next hour)
        expires_at = (datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).replace(hour=datetime.now(timezone.utc).hour + 1)).isoformat().replace('+00:00', 'Z')
        
        return GeoPrasidhOnboardingResponse(
            mobile_number=mobile_number,  # Return original format with +
            hash=computed_hash,
            expires_at=expires_at,
            status="pending"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in register_mobile_geoprasidh: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/onboarding/status/{mobile_number}")
async def get_onboarding_status(mobile_number: str):
    """
    Get onboarding status for a mobile number.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            onboarding_record = await conn.fetchrow(
                "SELECT mobile_number, request_timestamp, is_active FROM onboarding_mobile WHERE mobile_number = $1",
                mobile_number
            )
            
            if not onboarding_record:
                raise HTTPException(status_code=404, detail="Mobile number not found in onboarding system")
            
            # Check if any SMS has been successfully validated for this mobile
            sms_validated = await conn.fetchval("""
                SELECT EXISTS(
                    SELECT 1 FROM input_sms i 
                    JOIN sms_monitor m ON i.uuid = m.uuid 
                    WHERE i.sms_message LIKE '%' || $1 || '%' 
                    AND m.overall_status = 'valid'
                )
            """, mobile_number)
        
        return {
            "mobile_number": onboarding_record['mobile_number'],
            "request_timestamp": onboarding_record['request_timestamp'],
            "is_active": onboarding_record['is_active'],
            "sms_validated": sms_validated
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_onboarding_status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/onboarding/{mobile_number}")
async def deactivate_mobile(mobile_number: str):
    """
    Deactivate a mobile number from onboarding system.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE onboarding_mobile SET is_active = false WHERE mobile_number = $1",
                mobile_number
            )
            
            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Mobile number not found")
        
        return {"message": "Mobile number deactivated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in deactivate_mobile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/webhook/validated")
async def webhook_validated(request: Request):
    """
    Webhook endpoint for GeoPrasidh to receive validated SMS notifications.
    """
    try:
        data = await request.json()
        mobile_number = data.get('mobile_number', '')
        message = data.get('message', '')
        timestamp = data.get('timestamp', '')
        validation_results = data.get('validation_results', {})
        
        logger.info(f"Received webhook for mobile: {mobile_number}, message: {message}")
        
        # Process the validated message
        # This is where you'd update your database or trigger other actions
        
        return {
            "status": "received",
            "mobile_number": mobile_number,
            "processed": True,
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=400, detail=f"Error processing webhook: {str(e)}")

@app.get("/health")
async def health_check():
    """
    Comprehensive health check endpoint.
    Returns 200 if all systems operational, 503 if any component degraded.
    """
    health_status = {
        "status": "healthy",
        "components": {
            "database": {"status": "unknown"},
            "redis": {"status": "unknown"},
            "background_workers": {"status": "running"}
        }
    }
    overall_healthy = True
    
    # Check database connection
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            if result == 1:
                health_status["components"]["database"]["status"] = "healthy"
            else:
                health_status["components"]["database"]["status"] = "degraded"
                overall_healthy = False
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["components"]["database"]["status"] = "unhealthy"
        health_status["components"]["database"]["error"] = str(e)
        overall_healthy = False
    
    # Check Redis connection
    try:
        pong = await redis_pool.ping()
        if pong:
            health_status["components"]["redis"]["status"] = "healthy"
        else:
            health_status["components"]["redis"]["status"] = "degraded"
            overall_healthy = False
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health_status["components"]["redis"]["status"] = "unhealthy"
        health_status["components"]["redis"]["error"] = str(e)
        overall_healthy = False
    
    # Overall status
    health_status["status"] = "healthy" if overall_healthy else "degraded"
    
    # Return appropriate HTTP status code
    if overall_healthy:
        return health_status
    else:
        from fastapi import Response
        return Response(
            content=json.dumps(health_status),
            media_type="application/json",
            status_code=503
        )


# Import validation functions
from checks.blacklist_check import validate_blacklist_check
from checks.duplicate_check import validate_duplicate_check
from checks.foreign_number_check import validate_foreign_number_check
from checks.header_hash_check import validate_header_hash_check
from checks.mobile_check import validate_mobile_check
from checks.time_window_check import validate_time_window_check

# Explicit function mapping dictionary to prevent code injection
VALIDATION_FUNCTIONS = {
    'blacklist': validate_blacklist_check,
    'duplicate': validate_duplicate_check,
    'foreign_number': validate_foreign_number_check,
    'header_hash': validate_header_hash_check,
    'mobile': validate_mobile_check,
    'time_window': validate_time_window_check
}
