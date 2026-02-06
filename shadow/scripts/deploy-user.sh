#!/bin/bash
# Shadow Multi-Tenant Deploy Script
# Usage: ./deploy-user.sh <user_number> <phone_number>
# Example: ./deploy-user.sh 1 +5511999999999

set -e

USER_NUM=$1
PHONE=$2

if [ -z "$USER_NUM" ] || [ -z "$PHONE" ]; then
    echo "Usage: ./deploy-user.sh <user_number> <phone_number>"
    echo "Example: ./deploy-user.sh 1 +5511999999999"
    exit 1
fi

if [ "$USER_NUM" -lt 1 ] || [ "$USER_NUM" -gt 4 ]; then
    echo "Error: user_number must be between 1 and 4"
    exit 1
fi

# Calculate ports
GATEWAY_PORT=$((18789 + USER_NUM))
AGENT_PORT=$((8089 + USER_NUM))

# Create data directories
USER_DIR="./data/user${USER_NUM}"
mkdir -p "$USER_DIR/auth" "$USER_DIR/db"

# Generate token
TOKEN=$(openssl rand -hex 16 2>/dev/null || echo "user${USER_NUM}-$(date +%s)")

echo "=========================================="
echo "Shadow User ${USER_NUM} Configuration"
echo "=========================================="
echo ""
echo "Phone: ${PHONE}"
echo "Gateway Port: ${GATEWAY_PORT}"
echo "Agent Port: ${AGENT_PORT}"
echo "Data Dir: ${USER_DIR}"
echo "Token: ${TOKEN}"
echo ""
echo "Add to your .env.multi file:"
echo ""
echo "SHADOW_USER${USER_NUM}_PHONE=${PHONE}"
echo "SHADOW_USER${USER_NUM}_TOKEN=${TOKEN}"
echo ""
echo "Then run:"
echo "docker-compose -f docker-compose.multi.yml --profile user${USER_NUM} up -d"
echo ""
echo "Or to start all users:"
echo "docker-compose -f docker-compose.multi.yml --profile all up -d"
echo ""
echo "=========================================="

# Update .env.multi if it exists
if [ -f ".env.multi" ]; then
    echo ""
    read -p "Update .env.multi with these values? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Check if line exists and update, or append
        if grep -q "SHADOW_USER${USER_NUM}_PHONE" .env.multi; then
            sed -i "s/SHADOW_USER${USER_NUM}_PHONE=.*/SHADOW_USER${USER_NUM}_PHONE=${PHONE}/" .env.multi
            sed -i "s/SHADOW_USER${USER_NUM}_TOKEN=.*/SHADOW_USER${USER_NUM}_TOKEN=${TOKEN}/" .env.multi
        else
            echo "" >> .env.multi
            echo "# User ${USER_NUM}" >> .env.multi
            echo "SHADOW_USER${USER_NUM}_PHONE=${PHONE}" >> .env.multi
            echo "SHADOW_USER${USER_NUM}_TOKEN=${TOKEN}" >> .env.multi
        fi
        echo "Updated .env.multi"
    fi
fi
