import os
import logging
from typing import Generator, Optional
from fastapi import FastAPI, Header, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
try:
    import importlib.util
    svc_dir = os.path.dirname(__file__)
    tenant_path = os.path.join(svc_dir, "middleware", "tenant.py")
    if os.path.exists(tenant_path):
        spec = importlib.util.spec_from_file_location("service_tenant_middleware", tenant_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        TenantMiddleware = getattr(module, "TenantMiddleware")
    else:
        TenantMiddleware = None
except Exception:
    TenantMiddleware = None
from pydantic import BaseModel, EmailStr
from shared.logging_config import configure_logging
from sqlalchemy import create_engine, Column, Integer, String, Boolean, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from mcp.server.fastmcp import FastMCP

# Configure structured JSON logging
configure_logging("user-service")
try:
    import importlib.util
    svc_dir = os.path.dirname(__file__)
    logging_path = os.path.join(svc_dir, "middleware", "logging.py")
    if os.path.exists(logging_path):
        spec = importlib.util.spec_from_file_location("service_logging_middleware", logging_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        LoggingMiddleware = getattr(module, "LoggingMiddleware")
    else:
        LoggingMiddleware = None
except Exception:
    LoggingMiddleware = None
logger = logging.getLogger("user-service")

# Database Directory Setup
DATABASE_DIR = os.getenv("DATABASE_DIR", "/tmp")
os.makedirs(DATABASE_DIR, exist_ok=True)

Base = declarative_base()

# SQLAlchemy Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

# Dynamic Tenant Engine Helper with WAL Mode
def get_engine_for_tenant(tenant_id: str):
    db_path = os.path.join(DATABASE_DIR, f"tenant_{tenant_id}.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False}
    )
    
    # Enable Write-Ahead Logging (WAL) for SQLite performance and concurrency
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()
        
    return engine

def init_db(tenant_id: str):
    engine = get_engine_for_tenant(tenant_id)
    Base.metadata.create_all(bind=engine)

# FastAPI App Initialization
app = FastAPI(
    title="Multi-Tenant User Service",
    version="1.0.0",
    description="Production-grade user management service with SQLite WAL isolation per tenant."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Insert tenant middleware early in the pipeline (if loaded)
if TenantMiddleware:
    app.add_middleware(TenantMiddleware)


@app.on_event("startup")
def on_startup():
    logger.info("Starting user-service; ensuring database directory exists and ready.")


if LoggingMiddleware:
    app.add_middleware(LoggingMiddleware)
@app.on_event("shutdown")
def on_shutdown():
    logger.info("Shutting down user-service; closing connections if any.")


# Register API routers
try:
    from api.users import router as users_router
    app.include_router(users_router)
except Exception:
    pass


# FastMCP Server Instance for LLM Context Integration
mcp = FastMCP("User Service Context Provider")

@mcp.tool()
def get_user_context(tenant_id: str, user_id: int) -> str:
    """
    Retrieve the full context of a user for LLM evaluation and routing.
    """
    try:
        engine = get_engine_for_tenant(tenant_id)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return f"User {user_id} not found in tenant {tenant_id}."
            return f"User Context: ID={user.id}, Email={user.email}, Name={user.full_name}, Active={user.is_active}"
    except Exception as e:
        logger.error(f"Error fetching user context: {str(e)}")
        return f"Error retrieving user context: {str(e)}"

# Pydantic Schemas
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: Optional[bool] = True

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    id: int

    class Config:
        from_attributes = True

# Dependencies
def get_db(x_tenant_id: str = Header(..., description="Tenant Identifier")) -> Generator[Session, None, None]:
    if not x_tenant_id or not x_tenant_id.isalnum():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing X-Tenant-ID header. Only alphanumeric characters allowed."
        )
    init_db(x_tenant_id)
    engine = get_engine_for_tenant(x_tenant_id)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# REST Endpoints
@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists in this tenant."
        )
    db_user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        is_active=user_in.is_active
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    return user

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "user-service"}

# Dual-mode FastMCP SSE Endpoint Integration
@app.get("/mcp/tools")
def list_mcp_tools():
    return {
        "tools": [
            {
                "name": "get_user_context",
                "description": "Retrieve the full context of a user for LLM evaluation.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tenant_id": {"type": "string"},
                        "user_id": {"type": "integer"}
                    },
                    "required": ["tenant_id", "user_id"]
                }
            }
        ]
    }

@app.post("/mcp/tools/get_user_context")
def call_get_user_context(payload: dict):
    tenant_id = payload.get("tenant_id")
    user_id = payload.get("user_id")
    if not tenant_id or user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant_id or user_id in payload."
        )
    context = get_user_context(tenant_id, int(user_id))
    return {"result": context}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)