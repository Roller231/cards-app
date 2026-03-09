from typing import Optional, Dict, Any
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.card import Card
from app.models.order import Order
from app.models.user import User
from app.integrations.aifory_client import aifory_client
from app.services.card_service import card_service


class DepositService:
    """Service for card top-up/deposit operations."""
    
    async def get_deposit_offer(self, db: AsyncSession, user_id: int, card_id: int) -> Dict[str, Any]:
        """Get deposit offer for a card."""
        result = await db.execute(
            select(Card).where(Card.id == card_id, Card.user_id == user_id)
        )
        card = result.scalar_one_or_none()
        if not card:
            raise ValueError("Card not found")
        
        offer = await aifory_client.get_deposit_offer(card.partner_card_id)
        return {
            "min_deposit_amount": offer.get("minDepositAmount"),
            "max_deposit_amount": offer.get("maxDepositAmount"),
            "card_deposit_fee_percent": offer.get("cardDepositFeePercent"),
        }
    
    async def calculate_deposit(
        self,
        db: AsyncSession,
        user_id: int,
        card_id: int,
        amount: str,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate fees for deposit."""
        result = await db.execute(
            select(Card).where(Card.id == card_id, Card.user_id == user_id)
        )
        card = result.scalar_one_or_none()
        if not card:
            raise ValueError("Card not found")
        
        if not account_id:
            account_id = await card_service.get_account_id()
        
        calc = await aifory_client.calculate_deposit_order(
            card_id=card.partner_card_id,
            amount=amount,
            account_id=account_id,
        )
        return {
            "amount": calc.get("amount"),
            "fee": calc.get("fee"),
        }
    
    async def create_deposit(
        self,
        db: AsyncSession,
        user_id: int,
        card_id: int,
        amount: str,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create deposit order to top up a card."""
        result = await db.execute(
            select(Card).where(Card.id == card_id, Card.user_id == user_id)
        )
        card = result.scalar_one_or_none()
        if not card:
            raise ValueError("Card not found")
        
        # Check user balance
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")
        
        amount_decimal = Decimal(amount)
        if user.balance < amount_decimal:
            raise ValueError("Insufficient balance")
        
        # Deduct from user balance
        user.balance -= amount_decimal
        
        if not account_id:
            account_id = await card_service.get_account_id()
        
        # Create deposit order in Aifory
        order_data = await aifory_client.create_deposit_order(
            card_id=card.partner_card_id,
            amount=amount,
            account_id=account_id,
        )
        
        order_id = order_data.get("orderID")
        
        # Save order locally
        order = Order(
            user_id=user_id,
            partner_order_id=order_id,
            card_id=card.id,
            type="topup",
            amount=amount_decimal,
            status=1,  # Pending
        )
        db.add(order)
        await db.commit()
        
        return {"order_id": order_id}


deposit_service = DepositService()
