# Multi-stage build for FastAPI backend
# Optimized for production with minimal image size
# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12-slim@sha256:0bbd3d5f3abb2024c1b92ce69e8bdfefa17c248999827c34e2ed52ba0772da1b

FROM ${PYTHON_IMAGE} AS base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies (with BuildKit cache mount for faster rebuilds)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Development stage
FROM base AS development

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with hot reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production build stage
FROM base AS builder

# Copy application code
COPY . .

# Compile Python files for faster startup
RUN python -m compileall -b .

# Production stage
FROM ${PYTHON_IMAGE} AS production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# Create non-root user for security (no home dir, no shell — service account only)
RUN groupadd appuser -g 1000 && \
    useradd -u 1000 -g appuser -s /usr/sbin/nologin -M appuser && \
    chown -R appuser:appuser /app

# Copy application code
COPY --from=builder --chown=appuser:appuser /app .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with production settings (multiple workers, no access log)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]
