# Multi-stage build for ML service
# Optimized for TensorFlow/PyTorch workloads

FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies for ML libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Development stage
FROM base as development

# Install dev dependencies
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy application code
COPY . .

# Run tests by default in development
CMD ["pytest", "-v", "--cov=.", "--cov-report=term-missing"]

# Production stage
FROM base as production

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash mluser && \
    chown -R mluser:mluser /app

# Create directories for models
RUN mkdir -p /app/models/saved && \
    chown -R mluser:mluser /app/models

# Copy application code
COPY --chown=mluser:mluser . .

# Switch to non-root user
USER mluser

# Expose port for model serving (if needed)
EXPOSE 8001

# Health check
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 \
    CMD python -c "import tensorflow as tf; print('OK')" || exit 1

# Default command (can be overridden)
CMD ["python", "-m", "inference.serve"]
