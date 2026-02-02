# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first (for layer caching)
COPY pyproject.toml uv.lock* ./

# Install dependencies with uv (generates lock file if not present)
RUN uv sync --no-dev

# Copy application code
COPY data_server/ ./data_server/
COPY scripts/ ./scripts/

# Make entrypoint executable
RUN chmod +x scripts/start.sh

# Expose port
EXPOSE 8000

# Run with uv
CMD ["uv", "run", "uvicorn", "data_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
