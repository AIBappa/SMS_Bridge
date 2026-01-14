# SMS Receive API Key Setup Guide

## Overview

The `/sms/receive` endpoint now supports query parameter-based API key authentication. This provides a simple way to secure the webhook URL used by mobile SMS forwarding apps.

## Configuration

### 1. Set API Key in Admin UI

1. Navigate to Admin UI → **Settings History**
2. Edit the active settings payload
3. Add the `sms_receive_api_key` field:

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
  "sync_url": "https://your-backend.com/api/validated-sms",
  "recovery_url": "https://your-backend.com/api/recovery",
  "sms_receive_api_key": "your-secure-api-key-123",
  "checks": {
    "header_hash_check_enabled": true,
    "foreign_number_check_enabled": true,
    "count_check_enabled": true,
    "blacklist_check_enabled": true
  },
  "secrets": {
    "hmac_secret": "your-hmac-secret",
    "hash_key": "your-hash-key"
  }
}
```

4. Save the settings - changes take effect **immediately** via Redis cache

### 2. Update Mobile Webhook URL

Configure your SMS forwarding app (e.g., SMS Gateway, Tasker) with the new URL:

```
https://your-tunnel-domain.com/sms/receive?apiKey=your-secure-api-key-123
```

Or for local testing:

```
http://localhost:8080/sms/receive?apiKey=your-secure-api-key-123
```

## Usage Examples

### cURL Example

```bash
curl -X POST "https://your-tunnel.ngrok.io/sms/receive?apiKey=your-secure-api-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "mobile_number": "+9199XXYYZZAA",
    "message": "ONBOARD:A3B7K2M9",
    "received_at": "2026-01-15T12:00:00Z"
  }'
```

### Expected Response

**Success (202 Accepted):**
```json
{
  "status": "received",
  "message_id": "550e8400-e29b-41d4-a716-446655440000",
  "queued_for_processing": true
}
```

**Missing API Key (401 Unauthorized):**
```json
{
  "detail": "Missing apiKey query parameter"
}
```

**Invalid API Key (401 Unauthorized):**
```json
{
  "detail": "Invalid API key"
}
```

## Security Features

### Backward Compatibility
- If `sms_receive_api_key` is **not configured** in settings, the endpoint allows access without validation
- This ensures existing deployments continue to work without requiring immediate configuration

### Enforcement
- Once `sms_receive_api_key` is set in settings, the API key becomes **mandatory**
- All requests without the correct `apiKey` query parameter will be rejected with `401 Unauthorized`

### No Restart Required
- API key changes via Admin UI take effect immediately
- The key is cached in Redis (`config:current`)
- No server restart or downtime needed

## API Key Rotation

To rotate the API key:

1. Generate a new secure random key (recommended: 32+ characters)
2. Update `sms_receive_api_key` in Admin UI
3. Update the webhook URL in your mobile SMS forwarding app
4. Changes take effect instantly

### Generating Secure Keys

```python
# Python example
import secrets
api_key = secrets.token_urlsafe(32)
print(f"New API Key: {api_key}")
```

```bash
# Linux/macOS command line
openssl rand -base64 32
```

## Best Practices

1. **Use Strong Keys**: Generate random keys with at least 32 characters
2. **Rotate Regularly**: Change the API key periodically (e.g., every 90 days)
3. **HTTPS Only**: Always use HTTPS for production webhook URLs
4. **Monitor Access**: Check logs for unauthorized access attempts
5. **Keep Private**: Never commit API keys to git repositories

## OpenAPI Specification

The endpoint is documented in `integration_openapi.yaml`:

```yaml
/sms/receive:
  post:
    summary: Receive webhook from local mobile device for incoming SMS
    security:
      - ApiKeyQuery: []
    parameters:
      - name: apiKey
        in: query
        required: false
        schema:
          type: string
        description: API key for authentication (required if configured in settings)
```

## Troubleshooting

### Mobile App Not Sending Requests

1. Check the webhook URL includes the `?apiKey=` parameter
2. Verify the mobile device has internet connectivity
3. Check SMS forwarding app logs for errors

### 401 Unauthorized Errors

1. Verify the API key in the URL matches the one in Admin UI settings
2. Check for typos or extra spaces in the API key
3. Ensure the settings have been saved and are marked as active

### Service Not Configured (503 Error)

1. Check Redis connection is healthy
2. Verify active settings exist in the database
3. Restart the service if needed to reload settings

## Implementation Details

- **Schema**: `SettingsPayload.sms_receive_api_key` (Optional[str])
- **Validation**: `verify_sms_api_key()` dependency in `sms_server_v2.py`
- **Storage**: Redis `config:current` key (cached from Postgres)
- **Admin UI**: Managed via `SettingsHistoryAdmin`
