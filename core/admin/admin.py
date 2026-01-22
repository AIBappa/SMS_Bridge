"""
SMS Bridge v2.2 - Admin UI Module
SQLAdmin setup per tech spec Section 2.
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from sqladmin import Admin, ModelView, BaseView, expose, action
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse, HTMLResponse
from markupsafe import Markup
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
    MonitoringPortState,
    MonitoringPortHistory,
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
    
    async def authenticate(self, request: Request) -> bool:
        """
        Check if user is authenticated.
        
        Returns:
            True if authenticated (allow access)
            False if not authenticated (SQLAdmin will redirect to login)
        """
        try:
            session_data = dict(request.session) if hasattr(request, 'session') else {}
            is_authenticated = request.session.get("authenticated", False) if hasattr(request, 'session') else False
            
            logger.info(f"Authenticate check - Path: {request.url.path}, Has session: {hasattr(request, 'session')}, Session data: {session_data}, Authenticated: {is_authenticated}")
            
            if is_authenticated:
                logger.info(f"Authenticated as: {request.session.get('username')}, returning True to allow access")
                return True
            
            logger.info(f"Not authenticated, returning False to redirect to login from {request.url.path}")
            return False
        except Exception as e:
            logger.error(f"Error in authenticate: {e}", exc_info=True)
            return False


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


class MonitoringPortStateAdmin(ModelView, model=MonitoringPortState):
    """Admin view for Monitoring Port States with Open Port button"""
    name = "Port State"
    name_plural = "Monitoring Port States"
    icon = "fa-solid fa-network-wired"
    
    column_list = [
        MonitoringPortState.id,
        MonitoringPortState.service_name,
        MonitoringPortState.port,
        MonitoringPortState.is_open,
        MonitoringPortState.opened_at,
        MonitoringPortState.scheduled_close_at,
        MonitoringPortState.opened_by,
    ]
    
    column_searchable_list = [MonitoringPortState.service_name, MonitoringPortState.opened_by]
    column_sortable_list = [
        MonitoringPortState.id,
        MonitoringPortState.service_name,
        MonitoringPortState.opened_at,
        MonitoringPortState.scheduled_close_at,
    ]
    column_default_sort = [(MonitoringPortState.opened_at, True)]
    
    can_create = False  # Ports are opened via API/Admin tools
    can_edit = False
    can_delete = True  # Allow cleanup
    
    @action(
        name="open_port",
        label="Open Port",
        confirmation_message="Open this monitoring port for 1 hour?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def open_port_action(self, request: Request):
        """Enable the selected monitoring port(s) via HAProxy"""
        from core.database import get_db_context
        from core.admin.haproxy_port_management import open_monitoring_port
        
        pks = request.query_params.get("pks", "").split(",")
        username = request.session.get("username", "admin")
        
        if pks and pks[0]:
            with get_db_context() as db:
                for pk in pks:
                    try:
                        # Get the port state record
                        port_state = db.query(MonitoringPortState).filter(
                            MonitoringPortState.id == int(pk)
                        ).first()
                        
                        if port_state:
                            # Enable the port via HAProxy
                            open_monitoring_port(
                                db=db,
                                service_name=port_state.service_name,
                                username=username,
                                duration_seconds=3600  # 1 hour default
                            )
                            logger.info(f"Port enabled via HAProxy: {port_state.service_name} by {username}")
                    except Exception as e:
                        logger.error(f"Failed to open port {pk}: {e}")
        
        referer = request.headers.get("Referer")
        if referer:
            return RedirectResponse(referer)
        return RedirectResponse(request.url_for("admin:list", identity=self.identity))
    
    @action(
        name="close_port",
        label="Close Port",
        confirmation_message="Close this monitoring port?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def close_port_action(self, request: Request):
        """Disable the selected monitoring port(s) via HAProxy"""
        from core.database import get_db_context
        from core.admin.haproxy_port_management import close_monitoring_port
        
        pks = request.query_params.get("pks", "").split(",")
        username = request.session.get("username", "admin")
        
        if pks and pks[0]:
            with get_db_context() as db:
                for pk in pks:
                    try:
                        # Get the port state record
                        port_state = db.query(MonitoringPortState).filter(
                            MonitoringPortState.id == int(pk)
                        ).first()
                        
                        if port_state and port_state.is_open:
                            # Disable the port via HAProxy
                            close_monitoring_port(
                                db=db,
                                service_name=port_state.service_name,
                                username=username,
                                reason='manual'
                            )
                            logger.info(f"Port disabled via HAProxy: {port_state.service_name} by {username}")
                    except Exception as e:
                        logger.error(f"Failed to close port {pk}: {e}")
        
        referer = request.headers.get("Referer")
        if referer:
            return RedirectResponse(referer)
        return RedirectResponse(request.url_for("admin:list", identity=self.identity))


class MonitoringPortHistoryAdmin(ModelView, model=MonitoringPortHistory):
    """Admin view for Monitoring Port History (Audit Log)"""
    name = "Port History Entry"
    name_plural = "Monitoring Port History"
    icon = "fa-solid fa-clock-rotate-left"
    
    column_list = [
        MonitoringPortHistory.id,
        MonitoringPortHistory.service_name,
        MonitoringPortHistory.port,
        MonitoringPortHistory.action,
        MonitoringPortHistory.timestamp,
        MonitoringPortHistory.action_by,
        MonitoringPortHistory.reason,
    ]
    
    column_searchable_list = [MonitoringPortHistory.service_name, MonitoringPortHistory.action_by]
    column_sortable_list = [
        MonitoringPortHistory.id,
        MonitoringPortHistory.service_name,
        MonitoringPortHistory.timestamp,
    ]
    column_default_sort = [(MonitoringPortHistory.timestamp, True)]
    
    can_create = False  # Audit log is append-only via system
    can_edit = False
    can_delete = True  # Allow old log cleanup


# =============================================================================
# Custom Admin Views (BaseView) - Tools with Buttons
# =============================================================================

class TriggerRecoveryView(BaseView):
    """
    Custom admin view for triggering recovery process.
    Provides UI button to send batch of verified mobiles to recovery_url.
    """
    name = "Trigger Recovery"
    icon = "fa-solid fa-rotate"
    category = "Tools"
    
    @expose("/trigger-recovery", methods=["GET"])
    async def trigger_recovery_page(self, request: Request):
        """Serve the trigger recovery admin page with button"""
        html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Trigger Recovery - SMS Bridge Admin</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            margin-bottom: 20px;
        }
        .info {
            background-color: #e7f3ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin-bottom: 20px;
        }
        .warning {
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-bottom: 20px;
        }
        button {
            background-color: #d32f2f;
            color: white;
            padding: 15px 30px;
            font-size: 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 20px;
        }
        button:hover {
            background-color: #b71c1c;
        }
        button:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        .result {
            margin-top: 20px;
            padding: 15px;
            border-radius: 4px;
            display: none;
        }
        .result.success {
            background-color: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
        }
        .result.error {
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
        }
        .back-link {
            display: inline-block;
            margin-top: 20px;
            color: #2196F3;
            text-decoration: none;
        }
        .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔄 Manual Recovery Trigger</h1>
        
        <div class="info">
            <strong>ℹ️ What this does:</strong><br>
            Collects all failed users from the sync_queue and sends them as a batch to your recovery_url endpoint.
            Use this when automatic sync has failed and you want to manually resend all pending users.
        </div>
        
        <div class="warning">
            <strong>⚠️ Warning:</strong><br>
            This will send ALL users currently in the sync_queue to your recovery endpoint.
            Make sure your backend's recovery endpoint is available and ready to process the batch.
        </div>
        
        <button id="triggerBtn" onclick="triggerRecovery()">
            🚀 Trigger Recovery Now
        </button>
        
        <div id="result" class="result"></div>
        
        <a href="/admin" class="back-link">← Back to Admin Dashboard</a>
    </div>
    
    <script>
        async function triggerRecovery() {
            const btn = document.getElementById('triggerBtn');
            const result = document.getElementById('result');
            
            btn.disabled = true;
            btn.textContent = '⏳ Processing...';
            result.style.display = 'none';
            
            try {
                const response = await fetch('/admin/trigger-recovery', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    result.className = 'result success';
                    result.innerHTML = `<strong>✅ Success!</strong><br>${data.message}`;
                } else {
                    result.className = 'result error';
                    result.innerHTML = `<strong>❌ Error!</strong><br>${data.detail || data.message}`;
                }
                result.style.display = 'block';
            } catch (error) {
                result.className = 'result error';
                result.innerHTML = `<strong>❌ Error!</strong><br>Failed to connect to recovery endpoint: ${error.message}`;
                result.style.display = 'block';
            } finally {
                btn.disabled = false;
                btn.textContent = '🚀 Trigger Recovery Now';
            }
        }
    </script>
</body>
</html>
        """
        
        return HTMLResponse(content=html_content)


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
    
    # Register model views (Data Management)
    admin.add_view(SettingsHistoryAdmin)
    admin.add_view(SMSBridgeLogAdmin)
    admin.add_view(BlacklistMobileAdmin)
    admin.add_view(BackupUserAdmin)
    admin.add_view(PowerDownStoreAdmin)
    admin.add_view(AdminUserAdmin)
    admin.add_view(MonitoringPortStateAdmin)  # Has Open/Close Port action buttons
    admin.add_view(MonitoringPortHistoryAdmin)
    
    # Register custom views (Tools with buttons)
    admin.add_view(TriggerRecoveryView)
    
    logger.info(f"Admin UI mounted at {settings.admin_path}")
    logger.info("Admin Tools registered: 'Trigger Recovery'")
    
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
