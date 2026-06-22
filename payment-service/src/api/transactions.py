from typing import List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..main import SessionLocal

router = APIRouter(prefix="/api/payments", tags=["payments"])


class TransactionCreate(BaseModel):
    user_id: str = Field(...)
    amount: float
    transaction_type: str
    description: Optional[str] = None


class TransactionResponse(BaseModel):
    id: int
    tenant_id: str
    user_id: str
    amount: float
    transaction_type: str
    description: Optional[str]
    created_at: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/deposit", response_model=TransactionResponse)
def deposit(tx_in: TransactionCreate, tenant_id: str = Depends(lambda request: request.headers.get("X-Tenant-ID")), db: Session = Depends(get_db)):
    # naive wrapper that reuses main create_transaction logic
    from ..main import create_transaction
    return create_transaction(tx_in, tenant_id=tenant_id, db=db)


@router.get("/balance/{user_id}")
def balance(user_id: str, tenant_id: str = Depends(lambda request: request.headers.get("X-Tenant-ID")), db: Session = Depends(get_db)):
    from ..main import get_balance
    return get_balance(user_id, tenant_id=tenant_id, db=db)


@router.get("/transactions", response_model=List[TransactionResponse])
def transactions(user_id: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, limit: int = 50, offset: int = 0, tenant_id: str = Depends(lambda request: request.headers.get("X-Tenant-ID")), db: Session = Depends(get_db)):
    # reuse main.get_transactions
    from ..main import get_transactions
    return get_transactions(user_id=user_id, start_date=start_date, end_date=end_date, limit=limit, offset=offset, tenant_id=tenant_id, db=db)
