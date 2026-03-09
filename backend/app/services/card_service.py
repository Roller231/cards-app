from typing import List, Optional, Dict, Any
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.card import Card
from app.models.order import Order
from app.models.user import User
from app.integrations.aifory_client import aifory_client


class CardService:
    """Service for card management."""
    
    async def get_account_id(self) -> str:
        """Get accountID from Aifory for operations."""
        accounts_data = await aifory_client.get_accounts()
        # Extract first available account ID
        groups = accounts_data.get("groups", [])
        for group in groups:
            wallets = group.get("wallets", [])
            for wallet in wallets:
                accounts = wallet.get("accounts", [])
                if accounts:
                    return accounts[0].get("id")
        
        ungrouped = accounts_data.get("ungroupedWallets", [])
        for wallet in ungrouped:
            accounts = wallet.get("accounts", [])
            if accounts:
                return accounts[0].get("id")
        
        raise ValueError("No account found in Aifory")
    
    async def get_offers(self) -> Dict[str, Any]:
        """Get available card offers."""
        return await aifory_client.get_card_offers()
    
    async def calculate_issue(
        self,
        bin: str,
        amount: str,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate fees for card issuance."""
        if not account_id:
            account_id = await self.get_account_id()
        return await aifory_client.calculate_card_order(bin, amount, account_id)
    
    async def issue_card(
        self,
        db: AsyncSession,
        user_id: int,
        bin: str,
        amount: str,
        email: str,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Issue a new card."""
        if not account_id:
            account_id = await self.get_account_id()
        
        # Deduct from user balance
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")
        
        amount_decimal = Decimal(amount)
        if user.balance < amount_decimal:
            raise ValueError("Insufficient balance")
        
        user.balance -= amount_decimal
        
        # Create order in Aifory
        order_data = await aifory_client.create_card_order(
            bin=bin,
            amount=amount,
            email=email,
            account_id=account_id,
        )
        
        order_id = order_data.get("orderID")
        
        # Save order locally
        order = Order(
            user_id=user_id,
            partner_order_id=order_id,
            type="issue",
            amount=amount_decimal,
            status=1,  # Pending
        )
        db.add(order)
        await db.commit()
        
        return {"order_id": order_id}
    
    async def get_user_cards(self, db: AsyncSession, user_id: int) -> List[Card]:
        """Get all cards for a user."""
        result = await db.execute(
            select(Card).where(Card.user_id == user_id).order_by(Card.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_card(self, db: AsyncSession, user_id: int, card_id: int) -> Optional[Card]:
        """Get a specific card."""
        result = await db.execute(
            select(Card).where(Card.id == card_id, Card.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_card_requisites(self, db: AsyncSession, user_id: int, card_id: int) -> Dict[str, Any]:
        """Get card requisites from Aifory. DO NOT STORE!"""
        card = await self.get_card(db, user_id, card_id)
        if not card:
            raise ValueError("Card not found")
        
        requisites = await aifory_client.get_card_requisites(card.partner_card_id)
        return {
            "card_number": requisites.get("cardNumber"),
            "cvv": requisites.get("cvv"),
            "card_holder_name": requisites.get("cardHolderName"),
            "country": requisites.get("country"),
            "country_name": requisites.get("countryName"),
            "street": requisites.get("street"),
            "city": requisites.get("city"),
            "postal_code": requisites.get("postalCode"),
        }
    
    async def sync_cards_from_aifory(self, db: AsyncSession, user_id: int) -> List[Card]:
        """Sync cards from Aifory to local DB."""
        aifory_cards = await aifory_client.get_cards()
        cards_data = aifory_cards.get("cards", [])
        
        for card_data in cards_data:
            partner_card_id = card_data.get("cardID")
            
            # Check if card exists
            result = await db.execute(
                select(Card).where(Card.partner_card_id == partner_card_id)
            )
            existing_card = result.scalar_one_or_none()
            
            if existing_card:
                # Update status
                existing_card.status = card_data.get("cardStatus", existing_card.status)
            else:
                # Create new card record
                new_card = Card(
                    user_id=user_id,
                    partner_card_id=partner_card_id,
                    last4=card_data.get("cardNumberLastDigits", "0000"),
                    category=card_data.get("category"),
                    status=card_data.get("cardStatus", 1),
                    expired_at=card_data.get("expiredAt"),
                )
                db.add(new_card)
        
        await db.commit()
        return await self.get_user_cards(db, user_id)


card_service = CardService()
