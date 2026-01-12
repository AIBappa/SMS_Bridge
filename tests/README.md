# SMS Bridge Test Application

This is a comprehensive test application for the SMS Bridge system that allows you to send individual SMS messages or upload Excel/CSV files for batch testing.

## Features

- 📱 **Single SMS Testing**: Send individual SMS messages with a user-friendly web interface
- 📂 **Batch File Upload**: Upload Excel (.xlsx, .xls) or CSV files containing multiple SMS messages
- 🔧 **API Endpoint**: Programmatic SMS sending via REST API
- 📊 **Results Display**: View detailed results of batch processing
- 🏥 **Health Check**: Built-in health monitoring endpoint

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Navigate to the tests directory
cd /home/<user>/Documents/Software/SMS_Laptop_Setup/sms_bridge/tests

# Start the test application
docker-compose up -d

# View logs
docker-compose logs -f
```

The application will be available at: `http://localhost:3002`

### Manual Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variable (optional - defaults to K3s NodePort)
export SMS_BRIDGE_URL=http://localhost:30080

# Run the application
python test_app.py
```

## Usage

### 1. Web Interface

Open `http://localhost:3002` in your browser to access the web interface.

#### Single SMS Testing
- Fill in the sender number, SMS message, and timestamp
- Click "Send SMS" to send a single message to the SMS Bridge

#### Batch File Upload
- Upload an Excel (.xlsx, .xls) or CSV file with the required format
- View processing results with success/failure counts

### 2. File Format Requirements

Your Excel/CSV file must contain these columns:
- `sender_number`: Phone number (e.g., +1234567890)
- `sms_message`: SMS content (must contain mobile number for validation)
- `received_timestamp`: ISO timestamp (e.g., 2025-09-07T12:00:00Z)

#### Sample Data

A sample CSV file (`sample_sms_data.csv`) is included with test data that matches the validation requirements from best_practices.md lines 201-212.

### 3. API Usage

Send SMS programmatically:

```bash
curl -X POST http://localhost:3002/api/send_sms \
  -H "Content-Type: application/json" \
  -d '{
    "sender_number": "+1234567890",
    "sms_message": "Test message with mobile 9876543210",
    "received_timestamp": "2025-09-07T12:00:00Z"
  }'
```

### 4. Health Check

```bash
curl http://localhost:3002/health
```

## Configuration

### Environment Variables

- `SMS_BRIDGE_URL`: URL of the SMS Bridge server (default: http://localhost:30080 for K3s deployment)

### Docker Configuration

The Docker setup automatically:
- Connects to the SMS Bridge on the host system
- Mounts upload directory for file persistence
- Includes sample data for testing

## Testing Scenarios

### Test Cases Based on Best Practices (Lines 201-212)

The application is designed to test the SMS Bridge validation workflow:

1. **Valid SMS Messages**: Contains mobile numbers in the message content
2. **Invalid Messages**: Missing mobile numbers (should fail validation)
3. **Duplicate Testing**: Send same sender number multiple times
4. **Batch Processing**: Upload multiple messages simultaneously

### Example Test Commands

```bash
# Test single valid SMS
curl -X POST http://localhost:3002/api/send_sms \
  -H "Content-Type: application/json" \
  -d '{
    "sender_number": "+1234567890",
    "sms_message": "Verification code for mobile 9876543210",
    "received_timestamp": "2025-09-07T12:00:00Z"
  }'

# Test invalid SMS (no mobile number)
curl -X POST http://localhost:3002/api/send_sms \
  -H "Content-Type: application/json" \
  -d '{
    "sender_number": "+1234567891",
    "sms_message": "This message has no mobile number",
    "received_timestamp": "2025-09-07T12:01:00Z"
  }'
```

## Monitoring

### Health Check
- **Endpoint**: `GET /health`
- **Response**: `{"status": "healthy", "service": "SMS Bridge Test Application"}`

### Logs
```bash
# View application logs
docker-compose logs sms_test_app

# Follow logs in real-time
docker-compose logs -f sms_test_app
```

## Troubleshooting

### Common Issues

1. **Cannot connect to SMS Bridge**
   - Ensure SMS Bridge is running on localhost:30080 (K3s NodePort)
   - Check Docker network connectivity
   - Verify SMS_BRIDGE_URL environment variable

2. **File upload fails**
   - Check file format (Excel/CSV only)
   - Verify required columns exist
   - Ensure file is not corrupted

3. **Permission errors**
   - Ensure upload directory has proper permissions
   - Check Docker volume mounts

### Debug Commands

```bash
# Check if SMS Bridge is accessible (K3s deployment)
curl http://localhost:30080/health

# Test connectivity from container
docker-compose exec sms_test_app curl http://host.docker.internal:30080/health

# Check container logs
docker-compose logs sms_test_app

# Interactive shell access
docker-compose exec sms_test_app bash
```

## Integration with SMS Bridge

This test application integrates with the SMS Bridge validation workflow:

1. **Sends SMS**: Posts to `/sms/receive` endpoint
2. **Validation**: Bridge processes through validation checks
3. **Database**: Valid messages stored in `input_sms` → `out_sms`
4. **Cache**: Processed numbers cached in Redis
5. **Monitoring**: Results tracked in `sms_monitor` table

Perfect for testing the complete SMS processing pipeline described in the best practices documentation!
