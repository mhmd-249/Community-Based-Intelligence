# syntax=docker/dockerfile:1

# =============================================================================
# CBI Backend - Multi-stage Dockerfile
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies and build wheels
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy README for metadata
COPY README.md ./

# Install pip and build tools
RUN pip install --no-cache-dir --upgrade pip wheel

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install the package with all dependencies
RUN pip install --no-cache-dir .

# -----------------------------------------------------------------------------
# Stage 2: Runtime - Minimal production image
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd --gid 1000 cbi \
    && useradd --uid 1000 --gid cbi --shell /bin/bash --create-home cbi

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=cbi:cbi cbi/ ./cbi/
COPY --chown=cbi:cbi migrations/ ./migrations/

# Switch to non-root user
USER cbi

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command - run API server
CMD ["uvicorn", "cbi.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# -----------------------------------------------------------------------------
# Stage 3: Development - With hot reload and dev tools
# -----------------------------------------------------------------------------
FROM runtime AS development

USER root

COPY pyproject.toml README.md ./

# Install dev dependencies
RUN pip install --no-cache-dir -e ".[dev]"

USER cbi

# Development command with hot reload
CMD ["uvicorn", "cbi.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
