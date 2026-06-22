import datetime
import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models in the payment service.
    """
    pass

class Wallet(Base):
    """
    Represents a tenant-scoped user wallet tracking balance and currency.
    """
    __tablename__ = "wallets"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        description="Unique identifier for the wallet"
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        description="Identifier for the tenant partition"
    )
    user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        description="Identifier for the user owning this wallet"
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
        nullable=False,
        description="Current balance of the wallet"
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
        description="ISO 4217 currency code"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False
    )

    # Relationships
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="wallet",
        cascade="all, delete-orphan"
    )

    # Constraints & Indexes
    __table_args__ = (
        Index("ix_wallet_tenant_user", "tenant_id", "user_id", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "balance": str(self.balance),
            "currency": self.currency,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

class Transaction(Base):
    """
    Represents a ledger transaction entry for auditability and history.
    """
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        description="Unique identifier for the transaction"
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        description="Identifier for the tenant partition"
    )
    user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        description="Identifier for the user associated with this transaction"
    )
    wallet_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        description="Foreign key referencing the associated wallet"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        description="Absolute amount of the transaction"
    )
    type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        description="Transaction type: CREDIT or DEBIT"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="COMPLETED",
        nullable=False,
        description="Transaction status: PENDING, COMPLETED, FAILED"
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        description="Optional description or reference for the transaction"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
        index=True
    )

    # Relationships
    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")

    # Constraints & Indexes
    __table_args__ = (
        Index("ix_transaction_tenant_date", "tenant_id", "created_at"),
        Index("ix_transaction_wallet_date", "wallet_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "wallet_id": self.wallet_id,
            "amount": str(self.amount),
            "type": self.type,
            "status": self.status,
            "description": self.description,
            "created_at": self.created_at.isoformat()
        }