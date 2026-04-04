#!/bin/bash

# 🔐 JWT Authentication Test Script (Hinglish Guide)
# Yeh script JWT token test karte hain!

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🔐 JWT Authentication Test Script${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Get domain
read -p "Enter your domain (e.g., https://your-domain.com): " DOMAIN
read -p "Enter your JWT token (paste from browser): " TOKEN

if [ -z "$DOMAIN" ] || [ -z "$TOKEN" ]; then
    echo -e "${RED}❌ Domain or token is empty!${NC}"
    exit 1
fi

echo -e "\n${YELLOW}🧪 Testing Authentication...${NC}\n"

# Test 1: Without token
echo -e "${BLUE}[Test 1] Without Token (Guest Access):${NC}"
echo "Command: curl -i $DOMAIN/docs"
echo ""
RESPONSE=$(curl -s -w "\n%{http_code}" "$DOMAIN/docs" 2>&1 | tail -1)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "307" ]; then
    echo -e "${GREEN}✅ Status: $HTTP_CODE (Guest access working!)${NC}\n"
else
    echo -e "${RED}❌ Status: $HTTP_CODE (Problem with guest access)${NC}\n"
fi

# Test 2: With token
echo -e "${BLUE}[Test 2] With JWT Token:${NC}"
echo "Command: curl -i -H 'Authorization: Bearer [token]' $DOMAIN/docs"
echo ""
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$DOMAIN/docs" 2>&1)
    
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

echo "HTTP Status: $HTTP_CODE"
echo "Response body:"
echo "$BODY" | head -20

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "307" ]; then
    echo -e "\n${GREEN}✅ Token is VALID! (HTTP $HTTP_CODE)${NC}\n"
elif [ "$HTTP_CODE" = "401" ]; then
    echo -e "\n${RED}❌ Token is INVALID! (HTTP 401 - Unauthorized)${NC}"
    echo "   Possible causes:"
    echo "   1. JWT_SECRET backend mein match nahi"
    echo "   2. Token expired ho gya"
    echo "   3. Token format galat hai${NC}\n"
elif [ "$HTTP_CODE" = "403" ]; then
    echo -e "\n${RED}❌ Access Forbidden! (HTTP 403)${NC}"
    echo "   Token valid hai but user ko permission nahi${NC}\n"
else
    echo -e "\n${RED}❌ Server Error! (HTTP $HTTP_CODE)${NC}"
    echo "   Backend logs dekho: docker-compose logs backend --tail=20${NC}\n"
fi

# Test 3: Check backend logs
echo -e "${BLUE}[Test 3] Backend Logs (last 10 lines with token info):${NC}"
echo ""
if command -v docker-compose &> /dev/null; then
    docker-compose logs backend --tail=10 2>/dev/null | grep -E "auth|jwt|token|error" || echo "No relevant logs found"
else
    echo -e "${YELLOW}⚠️  docker-compose not found in PATH${NC}"
fi

echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}✅ Test Complete!${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${YELLOW}Issues?${NC}"
echo "1. SSH to VPS: ssh root@your_vps_ip"
echo "2. Check .env: grep JWT .env"
echo "3. Check logs: docker-compose logs backend --tail=50"
echo "4. Share output and I'll fix it!"
