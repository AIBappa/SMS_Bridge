"""
Mobile number utilities for consistent handling across validation checks
"""
import re

async def normalize_mobile_number(mobile_number: str, pool, default_country_code: str = "91") -> tuple:
    """
    Normalize mobile number by extracting country code and local number.
    
    Args:
    mobile_number: Raw mobile number (e.g., "+9199XXYYZZAA", "9199XXYYZZAA", "99XXYYZZAA")
        pool: Database connection pool
        default_country_code: Default country code if none provided
    
    Returns:
        tuple: (country_code, local_number)
    Example: ("91", "99XXYYZZAA")
    """
    # Remove all non-digit characters
    clean_number = re.sub(r'[^\d]', '', mobile_number)
    
    # Get allowed country codes from settings
    async with pool.acquire() as conn:
        allowed_codes_json = await conn.fetchval(
            "SELECT setting_value FROM sms_settings WHERE setting_key = 'allowed_country_codes'"
        )
    
    try:
        import json
        allowed_codes = json.loads(allowed_codes_json) if allowed_codes_json else ["91"]
    except:
        allowed_codes = ["91"]  # Default to India
    
    # Sort by length (longest first) to match longer country codes first
    allowed_codes.sort(key=len, reverse=True)
    
    country_code = default_country_code
    local_number = clean_number
    
    # Check if number starts with any allowed country code
    for code in allowed_codes:
        if clean_number.startswith(code):
            country_code = code
            local_number = clean_number[len(code):]
            break
    
    # If no country code matched and number is too long, assume default country code
    if local_number == clean_number and len(clean_number) > 10:
        # Try to extract using default country code
        if clean_number.startswith(default_country_code):
            local_number = clean_number[len(default_country_code):]
    
    return country_code, local_number

async def get_full_mobile_number(country_code: str, local_number: str) -> str:
    """
    Reconstruct full mobile number with country code
    """
    return f"+{country_code}{local_number}"

async def get_local_mobile_number(mobile_number: str, pool) -> str:
    """
    Get just the local part of mobile number (without country code)
    This is what should be stored/compared in onboarding_mobile table
    """
    country_code, local_number = await normalize_mobile_number(mobile_number, pool)
    return local_number
