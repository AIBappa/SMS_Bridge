# SMS Bridge Dockerfile for Coolify Deployment
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better Docker layer caching)
# core/ folder is symlinked or copied into coolify/ during deployment
COPY core/requirements.txt /app/core/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/core/requirements.txt

# Copy application code
COPY core/ /app/core/

# Create logs directory
RUN mkdir -p /app/logs && chmod 755 /app/logs

# Set Python path to include core module
ENV PYTHONPATH=/app

# Expose application port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the SMS server with uvicorn
CMD ["python", "-m", "uvicorn", "core.sms_server_v2:app", "--host", "0.0.0.0", "--port", "8080"]
