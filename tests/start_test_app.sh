#!/bin/bash

echo "🚀 Starting SMS Bridge Test Application..."

# Create uploads directory if it doesn't exist
mkdir -p uploads

# Check if SMS Bridge is running
echo "🔍 Checking SMS Bridge connectivity..."
if curl -s http://localhost:8080/health > /dev/null; then
    echo "✅ SMS Bridge is running and accessible"
else
    echo "⚠️  Warning: SMS Bridge may not be running at http://localhost:8080"
    echo "   Make sure to start the SMS Bridge first with Docker Compose"
    echo "   cd ../coolify && docker-compose up -d"
fi

# Start the test application
echo "🏃 Starting test application on port 3000..."
docker-compose up -d

echo ""
echo "📱 SMS Bridge Test Application is now running!"
echo "🌐 Web Interface: http://localhost:3000"
echo "🔧 API Endpoint: http://localhost:3000/api/send_sms"
echo "🏥 Health Check: http://localhost:3000/health"
echo ""
echo "📊 To view logs: docker-compose logs -f"
echo "🛑 To stop: docker-compose down"
