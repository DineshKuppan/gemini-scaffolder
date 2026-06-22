# Use a shared build argument for Python version
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS builder

# Install system dependencies needed for building certain Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv using the official pre-built binaries
COPY --from=ghcr.io/astral-sh/uv:0.5.1 /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml* uv.lock* README.md* ./

# Create virtual environment and install dependencies using uv
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f pyproject.toml ]; then \
        uv venv /opt/venv && \
        . /opt/venv/bin/activate && \
        uv pip install . ; \
    else \
        uv venv /opt/venv && \
        . /opt/venv/bin/activate && \
        uv pip install fastapi uvicorn sqlalchemy mcp fastmcp pydantic; \
    fi

# --- Runtime Stage ---
FROM python:${PYTHON_VERSION}-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8002 \
    SQLITE_DB_PATH="/app/data/payments.db"

# Create a non-privileged user to run the app
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/sh -m appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source code
COPY src/ /app/src/

# Create directory for SQLite database and set permissions
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose the service port
EXPOSE 8002

# Healthcheck using Python's built-in urllib to avoid installing curl in runtime
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=5)" || exit 1

# Run the FastAPI application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]