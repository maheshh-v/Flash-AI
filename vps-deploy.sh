#!/bin/bash
# Flash-AI Quick Deployment Script for VPS
# Run this after cloning the repo and configuring .env

set -e

echo "=========================================="
echo "🚀 Flash-AI VPS Deployment"
echo "=========================================="

# Step 1: Verify we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: docker-compose.yml not found!"
    echo "Make sure you're in the Flash-AI/Flash-AI directory"
    exit 1
fi

echo "✅ Found docker-compose.yml"

# Step 2: Build Docker image
echo ""
echo "📦 Building Docker image..."
docker-compose build

# Step 3: Start services
echo ""
echo "🚀 Starting services..."
docker-compose up -d

# Step 4: Wait for services to be ready
echo ""
echo "⏳ Waiting for services to start..."
sleep 5

# Step 5: Check status
echo ""
echo "📊 Service Status:"
docker-compose ps

# Step 6: Verify backend is responding
echo ""
echo "🔍 Checking backend health..."
if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "✅ Backend is responding at http://localhost:8000"
else
    echo "⚠️  Backend may still be starting, check logs with: docker-compose logs -f backend"
fi

# Step 7: Show next steps
echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "📚 Next Steps:"
echo "1. Install Nginx:"
echo "   apt install -y nginx certbot python3-certbot-nginx"
echo ""
echo "2. Configure Nginx (see VPS_DEPLOYMENT_GUIDE.md)"
echo ""
echo "3. Get SSL Certificate:"
echo "   certbot --nginx -d your_domain.com"
echo ""
echo "4. Setup auto-restart:"
echo "   # See systemd service section in VPS_DEPLOYMENT_GUIDE.md"
echo ""
echo "5. View logs:"
echo "   docker-compose logs -f backend"
echo ""
echo "=========================================="
