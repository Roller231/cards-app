from typing import Optional, Dict, Any
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.order import Order
from app.models.card import Card
from app.models.user import User
from app.integrations.aifory_client import aifory_client


class OrderService:
    """Service for order management and polling."""
    
    async def get_order_status(self, partner_order_id: str) -> Dict[str, Any]:
        """Get order status from Aifory."""
        details = await aifory_client.get_order_details(partner_order_id)
        return {
            "order_id": details.get("orderID"),
            "type": details.get("type"),
            "status_id": details.get("statusID"),
            "amount": details.get("amount"),
            "fee_percent": details.get("feePercent"),
            "fixed_fee": details.get("fixedFee"),
            "client_amount": details.get("clientAmount"),
            "currency_id": details.get("currencyID"),
            "card_id": details.get("cardID"),
            "created_at": details.get("createdAt"),
            "updated_at": details.get("updatedAt"),
        }
    
    async def get_user_order(
        self,
        db: AsyncSession,
        user_id: int,
        order_id: int,
    ) -> Optional[Order]:
        """Get order by ID for a user."""
        result = await db.execute(
            select(Order).where(Order.id == order_id, Order.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_order_by_partner_id(
        self,
        db: AsyncSession,
        partner_order_id: str,
    ) -> Optional[Order]:
        """Get order by partner order ID."""
        result = await db.execute(
            select(Order).where(Order.partner_order_id == partner_order_id)
        )
        return result.scalar_one_or_none()
    
    async def update_order_status(
        self,
        db: AsyncSession,
        partner_order_id: str,
    ) -> Dict[str, Any]:
        """Poll order status and update local DB."""
        # Get status from Aifory
        status_data = await self.get_order_status(partner_order_id)
        status_id = status_data.get("status_id")
        
        # Update local order
        order = await self.get_order_by_partner_id(db, partner_order_id)
        if order:
            order.status = status_id
            
            # If order succeeded and it's a card issue, sync cards
            if status_id == 2 and order.type == "issue":
                aifory_card_id = status_data.get("card_id")
                if aifory_card_id:
                    # Create card record
                    cards_data = await aifory_client.get_cards()
                    for card_data in cards_data.get("cards", []):
                        if card_data.get("cardID") == aifory_card_id:
                            new_card = Card(
                                user_id=order.user_id,
                                partner_card_id=aifory_card_id,
                                last4=card_data.get("cardNumberLastDigits", "0000"),
                                category=card_data.get("category"),
                                status=card_data.get("cardStatus", 2),
                                expired_at=card_data.get("expiredAt"),
                            )
                            db.add(new_card)
                            order.card_id = new_card.id
                            break
            
            # If order failed, refund user balance
            if status_id in [3, 5]:  # Failed or Canceled
                user_result = await db.execute(select(User).where(User.id == order.user_id))
                user = user_result.scalar_one_or_none()
                if user:
                    user.balance += order.amount
            
            await db.commit()
        
        return status_data


order_service = OrderService()
