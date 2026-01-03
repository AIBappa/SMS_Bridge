# Admin UI Security Guide

## Overview

The SMS Bridge Admin UI provides powerful management capabilities for your SMS verification system. This document outlines the security measures implemented to protect against unauthorized admin access.

## Security Measures

### 1. **Admin Creation Secret** 🔐

A secret key (like a master password) is required to create any admin user. This prevents random internet users from creating admin accounts even if they can access your server.

**Configuration:**
- Environment variable: `SMS_BRIDGE_ADMIN_CREATION_SECRET`
- Must be set before any admin can be created
- Should be a strong, random string (recommended: 32+ characters)

**Generate a secure secret:**
```bash
# Linux/macOS
openssl rand -hex 32

# Or use Python
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Add to your .env file:**
```bash
SMS_BRIDGE_ADMIN_CREATION_SECRET=your_generated_secret_here
```

### 2. **Admin Creation Lockdown** 🔒

After the first admin user is created, admin creation is automatically **locked down** by default. This prevents attackers from creating additional admin accounts.

**Configuration:**
- Environment variable: `SMS_BRIDGE_ADMIN_CREATION_LOCKDOWN`
- Default: `True` (recommended)
- Set to `False` only if you need to create multiple admins

### 3. **CLI-Only Admin Creation** 🖥️

Admin users can **ONLY** be created via the command-line script on the server. There is **NO web endpoint** for admin creation, preventing:
- Remote admin creation attacks
- CSRF attacks on admin creation
- Automated bot attacks

### 4. **Password Hashing** 🛡️

All admin passwords are hashed using **bcrypt** before storage. Raw passwords are never stored in the database.

## Creating Your First Admin

### Step 1: Set the Admin Creation Secret

Add to your `.env` file or Docker environment:

```bash
SMS_BRIDGE_ADMIN_CREATION_SECRET=your_very_secure_secret_key_here
SMS_BRIDGE_ADMIN_CREATION_LOCKDOWN=True
```

### Step 2: Run the Admin Creation Script

**From your server (SSH or local):**

```bash
# Method 1: Pass secret as argument
python3 scripts/create_admin.py admin YourStrongPassword123 your_secret_key

