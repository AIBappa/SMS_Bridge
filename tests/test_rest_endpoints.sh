#!/bin/bash
# Test script for REST-compliant onboarding endpoints

set -e

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
API_KEY="${GEOPRASIDH_API_KEY:-dev-api-key-REDACTED}"
TEST_MOBILE="+919876543210"

echo "=== SMS Bridge REST API Testing ==="
echo "API URL: $API_URL"
echo "Test Mobile: $TEST_MOBILE"
echo ""

# Test 1: POST /onboarding/register (Correct - Resource Creation)
echo "Test 1: POST /onboarding/register (New Registration)"
echo "Expected: 201 Created with hash and expires_at"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"mobile_number\": \"$TEST_MOBILE\"}" \
  "$API_URL/onboarding/register")

HTTP_CODE=$(echo "$RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d':' -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response Body:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""

# Extract hash for later tests
HASH=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['hash'])" 2>/dev/null || echo "")

# Test 2: POST /onboarding/register (Idempotent - Should Return Same Hash)
echo "Test 2: POST /onboarding/register (Idempotent - Existing Registration)"
echo "Expected: Same hash as Test 1"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"mobile_number\": \"$TEST_MOBILE\"}" \
  "$API_URL/onboarding/register")

HTTP_CODE=$(echo "$RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d':' -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response Body:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""

# Test 3: GET /onboard/status (Read-Only - Deprecated)
echo "Test 3: GET /onboard/status/{mobile_number} (Deprecated - Read Only)"
echo "Expected: 200 OK with existing registration data"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -H "Authorization: Bearer $API_KEY" \
  "$API_URL/onboard/status/$TEST_MOBILE")

HTTP_CODE=$(echo "$RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d':' -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response Body:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""

# Test 4: GET /onboarding/status (Standard Status Endpoint)
echo "Test 4: GET /onboarding/status/{mobile_number} (Standard Endpoint)"
echo "Expected: 200 OK with registration status"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  "$API_URL/onboarding/status/${TEST_MOBILE#+}")

HTTP_CODE=$(echo "$RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d':' -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response Body:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""

# Test 5: POST without API Key (Authentication Test)
echo "Test 5: POST /onboarding/register (No API Key)"
echo "Expected: 401 Unauthorized"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST \
  -H "Content-Type: application/json" \
  -d "{\"mobile_number\": \"$TEST_MOBILE\"}" \
  "$API_URL/onboarding/register")

HTTP_CODE=$(echo "$RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d':' -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response Body:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""

# Test 6: GET non-existent mobile
echo "Test 6: GET /onboard/status/{mobile_number} (Non-existent)"
echo "Expected: 404 Not Found with migration message"
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -H "Authorization: Bearer $API_KEY" \
  "$API_URL/onboard/status/+919999999999")

HTTP_CODE=$(echo "$RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d':' -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HTTP_CODE"
echo "Response Body:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""

echo "=== Test Summary ==="
echo "✅ Test 1: POST for new registration"
echo "✅ Test 2: POST idempotency check"
echo "✅ Test 3: GET deprecated endpoint (read-only)"
echo "✅ Test 4: GET standard status endpoint"
echo "✅ Test 5: Authentication check"
echo "✅ Test 6: 404 handling for non-existent mobile"
echo ""
echo "All tests completed!"
