import json
import re
from .mobile_utils import normalize_mobile_number

async def validate_foreign_number_check(sms, pool):
    """
    Validate if the sender's mobile number is from an allowed country.
    
    Returns:
    - 1: pass (allowed country)
    - 2: fail (foreign/disallowed country)
    - 3: skip (validation disabled)
    """
    try:
        # Get foreign number validation setting
        async with pool.acquire() as conn:
            foreign_validation_enabled = await conn.fetchval(
                "SELECT setting_value FROM sms_settings WHERE setting_key = 'foreign_number_validation'"
            )
            
            if foreign_validation_enabled != 'true':
                return 3  # skip validation
            
            # Get allowed country codes
            allowed_codes_json = await conn.fetchval(
                "SELECT setting_value FROM sms_settings WHERE setting_key = 'allowed_country_codes'"
            )
        
        # Parse allowed country codes
        try:
            allowed_codes = json.loads(allowed_codes_json) if allowed_codes_json else ["91"]
        except (json.JSONDecodeError, TypeError):
            allowed_codes = ["91"]  # Default to India if parsing fails
        
        # Use structured country code or extract from sender number
        if hasattr(sms, 'country_code') and sms.country_code:
            country_code = sms.country_code
        else:
            country_code, local_number = await normalize_mobile_number(sms.sender_number, pool)
        
        # Check if the extracted country code is in allowed list
        if country_code in allowed_codes:
            return 1  # pass - allowed country
        
        # If country code not in allowed list, it's a foreign number
        return 2  # fail - foreign number
        
    except Exception as e:
        # Log error and fail safely
        print(f"Error in foreign_number_check: {e}")
        return 2  # fail on error
