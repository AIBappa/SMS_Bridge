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


def _truncate_password_for_bcrypt(password: str) -> str:
    """
    Truncate password to 72 bytes for bcrypt compatibility.
    Bcrypt has a 72-byte limit - this truncates by bytes (not characters).
    """
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        return password_bytes[:72].decode('utf-8', errors='ignore')
    return password


class AdminAuth(AuthenticationBackend):
    """
    Authentication backend for SQLAdmin.
    Uses admin_users table for credentials.
    """
    
    def __init__(self, secret_key: str):
        super().__init__(secret_key)
    
    async def login(self, request: Request) -> bool:
        """Handle login form submission"""
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
        logger.info(f"Admin login attempt for user: {username}")
        
        if not username or not password:
            logger.warning("Login failed: Missing username or password")
            return False
        
        password_truncated = _truncate_password_for_bcrypt(password)
        
        # Verify credentials against database
        from core.database import get_db_context
        
        with get_db_context() as db:
            admin = db.query(AdminUser).filter(
                AdminUser.username == username
            ).first()
            
            if admin and pwd_context.verify(password_truncated, admin.password_hash):
                # Set session
                request.session.update({
                    "authenticated": True,
                    "username": username,
                })
                logger.info(f"Login successful for user: {username}, session: {dict(request.session)}")
                return True
            else:
                logger.warning(f"Login failed for user: {username} - Invalid credentials")
        
        return False
    
    async def logout(self, request: Request) -> bool:
        """Handle logout"""
        request.session.clear()
        return True
    
    async def authenticate(self, request: Request) -> Optional[RedirectResponse]:
        """Check if user is authenticated"""
        try:
            session_data = dict(request.session) if hasattr(request, 'session') else {}
            is_authenticated = request.session.get("authenticated", False) if hasattr(request, 'session') else False
            
            logger.info(f"Authenticate check - Path: {request.url.path}, Has session: {hasattr(request, 'session')}, Session data: {session_data}, Authenticated: {is_authenticated}")
            
            if not is_authenticated:
                logger.info(f"Not authenticated, redirecting to login from {request.url.path}")
                return RedirectResponse(
                    request.url_for("admin:login"),
                    status_code=302
                )
            logger.info(f"Authenticated as: {request.session.get('username')}, returning None to allow access")
            return None
        except Exception as e:
            logger.error(f"Error in authenticate: {e}", exc_info=True)
            return RedirectResponse(
                request.url_for("admin:login"),
                status_code=302
            )


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
    form_excluded_columns = [AdminUser.password_hash]
    
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
    form_excluded_columns = [BackupUser.pin]
    
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
    
    # Validate admin secret key
    if not settings.admin_secret_key:
        raise ValueError(
            "Admin secret key not configured. Set SMS_BRIDGE_ADMIN_SECRET_KEY environment variable."
        )
    
    # Create admin with authentication
    admin = Admin(
        app,
        engine=get_engine(),
        title="SMS Bridge Admin",
        base_url=settings.admin_path,
        authentication_backend=AdminAuth(secret_key=settings.admin_secret_key),
    )
    
    # Register model views
    admin.add_view(SettingsHistoryAdmin)
    admin.add_view(SMSBridgeLogAdmin)
    admin.add_view(BlacklistMobileAdmin)
    admin.add_view(BackupUserAdmin)
    admin.add_view(PowerDownStoreAdmin)
    admin.add_view(AdminUserAdmin)
    
    logger.info(f"Admin UI mounted at {settings.admin_path}")
    
    # Add custom monitoring ports page route
    setup_monitoring_ports_route(app, settings)
    
    return admin


def setup_monitoring_ports_route(app: FastAPI, settings):
    """
    Setup custom route for monitoring ports management page
    """
    from fastapi import Request
    from fastapi.responses import HTMLResponse
    from starlette.responses import RedirectResponse
    from pathlib import Path
    
    @app.get("/admin/monitoring-ports", response_class=HTMLResponse)
    async def monitoring_ports_page(request: Request):
        """Serve the monitoring ports management page"""
        # Check if user is authenticated
        if not request.session.get("authenticated"):
            return RedirectResponse(url=f"{settings.admin_path}/login")
        
        # Read and serve the HTML template
        template_path = Path(__file__).parent.parent / "templates" / "monitoring_ports.html"
        
        if not template_path.exists():
            return HTMLResponse("<h1>Monitoring Ports page not found</h1>", status_code=404)
        
        with open(template_path, 'r') as f:
            html_content = f.read()
        
        return HTMLResponse(content=html_content)
    
    logger.info("Registered custom route: /admin/monitoring-ports")


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
    
    password_truncated = _truncate_password_for_bcrypt(password)
    password_hash = pwd_context.hash(password_truncated)
    
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
        logger.exception("Failed to create admin user")
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
    
    password_truncated = _truncate_password_for_bcrypt(password)
    
    with get_db_context() as db:
        admin = db.query(AdminUser).filter(
            AdminUser.username == username
        ).first()
        
        if admin and pwd_context.verify(password_truncated, admin.password_hash):
            return True
    
    return False
