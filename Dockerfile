# Stage 1: Build telegram-bot-api from source
FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y \
    make \
    git \
    cmake \
    g++ \
    libssl-dev \
    zlib1g-dev \
    gperf \
    php-cli \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --recursive https://github.com/tdlib/telegram-bot-api.git \
    && cd telegram-bot-api \
    && mkdir build \
    && cd build \
    && cmake -DCMAKE_BUILD_TYPE=Release .. \
    && cmake --build . --target install

# Stage 2: Final runtime image
FROM python:3.11-slim-bookworm

# Install system dependencies (including ffmpeg and runtime libraries)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    openssl \
    zlib1g \
    libstdc++6 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the telegram-bot-api binary from stage 1
COPY --from=builder /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

# Set the working directory
WORKDIR /app

# Ensure Playwright browser installs to the correct location in the container
ENV PLAYWRIGHT_BROWSERS_PATH=/app/scraper/pw-browsers

# Copy requirements and install python packages
COPY scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir yt-dlp

# Install playwright browsers and system dependencies for them
RUN playwright install chromium
RUN playwright install-deps

# Copy the rest of the application
COPY . .

# Set permissions for Hugging Face non-root user (UID 1000)
RUN mkdir -p /app/scraper/browser_session && chmod -R 777 /app

# Expose port 7860 (Hugging Face default)
EXPOSE 7860

# Start script
CMD ["/bin/bash", "./start.sh"]
