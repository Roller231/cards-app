from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.card import Card
from app.integrations.aifory_client import aifory_client


class TransactionService:
    """Service for transaction management."""
    
    async def get_card_transactions(
        self,
        db: AsyncSession,
        user_id: int,
        card_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get transactions for a card."""
        result = await db.execute(
            select(Card).where(Card.id == card_id, Card.user_id == user_id)
        )
        card = result.scalar_one_or_none()
        if not card:
            raise ValueError("Card not found")
        
        tx_data = await aifory_client.get_card_transactions(
            card_id=card.partner_card_id,
            limit=limit,
            offset=offset,
        )
        
        transactions = []
        for tx in tx_data.get("transactions", []):
            transactions.append({
                "transaction_id": tx.get("transactionID"),
                "type": tx.get("type"),
                "amount": tx.get("amount"),
                "status_id": tx.get("statusID"),
                "created_at": tx.get("createdAt"),
            })
        
        return transactions
    
    async def get_transaction_details(
        self,
        db: AsyncSession,
        user_id: int,
        card_id: int,
        transaction_id: str,
    ) -> Dict[str, Any]:
        """Get transaction details."""
        result = await db.execute(
            select(Card).where(Card.id == card_id, Card.user_id == user_id)
        )
        card = result.scalar_one_or_none()
        if not card:
            raise ValueError("Card not found")
        
        details = await aifory_client.get_transaction_details(
            card_id=card.partner_card_id,
            transaction_id=transaction_id,
        )
        
        return {
            "transaction_id": transaction_id,
            "type": details.get("type"),
            "status_id": details.get("statusID"),
            "card_id": details.get("cardID"),
            "amount": details.get("amount"),
            "currency_id": details.get("currencyID"),
            "created_at": details.get("createdAt"),
            "merchant": details.get("merchant"),
            "failure_reason": details.get("failureReason"),
        }


transaction_service = TransactionService()
