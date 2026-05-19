#!/bin/bash

# Ensure we have the required API credentials
if [ -z "$TELEGRAM_API_ID" ] || [ -z "$TELEGRAM_API_HASH" ] || [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "ERROR: TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_BOT_TOKEN environment variables are required!"
    exit 1
fi

# Export PYTHONUNBUFFERED to ensure all python logs print immediately
export PYTHONUNBUFFERED=1

# Log out the bot from the official Telegram API servers to prevent conflicts
echo "Logging out bot from official Telegram servers..."
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/logOut"
echo ""

# Create directory for Telegram Bot API storage in /tmp (writable by anyone)
mkdir -p /tmp/telegram-bot-api-data
chmod -R 777 /tmp/telegram-bot-api-data

# Create log file and stream it to stdout in background
touch /tmp/telegram-bot-api.log
tail -f /tmp/telegram-bot-api.log &
TAIL_PID=$!
trap 'kill $TAIL_PID 2>/dev/null' EXIT

# Start the Local Telegram Bot API Server
echo "Starting Telegram Bot API Server..."
telegram-bot-api \
  --api-id="$TELEGRAM_API_ID" \
  --api-hash="$TELEGRAM_API_HASH" \
  --local \
  --dir=/tmp/telegram-bot-api-data \
  --http-port=8081 > /tmp/telegram-bot-api.log 2>&1 &
API_SERVER_PID=$!

# Wait for it to boot and verify it's running
sleep 3
if ! kill -0 $API_SERVER_PID 2>/dev/null; then
    echo "ERROR: telegram-bot-api server failed to start! Exited immediately."
    exit 1
fi

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
python -u scraper/main.py &
FASTAPI_PID=$!

# Wait for FastAPI to start and verify it's running
sleep 3
if ! kill -0 $FASTAPI_PID 2>/dev/null; then
    echo "ERROR: FastAPI server failed to start!"
    exit 1
fi

# Start the Telegram Bot
echo "Starting Telegram Bot..."
python -u scraper/bot.py
