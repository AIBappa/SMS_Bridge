import os
import hmac
import hashlib
import re

async def validate_header_hash_check(sms, pool):
    """
    Combined header and hash validation check.
    Validates SMS message format: <PERMITTED_HEADER>:<hash>
    
    Returns:
    - 1: pass (valid header and hash)
    - 2: fail (invalid header or hash)
    """
    try:
        message = sms.sms_message.strip()
        
        # Get permitted headers from settings
        async with pool.acquire() as conn:
            permitted_headers_str = await conn.fetchval(
                "SELECT setting_value FROM sms_settings WHERE setting_key = 'permitted_headers'"
            )
        
        if not permitted_headers_str:
            return 2  # fail - no permitted headers configured
        
        # Parse permitted headers (comma-separated list)
        permitted_headers = [h.strip() for h in permitted_headers_str.split(',')]
        
        # Check if message starts with any permitted header pattern
        header_found = None
        for header in permitted_headers:
            header_pattern = f"{header}:"
            if message.startswith(header_pattern):
                header_found = header
                break
        
        if not header_found:
            return 2  # fail - invalid header format
        
        # Extract hash from <HEADER>:<hash> format
        try:
            provided_hash = message.split(f"{header_found}:", 1)[1].strip()
        except IndexError:
            return 2  # fail - no hash after header
        
        # Basic hash format validation (should be 64 character hex for SHA256)
        if not re.match(r'^[a-fA-F0-9]{64}$', provided_hash):
            return 2  # fail - invalid hash format
        
        # Use structured mobile data or fallback to normalization
        if hasattr(sms, 'local_mobile') and sms.local_mobile:
            local_mobile = sms.local_mobile
        else:
            from .mobile_utils import get_local_mobile_number
            local_mobile = await get_local_mobile_number(sms.sender_number, pool)
        
        # Check if mobile number exists in onboarding table and get stored hash
        async with pool.acquire() as conn:
            onboarding_result = await conn.fetchrow(
                "SELECT hash FROM onboarding_mobile WHERE mobile_number = $1 AND is_active = true",
                local_mobile
            )
        
        if not onboarding_result:
            return 2  # fail - mobile number not found in onboarding table
        
        stored_hash = onboarding_result['hash']
        
        # Compare provided hash with stored hash
        if provided_hash.lower() != stored_hash.lower():
            return 2  # fail - hash mismatch
        
        return 1  # pass - all validations successful
        
    except Exception as e:
        # Log error and fail safely
        print(f"Error in header_hash_check: {e}")
        return 2  # fail on error
