# Production_2 SMS Bridge Dockerfile
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY core/requirements.txt /app/core/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/core/requirements.txt

# Copy application code
COPY core/ /app/core/

# Create logs directory
RUN mkdir -p /app/logs

# Set Python path to include core module
ENV PYTHONPATH=/app

# Expose application port
EXPOSE 8080

# Run the SMS server
CMD ["python", "-m", "uvicorn", "core.sms_server:app", "--host", "0.0.0.0", "--port", "8080"]
