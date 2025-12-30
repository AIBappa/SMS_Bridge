# Integration Documentation

## Overview

This document outlines the integration between the SMS Bridge system and external services. The SMS Bridge handles **two distinct types of inbound requests**:

1. **CF Hono Backend** → SMS Bridge (GET requests for hash generation and health monitoring)
2. **Local Mobile** → SMS Bridge (POST requests with SMS webhook data)

**Important**: This document is not part of the core SMS Bridge functionality and should be treated as external integration documentation.

## Architecture

The SMS Bridge system handles two distinct types of inbound requests:

```
┌─────────────────┐    GET (Hash/Health)    ┌─────────────────┐
│   CF Hono       │ ──────────────────────► │   SMS Bridge    │
│   Backend       │                         │  (K3s/Local)    │
└─────────────────┘                         └─────────────────┘
         ▲                                           │
         │ POST (SMS Data)                           │
         └───────────────────────────────────────────┘
                    ┌─────────────────┐
                    │   Local Mobile  │
                    │  (WiFi Network) │
                    └─────────────────┘
```

**Input Type 1**: CF Hono Backend → SMS Bridge (GET requests for hash generation and health monitoring)
**Input Type 2**: Local Mobile → SMS Bridge (POST requests with SMS webhook data)

## Configuration

### SMS Bridge Configuration (vault.yml)

The integration requires the following configuration in your Ansible Vault:

```yaml
cf_backend_url: "https://your-cf-worker.your-domain.workers.dev/sms-webhook"
cf_api_key: "your-secure-api-key-here"
```

### Environment Variables (CF Backend)

Your Cloudflare Worker/Hono backend should have these environment variables:

```bash
CF_API_KEY=your-secure-api-key-here
ALLOWED_IPS=your.static.ip.here,another.ip.range
RATE_LIMIT_WINDOW=60000
RATE_LIMIT_MAX_REQUESTS=100
```

## Inbound Communication Protocols

### Type 1: CF Hono Backend → SMS Bridge (GET Requests)

#### 1.1 Hash Generation Endpoint
**Purpose**: CF backend requests a hash for onboarding a new mobile number

- **Method**: GET
- **Endpoint**: `/onboard/register/{mobile_number}`
- **Authentication**: Bearer token required
 - **Example**: `GET /onboard/register/+9199XXYYZZAA`

**Request Headers**:
```
Authorization: Bearer {cf_api_key}
Content-Type: application/json
```

**Response Format (Success)**:
```json
{
  "status": "success",
  "mobile_number": "+9199XXYYZZAA",
  "hash": "a06f0b785d6613cadec3ed12c27e07615427bf1b79d091e9e8da22070ad14f7d",
  "expires_at": "2025-09-19T00:34:23Z",
  "generated_at": "2025-09-18T00:34:23Z"
}
```

**Response Format (Error)**:
```json
{
  "status": "error",
  "error": "Mobile number already onboarded",
  "code": "DUPLICATE_MOBILE"
}
```

#### 1.2 Health Check Endpoint
**Purpose**: CF backend monitors the health status of the SMS Bridge service

- **Method**: GET
- **Endpoint**: `/health`
- **Authentication**: Bearer token required
- **Example**: `GET /health`

**Response Format**:
```json
{
  "status": "healthy",
  "service": "sms-bridge",
  "version": "1.0.0",
  "timestamp": "2025-09-18T00:34:23Z",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "batch_processor": "running"
  }
}
```

### Type 2: Local Mobile → SMS Bridge (POST Requests)

#### 2.1 SMS Webhook Endpoint
**Purpose**: Local mobile device forwards received SMS messages to the bridge for processing

- **Method**: POST
- **Endpoint**: `/sms/receive`
- **Authentication**: Bearer token required (same as CF calls)
- **Content-Type**: `application/json` or `application/x-www-form-urlencoded`

**JSON Payload Format**:
```json
{
  "mobile_number": "+9199XXYYZZAA",
  "message": "ONBOARD:a06f0b785d6613cadec3ed12c27e07615427bf1b79d091e9e8da22070ad14f7d",
  "received_at": "2025-09-18T00:34:23Z",
  "sender": "+9199XXYYZZAA"
}
```

**Form-Encoded Format** (alternative):
```
mobile_number=+9199XXYYZZAA&message=ONBOARD:a06f0b785d6613cadec3ed12c27e07615427bf1b79d091e9e8da22070ad14f7d&received_at=2025-09-18T00:34:23Z&sender=+9199XXYYZZAA
```

**Response Format (Success)**:
```json
{
  "status": "received",
  "message_id": "uuid-generated-here",
  "queued_for_processing": true
}
```

**Response Format (Error)**:
```json
{
  "status": "error",
  "error": "Invalid mobile number format",
  "code": "VALIDATION_ERROR"
}
```

