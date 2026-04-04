#!/bin/bash
# Fix: Port Already Allocated Error on VPS

echo "=========================================="
echo "🔧 Fixing Port Already Allocated Error"
echo "=========================================="

echo ""
echo "Step 1: Find containers using port 6379..."
docker ps -a | grep -E "redis|6379" || echo "No redis containers found"

echo ""
echo "Step 2: Stop old containers..."
docker stop $(docker ps -a -q --filter "publish=6379") 2>/dev/null || echo "No running containers on 6379"

echo ""
echo "Step 3: Remove old containers..."
docker rm $(docker ps -a -q --filter "publish=6379") 2>/dev/null || echo "No old containers to remove"

echo ""
echo "Step 4: Remove all Flash-AI containers..."
docker-compose down --remove-orphans

echo ""
echo "Step 5: List all containers..."
docker ps -a

echo ""
echo "Step 6: Starting fresh..."
docker-compose build --no-cache
docker-compose up -d

echo ""
echo "Step 7: Verify containers..."
docker-compose ps

echo ""
echo "✅ Fixed!"
