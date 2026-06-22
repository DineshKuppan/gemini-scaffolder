import json
import logging
from shared.logging_config import configure_logging
from typing import Optional, Dict, Any
from fastmcp import FastMCP
from sqlalchemy.orm import Session
from sqlalchemy import select
from .database import SessionLocal
from .models import User

# Configure structured JSON logging
configure_logging("user-service")
logger = logging.getLogger("user-service.mcp")

# Initialize FastMCP server for the User Service
mcp = FastMCP("UserServiceContext")

@mcp.tool()
def get_user_context(user_id: int, tenant_id: str) -> str:
    """
    Retrieves the comprehensive context for a specific user within a multi-tenant environment.
    This tool is used by LLMs to understand the user's profile, status, and identity constraints.
    
    Args:
        user_id (int): The unique identifier of the user.
        tenant_id (str): The unique identifier of the tenant/organization.
        
    Returns:
        str: A JSON string containing user details or an error message.
    """
    logger.info(f"MCP Tool: Fetching context for user {user_id} in tenant {tenant_id}")
    
    db: Session = SessionLocal()
    try:
        # Query user with strict tenant isolation
        query = select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id
        )
        result = db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"User {user_id} not found for tenant {tenant_id}")
            return json.dumps({
                "status": "error",
                "message": "User not found or access denied for this tenant.",
                "context": {"user_id": user_id, "tenant_id": tenant_id}
            })

        # Construct the context object
        user_context = {
            "status": "success",
            "data": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "tenant_id": user.tenant_id,
                "is_active": user.is_active,
                "role": getattr(user, "role", "user"),
                "created_at": user.created_at.isoformat() if hasattr(user, "created_at") and user.created_at else None,
                "last_login": user.last_login.isoformat() if hasattr(user, "last_login") and user.last_login else None
            }
        }
        
        return json.dumps(user_context)

    except Exception as e:
        logger.error(f"Error in get_user_context tool: {str(e)}")
        return json.dumps({
            "status": "error",
            "message": "Internal server error while retrieving user context.",
            "details": str(e)
        })
    finally:
        db.close()

if __name__ == "__main__":
    # This allows the tool to be run directly for testing or as a standalone MCP server
    mcp.run()