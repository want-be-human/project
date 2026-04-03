# NetTwin-SOC Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Create data directories
RUN mkdir -p /app/data/pcaps
RUN mkdir -p /app/data/pcaps /app/models

# Environment variables
ENV DATABASE_URL="sqlite:///./data/nettwin.db"
ENV DATA_DIR="/app/data"
ENV PYTHONPATH="/app"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
