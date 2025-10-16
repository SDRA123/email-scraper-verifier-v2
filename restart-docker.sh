#!/bin/bash

# Email Verifier and Scraper v2 - Docker Restart Script
# Run this script on your Ubuntu PC to restart the containers with proper network configuration

echo "🚀 Restarting Email Verifier and Scraper v2..."

# Stop and remove existing containers
echo "🛑 Stopping existing containers..."
docker-compose down

# Remove any orphaned containers
docker-compose down --remove-orphans

# Build and start containers with fresh configuration
echo "🔨 Building and starting containers..."
docker-compose up --build -d

# Wait a moment for containers to start
sleep 5

# Show container status
echo "📊 Container Status:"
docker-compose ps

# Show logs for debugging
echo "📋 Recent Backend Logs:"
docker-compose logs --tail=20 backend

echo "📋 Recent Frontend Logs:"
docker-compose logs --tail=20 frontend

echo ""
echo "✅ Application should be accessible at:"
echo "   Frontend: http://192.168.18.14:3000"
echo "   Backend API: http://192.168.18.14:8000"
echo "   API Docs: http://192.168.18.14:8000/docs"
echo ""
echo "🔍 To monitor logs in real-time, run:"
echo "   docker-compose logs -f"
echo ""
echo "🛑 To stop the application, run:"
echo "   docker-compose down"