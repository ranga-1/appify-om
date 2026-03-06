# Production Dockerfile for Appify Object Modeler Service
FROM python:3.11-slim

WORKDIR /app

# Install UV and postgresql-client
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies directly from pyproject.toml
RUN uv pip install --system --no-cache -e .

# Copy application code
COPY app/ ./app/
COPY sql/ ./sql/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health')"

# Run application
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
