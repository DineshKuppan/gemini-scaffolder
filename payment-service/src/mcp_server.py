import os
import logging
from shared.logging_config import configure_logging
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, desc
from sqlalchemy.orm import sessionmaker, declarative_base
from fastmcp import FastMCP

# Configure structured JSON logging
configure_logging("payment-service")
logger = logging.getLogger("payment-service-mcp")

# Initialize FastMCP Server
mcp = FastMCP("Payment Service MCP")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///payment_service.db")

# SQLite WAL mode setup for high concurrency
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

if DATABASE_URL.startswith("sqlite"):
    try:
        with engine.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            logger.info("SQLite WAL mode enabled successfully.")
    except Exception as e:
        logger.error(f"Failed to set SQLite WAL mode: {e}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class Balance(Base):
    __tablename__ = "balances"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    balance = Column(Float, default=0.0, nullable=False)
    currency = Column(String, default="USD", nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)  # 'credit' or 'debit'
    status = Column(String, default="completed", nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

# Ensure tables exist
Base.metadata.create_all(bind=engine)

@mcp.tool()
def get_payment_context(tenant_id: str, user_id: str) -> str:
    """
    Retrieve the payment context for a specific user within a tenant.
    This includes current balance and recent transaction history.
    """
    logger.info(f"Fetching payment context for tenant: {tenant_id}, user: {user_id}")
    db = SessionLocal()
    try:
        balance_record = db.query(Balance).filter(
            Balance.tenant_id == tenant_id,
            Balance.user_id == user_id
        ).first()

        transactions = db.query(Transaction).filter(
            Transaction.tenant_id == tenant_id,
            Transaction.user_id == user_id
        ).order_by(desc(Transaction.created_at)).limit(10).all()

        balance_amount = balance_record.balance if balance_record else 0.0
        currency = balance_record.currency if balance_record else "USD"

        tx_list = []
        for tx in transactions:
            tx_list.append({
                "id": tx.id,
                "amount": tx.amount,
                "type": tx.type,
                "status": tx.status,
                "description": tx.description,
                "created_at": tx.created_at.isoformat()
            })

        context = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "balance": balance_amount,
            "currency": currency,
            "recent_transactions": tx_list
        }
        return json.dumps(context, indent=2)
    except Exception as e:
        logger.error(f"Error retrieving payment context: {str(e)}")
        return json.dumps({"error": f"Failed to retrieve payment context: {str(e)}"})
    finally:
        db.close()

@mcp.tool()
def record_transaction(tenant_id: str, user_id: str, amount: float, tx_type: str, description: str = None) -> str:
    """
    Record a transaction (credit or debit) and update the user's balance.
    tx_type must be 'credit' or 'debit'.
    """
    logger.info(f"Recording {tx_type} transaction of {amount} for tenant: {tenant_id}, user: {user_id}")
    if tx_type not in ["credit", "debit"]:
        return json.dumps({"error": "Invalid transaction type. Must be 'credit' or 'debit'."})
    if amount <= 0:
        return json.dumps({"error": "Transaction amount must be greater than zero."})

    db = SessionLocal()
    try:
        # Find or create balance record
        balance_record = db.query(Balance).filter(
            Balance.tenant_id == tenant_id,
            Balance.user_id == user_id
        ).first()

        if not balance_record:
            balance_record = Balance(
                tenant_id=tenant_id,
                user_id=user_id,
                balance=0.0,
                currency="USD"
            )
            db.add(balance_record)
            db.flush()

        # Calculate and verify balance updates
        if tx_type == "credit":
            balance_record.balance += amount
        elif tx_type == "debit":
            if balance_record.balance < amount:
                return json.dumps({"error": "Insufficient funds for debit transaction."})
            balance_record.balance -= amount

        # Record transaction log
        tx = Transaction(
            tenant_id=tenant_id,
            user_id=user_id,
            amount=amount,
            type=tx_type,
            status="completed",
            description=description
        )
        db.add(tx)
        db.commit()

        return json.dumps({
            "success": True,
            "new_balance": balance_record.balance,
            "currency": balance_record.currency,
            "transaction_id": tx.id
        })
    except Exception as e:
        db.rollback()
        logger.error(f"Transaction failed: {str(e)}")
        return json.dumps({"error": f"Transaction failed: {str(e)}"})
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("Starting Payment Service MCP Server...")
    mcp.run()