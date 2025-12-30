"""
SMS Bridge v2.2 - Hash Generation Utility
Generates Base32-encoded HMAC-SHA256 hashes for onboarding.
"""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Tuple


def generate_onboarding_hash(
    mobile: str,
    hmac_secret: str,
    hash_length: int = 8,
    server_timestamp: datetime = None,
) -> Tuple[str, datetime]:
    """
    Generate onboarding hash per tech spec:
    Base32(HMAC-SHA256(Mobile + Server_Timestamp, hmac_secret))[:hash_length]
    
    Args:
        mobile: Mobile number with country code
        hmac_secret: Secret key for HMAC
        hash_length: Output hash length (default 8)
        server_timestamp: Override timestamp (for testing)
    
    Returns:
        (hash: str, generated_at: datetime)
    """
    if server_timestamp is None:
        server_timestamp = datetime.utcnow()
    
    # Create message: Mobile + Timestamp
    message = f"{mobile}{server_timestamp.isoformat()}"
    
    # Generate HMAC-SHA256
    hmac_digest = hmac.new(
        key=hmac_secret.encode('utf-8'),
        msg=message.encode('utf-8'),
        digestmod=hashlib.sha256,
    ).digest()
    
    # Encode to Base32 (uppercase, no padding)
    base32_hash = base64.b32encode(hmac_digest).decode('utf-8').rstrip('=')
    
    # Truncate to hash_length
    truncated_hash = base32_hash[:hash_length].upper()
    
    return truncated_hash, server_timestamp


def verify_hash_format(hash_val: str, expected_length: int = 8) -> bool:
    """
    Verify hash format is valid.
    Must be uppercase alphanumeric Base32 characters.
    """
    if len(hash_val) != expected_length:
        return False
    
    # Base32 characters: A-Z and 2-7
    valid_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')
    return all(c in valid_chars for c in hash_val)


def generate_random_salt(length: int = 16) -> str:
    """Generate cryptographically secure random salt"""
    return secrets.token_hex(length)


def hash_pin(pin: str, salt: str) -> str:
    """
    Hash PIN with salt using SHA256.
    Used for storing PIN in transit (sync_queue).
    """
    salted = f"{salt}{pin}"
    return hashlib.sha256(salted.encode('utf-8')).hexdigest()
