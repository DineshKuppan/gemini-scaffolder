# System Skills & Capabilities Matrix

This document outlines the technical capabilities, architecture patterns, and Model Context Protocol (MCP) tools implemented across the multi-tenant microservices platform.

## 1. Core Architecture & Technologies

- **FastAPI & uv**: High-performance asynchronous Python web framework managed with `uv` for ultra-fast dependency resolution and workspace management.
- **Multi-Tenant SQLite (WAL)**: SQLite databases configured with Write-Ahead Logging (WAL) for high-concurrency read/write operations, isolated per tenant or managed via tenant-keyed schemas.
- **SQLAlchemy 2.0**: Modern async ORM utilizing type-annotated declarative mappings and robust connection pooling.
- **FastMCP (Model Context Protocol)**: Seamless integration of LLM-callable tools directly into the microservices, enabling Claude and other LLMs to query live system state securely.
- **LiteLLM Proxy & Gemini ADK Wrapper**: Resilient LLM routing with fallback engines, output evaluation loops, and structured JSON schema enforcement.

---

## 2. Microservices & FastMCP Tools

### A. User Service (`user-service`)
Responsible for tenant provisioning, user profiles, and context generation for LLMs.

*   **Database**: SQLite (`user_service.db`) in WAL mode.
*   **FastMCP Tool**: `get_user_context`
    *   **Input Parameters**:
        *   `user_id` (string, required): The unique identifier of the user.
        *   `tenant_id` (string, required): The tenant context identifier.
    *   **Output**: A structured JSON payload containing user profile details, active status, tenant metadata, and system permissions.
    *   **Implementation Detail**: Uses an async SQLAlchemy session to query the database, handles missing records gracefully, and formats the output for optimal LLM token consumption.

### B. Payment Service (`payment-service`)
Manages tenant balances, transaction ledgers, and financial history.

*   **Database**: SQLite (`payment_service.db`) in WAL mode.
*   **FastMCP Tool**: `get_payment_context`
    *   **Input Parameters**:
        *   `user_id` (string, required): The unique identifier of the user.
        *   `tenant_id` (string, required): The tenant context identifier.
        *   `start_date` (string, optional): ISO-8601 date to filter transaction history.
    *   **Output**: Current balance, currency, status, and a list of recent transactions (debits/credits) with timestamps.
    *   **Implementation Detail**: Implements strict decimal arithmetic for balances, transaction isolation levels to prevent double-spending, and date-range filtering.

### C. Gemini ADK Wrapper (`gemini_adk_wrapper`)
An intelligent gateway that wraps Gemini and LiteLLM to provide high-availability LLM inference.

*   **Capabilities**:
    *   **LiteLLM Proxy Fallback**: Automatically falls back to alternative models (e.g., Claude, GPT-4) if the primary Gemini API rate limits or fails.
    *   **Output Evaluation Loop**: Validates LLM outputs against strict JSON schemas or business rules. If validation fails, it automatically re-prompts the model with the error context (up to a configurable retry limit).
    *   **Context Injection**: Automatically calls FastMCP tools (`get_user_context`, `get_payment_context`) to enrich prompts before sending them to the LLM.

---

## 3. Deployment & Infrastructure

- **Multi-Stage Dockerfiles**: Optimized Docker builds utilizing `uv` to compile dependencies in a builder stage, resulting in minimal, secure runtime images.
- **Docker Compose**: Local orchestration of all services, including environment variable injection and volume mounting for SQLite databases.
- **Helm Charts**: Production-grade Kubernetes manifests featuring:
  - Horizontal Pod Autoscaling (HPA) based on CPU/Memory.
  - Liveness and Readiness probes pointing to FastAPI `/health` endpoints.
  - ConfigMaps and Secrets management for database paths and API keys.

---

## 4. Developer Runbook & Commands

### Dependency Management with `uv`
```bash
# Install dependencies
uv sync

# Add a new package to a service
uv add --package user-service sqlalchemy

# Run a service locally
uv run --package user-service uvicorn src.main:app --reload --port 8000
```

### Testing FastMCP Tools
FastMCP tools can be tested locally using the MCP inspector or by running the service with the MCP entrypoint:
```bash
# Run user-service MCP server
uv run --package user-service python -m src.mcp_server
```

### Database Migrations
Each service manages its own migrations via Alembic:
```bash
# Generate a migration
uv run alembic revision --autogenerate -m "Add user table"

# Apply migrations
uv run alembic upgrade head
```