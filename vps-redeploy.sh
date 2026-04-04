#!/bin/bash
# Quick VPS Redeployment Script for 401 Auth Fix
# Run this on your VPS after cloning

set -e

echo "=========================================="
echo "🚀 Flash-AI VPS Redeployment - Auth Fix"
echo "=========================================="

# Navigate to project
cd /opt/Flash-AI/Flash-AI || cd ~/Flash-AI/Flash-AI

echo ""
echo "📥 Pulling latest code from GitHub..."
git pull origin main

echo ""
echo "📝 Updating .env with development auth bypass..."

# Backup current .env
cp .env .env.backup

# Add or update DEV_AUTH_BYPASS if not present
if grep -q "DEV_AUTH_BYPASS" .env; then
    sed -i "s/DEV_AUTH_BYPASS=.*/DEV_AUTH_BYPASS=true/" .env
else
    cat >> .env << 'EOF'

# ============================================================
# Development Mode (DISABLE IN PRODUCTION!)
# ============================================================
DEV_AUTH_BYPASS=true
DEV_USER_ID=test_user
DEV_TENANT_ID=test_tenant
DEV_ROLE=admin
EOF
fi

echo "✅ .env updated with dev auth bypass"

echo ""
echo "🔨 Rebuilding Docker image..."
docker-compose build --no-cache

echo ""
echo "🛑 Stopping running containers..."
docker-compose down

echo ""
echo "🚀 Starting containers..."
docker-compose up -d

echo ""
echo "⏳ Waiting for backend to start..."
sleep 5

echo ""
echo "✅ Verifying backend is running..."
docker-compose ps

echo ""
echo "🔍 Checking logs for auth configuration..."
docker-compose logs backend | grep -i "DEV AUTH\|BYPASS\|CORS\|Uvicorn running" | tail -5

echo ""
echo "=========================================="
echo "✅ Redeployment Complete!"
echo "=========================================="
echo ""
echo "Test your API:"
echo "  curl https://your-domain.com/docs"
echo ""
echo "Should return HTTP 200 (not 401!)"
echo ""
