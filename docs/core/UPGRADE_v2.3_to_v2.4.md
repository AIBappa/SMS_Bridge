# SMS Bridge v2.3 → v2.4 Upgrade Notes

**Date:** January 20, 2026

## Summary

Version 2.4 corrects documentation discrepancies between the actual implementation and documentation. The settings structure in v2.3 documentation did not match the actual `SettingsPayload` schema used in the codebase.

## What Changed

### Documentation Updates

1. **Tech Spec:** `SMS_Bridge_tech_spec_v2.3.md` → `SMS_Bridge_tech_spec_v2.4.md`
   - Complete rewrite of Section 4 (Settings and Configuration)
   - All 13 settings now documented with detailed descriptions
   - Added subsections for each setting explaining What, Format, Example, Why, Default, Notes
   - Added complete settings JSON example

2. **Tech Snippets:** `SMS_Bridge_tech_snippets_v2.3.md` → `SMS_Bridge_tech_snippets_v2.4.md`
   - Updated settings structure example to match actual implementation
   - Removed deprecated nested structure

3. **Settings Template:** `core/config/sms_settings.json`
   - Updated from nested v2.3.0 structure to flat v2.4.0 structure
   - Now matches actual `SettingsPayload` schema

4. **API Key Setup:** `SMS_RECEIVE_API_KEY_SETUP.md`
   - Updated version reference to v2.4
   - Corrected settings example

### No Code Changes

**Important:** This is a documentation-only update. The actual code implementation has not changed. The settings structure that was documented in v2.3 was incorrect; the code always used the flat structure now documented in v2.4.

## Settings Structure Clarification

### What the Admin UI Actually Uses (Correct - Now Documented in v2.4)

```json
{
  "sms_receiver_number": "+919000000000",
  "allowed_prefix": "ONBOARD:",
  "hash_length": 8,
  "ttl_hash_seconds": 900,
  "sync_interval": 1.0,
  "log_interval": 120,
  "count_threshold": 5,
  "allowed_countries": ["+91", "+44"],
  "sync_url": "https://your-backend.com/api/validated-users",
  "recovery_url": "https://your-backend.com/api/recover",
  "sms_receive_api_key": null,
  "checks": {
    "header_hash_check_enabled": true,
    "foreign_number_check_enabled": true,
    "count_check_enabled": true,
    "blacklist_check_enabled": true
  },
  "secrets": {
    "hmac_secret": "CHANGE_ME_IN_PRODUCTION",
    "hash_key": "CHANGE_ME_IN_PRODUCTION"
  }
}
```

### What v2.3 Documentation Incorrectly Showed (Wrong)

```json
{
  "version": "2.3.0",
  "settings": {
    "rate_limits": { ... },
    "validation_checks": { ... },
    "monitoring_ports": { ... }
  }
}
```

This nested structure was never used by the code.

## Complete Settings Reference

All settings are now properly documented in the v2.4 tech spec with:

### Core Settings (1-6)
- `sms_receiver_number` - Phone number for receiving SMS
- `allowed_prefix` - Required SMS message prefix (e.g., "ONBOARD:")
- `hash_length` - Verification code length
- `ttl_hash_seconds` - Code validity duration
- `count_threshold` - Rate limit per phone number
- `allowed_countries` - Permitted country codes

### Backend Integration (7-9)
- `sync_url` - Endpoint for verified user data
- `recovery_url` - Endpoint for retry operations
- `sms_receive_api_key` - API key for webhook security

### Worker Intervals (10-11)
- `sync_interval` - Hot path frequency (default: 1.0 second)
- `log_interval` - Cold path frequency (default: 120 seconds)

### Validation Checks (12)
- `checks.header_hash_check_enabled` - Message format validation
- `checks.foreign_number_check_enabled` - Country code validation
- `checks.count_check_enabled` - Rate limit enforcement
- `checks.blacklist_check_enabled` - Blacklist checking

### Secrets (13)
- `secrets.hmac_secret` - Request signing key
- `secrets.hash_key` - Hash generation key

## Action Required

### For Existing Deployments

**No action required.** Your existing settings in the database are correct and match the v2.4 documentation. The code has always used this structure.

### For New Deployments

Use the v2.4 documentation and `sms_settings.json` template as reference when configuring your system.

### For Documentation Readers

Refer to the v2.4 documents for accurate settings information:
- [SMS_Bridge_tech_spec_v2.4.md](SMS_Bridge_tech_spec_v2.4.md) - Complete settings reference
- [SMS_Bridge_tech_snippets_v2.4.md](SMS_Bridge_tech_snippets_v2.4.md) - Code examples
- [SMS_RECEIVE_API_KEY_SETUP.md](SMS_RECEIVE_API_KEY_SETUP.md) - API key configuration

## Migration Path

Since this is a documentation-only update:

1. **No database migration needed**
2. **No code deployment needed**
3. **No settings changes needed**
4. **No service restart needed**

Simply use the v2.4 documentation going forward.

## Files Changed

```
Modified:
- docs/core/SMS_Bridge_tech_spec_v2.3.md → SMS_Bridge_tech_spec_v2.4.md
- docs/core/SMS_Bridge_tech_snippets_v2.3.md → SMS_Bridge_tech_snippets_v2.4.md
- docs/core/SMS_RECEIVE_API_KEY_SETUP.md
- core/config/sms_settings.json

New:
- docs/core/UPGRADE_v2.3_to_v2.4.md (this file)

Unchanged:
- All Python code (core/*.py)
- All database schemas (init/*.sql)
- All configuration files (docker-compose.yml, .env)
```

## Verification

To verify your deployment is using the correct settings structure:

1. **Check Admin UI:** Navigate to Settings History → View active settings
2. **Check Redis:** `redis-cli GET config:current | jq`
3. **Check Database:** `SELECT payload FROM settings_history WHERE is_active = true;`

All three should show the flat structure documented in v2.4.

---

**Questions?** Refer to [SMS_Bridge_tech_spec_v2.4.md](SMS_Bridge_tech_spec_v2.4.md) Section 4 for complete settings documentation.
