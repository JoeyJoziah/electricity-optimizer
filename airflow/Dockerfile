# Custom Airflow image with ML dependencies
# Based on official Apache Airflow image

FROM apache/airflow:2.8.0-python3.11 as base

# Switch to root to install system dependencies
USER root

# Install system dependencies for ML libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user
USER airflow

# Copy requirements and install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Development stage
FROM base as development

# Copy DAGs and plugins for development
COPY --chown=airflow:root dags /opt/airflow/dags
COPY --chown=airflow:root plugins /opt/airflow/plugins

# Production stage
FROM base as production

# Copy DAGs
COPY --chown=airflow:root dags /opt/airflow/dags

# Copy custom plugins
COPY --chown=airflow:root plugins /opt/airflow/plugins

# Copy ML code (for training DAG)
COPY --chown=airflow:root ../ml /opt/airflow/ml

# Set PYTHONPATH to include ML module
ENV PYTHONPATH="${PYTHONPATH}:/opt/airflow/ml"

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8080/health || exit 1
