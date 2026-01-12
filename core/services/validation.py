"""
SMS Bridge v2.2 - Validation Checks
Four validation checks as per tech spec Section 4.2
Each check returns: (status_code, message)
Status codes: 1=Pass, 2=Fail, 3=Disabled
"""
import logging
import re
from typing import Tuple, Optional, Dict, Any

from core.models.schemas import ChecksConfig
from core import redis_v2 as redis_client

logger = logging.getLogger(__name__)


class ValidationCheck:
    """Base class for validation checks"""
    name: str = "base_check"
    
    def run(self, enabled: bool, **kwargs) -> Tuple[int, Optional[str]]:
        """
        Execute the check.
        Returns: (status_code, message)
            - 1 = Pass
            - 2 = Fail (with message)
            - 3 = Disabled (skipped)
        """
        if not enabled:
            return 3, None
        return self._execute(**kwargs)
    
    def _execute(self, **kwargs) -> Tuple[int, Optional[str]]:
        """Override in subclass"""
        raise NotImplementedError


class HeaderHashCheck(ValidationCheck):
    """
    Check 1: Header Hash Validation
    - Validates message format: {prefix}{hash}
    - Validates hash exists in active_onboarding:{hash}
    """
    name = "header_hash_check"
    
    def _execute(self, **kwargs) -> Tuple[int, Optional[str]]:
        """
        Args:
            message: SMS message body (e.g., "ONBOARD:A3B7K2M9")
            allowed_prefix: Expected prefix (e.g., "ONBOARD:")
            hash_length: Expected hash length (e.g., 8)
        """
        message = kwargs['message']
        allowed_prefix = kwargs['allowed_prefix']
        hash_length = kwargs['hash_length']
        
        # Validate message format
        expected_length = len(allowed_prefix) + hash_length
        if len(message) != expected_length:
            return 2, f"Invalid message length: expected {expected_length}, got {len(message)}"
        
        # Validate prefix
        if not message.startswith(allowed_prefix):
            return 2, f"Message must start with '{allowed_prefix}'"
        
        # Extract hash
        hash_val = message[len(allowed_prefix):]
        
        # Lookup in Redis
        onboarding_data = redis_client.get_active_onboarding(hash_val)
        if onboarding_data is None:
            return 2, f"Hash not found or expired"
        
        # Pass - store extracted hash for later use
        logger.debug(f"Header hash check passed for hash={hash_val[:4]}...")
        return 1, None


class ForeignNumberCheck(ValidationCheck):
    """
    Check 2: Foreign Number Validation
    - Validates mobile country code is in allowed_countries list
    """
    name = "foreign_number_check"
    
    def _execute(self, **kwargs) -> Tuple[int, Optional[str]]:
        """
        Args:
            mobile_number: Full mobile with country code (e.g., "+9199XXYYZZAA")
            allowed_countries: List of allowed country codes (e.g., ["+91", "+44"])
        """
        mobile_number = kwargs['mobile_number']
        allowed_countries = kwargs['allowed_countries']
        
        # Extract country code from mobile
        country_code = self._extract_country_code(mobile_number)
        if country_code is None:
            return 2, "Invalid mobile number format"
        
        # Check if country is allowed
        if country_code not in allowed_countries:
            return 2, f"Country code {country_code} not supported"
        
        logger.debug(f"Foreign number check passed for {country_code}")
        return 1, None
    
    @staticmethod
    def _extract_country_code(mobile: str) -> Optional[str]:
        """
        Extract country code from mobile number.
        Supports: +91XXXXXXX, +44XXXXXXX, +1XXXXXXX formats
        """
        if not mobile.startswith("+"):
            return None
        
        # Common country code patterns
        # +1 (US/Canada), +44 (UK), +91 (India), +86 (China), etc.
        patterns = [
            r'^(\+1)\d{10}$',      # +1 followed by 10 digits (US/Canada)
            r'^(\+\d{2})\d{10}$',  # +XX followed by 10 digits (most countries)
            r'^(\+\d{3})\d{9,10}$', # +XXX followed by 9-10 digits
        ]
        
        for pattern in patterns:
            match = re.match(pattern, mobile)
            if match:
                return match.group(1)
        
        # Fallback: try to extract +XX or +XXX
        if len(mobile) >= 3:
            # Try +XX first
            if len(mobile) >= 12 and mobile[1:3].isdigit():
                return mobile[:3]
            # Try +XXX
            if len(mobile) >= 13 and mobile[1:4].isdigit():
                return mobile[:4]
        
        return None


