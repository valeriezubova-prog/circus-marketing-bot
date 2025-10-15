# syntax=docker/dockerfile:1
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Moscow

# Install minimal system dependencies and set timezone
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy application code and sample environment file
COPY app /app/app
COPY .env.example /app/.env.example

# Create a directory for persistent data (used for SQLite file_id storage)
RUN mkdir -p /data

# Use tini for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "app.main"]