"""
SMS Bridge v2.2 - Admin UI Module
SQLAdmin setup per tech spec Section 2.
"""
import logging
from typing import Optional

from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse
from passlib.context import CryptContext

from core.config import get_settings
from core.database import get_engine
from core.models import (
    SettingsHistory,
    AdminUser,
    SMSBridgeLog,
    BackupUser,
    PowerDownStore,
    BlacklistMobile,
)

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AdminAuth(AuthenticationBackend):
    """
    Authentication backend for SQLAdmin.
    Uses admin_users table for credentials.
    """
    
    async def login(self, request: Request) -> bool:
        """Handle login form submission"""
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
        if not username or not password:
            return False
        
        # Verify credentials against database
        from core.database import get_db_context
        
        with get_db_context() as db:
            admin = db.query(AdminUser).filter(
                AdminUser.username == username
            ).first()
            
            if admin and pwd_context.verify(password, admin.password_hash):
                # Set session
                request.session.update({
                    "authenticated": True,
                    "username": username,
                })
                return True
        
        return False
    
    async def logout(self, request: Request) -> bool:
        """Handle logout"""
        request.session.clear()
        return True
    
    async def authenticate(self, request: Request) -> Optional[RedirectResponse]:
        """Check if user is authenticated"""
        if not request.session.get("authenticated"):
            return RedirectResponse(
                request.url_for("admin:login"),
                status_code=302
            )
        return None


# =============================================================================
# Model Views
# =============================================================================

class SettingsHistoryAdmin(ModelView, model=SettingsHistory):
    """Admin view for Settings History"""
    name = "Settings"
    name_plural = "Settings History"
    icon = "fa-solid fa-gear"
    
    column_list = [
        SettingsHistory.version_id,
        SettingsHistory.is_active,
        SettingsHistory.created_at,
        SettingsHistory.created_by,
    ]
    
    column_searchable_list = [SettingsHistory.created_by]
    column_sortable_list = [SettingsHistory.version_id, SettingsHistory.created_at, SettingsHistory.is_active]
    column_default_sort = [(SettingsHistory.created_at, True)]
    
    can_create = True
    can_edit = True
    can_delete = False  # Preserve history
    
    form_excluded_columns = [SettingsHistory.created_at]


class AdminUserAdmin(ModelView, model=AdminUser):
    """Admin view for Admin Users"""
    name = "Admin User"
    name_plural = "Admin Users"
    icon = "fa-solid fa-user-shield"
    
    column_list = [
        AdminUser.id,
        AdminUser.username,
        AdminUser.is_super_admin,
        AdminUser.created_at,
    ]
    
    column_searchable_list = [AdminUser.username]
    column_sortable_list = [AdminUser.id, AdminUser.username, AdminUser.created_at]
    
    can_create = True
    can_edit = True
    can_delete = True


class SMSBridgeLogAdmin(ModelView, model=SMSBridgeLog):
    """Admin view for SMS Bridge Logs"""
    name = "Log Entry"
    name_plural = "Logs"
    icon = "fa-solid fa-list"
    
    column_list = [
        SMSBridgeLog.id,
        SMSBridgeLog.event,
        SMSBridgeLog.created_at,
    ]
    
    column_searchable_list = [SMSBridgeLog.event]
    column_sortable_list = [SMSBridgeLog.id, SMSBridgeLog.created_at, SMSBridgeLog.event]
    column_default_sort = [(SMSBridgeLog.created_at, True)]
    
    can_create = False
    can_edit = False
    can_delete = True  # Allow log cleanup


class BackupUserAdmin(ModelView, model=BackupUser):
    """Admin view for Backup Users (fallback mode)"""
    name = "Backup User"
    name_plural = "Backup Users"
    icon = "fa-solid fa-database"
    
    column_list = [
        BackupUser.id,
        BackupUser.mobile,
        BackupUser.hash,
        BackupUser.created_at,
        BackupUser.synced_at,
    ]
    
    column_searchable_list = [BackupUser.mobile]
    column_sortable_list = [BackupUser.id, BackupUser.created_at, BackupUser.synced_at]
    
    can_create = False
    can_edit = True  # Allow marking as synced
    can_delete = True


