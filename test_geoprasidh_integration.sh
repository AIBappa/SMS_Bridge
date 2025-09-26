#!/bin/bash

# Test script for GeoPrasidh integration endpoints
echo "Testing SMS Bridge endpoints for GeoPrasidh integration..."

BASE_URL="http://localhost:3001"
API_KEY="dev-api-key-REDACTED"
MOBILE_NUMBER="+9199XXYYZZ"

echo
echo "1. Testing health endpoint..."
curl -s -X GET "$BASE_URL/health" | jq .

echo
echo "2. Testing GeoPrasidh onboard endpoint..."
curl -s -X GET "$BASE_URL/onboard/register/$MOBILE_NUMBER" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" | jq .

echo
echo "3. Testing webhook endpoint..."
curl -s -X POST "$BASE_URL/webhook/validated" \
  -H "Content-Type: application/json" \
  -d '{
    "mobile_number": "'$MOBILE_NUMBER'",
    "message": "ONBOARD:abc123xyz789",
    "timestamp": "2025-09-25T05:30:00Z",
    "validation_results": {
      "message_validity": 1,
      "sender_verification": 1,
      "network_quality": 1
    }
  }' | jq .

echo
echo "Test complete!"