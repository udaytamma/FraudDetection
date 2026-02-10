FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Install Python dependencies (separate layer for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY config/ config/
COPY scripts/init_db.sql scripts/init_db.sql
COPY dashboard.py dashboard.py
COPY .streamlit/ .streamlit/

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Health check (uses PORT env var when set by Railway, defaults to 8000)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Run with uvicorn - shell form for Railway $PORT expansion, exec for signal handling
CMD exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
