#!/usr/bin/env python3
"""
Create Admin User Script
Run this to create an admin user for the SMS Bridge Admin UI
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.admin.admin import create_admin_user

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python create_admin.py <username> <password>")
        print("Example: python create_admin.py admin MySecurePassword123")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    print(f"Creating admin user: {username}")
    success = create_admin_user(username, password)
    
    if success:
        print(f"✅ Admin user '{username}' created successfully!")
        print(f"\nYou can now login at: http://localhost:8080/admin/")
        print(f"Username: {username}")
    else:
        print(f"❌ Failed to create admin user '{username}'")
        print("The user may already exist.")
        sys.exit(1)
