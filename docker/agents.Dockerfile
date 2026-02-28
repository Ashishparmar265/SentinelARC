# Use official Python slim base (minimal but sufficient)
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright/Chromium + Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libexpat1 \
    libgbm1 \
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxtst6 \
    wget \
    xdg-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 (for npx and Playwright)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest

# Install Playwright globally and download Chromium (during build)
RUN npm install -g playwright \
    && playwright install --with-deps chromium

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Install Playwright Python bindings if your code uses them directly
RUN pip install playwright \
    && playwright install-deps

# Copy application code
COPY src/ ./src/
COPY async_main.py .

# Create directories for volumes
RUN mkdir -p /app/output /app/temp /app/logs

# Expose port (optional, but good practice)
EXPOSE 8000

# Install zstd (required by Ollama installer)
RUN apt-get update && apt-get install -y zstd && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Pull model during build (server starts temporarily, pulls, then stops)
RUN ollama serve & sleep 10 && ollama pull llama3.1:8b && pkill ollama

# Run the application
CMD ["python", "async_main.py"]
