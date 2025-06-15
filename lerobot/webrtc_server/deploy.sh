#!/bin/bash

# LeRobot Central Teleoperation Server - Cloud Run Deployment Script
# Usage: ./deploy.sh [PROJECT_ID] [SERVICE_NAME] [REGION]

set -e

# Configuration
PROJECT_ID=${1:-"your-project-id"}
SERVICE_NAME=${2:-"lerobot-central-teleop"}
REGION=${3:-"us-central1"}
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🚀 Deploying LeRobot Central Teleoperation Server to Cloud Run"
echo "Project ID: ${PROJECT_ID}"
echo "Service Name: ${SERVICE_NAME}"
echo "Region: ${REGION}"
echo "Image: ${IMAGE_NAME}"

# Set the project
echo "📋 Setting GCP project..."
gcloud config set project ${PROJECT_ID}

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com

# Build and push the Docker image
echo "🏗️ Building Docker image..."
gcloud builds submit --tag ${IMAGE_NAME} .

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --port 8081 \
    --memory 2Gi \
    --cpu 2 \
    --timeout 3600 \
    --max-instances 10 \
    --set-env-vars "LEADER_PORT=" \
    --concurrency 1000

# Get the service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format='value(status.url)')

echo "✅ Deployment completed successfully!"
echo ""
echo "🌐 Service URL: ${SERVICE_URL}"
echo "🔗 WebSocket URL: wss://$(echo ${SERVICE_URL} | sed 's|https://||')"
echo ""
echo "📝 Next steps:"
echo "1. Update your remote_leader_agent.py with:"
echo "   central_server_host = '$(echo ${SERVICE_URL} | sed 's|https://||')'"
echo "   central_server_port = 443  # HTTPS port for Cloud Run"
echo ""
echo "2. Update your remote_follower_agent.py with the same settings"
echo ""
echo "3. Run your remote agents to connect to the cloud server"
echo ""
echo "🎯 Your LeRobot Central Teleoperation Server is now running in the cloud!" 