## Outbound Communication: SMS Bridge → CF Backend (POST)

When SMS messages from local mobiles pass all validation checks, they are forwarded to the external CF backend:

#### Endpoint
- **URL**: Configurable via `cf_backend_url` in vault.yml
- **Method**: POST
- **Content-Type**: `application/json`
- **Authentication**: Bearer token (`cf_api_key`)

#### JSON Payload Structure

```json
{
  "mobile_number": "+9199XXYYZZAA",
  "country_code": "91",
  "local_mobile": "99XXYYZZAA",
  "message": "ONBOARD:abc123def456...",
  "received_timestamp": "2024-01-15T10:30:45.123456",
  "validation_results": {
    "foreign_number_check": 1,
    "blacklist_check": 1,
    "duplicate_check": 1,
    "header_hash_check": 1,
    "mobile_check": 1,
    "time_window_check": 1
  },
  "batch_id": "uuid-string-here",
  "processed_at": "2024-01-15T10:30:45.123456"
}
```

#### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `mobile_number` | string | Full international mobile number with country code |
| `country_code` | string | Extracted country code (e.g., "91" for India) |
| `local_mobile` | string | Mobile number without country code |
| `message` | string | Original SMS message content |
| `received_timestamp` | string | ISO 8601 timestamp when SMS was received |
| `validation_results` | object | Results from each validation check (1=pass, 2=fail, 3=skipped) |
| `batch_id` | string | UUID of the processing batch |
| `processed_at` | string | ISO 8601 timestamp when validation completed |

#### Alternative Form-Encoded Format

For compatibility with systems that prefer form data:

```
mobile_number=+9199XXYYZZAA&country_code=91&local_mobile=99XXYYZZAA&message=ONBOARD:abc123...&received_timestamp=2024-01-15T10:30:45.123456&validation_results={"foreign_number_check":1,"blacklist_check":1,"duplicate_check":1,"header_hash_check":1,"mobile_check":1,"time_window_check":1}&batch_id=uuid-string&processed_at=2024-01-15T10:30:45.123456
```

## Security Implementation

### CF Hono Backend Security
- **Hash Generation**: Requires valid Bearer token, rate limited to prevent abuse
- **Health Checks**: Same authentication, higher rate limits allowed for monitoring
- **IP Whitelisting**: CF backend IPs should be whitelisted
- **Request Validation**: Strict validation of mobile number format

### Local Mobile Security
- **Webhook Authentication**: Same Bearer token as CF backend
- **Network Security**: Only accessible on local WiFi network
- **Input Sanitization**: All SMS content validated and sanitized
- **Rate Limiting**: Per-device rate limiting to prevent spam

#### 1. Bearer Token Authentication

```javascript
// Hono/CF Worker implementation
app.use('/sms-webhook', async (c, next) => {
  const authHeader = c.req.header('Authorization');
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return c.json({ error: 'Unauthorized' }, 401);
  }

  const token = authHeader.substring(7);
  if (token !== c.env.CF_API_KEY) {
    return c.json({ error: 'Invalid token' }, 401);
  }

  await next();
});
```

#### 2. IP Whitelisting

```javascript
const ALLOWED_IPS = c.env.ALLOWED_IPS.split(',');

app.use('/sms-webhook', async (c, next) => {
  const clientIP = c.req.header('CF-Connecting-IP') ||
                   c.req.header('X-Forwarded-For');

  if (!ALLOWED_IPS.includes(clientIP)) {
    return c.json({ error: 'Access denied' }, 403);
  }

  await next();
});
```

#### 3. Rate Limiting

```javascript
// Simple in-memory rate limiting (use Redis for production)
const rateLimit = new Map();

app.use('/sms-webhook', async (c, next) => {
  const clientIP = c.req.header('CF-Connecting-IP');
  const now = Date.now();
  const window = parseInt(c.env.RATE_LIMIT_WINDOW) || 60000;
  const limit = parseInt(c.env.RATE_LIMIT_MAX_REQUESTS) || 100;

  if (!rateLimit.has(clientIP)) {
    rateLimit.set(clientIP, []);
  }

  const requests = rateLimit.get(clientIP);
  requests.push(now);

  // Remove old requests
  while (requests.length > 0 && requests[0] < now - window) {
    requests.shift();
  }

  if (requests.length > limit) {
    return c.json({ error: 'Rate limit exceeded' }, 429);
  }

  await next();
});
```

#### 4. Input Validation