class CountCheck(ValidationCheck):
    """
    Check 3: Rate Limiting
    - Tracks SMS count per mobile using Redis counter
    - Fails if count exceeds threshold
    """
    name = "count_check"
    
    def _execute(self, **kwargs) -> Tuple[int, Optional[str]]:
        """
        Args:
            mobile_number: Sender mobile number
            count_threshold: Maximum SMS count per minute
        """
        mobile_number = kwargs['mobile_number']
        count_threshold = kwargs['count_threshold']
        
        # Increment counter (creates with TTL 60s if new)
        count = redis_client.incr_rate(mobile_number, ttl_seconds=60)
        
        if count > count_threshold:
            return 2, f"Rate limit exceeded ({count}/{count_threshold})"
        
        logger.debug(f"Count check passed: {count}/{count_threshold}")
        return 1, None


class BlacklistCheck(ValidationCheck):
    """
    Check 4: Blacklist Validation
    - Checks if mobile is in Redis blacklist set
    """
    name = "blacklist_check"
    
    def _execute(self, **kwargs) -> Tuple[int, Optional[str]]:
        """
        Args:
            mobile_number: Mobile number to check
        """
        mobile_number = kwargs['mobile_number']
        
        is_blacklisted = redis_client.sismember_blacklist(mobile_number)
        
        if is_blacklisted:
            logger.warning(f"Blacklisted mobile detected: {mobile_number[-4:]}")
            return 2, "Mobile number is blacklisted"
        
        logger.debug(f"Blacklist check passed for {mobile_number[-4:]}")
        return 1, None


# =============================================================================
# Validation Pipeline
# =============================================================================

def run_validation_pipeline(
    message: str,
    mobile_number: str,
    config: Dict[str, Any],
) -> Tuple[bool, Dict[str, Tuple[int, Optional[str]]]]:
    """
    Run all 4 validation checks in sequence.
    
    Args:
        message: SMS message body
        mobile_number: Sender mobile number
        config: Settings payload (must include 'checks' and other fields)
    
    Returns:
        (all_passed: bool, results: dict)
        results = {
            "header_hash_check": (status_code, message),
            "foreign_number_check": (status_code, message),
            "count_check": (status_code, message),
            "blacklist_check": (status_code, message),
        }
    """
    checks_config = config.get("checks", {})
    results = {}
    all_passed = True
    
    # 1. Header Hash Check
    header_check = HeaderHashCheck()
    status, msg = header_check.run(
        enabled=checks_config.get("header_hash_check_enabled", True),
        message=message,
        allowed_prefix=config.get("allowed_prefix", "ONBOARD:"),
        hash_length=config.get("hash_length", 8),
    )
    results["header_hash_check"] = (status, msg)
    if status == 2:
        all_passed = False
    
    # 2. Foreign Number Check
    foreign_check = ForeignNumberCheck()
    status, msg = foreign_check.run(
        enabled=checks_config.get("foreign_number_check_enabled", True),
        mobile_number=mobile_number,
        allowed_countries=config.get("allowed_countries", ["+91", "+44"]),
    )
    results["foreign_number_check"] = (status, msg)
    if status == 2:
        all_passed = False
    
    # 3. Count Check
    count_check = CountCheck()
    status, msg = count_check.run(
        enabled=checks_config.get("count_check_enabled", True),
        mobile_number=mobile_number,
        count_threshold=config.get("count_threshold", 5),
    )
    results["count_check"] = (status, msg)
    if status == 2:
        all_passed = False
    
    # 4. Blacklist Check
    blacklist_check = BlacklistCheck()
    status, msg = blacklist_check.run(
        enabled=checks_config.get("blacklist_check_enabled", True),
        mobile_number=mobile_number,
    )
    results["blacklist_check"] = (status, msg)
    if status == 2:
        all_passed = False
    
    return all_passed, results


def extract_hash_from_message(message: str, allowed_prefix: str) -> Optional[str]:
    """
    Helper function to extract hash from message.
    Returns None if message doesn't start with prefix.
    """
    if message.startswith(allowed_prefix):
        return message[len(allowed_prefix):]
    return None
