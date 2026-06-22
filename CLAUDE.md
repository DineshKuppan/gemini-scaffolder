# CLAUDE.md - Developer Guide & System Architecture

This document serves as the primary developer guide, operational runbook, and architectural blueprint for the Multi-Tenant FastAPI & FastMCP System.

## 1. System Architecture

The system is designed as a highly modular, multi-tenant microservices architecture powered by **Python 3.11+**, **uv** (fast package installer and runner), **FastAPI**, and **FastMCP** (Model Context Protocol) for seamless LLM/Agent integration.

```
+-----------------------------------------------------------------------------------+
|                                 Claude / LLM Client                               |
+-----------------------------------------------------------------------------------+
                                          | (Model Context Protocol - MCP)
                                          v
+-----------------------------------------------------------------------------------+
|                                  FastMCP Servers                                  |
|  - user-service MCP (get_user_context)   - payment-service MCP (get_balance_ctx)  |
+-----------------------------------------------------------------------------------+
         |                                                 |
         v (REST / Internal)                               v (REST / Internal)
+----------------------------------+             +----------------------------------+
|           user-service           |             |         payment-service          |
|  - FastAPI                       |             |  - FastAPI                       |
|  - SQLite (WAL Mode)             |             |  - SQLite (WAL Mode)             |
|  - Multi-tenant (Tenant Header)  |             |  - Multi-tenant (Tenant Header)  |
+----------------------------------+             +----------------------------------+
                 |                                                 |
                 +------------------------+------------------------+
                                          |
                                          v
                       +------------------------------------+
                       |         gemini_adk_wrapper         |
                       |  - LiteLLM Proxy Fallback Engine   |
                       |  - Output Evaluation Loop          |
                       +------------------------------------+
```

### Core Components
1. **user-service**: Manages user profiles, authentication, and tenant isolation. Uses SQLite in WAL (Write-Ahead Logging) mode with SQLAlchemy 2.0. Exposes a FastMCP tool `get_user_context` for LLM agents.
2. **payment-service**: Manages tenant balances, ledgers, and transaction histories. Exposes a FastMCP tool `get_payment_context`.
3. **gemini_adk_wrapper**: A resilient LLM proxy engine utilizing LiteLLM for fallback routing (e.g., Gemini -> Claude -> OpenAI) and an automated output evaluation loop to guarantee structured schema adherence.

---

## 2. Development & Operational Commands

We use `uv` for ultra-fast dependency management and execution.

### Local Setup & Installation
Ensure you have `uv` installed:
```bash
curl -sSf https://get.alik.dev/uv | sh  # Or brew install uv
```

Install dependencies for all services:
```bash
# From the root directory
uv pip install -e ./user-service
uv pip install -e ./payment-service
uv pip install -e ./gemini_adk_wrapper
```

### Running Services Locally

#### Running `user-service`
```bash
# Run FastAPI Web Server
cd user-service
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Run FastMCP Server (for LLM integration)
uv run mcp dev src/mcp_server.py
```

#### Running `payment-service`
```bash
# Run FastAPI Web Server
cd payment-service
uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# Run FastMCP Server
uv run mcp dev src/mcp_server.py
```

#### Running `gemini_adk_wrapper`
```bash
cd gemini_adk_wrapper
uv run uvicorn src.main:app --host 0.0.0.0 --port 8002 --reload
```

### Running with Docker Compose
To spin up the entire production-grade multi-tenant stack (including databases, services, and network isolation):
```bash
docker-compose up --build -d
```
To view logs:
```bash
docker-compose logs -f
```

### Running Tests
We use `pytest` for unit and integration testing.
```bash
# Run all tests
uv run pytest

# Run specific service tests
uv run pytest user-service/tests/
uv run pytest payment-service/tests/
uv run pytest gemini_adk_wrapper/tests/
```

---

## 3. Code Style & Guidelines

To maintain consistency across all services, adhere to the following standards:

### Python & Formatting
- **Python Version**: `3.11` or higher.
- **Formatter & Linter**: `ruff` is used for linting and formatting.
  - Run formatter: `uv run ruff format .`
  - Run linter: `uv run ruff check . --fix`
- **Type Hints**: Strict type hinting is required on all function signatures, FastAPI endpoints, and Pydantic models.

### Multi-Tenancy Strategy
- Every request to `user-service` and `payment-service` must include a `X-Tenant-ID` header.
- Databases are isolated per tenant using a **Database-per-Tenant** or **Schema-per-Tenant** approach.
- In SQLite, this is implemented dynamically by resolving the database file path based on the `X-Tenant-ID` header (e.g., `data/tenant_{tenant_id}.db`).
- Always enable WAL mode on SQLite connections for concurrent read/write performance:
  ```python
  from sqlalchemy import event
  @event.listens_for(engine, "connect")
  def set_sqlite_pragma(dbapi_connection, connection_record):
      cursor = dbapi_connection.cursor()
      cursor.execute("PRAGMA journal_mode=WAL")
      cursor.execute("PRAGMA synchronous=NORMAL")
      cursor.close()
  ```

### Error Handling & Responses
- Do not return raw database exceptions. Wrap all database operations in `try-except` blocks and raise standardized `HTTPException` payloads.
- Standard Error Response Schema:
  ```json
  {
    "detail": {
      "error_code": "RESOURCE_NOT_FOUND",
      "message": "The requested user was not found.",
      "tenant_id": "tenant_abc"
    }
  }
  ```

### FastMCP Tool Guidelines
- FastMCP tools must be self-documenting. Provide clear docstrings and type annotations so LLMs can accurately infer parameters.
- Always validate the incoming `tenant_id` context within the tool execution block.
- Example:
  ```python
  @mcp.tool()
  async def get_user_context(tenant_id: str, user_id: str) -> str:
      """
      Retrieves the full profile, active permissions, and metadata for a user
      within a specific tenant context.
      """
      # Implementation goes here
  ```

### LLM Fallback & Evaluation Loop (`gemini_adk_wrapper`)
- **LiteLLM Integration**: Use LiteLLM to define a fallback list (e.g., `gemini/gemini-1.5-pro` -> `anthropic/claude-3-5-sonnet` -> `openai/gpt-4o`).
- **Evaluation Loop**: Every structured output generated by the LLM must be validated against a Pydantic schema. If validation fails, the wrapper must automatically feed the validation error back to the LLM for self-correction (up to 3 retries) before falling back to the next model in the chain.

---

## 4. Deployment & Infrastructure

### Helm Charts
Kubernetes deployments are managed via Helm. The charts are located in `/deployments/helm`.
- To dry-run a deployment:
  ```bash
  helm install multi-tenant-stack ./deployments/helm --dry-run --debug
  ```
- To deploy to production:
  ```bash
  helm upgrade --install multi-tenant-stack ./deployments/helm -f ./deployments/helm/values.yaml
  ```

### Environment Variables
Copy `.env.example` to `.env` in each service directory and configure the secrets:
- `DATABASE_URL_TEMPLATE`: Template path for tenant databases.
- `LITELLM_MASTER_KEY`: API key for LiteLLM proxy.
- `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`: Model provider keys.