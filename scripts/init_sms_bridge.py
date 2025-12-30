#!/usr/bin/env python3
"""
SMS Bridge v2.2 - Initialization Script
Creates initial admin user and default settings.
Run once after database setup.
"""
import argparse
import json
import sys
from datetime import datetime
from getpass import getpass

# Add parent directory to path for imports
sys.path.insert(0, '/home/shantanu/Documents/Software/SMS_Laptop_Setup/sms_bridge')

from core.config import get_settings
from core.database import init_db, get_db_context
from core.admin import create_admin_user
from core.models import SettingsHistory, AdminUser


DEFAULT_SETTINGS = {
    "sms_receiver_number": "+918888888888",
    "allowed_prefix": "ONBOARD:",
    "hash_length": 8,
    "ttl_hash_seconds": 900,
    "sync_interval": 1.0,
    "log_interval": 120,
    "count_threshold": 5,
    "allowed_countries": ["+91", "+44"],
    "sync_url": "http://localhost:8001/api/sync",
    "recovery_url": "http://localhost:8001/api/recovery",
    "checks": {
        "header_hash_check_enabled": True,
        "foreign_number_check_enabled": True,
        "count_check_enabled": True,
        "blacklist_check_enabled": True
    },
    "secrets": {
        "hmac_secret": "change-this-secret-in-production",
        "hash_key": None
    }
}


def init_database():
    """Initialize database tables"""
    print("Initializing database tables...")
    init_db()
    print("✓ Database tables created")


def create_default_settings(created_by: str = "system"):
    """Create default settings entry"""
    with get_db_context() as db:
        # Check if settings exist
        existing = db.query(SettingsHistory).filter(
            SettingsHistory.is_active == True
        ).first()
        
        if existing:
            print(f"✓ Active settings already exist (version: {existing.version})")
            return
        
        # Create default settings
        settings = SettingsHistory(
            version="1.0.0",
            payload=DEFAULT_SETTINGS,
            is_active=True,
            created_by=created_by,
        )
        db.add(settings)
        print("✓ Default settings created")


def create_initial_admin(username: str, password: str, email: str = None):
    """Create initial admin user"""
    success = create_admin_user(username, password, email)
    if success:
        print(f"✓ Admin user '{username}' created")
    else:
        print(f"! Admin user '{username}' already exists")


def interactive_setup():
    """Interactive setup wizard"""
    print("\n=== SMS Bridge v2.2 Setup ===\n")
    
    # Initialize database
    init_database()
    
    # Create admin user
    print("\nCreate admin user:")
    username = input("  Username [admin]: ").strip() or "admin"
    email = input("  Email (optional): ").strip() or None
    password = getpass("  Password: ")
    password_confirm = getpass("  Confirm password: ")
    
    if password != password_confirm:
        print("! Passwords don't match")
        sys.exit(1)
    
    if len(password) < 8:
        print("! Password must be at least 8 characters")
        sys.exit(1)
    
    create_initial_admin(username, password, email)
    
    # Create default settings
    create_default_settings(created_by=username)
    
    print("\n✓ Setup complete!")
    print(f"\nStart the server with:")
    print(f"  cd /home/shantanu/Documents/Software/SMS_Laptop_Setup/sms_bridge")
    print(f"  python -m core.sms_server_v2")
    print(f"\nAdmin UI available at: http://localhost:8000/admin")


def main():
    parser = argparse.ArgumentParser(description="SMS Bridge Setup Script")
    parser.add_argument("--init-db", action="store_true", help="Initialize database only")
    parser.add_argument("--create-admin", action="store_true", help="Create admin user")
    parser.add_argument("--username", type=str, default="admin", help="Admin username")
    parser.add_argument("--password", type=str, help="Admin password")
    parser.add_argument("--email", type=str, help="Admin email")
    parser.add_argument("--create-settings", action="store_true", help="Create default settings")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive setup")
    
    args = parser.parse_args()
    
    if args.interactive or len(sys.argv) == 1:
        interactive_setup()
        return
    
    if args.init_db:
        init_database()
    
    if args.create_admin:
        if not args.password:
            print("Error: --password required with --create-admin")
            sys.exit(1)
        create_initial_admin(args.username, args.password, args.email)
    
    if args.create_settings:
        create_default_settings()


if __name__ == "__main__":
    main()
