# Multi-stage Dockerfile for user-service using uv

# Stage 1: Build dependencies and application virtual environment
FROM ghcr.io/astral-sh/uv:0.5.11-python3.11-alpine AS builder

WORKDIR /app

# Enable bytecode compilation and prevent uv from writing to global cache
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy dependency definition files
COPY pyproject.toml uv.lock* ./

# Install dependencies. If uv.lock does not exist, uv will generate/sync without it.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-install-project --no-dev; \
    else \
        uv sync --no-install-project --no-dev; \
    fi

# Copy the application source code
COPY src/ ./src/

# Sync the project itself (installs the current package into the venv)
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev; \
    else \
        uv sync --no-dev; \
    fi

# Stage 2: Minimal runtime environment
FROM python:3.11-slim-bookworm

WORKDIR /app

# Configure environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SQLITE_DB_PATH="/app/data/user_service.db"

# Install system dependencies (sqlite3 for database management, curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment and application from the builder stage
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Create a dedicated directory for SQLite WAL database and set appropriate permissions
RUN mkdir -p /app/data && chmod 777 /app/data

# Expose the port for the FastAPI application
EXPOSE 8000

# Define a healthcheck to ensure service availability
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run the FastAPI application using uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]