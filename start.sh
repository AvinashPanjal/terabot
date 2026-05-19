#!/bin/bash

# Ensure we have the required API credentials
if [ -z "$TELEGRAM_API_ID" ] || [ -z "$TELEGRAM_API_HASH" ]; then
    echo "ERROR: TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables are required!"
    exit 1
fi

# Create directory for Telegram Bot API storage in /tmp (writable by anyone)
mkdir -p /tmp/telegram-bot-api-data
chmod -R 777 /tmp/telegram-bot-api-data

# Start the Local Telegram Bot API Server
echo "Starting Telegram Bot API Server..."
telegram-bot-api \
  --api-id="$TELEGRAM_API_ID" \
  --api-hash="$TELEGRAM_API_HASH" \
  --local \
  --dir=/tmp/telegram-bot-api-data \
  --http-port=8081 &

# Wait for it to boot
sleep 2

# Set the local Bot API URL for bot.py to pick up
export TELEGRAM_LOCAL_API_URL="http://localhost:8081"

# Set the external URL for download links
if [ -n "$SPACE_HOST" ]; then
    export RENDER_EXTERNAL_URL="https://$SPACE_HOST"
fi

# Start the FastAPI server (extraction API)
echo "Starting FastAPI Server..."
# Port 7860 is required by Hugging Face Spaces
export PORT=7860
python scraper/main.py &

# Wait for FastAPI to start
sleep 2

# Start the Telegram Bot
echo "Starting Telegram Bot..."
python scraper/bot.py
