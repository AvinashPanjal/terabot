#!/bin/bash

# Ensure we have the required API credentials
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN environment variable is required!"
    exit 1
fi

# Export PYTHONUNBUFFERED to ensure all python logs print immediately
export PYTHONUNBUFFERED=1

# Log out the bot from the official Telegram API servers first to reset connection if needed
# (Only run if user wanted, but since we use official server, we do not need to log out/in.
# Actually, if we use the official Telegram API, calling logOut will make the bot token invalid for 10-15 minutes on official servers!
# WAIT! Yes, calling logOut on official API servers actually logs out the bot and revokes active sessions, but the bot token is still valid.
# But wait, we DO NOT need to call /logOut anymore because we are not using a local server!
# Calling logOut will log us out of the official server, meaning we have to wait a while or it might cause login issues.)
# So we REMOVE the logOut call entirely!

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
