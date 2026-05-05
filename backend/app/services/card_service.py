import asyncio
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
    if str(getattr(user, "username", "") or "") == "dev_user" and (settings.OPLATA_TEST_CLIENT_ID or "").strip():
        return settings.OPLATA_TEST_CLIENT_ID.strip()
    return f"user_{user.id}"


def _parse_offer_id(offer_id: str):
    """Split 'ravanaServerId:typeUuid' offer_id into components.

    offer_id format: 'RAVANA:RT-int:fcf0b632-b22e-495b-a368-c91ce820d6ee'
    ravanaServerId can contain colons, typeUuid is always the last segment.
    """
    last_colon = offer_id.rfind(":")
    if last_colon == -1:
        raise ValueError(f"Invalid offer_id format '{offer_id}'. Expected 'ravanaServerId:typeUuid'")
    return offer_id[:last_colon], offer_id[last_colon + 1:]


def _card_state_to_status(state: Any) -> str:
    s = str(state or "").upper()
    return "active" if s == "ACTIVE" else "inactive"


def _validation_status_requires_data(status: Any) -> bool:
    s = str(status or "").upper()
    return "ABSENT" in s or s in {"INVALID", "NOT_REGISTERED", "FAILED"}


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
            issue_fee_raw = provider.get("issueConstantFee") or 0
            min_balance_raw = provider.get("minimumCardBalance") or 0
            mdm_types = provider.get("clientMDMDataTypes") or []
            issue_fee = float(issue_fee_raw) + float(settings.ONLINE_ISSUE_FEE_USD)
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
                    "issue_fee": issue_fee,
                    "minimum_card_balance": float(min_balance_raw),
                    "monthly_fee": 0.0,
                    "ravana_server_id": ravana_server_id,
                    "type_uuid": type_uuid,
                    "description": f"{name} | Fee: ${issue_fee:.2f} | Min balance: ${float(min_balance_raw):.2f} | MDM: {', '.join(map(str, mdm_types)) if mdm_types else 'none'}",
                })
        return offers

    # ------------------------------------------------------------------
    # Ensure client is registered in O-Plata
    # ------------------------------------------------------------------

    async def _ensure_client(
        self,
        client_id: str,
        email: Optional[str] = None,
        document_number: Optional[str] = None,
        holder_first_name: Optional[str] = None,
        holder_last_name: Optional[str] = None,
    ) -> str:
        """Register client if not already registered, then complete basic KYC fields. Returns clientWalletId."""
        try:
            result = await oplata_client.register_client(client_id)
            wallet_id = result.get("clientWalletId") or ""
        except Exception as exc:
            logger.warning("register_client for %s failed: %s", client_id, exc)
            wallet_id = ""

        # All KYC steps use a single consistent dataset matching partner/start defaults.
        # Inconsistency between PERSON/COUNTRY/HOME and PARTNER causes
        # InvalidObjectContentException on partner/start.
        kyc_first_name = "Richard"
        kyc_last_name = "Wright"
        kyc_middle_name = "Ivanovich"
        kyc_dob = "1990-11-30"
        kyc_country = "RU"
        _email = email or f"{client_id}@oplata.test"

        # Complete KYC email verification
        try:
            await oplata_client.kyc_verify_email(client_id, _email)
            logger.info("KYC email set for %s: %s", client_id, _email)
        except Exception as exc:
            logger.warning("kyc_verify_email for %s failed: %s", client_id, exc)

        # Complete basic KYC fields often required by card providers in test environment
        try:
            await oplata_client.kyc_verify_person(
                client_id, kyc_first_name, kyc_last_name, kyc_dob, middle_name=kyc_middle_name,
            )
            logger.info("KYC person set for %s: %s %s", client_id, kyc_first_name, kyc_last_name)
        except Exception as exc:
            logger.warning("kyc_verify_person for %s failed: %s", client_id, exc)
        try:
            await oplata_client.kyc_verify_country(client_id, kyc_country)
            logger.info("KYC country set for %s: %s", client_id, kyc_country)
        except Exception as exc:
            logger.warning("kyc_verify_country for %s failed: %s", client_id, exc)
        try:
            await oplata_client.kyc_verify_home(
                client_id,
                address="1806",
                city="Moscow",
                country_code=kyc_country,
                state="Moscow",
                street="Tverskaya",
            )
            logger.info("KYC home set for %s", client_id)
        except Exception as exc:
            logger.warning("kyc_verify_home for %s failed: %s", client_id, exc)
        # Wait for HOME_ADDRESS to reach COMPLETED before calling partner/start
        # (partner/start is rejected if a prior KYC step is still UPDATING)
        for _attempt in range(8):
            try:
                _kinfo = await oplata_client.kyc_info(client_id)
                _home_states = [
                    o.get("orderState") for o in _kinfo.get("orderResponses", [])
                    if o.get("orderType") == "HOME_ADDRESS"
                ]
                if any(s == "UPDATING" for s in _home_states):
                    logger.info("Waiting for HOME_ADDRESS UPDATING→COMPLETED for %s...", client_id)
                    await asyncio.sleep(1.5)
                else:
                    break
            except Exception:
                break

        try:
            # Use client_id-derived unique document/phone to avoid cross-EON conflicts
            _hash = abs(hash(client_id)) % 10000000000
            _doc_number = str(_hash).zfill(10)
            _phone = f"+7916{str(_hash % 1000000).zfill(7)}"
            result = await oplata_client.kyc_verify_partner_start(
                client_id,
                first_name=kyc_first_name,
                last_name=kyc_last_name,
                middle_name=kyc_middle_name,
                date_of_birth=kyc_dob,
                country=kyc_country,
                email=_email,
                document_number=_doc_number,
                phone_number=_phone,
            )
            logger.info("KYC partner/start for %s: %s", client_id, result)
        except Exception as exc:
            logger.warning("kyc_verify_partner_start for %s failed: %s", client_id, exc)

        try:
            kyc_info = await oplata_client.kyc_info(client_id)
            logger.info("O-Plata KYC info for %s: %s", client_id, kyc_info)
        except Exception as exc:
            logger.warning("kyc_info for %s failed: %s", client_id, exc)

        return wallet_id

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
        email: Optional[str] = None,
        document_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Issue a virtual card via O-Plata for the given user."""
        ravana_server_id, type_uuid = _parse_offer_id(offer_id)
        client_id = _client_id(user)

        try:
            providers = await oplata_client.get_virtual_card_list(client_id)
            provider = next(
                (p for p in providers if str(p.get("ravanaServerId") or p.get("ravanaId") or "") == ravana_server_id),
                None,
            )
            if provider:
                logger.info(
                    "O-Plata provider requirements for %s on %s: clientMDMDataTypes=%s registered=%s",
                    client_id,
                    ravana_server_id,
                    provider.get("clientMDMDataTypes"),
                    provider.get("registered"),
                )
        except Exception as exc:
            logger.warning("Could not inspect O-Plata provider requirements for %s on %s: %s", client_id, ravana_server_id, exc)

        # 1. Register client on O-Plata (idempotent) and push MDM data
        await self._ensure_client(
            client_id,
            email=email,
            document_number=document_number,
            holder_first_name=holder_first_name,
            holder_last_name=holder_last_name,
        )

        try:
            validation = await oplata_client.validate_card_registration(client_id, ravana_server_id)
            validation_status = validation.get("status")
            logger.info("O-Plata card validation for %s on %s: %s", client_id, ravana_server_id, validation)
            if str(validation_status or "").upper() == "IDENTIFICATION_DOCUMENT_ABSENT":
                document_value = document_number or f"DOC-{client_id.upper()}"
                try:
                    await oplata_client.set_identification_document(client_id, document_value)
                    validation = await oplata_client.validate_card_registration(client_id, ravana_server_id)
                    validation_status = validation.get("status")
                    logger.info(
                        "O-Plata card validation after identification document for %s on %s: %s",
                        client_id,
                        ravana_server_id,
                        validation,
                    )
                except Exception as exc:
                    logger.warning("set_identification_document failed for %s: %s", client_id, exc)
            if _validation_status_requires_data(validation_status):
                raise ValueError(f"O-Plata client is not ready for card issuance: {validation_status}")
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("validate_card_registration failed for %s: %s", client_id, exc)

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
        try:
            result = await oplata_client.issue_virtual_card(
                client_id=client_id,
                name=holder_name or client_id,
                ravana_server_id=ravana_server_id,
                type_uuid=type_uuid,
            )
        except Exception as exc:
            if "required MDM data" in str(exc):
                try:
                    validation = await oplata_client.validate_card_registration(client_id, ravana_server_id)
                    raise ValueError(
                        f"O-Plata client is not ready for card issuance: {validation.get('status') or validation}"
                    )
                except ValueError:
                    raise
                except Exception:
                    pass
            raise
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
            providers = await oplata_client.get_virtual_card_list(client_id)
        except Exception as exc:
            logger.warning("get_virtual_card_list failed for %s: %s", client_id, exc)
            result = await db.execute(select(Card).where(Card.user_id == user.id))
            return list(result.scalars().all())

        cards_raw: List[Dict[str, Any]] = []
        for provider in providers:
            provider_ravana_id = str(provider.get("ravanaServerId") or provider.get("ravanaId") or "")
            for raw_card in provider.get("cardsList") or []:
                card_copy = dict(raw_card)
                if provider_ravana_id and not card_copy.get("ravanaServerId"):
                    card_copy["ravanaServerId"] = provider_ravana_id
                cards_raw.append(card_copy)

        for raw in cards_raw:
            card_id = str(raw.get("cardId") or raw.get("id") or "")
            ravana_id = str(raw.get("ravanaServerId") or "")
            if not card_id:
                continue

            masked_pan = str(raw.get("numberMasked") or raw.get("cardNumber") or "")
            last4 = masked_pan[-4:] if len(masked_pan) >= 4 else (masked_pan or "")
            holder = str(raw.get("holderName") or "")
            state = raw.get("state") or ""
            balance = Decimal("0")
            if ravana_id:
                try:
                    balance_raw = await oplata_client.get_card_funds_balance(client_id, card_id, ravana_id)
                    balance = Decimal(str(balance_raw.get("availableBalance") or balance_raw.get("balance") or 0))
                except Exception as exc:
                    logger.warning("get_card_funds_balance failed for %s/%s: %s", client_id, card_id, exc)
            expired_at = str(raw.get("expireAtMonth") or "")
            currency = str(raw.get("balanceCurrency") or raw.get("cardCurrency") or raw.get("currency") or "USD")

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
        exp_month = raw.get("expirationMonth") or ""
        exp_year = raw.get("expirationYear") or ""
        expiry = f"{exp_month}/{exp_year}" if exp_month and exp_year else (raw.get("expireAtMonth") or card.expired_at)
        return {
            "card_number": raw.get("number") or raw.get("pan") or raw.get("cardNumber"),
            "expiry": expiry,
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
        transactions = response.get("data") or response.get("content") or (response if isinstance(response, list) else [])

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
                        amount=float(latest_txn.get("amount") or 0),
                        currency=str(latest_txn.get("currency") or "USD"),
                        merchant=str(latest_txn.get("merchantName") or latest_txn.get("description") or ""),
                        date=str(latest_txn.get("transactionAt") or latest_txn.get("createdAt") or ""),
                        status=str(latest_txn.get("status") or ""),
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
