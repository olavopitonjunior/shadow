#!/bin/bash
# Shadow QR Code Setup Script
# Usage: ./setup-qr.sh <user_number>
# Shows the QR code for a specific user to scan

set -e

USER_NUM=$1

if [ -z "$USER_NUM" ]; then
    echo "Usage: ./setup-qr.sh <user_number>"
    echo "Example: ./setup-qr.sh 1"
    exit 1
fi

GATEWAY_PORT=$((18789 + USER_NUM))
CONTAINER_NAME="shadow-gateway-user${USER_NUM}"

echo "=========================================="
echo "Shadow User ${USER_NUM} QR Setup"
echo "=========================================="
echo ""
echo "Starting gateway for user ${USER_NUM}..."
echo "Gateway URL: http://localhost:${GATEWAY_PORT}"
echo ""
echo "Please wait for the QR code to appear..."
echo "Scan it with WhatsApp > Menu > Linked Devices > Link a Device"
echo ""
echo "Press Ctrl+C when done scanning."
echo ""
echo "=========================================="
echo ""

# Follow logs to show QR code
docker logs -f "$CONTAINER_NAME" 2>&1 | while read line; do
    echo "$line"
    # Check if connected
    if echo "$line" | grep -q "Connection open"; then
        echo ""
        echo "=========================================="
        echo "Connected! User ${USER_NUM} is now active."
        echo "=========================================="
        break
    fi
done