```javascript
const validateSMSPayload = (data) => {
  const required = ['mobile_number', 'country_code', 'validation_results'];
  const hasRequired = required.every(field => data.hasOwnProperty(field));

  if (!hasRequired) return false;

  // Validate mobile number format
  const mobileRegex = /^\+\d{10,15}$/;
  if (!mobileRegex.test(data.mobile_number)) return false;

  // Validate country code
  if (!/^\d{1,4}$/.test(data.country_code)) return false;

  return true;
};

app.post('/sms-webhook', async (c) => {
  const payload = await c.req.json();

  if (!validateSMSPayload(payload)) {
    return c.json({ error: 'Invalid payload structure' }, 400);
  }

  // Process validated data...
});
```

### Cloudflare Security Features

#### WAF Rules
Create custom WAF rules in Cloudflare Dashboard:

1. **Block non-POST requests** to `/sms-webhook`
2. **Block requests without Authorization header**
3. **Block requests from non-whitelisted IPs**
4. **Block malformed JSON payloads**

#### Bot Management
- Enable "Bot Fight Mode"
- Configure "Bot Management" rules
- Use "Super Bot Fight Mode" for enhanced protection

#### DDoS Protection
- Automatically enabled with Cloudflare
- Configure rate limiting rules
- Set up custom rules for your endpoint

## Setup Instructions

### 1. Configure SMS Bridge

Update your `vault.yml`:

```yaml
cf_backend_url: "https://your-worker.your-domain.workers.dev/sms-webhook"
cf_api_key: "generate-a-secure-random-key-here"
```

### 2. Deploy CF Worker

```javascript
// worker.js
import { Hono } from 'hono'

const app = new Hono()

// Security middleware
app.use('/sms-webhook', async (c, next) => {
  // Implement authentication, IP whitelisting, rate limiting
  await next();
});

app.post('/sms-webhook', async (c) => {
  const payload = await c.req.json();

  // Process SMS data
  console.log('Received validated SMS:', payload);

  // Store in your database, trigger workflows, etc.

  return c.json({ status: 'success', received: true });
});

export default app
```

### 3. Configure Environment Variables

In Cloudflare Dashboard:
- Go to Workers → Your Worker → Settings → Variables
- Add `CF_API_KEY`, `ALLOWED_IPS`, etc.

### 4. Set Up DNS and Routing

1. Create a subdomain (e.g., `api.your-domain.com`)
2. Point it to your Cloudflare Worker
3. Configure SSL/TLS settings

## Testing

### Test CF Hono Backend Calls

#### Hash Generation Test
```bash
# Test hash generation for new mobile
curl -X GET "https://your-tunnel-domain.com/onboard/register/+9199XXYYZZAA" \
  -H "Authorization: Bearer $CF_API_KEY" \
  -H "Content-Type: application/json"
```

#### Health Check Test
```bash
# Test health endpoint
curl -X GET "https://your-tunnel-domain.com/health" \
  -H "Authorization: Bearer $CF_API_KEY"
```

### Test Local Mobile Webhook

#### SMS Webhook Test
```bash
# Test SMS webhook from local mobile
curl -X POST "http://localhost:8080/sms/receive" \
  -H "Authorization: Bearer $CF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
  "mobile_number": "+9199XXYYZZAA",
    "message": "ONBOARD:test-hash-here",
    "received_at": "2025-09-18T00:34:23Z"
  }'
```

#### Form-Encoded SMS Test
```bash
# Test with form-encoded data
curl -X POST "http://localhost:8080/sms/receive" \
  -H "Authorization: Bearer $CF_API_KEY" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "mobile_number=+9199XXYYZZAA&message=ONBOARD:test-hash&received_at=2025-09-18T00:34:23Z"
```

### Test Outbound Communication

#### Test Authentication
```bash
#!/bin/bash

# Test without token (should fail)
curl -X POST https://your-worker.your-domain.workers.dev/sms-webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'

# Test with wrong token (should fail)
curl -X POST https://your-worker.your-domain.workers.dev/sms-webhook \
  -H "Authorization: Bearer wrong-token" \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'

# Test with correct token (should succeed)
curl -X POST https://your-worker.your-domain.workers.dev/sms-webhook \
  -H "Authorization: Bearer $CF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mobile_number": "+9199XXYYZZAA", "country_code": "91", "validation_results": {"all": "passed"}}'
```

#### Test Rate Limiting
```bash
#!/bin/bash

# Send multiple requests quickly
for i in {1..150}; do
  curl -X POST https://your-worker.your-domain.workers.dev/sms-webhook \
    -H "Authorization: Bearer $CF_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"test": "rate-limit-test"}' &
done
```

## Monitoring & Observability

### CF Worker Logs
```javascript
// Add logging to your worker
app.post('/sms-webhook', async (c) => {
  console.log(`[${new Date().toISOString()}] SMS received from ${c.req.header('CF-Connecting-IP')}`);

  // Process request...

  console.log(`[${new Date().toISOString()}] SMS processed successfully`);
});
```

