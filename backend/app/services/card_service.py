import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.aifory_client import aifory_client
from app.models.card import Card
from app.models.order import Order
from app.models.user import User

logger = logging.getLogger(__name__)


class CardService:
    async def _get_usdt_accounts(self) -> Dict[str, str]:
        """Return USDT ERC-20 (accountID) and USDT TRC-20 (accountIDToExchange) account IDs.

        Aifory processes all card operations through a USDT exchange flow:
          accountID           = USDT ERC-20 (currencyID: 2000) - source funds
          accountIDToExchange = USDT TRC-20 (currencyID: 2001) - exchange target
        """
        accounts = await aifory_client.get_accounts()
        if not accounts:
            raise ValueError("No accounts found on parent Aifory account")

        usdt_erc20: Optional[str] = None
        usdt_trc20: Optional[str] = None

        for acc in accounts:
            cid = acc.get("currencyID") or acc.get("currencyId")
            aid = acc.get("id") or acc.get("accountId") or acc.get("accountID")
            try:
                cid_int = int(cid)
            except (TypeError, ValueError):
                continue
            if cid_int == 2000 and aid:
                usdt_erc20 = str(aid)
            elif cid_int == 2001 and aid:
                usdt_trc20 = str(aid)

        if not usdt_erc20:
            raise ValueError("USDT ERC-20 account (currencyID=2000) not found on parent Aifory account")
        if not usdt_trc20:
            raise ValueError("USDT TRC-20 account (currencyID=2001) not found on parent Aifory account")

        return {"account_id": usdt_erc20, "account_id_to_exchange": usdt_trc20}

    # ------------------------------------------------------------------
    # Offers
    # ------------------------------------------------------------------

    async def get_offers(self) -> List[Dict[str, Any]]:
        """Return available card offer products from Aifory (categories 2 and 3 only)."""
        raw = await aifory_client.get_card_offers_simple()
        markup = float(settings.CARD_ISSUE_MARKUP_PERCENT)

        offers = []
        for o in raw:
            category = o.get("category")
            if category == 1:
                continue

            currency_id = o.get("createCardCurrency")
            if currency_id == 1010:
                currency_str = "USD"
            elif currency_id == 1020:
                currency_str = "EUR"
            else:
                currency_str = str(currency_id) if currency_id else "Unknown"

            aifory_fee_percent = float(o.get("createCardFeePercent") or 0)
            display_fee_percent = aifory_fee_percent + markup

            offers.append(
                {
                    "id": o.get("bin"),
                    "name": f"Virtual Card (Category {category})",
                    "currency": currency_str,
                    "currency_id": currency_id,
                    "category": category,
                    "issue_fee": float(o.get("createCardFixedFee") or 0),
                    "fee_percent": display_fee_percent,
                    "monthly_fee": 0.0,
                    "min_amount": float(o.get("minAmount") or 15.0),
                    "max_amount": float(o.get("maxAmount") or 50000.0),
                    "description": f"Min: ${o.get('minAmount')}, Max: ${o.get('maxAmount')}",
                }
            )
        return offers

    # ------------------------------------------------------------------
    # Issue card
    # ------------------------------------------------------------------

    async def issue_card(
        self,
        db: AsyncSession,
        user: User,
        offer_id: str,
        holder_first_name: str,
        holder_last_name: str,
        amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Create a card issuance order via Aifory.
        Uses USDT ERC-20/TRC-20 accounts + client-generated validateKey.
        Charges user: Aifory's clientAmount * (1 + CARD_ISSUE_MARKUP_PERCENT / 100).
        """
        # 1. Find offer and determine card amount
        offers_raw = await aifory_client.get_card_offers_simple()
        offer = next((o for o in offers_raw if str(o.get("bin")) == str(offer_id)), None)
        if not offer:
            raise ValueError(f"Offer '{offer_id}' not found")

        min_amount = float(offer.get("minAmount") or 15.0)
        card_amount = float(amount) if (amount and float(amount) >= min_amount) else min_amount

        # 2. Get USDT ERC-20 and TRC-20 account IDs
        usdt = await self._get_usdt_accounts()

        # 3. Client-generated idempotency key (same key used for calculate + order)
        validate_key = str(uuid.uuid4())

        # 4. Commission logic: user pays amount + our markup, Aifory gets only amount
        # Example: user wants $20 card, pays $20 + 5% = $21, Aifory gets $20
        card_amount_decimal = Decimal(str(card_amount))
        markup = Decimal(str(settings.CARD_ISSUE_MARKUP_PERCENT))
        our_fee = card_amount_decimal * markup / Decimal("100")
        user_total = card_amount_decimal + our_fee  # User pays: $20 + $1 = $21
        
        # Send only the requested card amount to Aifory (without our commission)
        aifory_amount = card_amount_decimal  # Aifory gets: $20
        our_profit = our_fee  # Our profit: $1

        # 6. Check user balance
        if Decimal(str(user.balance)) < user_total:
            raise ValueError(
                f"Insufficient balance. Required: {user_total:.2f} USD, available: {user.balance}"
            )

        # 7. Place order on Aifory - send only the card amount (without our commission)
        result = await aifory_client.create_card_order(
            account_id=usdt["account_id"],
            offer_id=offer_id,
            amount=float(aifory_amount),  # Send $20 to Aifory, not $21
            account_id_to_exchange=usdt["account_id_to_exchange"],
            validate_key=validate_key,
        )
        partner_order_id = (
            result.get("orderID") or result.get("orderId") or result.get("id")
        )
        logger.info(
            "Card order created: partner_order_id=%s user_id=%s card_amount=%s user_charge=%s",
            partner_order_id, user.id, card_amount, user_total,
        )

        # 8. Deduct from user balance
        user.balance = Decimal(str(user.balance)) - user_total

        # 9. Save order record with completed status
        order = Order(
            user_id=user.id,
            partner_order_id=partner_order_id,
            type="issue",
            amount=user_total,
            fee=our_profit,
            status="completed",
            description=f"Card issuance: offer {offer_id}, card balance: ${card_amount:.2f}",
        )
        db.add(order)
        await db.flush()

        # 10. Immediately fetch order details to get card data
        try:
            details = await aifory_client.get_order_details(partner_order_id)
            aifory_card_id = details.get("cardID") or details.get("cardId")
            status_id = details.get("statusID") or details.get("statusId")
            
            # Update order with Aifory status
            if status_id is not None:
                order.aifory_status_id = int(status_id)
            
            # Create card record if we have cardID
            if aifory_card_id:
                # Get card details from Aifory cards list
                aifory_cards = await aifory_client.get_cards("")
                card_data = None
                for c in aifory_cards:
                    cid = c.get("cardID") or c.get("cardId") or c.get("id")
                    if str(cid) == str(aifory_card_id):
                        card_data = c
                        break
                
                if card_data:
                    currency_id = card_data.get("currencyID") or offer.get("createCardCurrency")
                    currency_str = "USD" if currency_id == 1010 else ("EUR" if currency_id == 1020 else str(currency_id or ""))
                    
                    card = Card(
                        user_id=user.id,
                        aifory_card_id=str(aifory_card_id),
                        category=card_data.get("category") or offer.get("category"),
                        card_status=card_data.get("cardStatus"),
                        expired_at=card_data.get("expiredAt"),
                        last4=str(card_data.get("cardNumberLastDigits") or ""),
                        holder_name=f"{holder_first_name} {holder_last_name}",
                        currency=currency_str,
                        currency_id=currency_id,
                        payment_system_id=card_data.get("paymentSystemID"),
                        balance=Decimal(str(card_data.get("balance") or card_amount)),
                        status="active" if card_data.get("cardStatus") == 2 else "inactive",
                        offer_id=offer_id,
                    )
                    db.add(card)
                    await db.flush()
                    
                    # Link order to card
                    order.card_id = card.id
                    
                    logger.info(
                        "Card created immediately: card_id=%s aifory_card_id=%s user_id=%s",
                        card.id, aifory_card_id, user.id
                    )
                else:
                    logger.warning("Card data not found in Aifory cards list for cardID=%s", aifory_card_id)
            else:
                logger.warning("No cardID returned in order details for order=%s", partner_order_id)
                
        except Exception as exc:
            logger.error("Failed to fetch order details immediately: %s", exc)
            # Don't fail the whole operation, just log the error

        return {"local_order_id": order.id, "partner_order_id": partner_order_id}

    # ------------------------------------------------------------------
    # Sync cards from Aifory into local DB
    # ------------------------------------------------------------------

    async def sync_cards(self, db: AsyncSession, user: User) -> List[Card]:
        """
        Pull all cards from the parent Aifory account, update balances/status,
        and link any un-linked pending issue orders to their resulting card.
        """
        # Build map of all Aifory cards: cardID → raw card dict
        aifory_cards = await aifory_client.get_cards("")
        aifory_map: Dict[str, Dict] = {}
        for c in aifory_cards:
            cid = c.get("cardID") or c.get("cardId") or c.get("id")
            if cid:
                aifory_map[str(cid)] = c

        # Update balances/status for already-linked cards
        all_cards_result = await db.execute(select(Card).where(Card.user_id == user.id))
        for card in all_cards_result.scalars().all():
            if card.aifory_card_id and card.aifory_card_id in aifory_map:
                raw = aifory_map[card.aifory_card_id]
                card.card_status = raw.get("cardStatus")
                card.balance = Decimal(str(raw.get("balance") or 0))
                card.status = "active" if raw.get("cardStatus") == 2 else "inactive"

        # Find pending issue orders without a linked card
        pending_result = await db.execute(
            select(Order).where(
                Order.user_id == user.id,
                Order.type == "issue",
                Order.card_id.is_(None),
                Order.partner_order_id.isnot(None),
            )
        )
        for order in pending_result.scalars().all():
            try:
                details = await aifory_client.get_order_details(order.partner_order_id)
            except Exception as exc:
                logger.warning("Could not fetch order %s: %s", order.partner_order_id, exc)
                continue

            aifory_card_id = details.get("cardID") or details.get("cardId")
            status_id = details.get("statusID") or details.get("statusId")
            aifory_type = details.get("type")
            holder_name = details.get("cardHolderName")

            if status_id is not None:
                order.aifory_status_id = int(status_id)
                if status_id == 2:
                    order.status = "active"
                elif status_id == 3:
                    order.status = "failed"
            if aifory_type is not None:
                order.aifory_type = int(aifory_type)

            if not aifory_card_id:
                continue

            raw = aifory_map.get(str(aifory_card_id))
            if not raw:
                continue

            existing_result = await db.execute(
                select(Card).where(Card.aifory_card_id == str(aifory_card_id))
            )
            card = existing_result.scalar_one_or_none()
            if not card:
                currency_id = raw.get("currencyID")
                currency_str = "USD" if currency_id == 1010 else ("EUR" if currency_id == 1020 else str(currency_id or ""))
                desc_parts = (order.description or "").split("offer ")
                extracted_offer_id = desc_parts[-1].split(",")[0] if len(desc_parts) > 1 else None
                card = Card(
                    user_id=user.id,
                    aifory_card_id=str(aifory_card_id),
                    category=raw.get("category"),
                    card_status=raw.get("cardStatus"),
                    expired_at=raw.get("expiredAt"),
                    last4=str(raw.get("cardNumberLastDigits") or ""),
                    holder_name=holder_name,
                    currency=currency_str,
                    currency_id=currency_id,
                    payment_system_id=raw.get("paymentSystemID"),
                    balance=Decimal(str(raw.get("balance") or 0)),
                    status="active" if raw.get("cardStatus") == 2 else "inactive",
                    offer_id=extracted_offer_id or None,
                )
                db.add(card)
                await db.flush()
            else:
                card.card_status = raw.get("cardStatus")
                card.balance = Decimal(str(raw.get("balance") or 0))
                card.status = "active" if raw.get("cardStatus") == 2 else "inactive"
                if holder_name and not card.holder_name:
                    card.holder_name = holder_name

            order.card_id = card.id

        final_result = await db.execute(select(Card).where(Card.user_id == user.id))
        return list(final_result.scalars().all())

    # ------------------------------------------------------------------
    # Get user cards (local)
    # ------------------------------------------------------------------

    async def get_user_cards(self, db: AsyncSession, user_id: int) -> List[Card]:
        result = await db.execute(select(Card).where(Card.user_id == user_id))
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Get card requisites
    # ------------------------------------------------------------------

    async def get_card_requisites(self, db: AsyncSession, user_id: int, card_id: str) -> Dict:
        # Prefer lookup by Aifory card ID (UUID string). Fallback to local numeric ID if digits.
        if isinstance(card_id, str) and not card_id.isdigit():
            result = await db.execute(
                select(Card).where(Card.aifory_card_id == card_id, Card.user_id == user_id)
            )
        else:
            result = await db.execute(
                select(Card).where(Card.id == int(card_id), Card.user_id == user_id)
            )
        card = result.scalar_one_or_none()
        if not card:
            raise ValueError("Card not found")
        if not card.aifory_card_id:
            raise ValueError("Card is not yet linked to Aifory (issuance may still be pending)")

        raw = await aifory_client.get_card_requisites(card.aifory_card_id)
        return {
            "card_number": raw.get("cardNumber") or raw.get("pan") or raw.get("number"),
            "expiry": raw.get("expiredAt") or raw.get("expiry") or raw.get("expiryDate"),
            "cvv": raw.get("cvv"),
            "holder_name": raw.get("cardHolderName") or raw.get("holderName") or card.holder_name,
            "street": raw.get("street"),
            "city": raw.get("city"),
            "postal_code": raw.get("postalCode"),
            "country_name": raw.get("countryName"),
        }

    # ------------------------------------------------------------------
    # Get card transactions
    # ------------------------------------------------------------------

    async def get_card_transactions(
        self,
        db: AsyncSession,
        user_id: int,
        card_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        if isinstance(card_id, str) and not card_id.isdigit():
            result = await db.execute(
                select(Card).where(Card.aifory_card_id == card_id, Card.user_id == user_id)
            )
        else:
            result = await db.execute(
                select(Card).where(Card.id == int(card_id), Card.user_id == user_id)
            )
        card = result.scalar_one_or_none()
        if not card:
            raise ValueError("Card not found")
        if not card.aifory_card_id:
            raise ValueError("Card is not yet linked to Aifory (issuance may still be pending)")
        return await aifory_client.get_card_transactions(card.aifory_card_id, limit=limit, offset=offset)


    # ------------------------------------------------------------------
    # Deposit (top-up card balance via Aifory)
    # ------------------------------------------------------------------

    async def deposit_card(
        self,
        db: AsyncSession,
        user: User,
        card_id: str,
        amount: float,
    ) -> Dict[str, Any]:
        """
        Top up a specific card balance via Aifory deposit order.
        Uses USDT ERC-20/TRC-20 accounts + client-generated validateKey.
        Charges user: Aifory's total * (1 + CARD_TOPUP_MARKUP_PERCENT / 100).
        """
        if isinstance(card_id, str) and not card_id.isdigit():
            card_result = await db.execute(
                select(Card).where(Card.aifory_card_id == card_id, Card.user_id == user.id)
            )
        else:
            card_result = await db.execute(
                select(Card).where(Card.id == int(card_id), Card.user_id == user.id)
            )
        card = card_result.scalar_one_or_none()
        if not card:
            raise ValueError("Card not found")
        if not card.aifory_card_id:
            raise ValueError("Card is not yet linked to Aifory (issuance may still be pending)")

        # Get USDT accounts
        usdt = await self._get_usdt_accounts()

        # Client-generated idempotency key
        validate_key = str(uuid.uuid4())

        # Calculate fee (Aifory's own total is for their processing only)
        calc = await aifory_client.calculate_deposit_order(
            account_id=usdt["account_id"],
            card_id=card.aifory_card_id,
            amount=amount,
            account_id_to_exchange=usdt["account_id_to_exchange"],
            validate_key=validate_key,
        )
        aifory_total = Decimal(str(calc.get("amount") or amount))  # For reference/logging
        aifory_fee = Decimal(str(calc.get("fee") or 0))            # For reference/logging

        # Apply our markup ONLY on the base amount requested by the user
        # Example: amount=$1, markup=5% => user pays $1.05 (not $1.09)
        base_amount = Decimal(str(amount))
        markup = Decimal(str(settings.CARD_TOPUP_MARKUP_PERCENT))
        our_profit = base_amount * markup / Decimal("100")
        user_total = base_amount + our_profit

        # Check user balance
        if Decimal(str(user.balance)) < user_total:
            raise ValueError(
                f"Insufficient balance. Required: {user_total:.2f} USD, available: {user.balance}"
            )

        # Place deposit order on Aifory
        result = await aifory_client.create_deposit_order(
            account_id=usdt["account_id"],
            card_id=card.aifory_card_id,
            amount=amount,
            account_id_to_exchange=usdt["account_id_to_exchange"],
            validate_key=validate_key,
        )
        partner_order_id = result.get("orderID") or result.get("orderId") or result.get("id")

        # Deduct from user balance
        user.balance = Decimal(str(user.balance)) - user_total

        # Save order record
        order = Order(
            user_id=user.id,
            partner_order_id=partner_order_id,
            card_id=card.id,
            type="topup",
            amount=user_total,
            fee=our_profit,
            status="pending",
            description=f"Card top-up: ${amount:.2f} to card ...{card.aifory_card_id[-8:] if card.aifory_card_id else ''}",
        )
        db.add(order)
        await db.flush()

        return {"local_order_id": order.id, "partner_order_id": partner_order_id}

    # ------------------------------------------------------------------
    # Get deposit offers for a card
    # ------------------------------------------------------------------

    async def get_deposit_offers(self, db: AsyncSession, user_id: int, card_id: str) -> List[Dict]:
        """Return deposit offers available for a given card."""
        if isinstance(card_id, str) and not card_id.isdigit():
            card_result = await db.execute(
                select(Card).where(Card.aifory_card_id == card_id, Card.user_id == user_id)
            )
        else:
            card_result = await db.execute(
                select(Card).where(Card.id == int(card_id), Card.user_id == user_id)
            )
        card = card_result.scalar_one_or_none()
        if not card:
            raise ValueError("Card not found")
        if not card.aifory_card_id:
            raise ValueError("Card is not yet linked to Aifory")

        return await aifory_client.get_deposit_offers("", card.aifory_card_id)


card_service = CardService()
