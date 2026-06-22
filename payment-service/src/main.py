import os
from datetime import datetime
import logging
from shared.logging_config import configure_logging

# Configure structured JSON logging for this service
configure_logging("payment-service")
from typing import List, Optional
from fastapi import FastAPI, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from fastmcp import FastMCP

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./payment.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TenantBalance(Base):
    __tablename__ = "tenant_balances"
    tenant_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, primary_key=True, index=True)
    balance = Column(Float, default=0.0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    transaction_type = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


Base.metadata.create_all(bind=engine)


class TransactionCreate(BaseModel):
    user_id: str = Field(..., example="user_123")
    amount: float = Field(..., description="Positive for deposit, negative for withdrawal")
    transaction_type: str = Field(..., example="deposit")
    description: Optional[str] = Field(None, example="Monthly subscription payment")


class TransactionResponse(BaseModel):
    id: int
    tenant_id: str
    user_id: str
    amount: float
    transaction_type: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class BalanceResponse(BaseModel):
    tenant_id: str
    user_id: str
    balance: float
    updated_at: datetime

    class Config:
        from_attributes = True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    if not x_tenant_id or x_tenant_id.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is missing or empty",
        )
    return x_tenant_id


# FastMCP Server Setup
mcp = FastMCP("Payment Service MCP")


@mcp.tool()
def get_balance_context(tenant_id: str, user_id: str) -> str:
    db = SessionLocal()
    try:
        balance_record = db.query(TenantBalance).filter(
            TenantBalance.tenant_id == tenant_id,
            TenantBalance.user_id == user_id,
        ).first()

        balance = balance_record.balance if balance_record else 0.0

        recent_txs = db.query(Transaction).filter(
            Transaction.tenant_id == tenant_id,
            Transaction.user_id == user_id,
        ).order_by(Transaction.created_at.desc()).limit(5).all()

        tx_list = []
        for tx in recent_txs:
            tx_list.append(
                f"- {tx.created_at.isoformat()}: {tx.transaction_type} of {tx.amount} ({tx.description or 'No description'})"
            )

        tx_history_str = "\n".join(tx_list) if tx_list else "No recent transactions."

        return (
            f"Tenant: {tenant_id}\n"
            f"User ID: {user_id}\n"
            f"Current Balance: ${balance:.2f}\n\n"
            f"Recent Transactions:\n{tx_history_str}"
        )
    finally:
        db.close()


app = FastAPI(
    title="Multi-Tenant Payment Service",
    description="Production-grade payment tracking and transaction history service with FastMCP integration.",
    version="1.0.0",
)


# Register middleware if available (load service-local modules by path to avoid
# cross-service `middleware` package collisions when tests load multiple apps)
try:
    import importlib.util
    svc_dir = os.path.dirname(__file__)
    tenant_path = os.path.join(svc_dir, "middleware", "tenant.py")
    if os.path.exists(tenant_path):
        spec = importlib.util.spec_from_file_location("service_tenant_middleware", tenant_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        TenantMiddleware = getattr(module, "TenantMiddleware")
        if TenantMiddleware:
            app.add_middleware(TenantMiddleware)
except Exception:
    pass

try:
    import importlib.util
    svc_dir = os.path.dirname(__file__)
    logging_path = os.path.join(svc_dir, "middleware", "logging.py")
    if os.path.exists(logging_path):
        spec = importlib.util.spec_from_file_location("service_logging_middleware", logging_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        LoggingMiddleware = getattr(module, "LoggingMiddleware")
        if LoggingMiddleware:
            app.add_middleware(LoggingMiddleware)
except Exception:
    pass


@app.on_event("startup")
def on_startup():
    try:
        logger = __import__("logging").getLogger("payment-service")
        logger.info("Starting payment-service; performing startup checks.")
    except Exception:
        pass


@app.on_event("shutdown")
def on_shutdown():
    try:
        logger = __import__("logging").getLogger("payment-service")
        logger.info("Shutting down payment-service; cleaning up.")
    except Exception:
        pass


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "payment-service"}


try:
    from api.transactions import router as payments_router

    app.include_router(payments_router)
except Exception:
    pass


@app.post("/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    tx_in: TransactionCreate,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    try:
        balance_record = (
            db.query(TenantBalance)
            .filter(TenantBalance.tenant_id == tenant_id, TenantBalance.user_id == tx_in.user_id)
            .with_for_update()
            .first()
        )

        if not balance_record:
            balance_record = TenantBalance(tenant_id=tenant_id, user_id=tx_in.user_id, balance=0.0)
            db.add(balance_record)
            db.flush()

        if tx_in.amount < 0 and (balance_record.balance + tx_in.amount) < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient funds. Current balance: {balance_record.balance}",
            )

        balance_record.balance += tx_in.amount
        balance_record.updated_at = datetime.utcnow()

        db_tx = Transaction(
            tenant_id=tenant_id,
            user_id=tx_in.user_id,
            amount=tx_in.amount,
            transaction_type=tx_in.transaction_type,
            description=tx_in.description,
        )
        db.add(db_tx)
        db.commit()
        db.refresh(db_tx)
        return db_tx
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")


@app.get("/balances/{user_id}", response_model=BalanceResponse)
def get_balance(user_id: str, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)):
    balance_record = db.query(TenantBalance).filter(TenantBalance.tenant_id == tenant_id, TenantBalance.user_id == user_id).first()
    if not balance_record:
        return BalanceResponse(tenant_id=tenant_id, user_id=user_id, balance=0.0, updated_at=datetime.utcnow())
    return balance_record


@app.get("/transactions", response_model=List[TransactionResponse])
def get_transactions(
    user_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    query = db.query(Transaction).filter(Transaction.tenant_id == tenant_id)
    if user_id:
        query = query.filter(Transaction.user_id == user_id)
    if start_date:
        query = query.filter(Transaction.created_at >= start_date)
    if end_date:
        query = query.filter(Transaction.created_at <= end_date)

    transactions = query.order_by(Transaction.created_at.desc()).offset(offset).limit(limit).all()
    return transactions


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
