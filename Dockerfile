# =============================================================
# Dockerfile - Spotify Controller
# Multi-stage build for optimized production image
# =============================================================

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better cache utilization
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# =============================================================
# Stage 2: Production
# =============================================================
FROM python:3.11-slim as production

# Labels
LABEL maintainer="quanq026"
LABEL application="spo-controller"
LABEL version="2.0"
LABEL description="Self-hosted Spotify remote control with multi-user authentication"

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/root/.local/bin:$PATH" \
    ENVIRONMENT=production

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Copy application source code
COPY index.py .
COPY database.py .
COPY auth.py .

# Copy static files
COPY index.html .
COPY login.html .
COPY register.html .
COPY setup.html .
COPY welcome.html .
COPY style.css .
COPY script.js .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Run application with uvicorn (single worker to keep oauth state in memory)
CMD ["python", "-m", "uvicorn", "index:app", "--host", "0.0.0.0", "--port", "8000"]
