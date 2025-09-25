# SMS Bridge Integration Setup Prompt

## 🚨 **URGENT: Fix 403 Forbidden Errors**

Your SMS Bridge is receiving requests from Cloudflare Workers but rejecting them with 403 Forbidden (error code 1003). This is preventing the mobile onboarding integration from working.

## 📋 **Current Status**

### ✅ **What's Working:**
- Cloudflare tunnel is active and connected
- CF Workers can reach your SMS Bridge at `localhost:3001`
- Database tables are created and ready
- API endpoints are configured in CF Hono

### ❌ **What's Broken:**
- SMS Bridge returns 403 Forbidden for all requests
- No hash generation for mobile verification
- Integration flow is blocked

## 🔧 **What You Need to Fix**

### **1. Accept Cloudflare Worker Requests (IP Whitelisting)**

**Problem:** Getting `403 Forbidden` with `error code: 1003`

**Solution:** Configure your SMS Bridge to accept requests from Cloudflare Worker IP ranges.

**Cloudflare Worker IP Ranges to Whitelist:**
```
173.245.48.0/20
103.21.244.0/22
103.22.200.0/22
103.31.4.0/22
141.101.64.0/18
108.162.192.0/18
190.93.240.0/20
188.114.96.0/20
197.234.240.0/22
198.41.128.0/17
162.158.0.0/15
104.16.0.0/13
104.24.0.0/14
172.64.0.0/13
131.0.252.0/22
```

**Alternative:** Disable IP restrictions for the `/onboard/register` endpoint.

### **2. Accept API Key Authentication**

**Problem:** Requests include `Authorization: Bearer dev-api-key-12345` but are rejected.

**Solution:** Validate the API key `dev-api-key-12345` and allow requests with this header.

### **3. Return Proper JSON Response Format**

**Problem:** Returning 403 instead of hash data.

**Solution:** Return proper JSON response for mobile verification requests.

## 📡 **Required API Endpoints**

### **GET /onboard/register/{mobile_number}**

**Request:**
```
GET /onboard/register/+919699511296
Headers:
  Authorization: Bearer dev-api-key-12345
  Content-Type: application/json
  User-Agent: GeoPrasidh-CF-Backend/1.0
```

**Response (Success):**
```json
{
  "mobile_number": "+919699511296",
  "hash": "abc123xyz789",
  "expires_at": "2025-09-25T06:00:00Z",
  "status": "pending"
}
```

**Response (Error):**
```json
{
  "error": "Invalid mobile format",
  "message": "Mobile number must be in E.164 format",
  "code": "VALIDATION_ERROR"
}
```

### **POST /webhook/validated**

**Request:**
```json
{
  "mobile_number": "+919699511296",
  "message": "ONBOARD:abc123xyz789",
  "timestamp": "2025-09-25T05:30:00Z",
  "validation_results": {
    "message_validity": 1,
    "sender_verification": 1,
    "network_quality": 1
  }
}
```

**Response:**
```json
{
  "status": "received",
  "mobile_number": "+919699511296",
  "processed": true,
  "timestamp": "2025-09-25T05:30:00Z"
}
```

## 🧪 **Testing Instructions**

### **Test Hash Generation:**
```bash
# Should return hash instead of 403
curl -X GET "http://localhost:3001/onboard/register/+919699511296" \
  -H "Authorization: Bearer dev-api-key-12345" \
  -H "Content-Type: application/json"
```

### **Test Webhook:**
```bash
# Test webhook endpoint
curl -X POST "http://localhost:3001/webhook/validated" \
  -H "Content-Type: application/json" \
  -d '{
    "mobile_number": "+919699511296",
    "message": "ONBOARD:abc123xyz789",
    "timestamp": "2025-09-25T05:30:00Z",
    "validation_results": {"message_validity":1,"sender_verification":1,"network_quality":1}
  }'
```

## 🔄 **Integration Flow**

```
1. Mobile App → CF Hono → SMS Bridge (via tunnel)
   GET /onboard/register/+919699511296

2. SMS Bridge → Returns hash → CF Hono → Mobile App

3. SMS Bridge → Validates SMS → Sends webhook → CF Hono
   POST /webhook/validated

4. CF Hono → Updates database → Returns success
```

## 📊 **Expected Behavior**

### **Before Fix:**
```json
{
  "response_status": 403,
  "response_body": "error code: 1003"
}
```

### **After Fix:**
```json
{
  "mobile_number": "+919699511296",
  "hash": "abc123xyz789",
  "expires_at": "2025-09-25T06:00:00Z",
  "status": "pending"
}
```

## 🚀 **Quick Fix Checklist**

- [ ] Whitelist Cloudflare Worker IPs or disable IP restrictions
- [ ] Accept API key `dev-api-key-12345` in Authorization header
- [ ] Return JSON hash response instead of 403
- [ ] Test with curl commands above
- [ ] Verify webhook endpoint accepts POST requests

## 📞 **Integration Details**

- **Tunnel Name:** GeoPrasidh_Onboarding_SMS
- **Tunnel ID:** afd4ca4a-8770-48bd-a0ea-a23e08ad872a
- **SMS Bridge Port:** 3001
- **API Key:** dev-api-key-12345
- **CF Worker URL:** https://geoprasidh-backend.jadhavshantanu.workers.dev

## 🎯 **Priority**

**Fix the 403 errors first** - everything else is ready and working. Once SMS Bridge accepts requests and returns hashes, the full mobile onboarding integration will work seamlessly.

---

**Copy this entire document to your SMS Bridge machine and give it to your VSCode Copilot instance!**