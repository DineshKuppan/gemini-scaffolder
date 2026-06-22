import os
import logging
from shared.logging_config import configure_logging
from typing import Optional
from fastmcp import FastMCP
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

# Configure structured JSON logging
configure_logging("user-service")
logger = logging.getLogger("user-service-mcp")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./user_service.db")
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Enable WAL mode for SQLite to support concurrent reads/writes
if DATABASE_URL.startswith("sqlite"):
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
            logger.info("SQLite WAL mode and synchronous normal configured successfully.")
    except Exception as e:
        logger.error(f"Failed to configure SQLite WAL mode: {e}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# User Model Definition
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    username = Column(String, nullable=False)
    email = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String, default="user")

# Ensure tables exist (for standalone/demo runs)
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    logger.error(f"Database table creation failed: {e}")

# Initialize FastMCP Server
mcp = FastMCP(
    "User Service MCP Server",
    dependencies=["sqlalchemy", "databases"]
)

@mcp.tool()
def get_user_context(user_id: int, tenant_id: str) -> str:
    """
    Retrieve comprehensive context for a specific user within a tenant.
    This includes profile information, status, and system role.
    
    Args:
        user_id: The unique identifier of the user.
        tenant_id: The identifier of the tenant partition.
    """
    logger.info(f"MCP Tool 'get_user_context' invoked for user_id={user_id}, tenant_id={tenant_id}")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
        if not user:
            return f"Error: User with ID {user_id} not found in tenant '{tenant_id}'."
        
        status_str = "Active" if user.is_active else "Inactive"
        return (
            f"User Context Information:\n"
            f"-------------------------\n"
            f"User ID: {user.id}\n"
            f"Tenant ID: {user.tenant_id}\n"
            f"Username: {user.username}\n"
            f"Email: {user.email}\n"
            f"Status: {status_str}\n"
            f"Role: {user.role}\n"
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_user_context: {str(e)}")
        return f"Database Error: Unable to retrieve user context due to an internal database issue."
    except Exception as e:
        logger.error(f"Unexpected error in get_user_context: {str(e)}")
        return f"Error: An unexpected error occurred: {str(e)}"
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("Starting User Service FastMCP Server...")
    mcp.run()