class PowerDownStoreAdmin(ModelView, model=PowerDownStore):
    """Admin view for Power Down Store"""
    name = "Power Down Entry"
    name_plural = "Power Down Store"
    icon = "fa-solid fa-power-off"
    
    column_list = [
        PowerDownStore.id,
        PowerDownStore.key_name,
        PowerDownStore.created_at,
    ]
    
    column_searchable_list = [PowerDownStore.key_name]
    column_sortable_list = [PowerDownStore.id, PowerDownStore.created_at]
    
    can_create = False
    can_edit = False
    can_delete = True


class BlacklistMobileAdmin(ModelView, model=BlacklistMobile):
    """Admin view for Blacklisted Mobiles"""
    name = "Blacklisted Number"
    name_plural = "Blacklist"
    icon = "fa-solid fa-ban"
    
    column_list = [
        BlacklistMobile.id,
        BlacklistMobile.mobile,
        BlacklistMobile.reason,
        BlacklistMobile.created_at,
        BlacklistMobile.created_by,
    ]
    
    column_searchable_list = [BlacklistMobile.mobile, BlacklistMobile.reason]
    column_sortable_list = [BlacklistMobile.id, BlacklistMobile.created_at]
    
    can_create = True
    can_edit = True
    can_delete = True


# =============================================================================
# Admin Setup Function
# =============================================================================

def setup_admin(app: FastAPI) -> Admin:
    """
    Setup SQLAdmin with all model views.
    
    Args:
        app: FastAPI application instance
    
    Returns:
        Admin instance
    """
    settings = get_settings()
    
    # Create admin with authentication
    admin = Admin(
        app,
        engine=get_engine(),
        title="SMS Bridge Admin",
        base_url=settings.admin_path,
        authentication_backend=AdminAuth(secret_key="change-me-in-production"),
    )
    
    # Register model views
    admin.add_view(SettingsHistoryAdmin)
    admin.add_view(SMSBridgeLogAdmin)
    admin.add_view(BlacklistMobileAdmin)
    admin.add_view(BackupUserAdmin)
    admin.add_view(PowerDownStoreAdmin)
    admin.add_view(AdminUserAdmin)
    
    logger.info(f"Admin UI mounted at {settings.admin_path}")
    
    return admin


# =============================================================================
# Admin User Management
# =============================================================================

def create_admin_user(username: str, password: str) -> bool:
    """
    Create a new admin user (INTERNAL USE ONLY).
    
    ⚠️  SECURITY: This function should ONLY be called by ensure_admin_from_env()
    during application startup. It is NOT exported in __init__.py and should
    never be exposed via CLI script or web endpoint.
    
    Args:
        username: Admin username
        password: Admin password (will be hashed)
    
    Returns:
        bool: True if user created successfully, False otherwise
    """
    from core.database import get_db_context
    
    password_hash = pwd_context.hash(password)
    
    try:
        with get_db_context() as db:
            # Check if user exists
            existing = db.query(AdminUser).filter(
                AdminUser.username == username
            ).first()
            
            if existing:
                logger.warning(f"Admin user '{username}' already exists")
                return False
            
            admin = AdminUser(
                username=username,
                password_hash=password_hash,
            )
            db.add(admin)
        
        logger.info(f"Created admin user: {username}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")
        return False


def ensure_admin_from_env() -> None:
    """
    Create admin user from environment variables if it doesn't exist.
    Called during application startup.
    """
    from core.config import get_settings
    
    settings = get_settings()
    
    if not settings.admin_username or not settings.admin_password:
        logger.info("Admin credentials not set in environment, skipping auto-creation")
        return
    
    # Check if admin already exists
    from core.database import get_db_context
    with get_db_context() as db:
        existing = db.query(AdminUser).filter(
            AdminUser.username == settings.admin_username
        ).first()
        
        if existing:
            logger.info(f"Admin user '{settings.admin_username}' already exists")
            return
    
    # Create admin from environment
    success = create_admin_user(settings.admin_username, settings.admin_password)
    if success:
        logger.info(f"Auto-created admin user from environment: {settings.admin_username}")
    else:
        logger.error(f"Failed to auto-create admin user: {settings.admin_username}")


def verify_admin_password(username: str, password: str) -> bool:
    """Verify admin user password"""
    from core.database import get_db_context
    
    with get_db_context() as db:
        admin = db.query(AdminUser).filter(
            AdminUser.username == username
        ).first()
        
        if admin and pwd_context.verify(password, admin.password_hash):
            return True
    
    return False
