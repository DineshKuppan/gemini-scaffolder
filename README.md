# Multi-Tenant AI-Powered Microservices

This repository contains a production-grade multi-tenant architecture leveraging **FastAPI**, **FastMCP**, and **uv** for high-performance Python microservices. It integrates AI capabilities via a Gemini/LiteLLM wrapper and provides context-aware tools for LLM agents.

## 🏗 Architecture Overview

- **user-service**: Manages user profiles and multi-tenant context using SQLite (WAL mode) and SQLAlchemy. Provides a FastMCP tool `get_user_context`.
- **payment-service**: Handles financial ledgers, balance tracking, and transaction history. Provides a FastMCP tool `get_balance_context`.
- **gemini_adk_wrapper**: A proxy engine using LiteLLM for fallback management and an evaluation loop for AI outputs.
- **Infrastructure**: Fully containerized with Docker, orchestrated via Docker Compose, and ready for Kubernetes with Helm charts.

## 🚀 Tech Stack

- **Language**: Python 3.12+
- **Package Manager**: [uv](https://github.com/astral-sh/uv)
- **Framework**: FastAPI
- **Database**: SQLite with Write-Ahead Logging (WAL)
- **ORM**: SQLAlchemy 2.0 (Async)
- **MCP**: FastMCP (Model Context Protocol)
- **AI Proxy**: LiteLLM
- **Deployment**: Docker, Helm

## 🛠 Getting Started

### Prerequisites

- Install `uv`: `curl -LsSf https://astral-sh/uv/install.sh | sh`
- Install Docker and Docker Compose.

### Local Development

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd multi-tenant-fastmcp
   ```

2. **Environment Setup**:
   ```bash
   cp env_example .env
   # Edit .env with your API keys (GEMINI_API_KEY, etc.)
   ```

3. **Install Dependencies**:
   ```bash
   uv sync
   ```

4. **Run Services via Docker Compose**:
   ```bash
   docker-compose up --build
   ```

## 🔌 MCP Tools

This system implements the Model Context Protocol (MCP) to allow LLMs to query live system data safely.

- **User Context**: `mcp://user-service/get_user_context?user_id=...` returns tenant-specific metadata.
- **Payment Context**: `mcp://payment-service/get_balance_context?user_id=...` returns current balance and recent transaction summaries.

## 📂 Project Structure

```text
.
├── user-service/           # User & Tenant Management
│   ├── src/                # FastAPI application
│   ├── Dockerfile          # Multi-stage build
│   └── pyproject.toml      # uv configuration
├── payment-service/        # Ledger & Transactions
│   ├── src/                # FastAPI application
│   ├── Dockerfile
│   └── pyproject.toml
├── gemini_adk_wrapper/     # AI Proxy & Eval Loop
│   ├── src/
│   └── Dockerfile
├── charts/                 # Helm charts for K8s
├── docker-compose.yml      # Root orchestration
├── CLAUDE.md               # Development guide
└── SKILLS.md               # MCP Skill definitions
```

## 🧪 Testing

Run tests for all services using `uv`:

```bash
uv run pytest
```

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.