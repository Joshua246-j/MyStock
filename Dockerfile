# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

# Python and application environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOST=0.0.0.0 \
    PORT=8000

# Install minimal OS dependencies required for C-extensions, SQLite, and container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create secure non-root user and group
RUN groupadd -r appgroup --gid 10001 && \
    useradd -r -g appgroup --uid 10001 --create-home --home-dir /home/appuser appuser

WORKDIR /app

# Cache pip dependency installation
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy required application modules, migrations, static assets, and run scripts
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY static ./static
COPY run.py ./
COPY entrypoint.sh ./

# Prepare storage directories and assign ownership to non-root user
RUN mkdir -p /app/data/faiss /app/data/documents /app/data/datasets /app/data/web /app/uploads /home/appuser/.cache/py-yfinance && \
    chmod +x /app/entrypoint.sh && \
    chown -R appuser:appgroup /app /home/appuser/.cache

# Run as non-root user
USER appuser

EXPOSE 8000

# Container healthcheck requires the configured chat and embedding models to be usable.
HEALTHCHECK --interval=30s --timeout=5s --start-period=360s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/ready || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
