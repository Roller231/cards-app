import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.oplata_client import oplata_client
from app.models.card import Card
from app.models.order import Order
from app.models.user import User
from app.services.telegram_bot_service import notify_card_issued, notify_card_transaction, notify_topup_result

logger = logging.getLogger(__name__)


def _client_id(user: User) -> str:
    """Derive O-Plata clientId for a given user."""
    return f"user_{user.id}"


def _parse_offer_id(offer_id: str):
    """Split 'ravanaServerId:typeUuid' offer_id into components."""
    parts = offer_id.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid offer_id format '{offer_id}'. Expected 'ravanaServerId:typeUuid'")
    return parts[0], parts[1]


def _card_state_to_status(state: Any) -> str:
    s = str(state or "").upper()
    return "active" if s == "ACTIVE" else "inactive"


class CardService:

    # ------------------------------------------------------------------
    # Offers (card types from O-Plata)
    # ------------------------------------------------------------------

    async def get_offers(self) -> List[Dict[str, Any]]:
        """Return available virtual card types from O-Plata."""
        test_client = settings.OPLATA_TEST_CLIENT_ID or "Developer"
        try:
            providers = await oplata_client.get_virtual_card_list(test_client)
        except Exception as exc:
            logger.warning("Could not fetch O-Plata card types: %s", exc)
            return []

        offers = []
        for provider in providers:
            ravana_server_id = provider.get("ravanaServerId") or provider.get("ravanaId") or ""
            if not ravana_server_id:
                continue
            card_types = provider.get("cardTypesList") or []
            for ct in card_types:
                type_uuid = ct.get("uuid") or ""
                if not type_uuid:
                    continue
                payment_system = ct.get("paymentSystem") or ""
                name = ct.get("localizedName") or f"{payment_system} Virtual Card"
                offers.append({
                    "id": f"{ravana_server_id}:{type_uuid}",
                    "name": name,
                    "payment_system": payment_system,
                    "currency": provider.get("cardCurrency") or "USD",
                    "issue_fee": float(settings.ONLINE_ISSUE_FEE_USD),
                    "monthly_fee": 0.0,
                    "ravana_server_id": ravana_server_id,
                    "type_uuid": type_uuid,
                    "description": ct.get("description") or name,
                })
        return offers

    # ------------------------------------------------------------------
    # Ensure client is registered in O-Plata
    # ------------------------------------------------------------------

    async def _ensure_client(self, client_id: str) -> str:
        """Register client if not already registered. Returns clientWalletId."""
        try:
            result = await oplata_client.register_client(client_id)
            return result.get("clientWalletId") or ""
        except Exception as exc:
            logger.warning("register_client for %s failed: %s", client_id, exc)
            return ""

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
        skip_balance_check: bool = False,
    ) -> Dict[str, Any]:
        """Issue a virtual card via O-Plata for the given user."""
        ravana_server_id, type_uuid = _parse_offer_id(offer_id)
        client_id = _client_id(user)

        # 1. Register client on O-Plata (idempotent)
        await self._ensure_client(client_id)

        # 2. Determine card amount and fee
        card_amount = Decimal(str(amount or 0))
        fixed_fee = Decimal(str(settings.ONLINE_ISSUE_FEE_USD))
        user_total = card_amount + fixed_fee

        # 3. Check user balance
        if not skip_balance_check and Decimal(str(user.balance)) < user_total:
            raise ValueError(
                f"Insufficient balance. Required: {user_total:.2f} USD, available: {user.balance}"
            )

        # 4. Issue card on O-Plata
        holder_name = f"{holder_first_name} {holder_last_name}".strip()
        result = await oplata_client.issue_virtual_card(
            client_id=client_id,
            name=holder_name or client_id,
            ravana_server_id=ravana_server_id,
            type_uuid=type_uuid,
        )
        payment_uuid = result.get("uuid") or result.get("id") or str(uuid.uuid4())
        logger.info(
            "Card issued: payment_uuid=%s client_id=%s user_id=%s",
            payment_uuid, client_id, user.id,
        )

        # 5. Deduct from user balance
        if not skip_balance_check:
            user.balance = Decimal(str(user.balance)) - user_total

        # 6. Save order
        order = Order(
            user_id=user.id,
            partner_order_id=payment_uuid,
            type="issue",
            amount=user_total,
            fee=fixed_fee,
            status="pending",
            description=f"Card issuance: {ravana_server_id}:{type_uuid}",
        )
        db.add(order)
        await db.flush()

        # 7. Notify
        try:
            await notify_card_issued(
                db=db, user=user,
                card_amount=float(card_amount),
                card_last4="",
                fee=float(fixed_fee),
                success=True,
            )
        except Exception as _n:
            logger.debug("Card issue notification error: %s", _n)

        return {"local_order_id": order.id, "partner_order_id": payment_uuid}

    # ------------------------------------------------------------------
    # Sync cards from O-Plata into local DB
    # ------------------------------------------------------------------

    async def sync_cards(self, db: AsyncSession, user: User) -> List[Card]:
        """Pull all virtual cards from O-Plata for this user and upsert into local DB."""
        client_id = _client_id(user)
        try:
            history = await oplata_client.get_virtual_card_history(client_id, page_size=100)
        except Exception as exc:
            logger.warning("get_virtual_card_history failed for %s: %s", client_id, exc)
            result = await db.execute(select(Card).where(Card.user_id == user.id))
            return list(result.scalars().all())

        cards_raw = history.get("content") or []

        for raw in cards_raw:
            card_id = str(raw.get("cardId") or raw.get("id") or "")
            ravana_id = str(raw.get("ravanaServerId") or "")
            if not card_id:
                continue

            masked_pan = str(raw.get("cardNumber") or "")
            last4 = masked_pan[-4:] if len(masked_pan) >= 4 else (masked_pan or "")
            holder = str(raw.get("holderName") or "")
            state = raw.get("state") or ""
            balance = Decimal(str(raw.get("balance") or 0))
            expired_at = str(raw.get("expireAtMonth") or "")
            currency = str(raw.get("currency") or raw.get("cardCurrency") or "USD")

            # Check if card already exists
            existing_result = await db.execute(
                select(Card).where(Card.aifory_card_id == card_id)
            )
            card = existing_result.scalar_one_or_none()

            if card:
                card.balance = balance
                card.status = _card_state_to_status(state)
                card.card_status = 2 if card.status == "active" else 0
                card.last4 = last4 or card.last4
                card.holder_name = holder or card.holder_name
                card.expired_at = expired_at or card.expired_at
                card.currency = currency or card.currency
                card.offer_id = ravana_id or card.offer_id
                logger.info("Synced card: card_id=%s user_id=%s balance=%s", card.id, user.id, balance)
            else:
                card = Card(
                    user_id=user.id,
                    aifory_card_id=card_id,
                    offer_id=ravana_id,
                    last4=last4,
                    holder_name=holder,
                    currency=currency,
                    balance=balance,
                    status=_card_state_to_status(state),
                    card_status=2 if _card_state_to_status(state) == "active" else 0,
                    expired_at=expired_at,
                )
                db.add(card)
                await db.flush()

                # Link pending issue order if exists
                pending_result = await db.execute(
                    select(Order).where(
                        Order.user_id == user.id,
                        Order.type == "issue",
                        Order.card_id.is_(None),
                    )
                )
                pending = pending_result.scalars().first()
                if pending:
                    pending.card_id = card.id
                    pending.status = "completed"

        final_result = await db.execute(select(Card).where(Card.user_id == user.id))
        return list(final_result.scalars().all())

    # ------------------------------------------------------------------
    # Get user cards (local)
    # ------------------------------------------------------------------

    async def get_user_cards(self, db: AsyncSession, user_id: int) -> List[Card]:
        result = await db.execute(select(Card).where(Card.user_id == user_id))
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Get card requisites (PAN / CVV)
    # ------------------------------------------------------------------

    async def get_card_requisites(self, db: AsyncSession, user_id: int, card_id: str) -> Dict:
        card = await self._resolve_card(db, user_id, card_id)

        if not card.aifory_card_id:
            raise ValueError("Card has no external ID (issuance may still be pending)")
        if not card.offer_id:
            raise ValueError("Card has no ravanaServerId stored")

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        client_id = _client_id(user) if user else f"user_{user_id}"

        raw = await oplata_client.get_card_secret(
            client_id=client_id,
            card_id=card.aifory_card_id,
            ravana_server_id=card.offer_id,
        )
        return {
            "card_number": raw.get("pan") or raw.get("cardNumber") or raw.get("number"),
            "expiry": raw.get("expireAtMonth") or raw.get("expiry") or card.expired_at,
            "cvv": raw.get("cvv"),
            "holder_name": raw.get("holderName") or raw.get("cardHolderName") or card.holder_name,
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
        card = await self._resolve_card(db, user_id, card_id)

        if not card.aifory_card_id:
            raise ValueError("Card has no external ID")
        if not card.offer_id:
            raise ValueError("Card has no ravanaServerId stored")

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        client_id = _client_id(user) if user else f"user_{user_id}"

        page_size = limit
        page_number = offset // limit if limit > 0 else 0

        response = await oplata_client.get_card_transaction_list(
            client_id=client_id,
            card_id=card.aifory_card_id,
            ravana_server_id=card.offer_id,
            page_number=page_number,
            page_size=page_size,
        )
        transactions = response.get("content") or response if isinstance(response, list) else []

        # Notify about latest transaction if new
        if transactions and user and user.telegram_user_id:
            latest_txn = transactions[0]
            last_notified_id = getattr(card, "last_notified_transaction_id", None)
            txn_id = str(latest_txn.get("uuid") or latest_txn.get("id") or "")
            if txn_id and last_notified_id != txn_id:
                try:
                    await notify_card_transaction(
                        db=db, user=user,
                        card_last4=card.last4 or "",
                        amount=float(latest_txn.get("amount") or latest_txn.get("amountNormalized") or 0),
                        currency=str(latest_txn.get("currency") or "USD"),
                        merchant=str(latest_txn.get("description") or latest_txn.get("merchant") or ""),
                        date=str(latest_txn.get("date") or latest_txn.get("createdAt") or ""),
                        status=str(latest_txn.get("state") or latest_txn.get("status") or ""),
                    )
                    if hasattr(card, "last_notified_transaction_id"):
                        card.last_notified_transaction_id = txn_id
                        await db.flush()
                except Exception as _n:
                    logger.debug("Transaction notification error: %s", _n)

        return transactions

    # ------------------------------------------------------------------
    # Deposit (top-up card balance via O-Plata)
    # ------------------------------------------------------------------

    async def deposit_card(
        self,
        db: AsyncSession,
        user: User,
        card_id: str,
        amount: float,
        skip_balance_check: bool = False,
    ) -> Dict[str, Any]:
        """Top up a specific card balance via O-Plata."""
        card = await self._resolve_card(db, user.id, card_id)

        if not card.aifory_card_id:
            raise ValueError("Card has no external ID")
        if not card.offer_id:
            raise ValueError("Card has no ravanaServerId stored")

        base_amount = Decimal(str(amount))
        if str(card.offer_id).startswith("525847"):
            markup_percent = Decimal(str(settings.ONLINE_PLUS_TOPUP_MARKUP_PERCENT))
        else:
            markup_percent = Decimal(str(settings.ONLINE_TOPUP_MARKUP_PERCENT))
        our_profit = base_amount * markup_percent / Decimal("100")
        user_total = base_amount + our_profit

        if not skip_balance_check and Decimal(str(user.balance)) < user_total:
            raise ValueError(
                f"Insufficient balance. Required: {user_total:.2f} USD, available: {user.balance}"
            )

        client_id = _client_id(user)
        result = await oplata_client.topup_card(
            client_id=client_id,
            card_id=card.aifory_card_id,
            ravana_server_id=card.offer_id,
            amount=amount,
        )
        payment_uuid = result.get("uuid") or result.get("id") or str(uuid.uuid4())

        if not skip_balance_check:
            user.balance = Decimal(str(user.balance)) - user_total

        order = Order(
            user_id=user.id,
            partner_order_id=payment_uuid,
            card_id=card.id,
            type="topup",
            amount=user_total,
            fee=our_profit,
            status="pending",
            description=f"Card top-up: ${amount:.2f} to card ...{card.aifory_card_id[-8:]}",
        )
        db.add(order)
        await db.flush()

        try:
            await notify_topup_result(
                db=db, user=user,
                card_last4=card.last4 or "",
                amount=float(amount),
                fee=float(our_profit),
                success=True,
            )
        except Exception as _n:
            logger.debug("Topup notification error: %s", _n)

        return {"local_order_id": order.id, "partner_order_id": payment_uuid}

    # ------------------------------------------------------------------
    # Get deposit offers (kept for API compatibility)
    # ------------------------------------------------------------------

    async def get_deposit_offers(self, db: AsyncSession, user_id: int, card_id: str) -> List[Dict]:
        """Return top-up options for a card."""
        card = await self._resolve_card(db, user_id, card_id)
        if not card:
            raise ValueError("Card not found")
        return [
            {
                "id": "topup_usd",
                "name": "Top up USD",
                "currency": card.currency or "USD",
                "min_amount": 1.0,
                "max_amount": 10000.0,
                "markup_percent": float(settings.ONLINE_TOPUP_MARKUP_PERCENT),
            }
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_card(self, db: AsyncSession, user_id: int, card_id: str) -> Card:
        """Find card by external_card_id (aifory_card_id) or by local numeric id."""
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
        return card


card_service = CardService()
