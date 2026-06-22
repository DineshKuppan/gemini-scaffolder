from fastmcp import FastMCP
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Balance, Transaction
import logging
from shared.logging_config import configure_logging
from datetime import datetime

# Configure structured JSON logging
configure_logging("payment-service")
logger = logging.getLogger("payment-service.fastmcp")

# Initialize FastMCP server for the Payment Service
# This allows Claude or other MCP clients to interact with the payment data
mcp = FastMCP("PaymentService")

@mcp.tool()
def get_payment_context(user_id: str, tenant_id: str) -> str:
    """
    Retrieves a comprehensive financial summary for a specific user within a tenant.
    This includes the current balance and the 5 most recent transactions.
    
    Args:
        user_id (str): The unique identifier of the user.
        tenant_id (str): The unique identifier of the tenant (multi-tenant isolation).
    
    Returns:
        str: A formatted string containing the user's financial context or an error message.
    """
    db = SessionLocal()
    try:
        logger.info(f"Fetching payment context for user {user_id} in tenant {tenant_id}")
        
        # Query the balance record
        balance_record = db.query(Balance).filter(
            Balance.user_id == user_id,
            Balance.tenant_id == tenant_id
        ).first()

        if not balance_record:
            return f"No financial record found for User ID: {user_id} under Tenant ID: {tenant_id}."

        # Query the 5 most recent transactions
        recent_transactions = db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.tenant_id == tenant_id
        ).order_by(Transaction.created_at.desc()).limit(5).all()

        # Build the context response
        context = [
            f"--- Payment Context for User: {user_id} ---",
            f"Tenant ID: {tenant_id}",
            f"Current Balance: {balance_record.amount:,.2f} {balance_record.currency}",
            f"Last Updated: {balance_record.updated_at.isoformat() if balance_record.updated_at else 'N/A'}",
            "\nRecent Transaction History:"
        ]

        if not recent_transactions:
            context.append(" - No transactions found for this user.")
        else:
            for tx in recent_transactions:
                timestamp = tx.created_at.strftime("%Y-%m-%d %H:%M:%S")
                tx_type = tx.transaction_type.upper()
                context.append(
                    f" - [{timestamp}] {tx_type}: {tx.amount:,.2f} {tx.currency} "
                    f"(Status: {tx.status}, Ref: {tx.reference_id})"
                )

        return "\n".join(context)

    except Exception as e:
        logger.error(f"Error generating payment context: {str(e)}", exc_info=True)
        return f"Error: An internal error occurred while retrieving payment context for user {user_id}."
    finally:
        db.close()

@mcp.tool()
def check_user_has_funds(user_id: str, tenant_id: str, required_amount: float, currency: str = "USD") -> str:
    """
    Checks if a user has sufficient balance for a proposed transaction.
    
    Args:
        user_id (str): The user identifier.
        tenant_id (str): The tenant identifier.
        required_amount (float): The amount to check against.
        currency (str): The currency code (default: USD).
    """
    db = SessionLocal()
    try:
        balance = db.query(Balance).filter(
            Balance.user_id == user_id,
            Balance.tenant_id == tenant_id,
            Balance.currency == currency
        ).first()

        if not balance:
            return f"User {user_id} has no balance record for {currency}."

        if balance.amount >= required_amount:
            return f"SUCCESS: User has sufficient funds. Current: {balance.amount} {currency}, Required: {required_amount} {currency}."
        else:
            return f"FAILURE: Insufficient funds. Current: {balance.amount} {currency}, Required: {required_amount} {currency}."
    finally:
        db.close()

if __name__ == "__main__":
    # When run directly, start the MCP server
    mcp.run()