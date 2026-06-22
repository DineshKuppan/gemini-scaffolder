import os
import asyncio
from typing import AsyncGenerator, Dict
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

# Cache for tenant engines to prevent resource leaks and redundant connections
_tenant_engines: Dict[str, AsyncEngine] = {}
_lock = asyncio.Lock()

# Base directory configuration
DEFAULT_DB_DIR = os.getenv("DB_DIR", "./data")

# Ensure DB directory exists
os.makedirs(DEFAULT_DB_DIR, exist_ok=True)

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models in the user-service."""
    pass

def _configure_sqlite_connection(dbapi_connection, connection_record):
    """
    Configure SQLite connection parameters for high performance and integrity.
    Enables Write-Ahead Logging (WAL) mode, normal synchronous mode, and foreign key constraints.
    """
    import sqlite3
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

async def get_tenant_engine(tenant_id: str) -> AsyncEngine:
    """
    Retrieve or create a cached SQLAlchemy AsyncEngine for a specific tenant.
    Implements strict tenant isolation using separate SQLite database files.
    """
    async with _lock:
        # Sanitize tenant_id to prevent path traversal attacks
        safe_tenant_id = "".join(c for c in tenant_id if c.isalnum() or c in ("-", "_"))
        if not safe_tenant_id:
            safe_tenant_id = "default"

        if safe_tenant_id in _tenant_engines:
            return _tenant_engines[safe_tenant_id]

        db_path = os.path.join(DEFAULT_DB_DIR, f"user_service_{safe_tenant_id}.db")
        database_url = f"sqlite+aiosqlite:///{db_path}"

        engine = create_async_engine(
            database_url,
            connect_args={"check_same_thread": False},
            echo=False,
            pool_pre_ping=True,
        )

        # Register WAL and foreign key pragmas on connection
        event.listen(engine.sync_engine, "connect", _configure_sqlite_connection)

        _tenant_engines[safe_tenant_id] = engine
        return engine

async def get_tenant_db(tenant_id: str) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency generator for obtaining a tenant-specific AsyncSession.
    Ensures proper transaction management, committing on success and rolling back on error.
    """
    engine = await get_tenant_engine(tenant_id)
    async_session = async_sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    async with async_session() as session:
        try: 
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_tenant_database(tenant_id: str) -> None:
    """
    Initialize database schema for a specific tenant.
    Useful for dynamic provisioning of new tenants.
    """
    engine = await get_tenant_engine(tenant_id)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)