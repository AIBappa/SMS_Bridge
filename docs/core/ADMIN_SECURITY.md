# Admin UI Security Guide

## Overview

The SMS Bridge Admin UI provides powerful management capabilities for your SMS verification system. This document outlines the security measures to protect against unauthorized admin access.

## Security Approach

Admin credentials are stored in your `.env` file and automatically create the admin user on first startup. This approach is secure because:

1. **`.env` file protection** - Already in `.gitignore`, never committed to version control
2. **Coolify secret management** - Coolify stores environment variables securely
3. **Server access required** - Only users with SSH/server access can modify `.env`
4. **HTTPS protection** - Use Cloudflare Tunnel or reverse proxy for encrypted access

## Creating Your First Admin

### Step 1: Set Admin Credentials in .env

Add to your `.env` file or Coolify environment variables:

```bash
SMS_BRIDGE_ADMIN_USERNAME=admin
SMS_BRIDGE_ADMIN_PASSWORD=YourVeryStrongPassword123!
```

**Generate a strong password:**
```bash
# Linux/macOS - random 20 character password
openssl rand -base64 20

# Or use Python
python3 -c "import secrets, string; chars = string.ascii_letters + string.digits + string.punctuation; print(''.join(secrets.choice(chars) for _ in range(20)))"
```

### Step 2: Deploy/Restart Application

The admin user is **automatically created** on startup if:
- `SMS_BRIDGE_ADMIN_USERNAME` is set
- `SMS_BRIDGE_ADMIN_PASSWORD` is set  
- User doesn't already exist

**Using Docker Compose:**
```bash
docker-compose restart sms_receiver
```

**Using Coolify:**
Just redeploy the service - Coolify will restart with new environment variables.

### Step 3: Login

Access the admin UI at: `https://your-domain/admin/`

- Username: (value from `SMS_BRIDGE_ADMIN_USERNAME`)
- Password: (value from `SMS_BRIDGE_ADMIN_PASSWORD`)

That's it! No separate script needed.

## Creating Additional Admins

**Security Note:** For maximum security, there is no script or programmatic way to create admin users. All admin creation happens via environment variables on startup.

### To Add More Admins:

1. **Using Admin UI** (Recommended when available)
   - Future versions will support creating additional admins through the UI
   - Requires being logged in as an existing admin

2. **Via Database Direct Access** (Advanced users only)
   ```bash
   # Generate password hash
   python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('NewPassword123'))"
   
   # Insert into database (replace <username> and <hash>)
   docker exec -it sms_postgres psql -U postgres -d sms_bridge -c \
     "INSERT INTO admin_users (username, password_hash, created_at) VALUES ('<username>', '<hash>', NOW());"
   ```

3. **Deploy Separate Instance** (For multi-admin scenarios)
   - Add additional admin credentials to `.env`:
     ```bash
     SMS_BRIDGE_ADMIN_USERNAME=newadmin
     SMS_BRIDGE_ADMIN_PASSWORD=SecurePass456
     ```
   - Restart application
   - New admin auto-created if username doesn't exist yet

## Security Best Practices

### ✅ DO

- **Use strong admin passwords** (16+ characters, mixed case, numbers, symbols)
- **Generate passwords with a tool** (use `openssl rand -base64 20`)
- **Never commit .env to Git** (already in `.gitignore`)
- **Use HTTPS** for the admin UI (via Cloudflare Tunnel or reverse proxy)
- **Limit SSH access** to your server
- **Enable 2FA** on your hosting account (Hetzner, etc.)
- **Rotate passwords regularly** (change in .env and restart)
- **Use unique credentials** for each deployment

### ❌ DON'T

- **Don't use weak passwords** like "password123" or "admin"  
- **Don't share credentials** via unsecured channels (email, chat)
- **Don't expose admin UI** without HTTPS
- **Don't reuse passwords** across multiple services
- **Don't leave default credentials** (always change from example values)

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

### Admin user not created on startup

**Problem:** Logged in but admin user doesn't exist.

**Solution:**
1. Check logs: `docker logs sms_receiver | grep -i admin`
2. Verify environment variables are set:
   ```bash
   docker exec sms_receiver printenv | grep SMS_BRIDGE_ADMIN
   ```
3. Ensure both USERNAME and PASSWORD are set (not empty)
4. Restart application: `docker-compose restart sms_receiver`

### Can't login with credentials from .env

**Problem:** Credentials don't work at login page.

**Solution:**
1. Check if user was actually created:
   ```bash
   docker exec -it sms_postgres psql -U postgres -d sms_bridge -c "SELECT username, created_at FROM admin_users;"
   ```
2. If user exists, password might be wrong - see Emergency Access Recovery below
3. If user doesn't exist, check startup logs for errors

## Emergency Access Recovery

If you lose admin credentials:

### Option 1: Update .env and Restart

```bash
# Update credentials in .env
SMS_BRIDGE_ADMIN_USERNAME=admin  # existing username
SMS_BRIDGE_ADMIN_PASSWORD=NewPassword123  # new password

# Restart to trigger re-creation (will skip if user exists)
# Instead, manually update password hash:
```

### Option 2: Reset Password via Database

```bash
# Generate new password hash
python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('NewPassword123'))"

# Update in database (replace <hash> and <username>)
docker exec -it sms_postgres psql -U postgres -d sms_bridge -c \
  "UPDATE admin_users SET password_hash='<hash>' WHERE username='<username>';"
```

### Option 3: Delete and Recreate

```bash
# Delete existing admin
docker exec -it sms_postgres psql -U postgres -d sms_bridge -c \
  "DELETE FROM admin_users WHERE username='admin';"

# Set credentials in .env
SMS_BRIDGE_ADMIN_USERNAME=admin
SMS_BRIDGE_ADMIN_PASSWORD=NewSecurePassword123

# Restart application
docker-compose restart sms_receiver
```

## Questions?

For security concerns or questions:
- Check the [main README](../README.md)
- Review [Technical Specification](core/SMS_Bridge_tech_spec_v2.2.md)
- Open a GitHub issue (for non-sensitive questions only)

---

**Remember:** Security is a process, not a feature. Regularly review your security posture!
