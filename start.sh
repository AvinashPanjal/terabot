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

# Create an empty log file
touch /tmp/app.log

# Start the FastAPI server (extraction API)
echo "Starting FastAPI Server..." | tee -a /tmp/app.log
# Use PORT env variable if set (Render), otherwise default to 7860 (Hugging Face)
if [ -z "$PORT" ]; then
    export PORT=7860
fi
python -u scraper/main.py >> /tmp/app.log 2>&1 &
FASTAPI_PID=$!

# Wait for FastAPI to start and verify it's running
sleep 3
if ! kill -0 $FASTAPI_PID 2>/dev/null; then
    echo "ERROR: FastAPI server failed to start!" | tee -a /tmp/app.log
    cat /tmp/app.log
    exit 1
fi

# Start the Telegram Bot
echo "Starting Telegram Bot..." | tee -a /tmp/app.log
python -u scraper/bot.py >> /tmp/app.log 2>&1 &
BOT_PID=$!

# Trap signals to clean up background processes on exit
trap 'kill $FASTAPI_PID $BOT_PID 2>/dev/null' EXIT

# Start tailing the combined log in the foreground to stream to Render console
tail -n +1 -f /tmp/app.log &
TAIL_PID=$!

# Monitor background processes; if either crashes, exit start.sh
wait -n $FASTAPI_PID $BOT_PID

# Exit code of the crashed process
EXIT_STATUS=$?
echo "ERROR: One of the background processes stopped with status $EXIT_STATUS. Exiting..." | tee -a /tmp/app.log
kill $TAIL_PID 2>/dev/null
exit $EXIT_STATUS
