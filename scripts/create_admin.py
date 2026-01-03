#!/usr/bin/env python3
"""
Create Admin User Script
Run this to create an admin user for the SMS Bridge Admin UI

Security Requirements:
- ADMIN_CREATION_SECRET must be set in environment (SMS_BRIDGE_ADMIN_CREATION_SECRET)
- By default, only one admin can be created (lockdown after first admin)
"""
import sys
import os
import getpass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.admin.admin import create_admin_user

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python create_admin.py <username> <password> <creation_secret>")
        print("")
        print("Arguments:")
        print("  username         - Admin username")
        print("  password         - Admin password")
        print("  creation_secret  - Secret from SMS_BRIDGE_ADMIN_CREATION_SECRET env var")
        print("")
        print("Example:")
        print("  python create_admin.py admin MySecurePassword123 your_secret_key")
        print("")
        print("Alternative (interactive mode for secret):")
        print("  python create_admin.py admin MySecurePassword123")
        print("  (you will be prompted for the creation secret)")
        print("")
        print("⚠️  SECURITY NOTE:")
        print("The creation secret must match SMS_BRIDGE_ADMIN_CREATION_SECRET")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    # Get creation secret from command line or prompt
    if len(sys.argv) >= 4:
        creation_secret = sys.argv[3]
    else:
        print("")
        creation_secret = getpass.getpass("Enter admin creation secret (from .env): ")
    
    print(f"\nCreating admin user: {username}")
    success = create_admin_user(username, password, creation_secret)
    
    if success:
        print(f"\n✅ Admin user '{username}' created successfully!")
        print(f"\nYou can now login at: http://your-domain/admin/")
        print(f"Username: {username}")
        print(f"\n⚠️  SECURITY REMINDER:")
        print("- Keep your admin credentials secure")
        print("- Admin creation is now locked down (if SMS_BRIDGE_ADMIN_CREATION_LOCKDOWN=True)")
        print("- Remove ADMIN_CREATION_SECRET from server after creating first admin")
    else:
        print(f"\n❌ Failed to create admin user '{username}'")
        print("")
        print("Possible reasons:")
        print("  1. User already exists")
        print("  2. Invalid or missing ADMIN_CREATION_SECRET")
        print("  3. Admin creation is locked (first admin already created)")
        print("  4. Database connection issue")
        print("")
        print("To create additional admins after lockdown:")
        print("  Set SMS_BRIDGE_ADMIN_CREATION_LOCKDOWN=False")
        sys.exit(1)