# Method 2: Interactive mode (secret not visible in command history)
python3 scripts/create_admin.py admin YourStrongPassword123
# You'll be prompted for the secret
```

**Using Docker:**

```bash
docker exec -it sms_receiver python3 scripts/create_admin.py admin YourStrongPassword123
# You'll be prompted for the secret
```

### Step 3: Secure the Secret

**IMPORTANT:** After creating your first admin:

1. **Remove the secret from the server** (optional but recommended):
   ```bash
   # Edit your .env and remove or comment out the line:
   # SMS_BRIDGE_ADMIN_CREATION_SECRET=...
   ```

2. **Store the secret securely offline** (in case you need to create more admins later)

3. **Restart your application** to reload environment variables

## Creating Additional Admins

If you need to create more admin users after lockdown:

### Temporary Lockdown Disable

1. Set `SMS_BRIDGE_ADMIN_CREATION_LOCKDOWN=False` in your `.env`
2. Restart the application
3. Run the admin creation script with the secret
4. Set `SMS_BRIDGE_ADMIN_CREATION_LOCKDOWN=True` again
5. Restart the application

### Alternative: Create from Admin UI

Once logged in as an admin, you can create additional admins through the Admin UI without needing the creation secret (coming soon in future versions).

## Security Best Practices

### ✅ DO

- **Generate a strong, random secret** (32+ characters)
- **Store the secret in a password manager** after removing from server
- **Use strong admin passwords** (12+ characters, mixed case, numbers, symbols)
- **Enable admin creation lockdown** (`SMS_BRIDGE_ADMIN_CREATION_LOCKDOWN=True`)
- **Remove the secret from .env** after creating first admin
- **Use HTTPS** for the admin UI (via Cloudflare Tunnel or reverse proxy)
- **Limit SSH access** to your server
- **Enable 2FA** on your hosting account (Hetzner, etc.)

### ❌ DON'T

- **Don't commit the secret to Git** (use `.env` which is in `.gitignore`)
- **Don't use weak secrets** like "password123" or "admin"
- **Don't share the secret** via unsecured channels (email, chat)
- **Don't expose the admin UI** without HTTPS
- **Don't use the same secret** for multiple deployments
- **Don't leave the secret in .env** long-term (remove after first admin creation)

## Cloudflare Tunnel Security

When exposing via Cloudflare Tunnel:

1. **Enable Cloudflare Access** (optional but recommended):
   - Add email-based authentication before reaching your app
   - Requires Cloudflare Zero Trust (free tier available)

2. **Use Cloudflare WAF rules** to:
   - Rate limit login attempts
   - Block suspicious IP addresses
   - Monitor for attack patterns

3. **Enable Cloudflare Bot Management** to block automated attacks

## Threat Model

### What This Protects Against ✅

1. **Unauthorized admin creation** - Random users can't create admin accounts
2. **Post-deployment attacks** - After first admin, no more admins can be created
3. **Automated bot attacks** - No web endpoint exists for admin creation
4. **Credential stuffing** - Strong password requirements and bcrypt hashing
5. **Command injection** - CLI script uses parameterized database queries

### What This Does NOT Protect Against ❌

1. **Compromised server** - If attacker has SSH/root access, they control everything
2. **Stolen admin credentials** - Use strong passwords and secure storage
3. **SQL injection** (already protected by SQLAlchemy ORM)
4. **XSS attacks** (already protected by FastAPI/Starlette)
5. **Physical access to server** - Encrypt your disks!

## Monitoring & Auditing

### Check Admin Users

```bash
# Via Docker
docker exec -it sms_receiver python3 -c "
from core.database import get_db_context
from core.models import AdminUser
with get_db_context() as db:
    admins = db.query(AdminUser).all()
    for admin in admins:
        print(f'Admin: {admin.username} (created: {admin.created_at})')
"
```

### Monitor Login Attempts

Check application logs for suspicious admin login activity:

```bash
docker logs sms_receiver | grep "Admin login"
```

## Troubleshooting

### "ADMIN_CREATION_SECRET not set in environment"

**Problem:** The environment variable is missing or not loaded.

**Solution:**
1. Add `SMS_BRIDGE_ADMIN_CREATION_SECRET=...` to your `.env` file
2. Restart the application to reload environment variables

### "Invalid admin creation secret provided"

**Problem:** The secret you provided doesn't match the one in `.env`.

**Solution:**
1. Double-check the secret in your `.env` file
2. Make sure there are no extra spaces or quotes
3. Restart application after changing `.env`

### "Admin creation is locked down"

**Problem:** Lockdown is enabled and first admin already exists.

**Solution:**
1. Set `SMS_BRIDGE_ADMIN_CREATION_LOCKDOWN=False` in `.env`
2. Restart application
3. Create new admin
4. Set `SMS_BRIDGE_ADMIN_CREATION_LOCKDOWN=True` again
5. Restart application

### "Admin user already exists"

**Problem:** Username is taken.

**Solution:**
Use a different username or delete the existing user from the database.

## Emergency Access Recovery

If you lose admin credentials:

### Option 1: Reset Password via Database

```bash
# Generate new password hash
python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('NewPassword123'))"

# Update in database (replace <hash> and <username>)
docker exec -it sms_postgres psql -U postgres -d sms_bridge -c \
  "UPDATE admin_users SET password_hash='<hash>' WHERE username='<username>';"
```

### Option 2: Create New Admin

If you have the `ADMIN_CREATION_SECRET` backed up:

1. Temporarily disable lockdown
2. Create new admin with the script
3. Re-enable lockdown

## Questions?

For security concerns or questions:
- Check the [main README](../README.md)
- Review [Technical Specification](core/SMS_Bridge_tech_spec_v2.2.md)
- Open a GitHub issue (for non-sensitive questions only)

---

**Remember:** Security is a process, not a feature. Regularly review your security posture!
