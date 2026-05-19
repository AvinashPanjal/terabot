#!/bin/bash
# Start the FastAPI extraction microservice in the background
python main.py &

# Start the Telegram bot in the foreground
python bot.py