### Cloudflare Analytics
- Monitor request volume and success rates
- Set up alerts for failed requests
- Track geographic distribution of requests

### Error Handling
```javascript
app.onError((err, c) => {
  console.error(`[${new Date().toISOString()}] Error: ${err.message}`);
  return c.json({ error: 'Internal server error' }, 500);
});
```

## Troubleshooting

### CF Hono Backend Issues

1. **401 Unauthorized on Hash Request**
   - Verify Bearer token format: `Bearer {token}`
   - Check if token matches `cf_api_key` in [`vault.yml`](vault.yml )
   - Ensure token is URL-safe (no special characters)

2. **404 Not Found on /onboard/register**
   - Verify tunnel is properly configured and running
   - Check DNS resolution for tunnel hostname
   - Confirm ingress rules in tunnel configuration

3. **429 Rate Limited**
   - Hash generation is rate limited to prevent abuse
   - Wait before retrying or increase rate limit settings

4. **500 Internal Server Error on Health Check**
   - Check SMS Bridge service status
   - Verify database and Redis connectivity
   - Review application logs for errors

### Local Mobile Issues

1. **Connection Refused**
   - Ensure mobile is on same WiFi network
   - Verify SMS Bridge service is running on port 8080
   - Check firewall settings

2. **400 Bad Request**
   - Validate JSON payload structure
   - Check mobile number format (+country code)
   - Verify message content format

3. **Processing Delays**
   - Check batch processor status
   - Verify Redis connectivity
   - Monitor system resources

4. **Authentication Failed**
   - Ensure Bearer token matches `cf_api_key`
   - Check token format and encoding
   - Verify token hasn't expired

### Outbound Communication Issues

1. **Connection Timeout to CF Backend**
   - Verify `cf_backend_url` in [`vault.yml`](vault.yml )
   - Check network connectivity
   - Review DNS resolution

2. **403 Forbidden from CF Backend**
   - Verify IP whitelisting on CF side
   - Check `ALLOWED_IPS` configuration
   - Confirm client IP detection

3. **429 Rate Limited by CF Backend**
   - Review rate limiting configuration
   - Check `RATE_LIMIT_WINDOW` and `RATE_LIMIT_MAX_REQUESTS`
   - Consider increasing limits if needed

### Debug Mode
```javascript
// Enable debug logging for CF backend
app.use('/sms-webhook', async (c, next) => {
  if (c.env.DEBUG === 'true') {
    console.log('Request details:', {
      method: c.req.method,
      url: c.req.url,
      headers: Object.fromEntries(c.req.raw.headers),
      ip: c.req.header('CF-Connecting-IP')
    });
  }
  await next();
});

// Enable debug logging for SMS Bridge
// Add to sms_server.py startup
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Best Practices

### Security
- Rotate API keys regularly
- Use strong, random keys (at least 32 characters)
- Monitor access logs for suspicious activity
- Keep IP whitelists current

### Performance
- Implement proper error handling
- Use async/await for I/O operations
- Cache frequently accessed data
- Monitor memory usage

### Reliability
- Implement retry logic in SMS Bridge
- Handle network timeouts gracefully
- Log all errors with context
- Set up monitoring alerts

## Deployment Checklist

- [ ] Configure `vault.yml` with correct URLs and keys
- [ ] Deploy CF Worker with security middleware
- [ ] Set up environment variables
- [ ] Configure DNS and SSL
- [ ] Test authentication and validation
- [ ] Enable Cloudflare security features
- [ ] Set up monitoring and alerts
- [ ] Test failover scenarios
- [ ] Document emergency procedures

---

**Note**: This document is maintained separately from the core SMS Bridge functionality and should be updated whenever the integration requirements change.

## OpenAPI Specification (machine-readable)

An OpenAPI 3.0 specification is included to remove ambiguity and enable automated tooling (codegen, validators, or AI coders).

- File: `docs/integration_openapi.yaml`
- Purpose: Canonical schema for endpoints, request/response bodies, headers, status codes, and examples.

### Canonical Conventions (followed by the OpenAPI file)
- Timestamps: All timestamps MUST use ISO 8601 UTC with trailing `Z`, e.g. `2025-09-19T12:00:00Z`.
 - Mobile numbers: E.164 format (e.g. `+9199XXYYZZAA`).
- Authentication: Bearer token in `Authorization: Bearer {token}` header. The token is stored as `CF_API_KEY` in environment or vault.
- Error responses: Use the `ErrorResponse` schema (fields: `code`, `message`, optional `details`, `timestamp`).
- Rate limiting: Default is `RATE_LIMIT_MAX_REQUESTS` per `RATE_LIMIT_WINDOW` ms; when exceeded return `429` with `Retry-After` header.

Refer to `docs/integration_openapi.yaml` for exact schemas and examples.