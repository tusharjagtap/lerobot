# Use Python 3.10 as base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire lerobot webrtc_server directory
COPY . .

# Set Python path to include the parent directories
ENV PYTHONPATH=/app:/app/../..

# Expose port (Cloud Run will set this via PORT env var)
EXPOSE 8080

# Command to run the cloud-optimized application
CMD ["python", "cloud_central_teleop_server.py"] 