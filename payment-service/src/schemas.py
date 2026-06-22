from enum import Enum
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    REFUND = "refund"
    CHARGE = "charge"

class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class TransactionBase(BaseModel):
    amount: Decimal = Field(
        ..., 
        gt=0, 
        max_digits=12, 
        decimal_places=2, 
        description="Transaction amount (must be positive and have up to 2 decimal places)"
    )
    currency: str = Field(
        default="USD", 
        min_length=3, 
        max_length=3, 
        description="3-letter ISO currency code"
    )
    description: Optional[str] = Field(
        None, 
        max_length=255, 
        description="Optional transaction description or memo"
    )

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper()

class TransactionCreate(TransactionBase):
    user_id: str = Field(..., description="The unique identifier of the user")
    type: TransactionType = Field(..., description="Type of the transaction (deposit, withdrawal, refund, charge)")
    reference_id: Optional[str] = Field(None, description="External reference ID from payment gateway")

class TransactionResponse(TransactionBase):
    id: str = Field(..., description="Unique transaction identifier")
    user_id: str = Field(..., description="The unique identifier of the user")
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenancy")
    type: TransactionType
    status: TransactionStatus
    reference_id: Optional[str] = Field(None, description="External reference ID if applicable")
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }

class BalanceResponse(BaseModel):
    user_id: str = Field(..., description="The unique identifier of the user")
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenancy")
    balance: Decimal = Field(..., max_digits=12, decimal_places=2, description="Current available balance")
    currency: str = Field(default="USD", description="Currency of the balance")
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }

class DepositRequest(TransactionBase):
    reference_id: Optional[str] = Field(None, description="External payment gateway reference ID")

class WithdrawRequest(TransactionBase):
    reference_id: Optional[str] = Field(None, description="External payment gateway reference ID")

class TransactionHistoryResponse(BaseModel):
    user_id: str = Field(..., description="The unique identifier of the user")
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenancy")
    transactions: List[TransactionResponse] = Field(default_factory=list, description="List of transactions matching query")
    total_count: int = Field(..., description="Total number of transactions matching query")
    current_balance: Decimal = Field(..., description="Current available balance for the user")

    model_config = {
        "from_attributes": True
    }