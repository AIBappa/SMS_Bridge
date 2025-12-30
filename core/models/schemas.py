"""
SMS Bridge v2.2 - Pydantic Schemas
Request/Response models for all API endpoints.
Aligned with integration_openapi.yaml
"""
from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field


# =============================================================================
# Settings Payload (stored in settings_history.payload)
# =============================================================================

class ChecksConfig(BaseModel):
    """Enable/disable flags for validation checks"""
    header_hash_check_enabled: bool = True
    foreign_number_check_enabled: bool = True
    count_check_enabled: bool = True
    blacklist_check_enabled: bool = True


class SecretsConfig(BaseModel):
    """Secrets stored in settings payload"""
    hmac_secret: str
    hash_key: Optional[str] = None


class SettingsPayload(BaseModel):
    """
    Full settings payload stored in settings_history.payload.
    Cached to Redis key config:current when is_active=True.
    """
    sms_receiver_number: str = Field(..., description="Number user sends SMS to")
    allowed_prefix: str = Field(default="ONBOARD:", description="Required SMS prefix")
    hash_length: int = Field(default=8, description="Hash output length")
    ttl_hash_seconds: int = Field(default=900, description="TTL for active_onboarding:{hash}")
    sync_interval: float = Field(default=1.0, description="Sync worker interval in seconds")
    log_interval: int = Field(default=120, description="Audit worker interval in seconds")
    count_threshold: int = Field(default=5, description="Rate limit per mobile")
    allowed_countries: List[str] = Field(default=["+91", "+44"], description="Allowed country codes")
    sync_url: str = Field(..., description="URL for validated user data sync")
    recovery_url: str = Field(..., description="URL for recovery trigger")
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
    secrets: SecretsConfig


# =============================================================================
# POST /onboarding/register
# =============================================================================

class OnboardRegisterRequest(BaseModel):
    """Request body for /onboarding/register"""
    mobile_number: str = Field(..., description="Mobile number with country code (e.g., +9199XXYYZZAA)")
    email: Optional[str] = Field(None, description="Optional email address")
    device_id: Optional[str] = Field(None, description="Optional device identifier")


class OnboardRegisterResponse(BaseModel):
    """Response for successful /onboarding/register"""
    status: str = Field(default="success")
    sms_receiving_number: str = Field(..., description="Number user sends SMS to")
    hash: str = Field(..., description="Hash to include in SMS body after prefix")
    generated_at: datetime = Field(..., description="Timestamp of hash generation")
    user_deadline: datetime = Field(..., description="Soft deadline for user display")
    user_timelimit_seconds: int = Field(default=300, description="Countdown value for UI timer")


# =============================================================================
# POST /sms/receive
# =============================================================================

class SMSReceiveRequest(BaseModel):
    """Request body for /sms/receive (from SMS gateway or Test Lab)"""
    mobile_number: str = Field(..., description="Sender mobile number")
    message: str = Field(..., description="SMS message body (e.g., 'ONBOARD:A3B7K2M9')")
    received_at: datetime = Field(..., description="Timestamp when SMS was received")


class SMSReceiveResponse(BaseModel):
    """Response for /sms/receive"""
    status: str = Field(..., description="received | failed")
    message_id: str = Field(..., description="UUID for tracking")
    queued_for_processing: bool = Field(default=True)


# =============================================================================
# POST /pin-setup
# =============================================================================

class PinSetupRequest(BaseModel):
    """Request body for /pin-setup"""
    mobile_number: str = Field(..., description="Verified mobile number")
    pin: str = Field(..., description="User's chosen PIN")
    hash: str = Field(..., description="Hash from onboarding")


class PinSetupResponse(BaseModel):
    """Response for /pin-setup"""
    status: str = Field(default="success")
    message: str = Field(default="PIN accepted, account creation in progress")


# =============================================================================
# GET /health
# =============================================================================

class HealthChecks(BaseModel):
    """Component health status"""
    database: str = Field(..., description="healthy | degraded | unhealthy")
    redis: str = Field(..., description="healthy | degraded | unhealthy")
    batch_processor: str = Field(..., description="running | stopped | degraded")


class HealthResponse(BaseModel):
    """Response for /health endpoint"""
    status: str = Field(..., description="healthy | degraded | unhealthy")
    service: str = Field(default="sms-bridge")
    version: str = Field(default="2.2.0")
    timestamp: datetime
    checks: HealthChecks


# =============================================================================
# POST /admin/trigger-recovery
# =============================================================================

class TriggerRecoveryResponse(BaseModel):
    """Response for /admin/trigger-recovery"""
    status: str = Field(default="success")
    triggered_at: datetime
    message: str = Field(default="Recovery process initiated")


# =============================================================================
# Outbound Payload (to sync_url)
# =============================================================================

class OutboundValidatedSms(BaseModel):
    """
    Payload pushed to sync_queue and sent to sync_url.
    Contains only essential data for backend integration.
    """
    mobile: str = Field(..., description="Verified mobile number")
    pin: str = Field(..., description="User's chosen PIN")
    hash: str = Field(..., description="Hash from onboarding")


# =============================================================================
# Audit Buffer Event
# =============================================================================

class AuditEvent(BaseModel):
    """Event structure for audit_buffer"""
    event: str = Field(..., description="Event type (e.g., HASH_GEN, SMS_VERIFIED, PIN_COLLECTED)")
    details: Dict[str, Any] = Field(default_factory=dict, description="Event-specific details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Error Responses
# =============================================================================

class ErrorResponse(BaseModel):
    """Standard error response"""
    detail: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")


# =============================================================================
# Check Status Codes
# =============================================================================
# 1 = Pass
# 2 = Fail
# 3 = Disabled (skipped)

class ValidationResult(BaseModel):
    """Result of a single validation check"""
    check_name: str
    status: int = Field(..., ge=1, le=3, description="1=Pass, 2=Fail, 3=Disabled")
    message: Optional[str] = None
