from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
from typing import List, Optional
from . import models, schemas

def get_balance(db: Session, tenant_id: str, user_id: str) -> models.Balance:
    """
    Retrieves the current balance for a specific user within a tenant.
    If no balance record exists, one is initialized at 0.0.
    """
    balance = db.query(models.Balance).filter(
        models.Balance.tenant_id == tenant_id,
        models.Balance.user_id == user_id
    ).first()
    
    if not balance:
        balance = models.Balance(
            tenant_id=tenant_id, 
            user_id=user_id, 
            amount=0.0,
            updated_at=datetime.utcnow()
        )
        db.add(balance)
        db.commit()
        db.refresh(balance)
    
    return balance

def create_transaction(
    db: Session, 
    tenant_id: str, 
    user_id: str, 
    amount: float, 
    transaction_type: str, 
    description: str = ""
) -> models.Transaction:
    """
    Executes a transaction by updating the user's balance and creating a transaction log entry.
    Uses 'with_for_update' to ensure atomicity during the balance shift.
    """
    # Lock the balance row for update to prevent race conditions
    balance = db.query(models.Balance).filter(
        models.Balance.tenant_id == tenant_id,
        models.Balance.user_id == user_id
    ).with_for_update().first()

    if not balance:
        balance = models.Balance(
            tenant_id=tenant_id, 
            user_id=user_id, 
            amount=0.0,
            updated_at=datetime.utcnow()
        )
        db.add(balance)

    # Update balance amount
    balance.amount += amount
    balance.updated_at = datetime.utcnow()

    # Create the transaction record
    db_transaction = models.Transaction(
        tenant_id=tenant_id,
        user_id=user_id,
        amount=amount,
        transaction_type=transaction_type,
        description=description,
        timestamp=datetime.utcnow()
    )
    
    db.add(db_transaction)
    
    try:
        db.commit()
        db.refresh(db_transaction)
        return db_transaction
    except Exception as e:
        db.rollback()
        raise e

def get_transactions(
    db: Session, 
    tenant_id: str, 
    user_id: str, 
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None, 
    skip: int = 0, 
    limit: int = 100
) -> List[models.Transaction]:
    """
    Retrieves transaction history for a user, filtered by tenant and optional date ranges.
    Results are ordered by timestamp descending.
    """
    query = db.query(models.Transaction).filter(
        models.Transaction.tenant_id == tenant_id,
        models.Transaction.user_id == user_id
    )

    if start_date:
        query = query.filter(models.Transaction.timestamp >= start_date)
    if end_date:
        query = query.filter(models.Transaction.timestamp <= end_date)

    return query.order_by(models.Transaction.timestamp.desc()).offset(skip).limit(limit).all()

def get_tenant_transaction_summary(db: Session, tenant_id: str) -> dict:
    """
    Aggregates transaction data for a specific tenant for reporting purposes.
    """
    from sqlalchemy import func
    total_volume = db.query(func.sum(models.Transaction.amount)).filter(
        models.Transaction.tenant_id == tenant_id
    ).scalar() or 0.0
    
    transaction_count = db.query(func.count(models.Transaction.id)).filter(
        models.Transaction.tenant_id == tenant_id
    ).scalar() or 0

    return {
        "tenant_id": tenant_id,
        "total_volume": total_volume,
        "transaction_count": transaction_count
    }