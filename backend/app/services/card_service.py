import asyncio
import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.integrations.oplata_client import oplata_client
from app.models.card import Card
from app.models.order import Order
from app.models.user import User
from app.services.telegram_bot_service import notify_card_issued, notify_card_transaction, notify_topup_result

logger = logging.getLogger(__name__)


def _client_id(user: User) -> str:
    """Derive O-Plata clientId for a given user.

    All local users share a single funded O-Plata client (Developer).
    Card ownership is tracked locally via Card.user_id and a user-tag embedded
    in the card name during issuance (see _user_card_tag / _strip_user_tag).
    """
    return (settings.OPLATA_TEST_CLIENT_ID or "Developer").strip()


def _user_card_tag(user_id: int) -> str:
    """Prefix embedded in O-Plata card name to identify the owning local user."""
    return f"u{user_id}:"


def _strip_user_tag(name: str) -> str:
    """Strip the user ownership tag from a card name, e.g. 'u42:John Doe' -> 'John Doe'."""
    if name and ":" in name:
        prefix, _, rest = name.partition(":")
        if prefix.startswith("u") and prefix[1:].isdigit():
            return rest.strip()
    return name


def _user_id_from_tag(name: str) -> Optional[int]:
    """Extract user_id from card name tag, e.g. 'u42:John Doe' -> 42. Returns None if absent."""
    if name and ":" in name:
        prefix, _, _ = name.partition(":")
        if prefix.startswith("u") and prefix[1:].isdigit():
            return int(prefix[1:])
    return None


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
    if s == "ACTIVE":
        return "active"
    if s in {"PROCESSING", "PENDING", "UPDATING", "CREATED", "CREATING", "ISSUING"}:
        return "processing"
    if not s:
        return "inactive"
    return s.lower()


def _card_status_code(state: Any) -> int:
    status = _card_state_to_status(state)
    if status == "active":
        return 2
    if status == "processing":
        return 1
    return 0


def _card_is_active(state: Any) -> bool:
    return _card_state_to_status(state) == "active"


def _is_card_type_issuable(card_type: Dict[str, Any]) -> bool:
    if bool(card_type.get("readOnly")):
        return False
    status = str(card_type.get("status") or card_type.get("state") or "").upper()
    if status and status not in {"ACTIVE", "ENABLED"}:
        return False
    return True


def _validation_status_requires_data(status: Any) -> bool:
    s = str(status or "").upper()
    return "ABSENT" in s or s in {"INVALID", "FAILED"}


class CardService:

    async def _find_processing_placeholder_card(
        self,
        db: AsyncSession,
        user_id: int,
        ravana_id: str,
        holder_name: str,
    ) -> Optional[Card]:
        placeholder_result = await db.execute(
            select(Card).where(
                Card.user_id == user_id,
                Card.aifory_card_id.is_(None),
                Card.offer_id == ravana_id,
                or_(Card.status == "processing", Card.status == "creating"),
            ).order_by(Card.id.desc())
        )
        placeholders = list(placeholder_result.scalars().all())
        if not placeholders:
            return None
        if holder_name:
            for placeholder in placeholders:
                if str(placeholder.holder_name or "").strip() == holder_name:
                    return placeholder
        return placeholders[0]

    async def _ensure_issue_placeholder_card(
        self,
        db: AsyncSession,
        user: User,
        ravana_id: str,
        holder_name: str,
        currency: str,
    ) -> Card:
        placeholder = await self._find_processing_placeholder_card(db, user.id, ravana_id, holder_name)
        if placeholder:
            placeholder.holder_name = holder_name or placeholder.holder_name
            placeholder.currency = currency or placeholder.currency
            placeholder.offer_id = ravana_id or placeholder.offer_id
            placeholder.status = "creating"
            placeholder.card_status = 1
            return placeholder

        placeholder = Card(
            user_id=user.id,
            aifory_card_id=None,
            offer_id=ravana_id,
            last4=None,
            holder_name=holder_name,
            currency=currency,
            balance=Decimal("0"),
            status="creating",
            card_status=1,
            expired_at=None,
        )
        db.add(placeholder)
        await db.flush()
        return placeholder

    async def _link_issue_order_to_card(
        self,
        db: AsyncSession,
        user_id: int,
        card: Card,
        order_status: str,
    ) -> None:
        pending_result = await db.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.type == "issue",
                Order.card_id.is_(None),
            ).order_by(Order.id.asc())
        )
        pending = pending_result.scalars().first()
        if pending:
            pending.card_id = card.id
            pending.status = order_status

    async def _update_linked_issue_orders(
        self,
        db: AsyncSession,
        user_id: int,
        card: Card,
        order_status: str,
    ) -> None:
        linked_result = await db.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.type == "issue",
                Order.card_id == card.id,
            ).order_by(Order.id.asc())
        )
        linked_orders = list(linked_result.scalars().all())
        if linked_orders:
            for linked_order in linked_orders:
                linked_order.status = order_status
            return
        await self._link_issue_order_to_card(db, user_id, card, order_status)

    async def _detach_card_from_orders(
        self,
        db: AsyncSession,
        user_id: int,
        card_id: int,
        issue_order_status: Optional[str] = None,
    ) -> None:
        linked_result = await db.execute(
            select(Order).where(
                Order.user_id == user_id,
                Order.card_id == card_id,
            ).order_by(Order.id.asc())
        )
        linked_orders = list(linked_result.scalars().all())
        for linked_order in linked_orders:
            linked_order.card_id = None
            if issue_order_status and linked_order.type == "issue":
                linked_order.status = issue_order_status

    async def _follow_payment(self, client_id: str, payment_uuid: str, payment_kind: str) -> Dict[str, Any]:
        payment_data: Dict[str, Any] = {}
        confirm_attempted = False
        for _attempt in range(10):
            try:
                payment_data = await oplata_client.get_transaction_payment(client_id, payment_uuid)
                payment_state = str(payment_data.get("state") or "").upper()
                current_action = str(payment_data.get("currentAction") or "").upper()
                logger.info(
                    "O-Plata %s payment status for %s: uuid=%s state=%s currentAction=%s",
                    payment_kind,
                    client_id,
                    payment_uuid,
                    payment_state,
                    current_action,
                )
                if not confirm_attempted:
                    confirm_attempted = True
                    try:
                        confirm_result = await oplata_client.confirm_payment(client_id, payment_uuid)
                        logger.info(
                            "O-Plata %s payment confirm for %s: uuid=%s result=%s",
                            payment_kind,
                            client_id,
                            payment_uuid,
                            confirm_result,
                        )
                        if isinstance(confirm_result, dict) and confirm_result:
                            payment_data = confirm_result
                            payment_state = str(payment_data.get("state") or payment_state).upper()
                    except httpx.HTTPStatusError as exc:
                        response_text = exc.response.text if exc.response is not None else ""
                        if exc.response is not None and exc.response.status_code == 404 and "No such reference or expired" in response_text:
                            logger.info(
                                "O-Plata %s payment does not require confirm for %s uuid=%s: %s",
                                payment_kind,
                                client_id,
                                payment_uuid,
                                response_text,
                            )
                        else:
                            logger.warning(
                                "O-Plata %s payment confirm failed for %s uuid=%s: %s: %s",
                                payment_kind,
                                client_id,
                                payment_uuid,
                                exc.__class__.__name__,
                                exc,
                            )
                    except Exception as exc:
                        logger.warning(
                            "O-Plata %s payment confirm failed for %s uuid=%s: %s: %s",
                            payment_kind,
                            client_id,
                            payment_uuid,
                            exc.__class__.__name__,
                            exc,
                        )
                if payment_state in {"COMPLETED", "CANCELED", "FAILED", "REFUNDED"}:
                    return payment_data
            except Exception as exc:
                logger.warning(
                    "O-Plata %s payment status fetch failed for %s uuid=%s: %s: %s",
                    payment_kind,
                    client_id,
                    payment_uuid,
                    exc.__class__.__name__,
                    exc,
                )
            await asyncio.sleep(2)
        if str(payment_data.get("state") or "").upper() == "WITHDRAWAL_SENT":
            logger.warning(
                "O-Plata %s payment is stuck in WITHDRAWAL_SENT for %s: uuid=%s payload=%s",
                payment_kind,
                client_id,
                payment_uuid,
                payment_data,
            )
        return payment_data

    async def _wait_for_card_materialization(
        self,
        db: AsyncSession,
        user: User,
        order: Order,
        client_id: str,
        payment_uuid: str,
    ) -> None:
        for _attempt in range(15):
            try:
                await self.sync_cards(db, user)
            except Exception as exc:
                logger.debug("Post-issue sync failed for %s: %s", client_id, exc)
            if order.card_id:
                linked_card = await self._resolve_card(db, user.id, str(order.card_id))
                if linked_card.aifory_card_id:
                    logger.info(
                        "O-Plata card materialized for %s: payment_uuid=%s local_card_id=%s external_card_id=%s",
                        client_id,
                        payment_uuid,
                        order.card_id,
                        linked_card.aifory_card_id,
                    )
                    return
            await asyncio.sleep(2)
        if order.card_id:
            linked_card = await self._resolve_card(db, user.id, str(order.card_id))
            logger.info(
                "O-Plata card placeholder is still processing after issue follow-up: client_id=%s payment_uuid=%s local_card_id=%s status=%s",
                client_id,
                payment_uuid,
                linked_card.id,
                linked_card.status,
            )
        else:
            logger.info(
                "O-Plata card is still not materialized after issue follow-up: client_id=%s payment_uuid=%s",
                client_id,
                payment_uuid,
            )

    async def _finalize_issue_follow_up(
        self,
        user_id: int,
        order_id: int,
        payment_uuid: str,
        card_amount: float,
        fixed_fee: float,
    ) -> None:
        async with AsyncSessionLocal() as db:
            try:
                user_result = await db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                order_result = await db.execute(
                    select(Order).where(Order.id == order_id, Order.user_id == user_id)
                )
                order = order_result.scalar_one_or_none()
                if not user or not order:
                    logger.warning(
                        "Skipping async issue follow-up: user_id=%s order_id=%s payment_uuid=%s not found",
                        user_id,
                        order_id,
                        payment_uuid,
                    )
                    return

                client_id = _client_id(user)
                issue_payment = await self._follow_payment(client_id, payment_uuid, "issue")
                if issue_payment:
                    logger.info(
                        "O-Plata final issue payment snapshot for %s: uuid=%s state=%s currentAction=%s",
                        client_id,
                        payment_uuid,
                        issue_payment.get("state"),
                        issue_payment.get("currentAction"),
                    )
                issue_state = str(issue_payment.get("state") or "").upper()
                if issue_state in {"CANCELED", "FAILED", "REFUNDED"}:
                    order.status = "failed"
                    if order.card_id:
                        linked_card = await self._resolve_card(db, user.id, str(order.card_id))
                        linked_card.status = "failed"
                        linked_card.card_status = 0
                    try:
                        await notify_card_issued(
                            db=db, user=user,
                            card_amount=card_amount,
                            card_last4="",
                            fee=fixed_fee,
                            success=False,
                            error_msg=issue_state or "Card issuance failed",
                        )
                    except Exception as _n:
                        logger.debug("Card issue failure notification error: %s", _n)
                    await db.commit()
                    return

                await self._wait_for_card_materialization(db, user, order, client_id, payment_uuid)

                if order.card_id:
                    linked_card = await self._resolve_card(db, user.id, str(order.card_id))
                    if _card_is_active(linked_card.status):
                        try:
                            await notify_card_issued(
                                db=db, user=user,
                                card_amount=card_amount,
                                card_last4=linked_card.last4 or "",
                                fee=fixed_fee,
                                success=True,
                            )
                        except Exception as _n:
                            logger.debug("Card issue notification error: %s", _n)

                await db.commit()
            except Exception as exc:
                if 'user' in locals() and user:
                    try:
                        await notify_card_issued(
                            db=db, user=user,
                            card_amount=card_amount,
                            card_last4="",
                            fee=fixed_fee,
                            success=False,
                            error_msg=str(exc),
                        )
                    except Exception as _n:
                        logger.debug("Card issue exception notification error: %s", _n)
                logger.error(
                    "Async issue follow-up failed for user_id=%s order_id=%s payment_uuid=%s: %s",
                    user_id,
                    order_id,
                    payment_uuid,
                    exc,
                )
                await db.rollback()

    # ------------------------------------------------------------------
    # Offers (card types from O-Plata)
    # ------------------------------------------------------------------

    async def get_offers(self) -> List[Dict[str, Any]]:
        """Return available virtual card types from O-Plata."""
        test_client = settings.OPLATA_TEST_CLIENT_ID or "Developer"
        try:
            providers = await oplata_client.get_virtual_card_list(test_client)
        except Exception as exc:
            logger.warning("Could not fetch O-Plata card types: %s: %s", exc.__class__.__name__, exc)
            return []

        offers = []
        for provider in providers:
            ravana_server_id = provider.get("ravanaServerId") or provider.get("ravanaId") or ""
            if not ravana_server_id:
                continue
            min_balance_raw = provider.get("minimumCardBalance") or 0
            mdm_types = provider.get("clientMDMDataTypes") or []
            issue_fee = float(settings.ONLINE_ISSUE_FEE_USD)
            card_types = provider.get("cardTypesList") or []
            for ct in card_types:
                type_uuid = ct.get("uuid") or ""
                if not type_uuid:
                    continue
                if not _is_card_type_issuable(ct):
                    logger.info(
                        "Skipping non-issuable O-Plata card type for %s on %s: uuid=%s readOnly=%s status=%s state=%s",
                        test_client,
                        ravana_server_id,
                        type_uuid,
                        ct.get("readOnly"),
                        ct.get("status"),
                        ct.get("state"),
                    )
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
        kyc_first_name = "Test"
        kyc_last_name = "Testov"
        kyc_middle_name = "Testovich"
        kyc_dob = "1980-01-01"
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

        _partner_already_verified = False
        try:
            _pre_partner_info = await oplata_client.kyc_info(client_id)
            _partner_already_verified = "PARTNER" in (_pre_partner_info.get("checksVerified") or [])
        except Exception:
            _partner_already_verified = False

        if _partner_already_verified:
            logger.info("Skipping KYC partner/start for %s: PARTNER already verified", client_id)
        else:
            try:
                result = await oplata_client.kyc_verify_partner_start(
                    client_id,
                    first_name=kyc_first_name,
                    last_name=kyc_last_name,
                    middle_name=kyc_middle_name,
                    date_of_birth=kyc_dob,
                    country=kyc_country,
                    email=_email,
                )
                logger.info("KYC partner/start for %s: %s", client_id, result)
            except Exception as exc:
                logger.warning("kyc_verify_partner_start for %s failed: %s", client_id, exc)

        # Wait for PARTNER to reach COMPLETED before returning — validate will fail otherwise
        for _attempt in range(12):
            try:
                kyc_info = await oplata_client.kyc_info(client_id)
                logger.info("O-Plata KYC info for %s: %s", client_id, kyc_info)
                _partner_states = [
                    o.get("orderState") for o in kyc_info.get("orderResponses", [])
                    if o.get("orderType") == "PARTNER"
                ]
                if _partner_states and all(s not in ("UPDATING", "PROCESSING") for s in _partner_states):
                    break
                if _partner_states:
                    logger.info("Waiting for PARTNER to complete for %s (%s)...", client_id, _partner_states)
                    await asyncio.sleep(2)
                else:
                    break
            except Exception as exc:
                logger.warning("kyc_info polling for %s failed: %s", client_id, exc)
                break

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
        eager_placeholder_commit: bool = False,
        defer_follow_up: bool = False,
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
            if not provider:
                raise ValueError(f"O-Plata provider {ravana_server_id} is unavailable for this client")
            logger.info(
                "O-Plata provider requirements for %s on %s: clientMDMDataTypes=%s registered=%s",
                client_id,
                ravana_server_id,
                provider.get("clientMDMDataTypes"),
                provider.get("registered"),
            )
            selected_card_type = next(
                (ct for ct in (provider.get("cardTypesList") or []) if str(ct.get("uuid") or "") == type_uuid),
                None,
            )
            if not selected_card_type:
                raise ValueError(f"O-Plata card type {type_uuid} is unavailable for provider {ravana_server_id}")
            logger.info(
                "Selected O-Plata card type for %s: provider=%s type_uuid=%s readOnly=%s status=%s state=%s",
                client_id,
                ravana_server_id,
                type_uuid,
                selected_card_type.get("readOnly"),
                selected_card_type.get("status"),
                selected_card_type.get("state"),
            )
            if not _is_card_type_issuable(selected_card_type):
                raise ValueError(
                    f"O-Plata card type {type_uuid} is not active for issuance "
                    f"(readOnly={selected_card_type.get('readOnly')}, "
                    f"status={selected_card_type.get('status') or selected_card_type.get('state') or 'unknown'})"
                )
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
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
        tagged_name = f"{_user_card_tag(user.id)}{holder_name or client_id}"
        try:
            result = await oplata_client.issue_virtual_card(
                client_id=client_id,
                name=tagged_name,
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
        logger.info("issue_virtual_card raw result for %s: %s", client_id, result)
        payment_uuid = result.get("uuid") or result.get("id") or str(uuid.uuid4())
        logger.info(
            "Card issue request created: payment_uuid=%s client_id=%s user_id=%s",
            payment_uuid, client_id, user.id,
        )

        # 5. Deduct from user balance
        if not skip_balance_check:
            user.balance = Decimal(str(user.balance)) - user_total

        # 6. Save issuance order; actual card data arrives asynchronously via card/list
        order = Order(
            user_id=user.id,
            partner_order_id=payment_uuid,
            type="issue",
            amount=card_amount,
            fee=fixed_fee,
            status="pending",
            description=f"Card issuance: {ravana_server_id}:{type_uuid}",
        )
        db.add(order)
        await db.flush()
        order.status = "processing"
        if eager_placeholder_commit or defer_follow_up:
            await db.commit()
            logger.info(
                "Committed issue order for user_id=%s order_id=%s payment_uuid=%s",
                user.id,
                order.id,
                payment_uuid,
            )

        if defer_follow_up:
            asyncio.create_task(
                self._finalize_issue_follow_up(
                    user_id=user.id,
                    order_id=order.id,
                    payment_uuid=payment_uuid,
                    card_amount=float(card_amount),
                    fixed_fee=float(fixed_fee),
                )
            )
            return {"local_order_id": order.id, "partner_order_id": payment_uuid}

        # 7. Follow issue payment lifecycle and wait for card materialization in O-Plata
        issue_payment = await self._follow_payment(client_id, payment_uuid, "issue")
        if issue_payment:
            logger.info(
                "O-Plata final issue payment snapshot for %s: uuid=%s state=%s currentAction=%s",
                client_id,
                payment_uuid,
                issue_payment.get("state"),
                issue_payment.get("currentAction"),
            )
        issue_state = str(issue_payment.get("state") or "").upper() if issue_payment else ""
        if issue_state in {"CANCELED", "FAILED", "REFUNDED"}:
            order.status = "failed"
            if order.card_id:
                linked_card = await self._resolve_card(db, user.id, str(order.card_id))
                linked_card.status = "failed"
                linked_card.card_status = 0
            await notify_card_issued(
                db=db, user=user,
                card_amount=float(card_amount),
                card_last4="",
                fee=float(fixed_fee),
                success=False,
                error_msg=issue_state or "Card issuance failed",
            )
            raise ValueError(issue_state or "Card issuance failed")
        await self._wait_for_card_materialization(db, user, order, client_id, payment_uuid)

        # 8. Notify only when a concrete card record is already available locally
        if order.card_id:
            linked_card = await self._resolve_card(db, user.id, str(order.card_id))
            if _card_is_active(linked_card.status):
                try:
                    await notify_card_issued(
                        db=db, user=user,
                        card_amount=float(card_amount),
                        card_last4=linked_card.last4 or "",
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
        """Pull all virtual cards from O-Plata into local DB."""
        client_id = _client_id(user)
        try:
            providers = await oplata_client.get_virtual_card_list(client_id)
        except Exception as exc:
            logger.warning("get_virtual_card_list failed for %s: %s: %s", client_id, exc.__class__.__name__, exc)
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

        existing_result = await db.execute(select(Card).where(Card.user_id == user.id))
        existing_cards = list(existing_result.scalars().all())
        synced_local_card_ids = set()


        for raw in cards_raw:
            card_id = str(raw.get("cardId") or raw.get("id") or "")
            ravana_id = str(raw.get("ravanaServerId") or "")
            masked_pan = str(raw.get("numberMasked") or raw.get("cardNumber") or "")
            last4 = masked_pan[-4:] if len(masked_pan) >= 4 else (masked_pan or "")
            raw_name = str(raw.get("holderName") or raw.get("name") or "")
            holder = _strip_user_tag(raw_name)

            # Ownership check: if card has a user tag, skip it if it belongs to a different user.
            # Cards without any tag (legacy / external) are only accepted if already in local DB.
            tagged_owner_id = _user_id_from_tag(raw_name)
            if tagged_owner_id is not None and tagged_owner_id != user.id:
                continue
            state = raw.get("state") or ""
            balance = Decimal("0")
            if card_id and ravana_id and _card_is_active(state):
                try:
                    balance_raw = await oplata_client.get_card_funds_balance(client_id, card_id, ravana_id)
                    balance = Decimal(str(balance_raw.get("availableBalance") or balance_raw.get("balance") or 0))
                except Exception as exc:
                    logger.warning("get_card_funds_balance failed for %s/%s: %s", client_id, card_id, exc)
            expired_at = str(raw.get("expireAtMonth") or "")
            currency = str(raw.get("balanceCurrency") or raw.get("cardCurrency") or raw.get("currency") or "USD")

            if not card_id:
                placeholder = await self._find_processing_placeholder_card(db, user.id, ravana_id, holder)
                if placeholder:
                    placeholder.last4 = last4 or placeholder.last4
                    placeholder.holder_name = holder or placeholder.holder_name
                    placeholder.expired_at = expired_at or placeholder.expired_at
                    placeholder.currency = currency or placeholder.currency
                    placeholder.offer_id = ravana_id or placeholder.offer_id
                    placeholder.status = _card_state_to_status(state)
                    placeholder.card_status = _card_status_code(state)
                else:
                    placeholder = Card(
                        user_id=user.id,
                        aifory_card_id=None,
                        offer_id=ravana_id,
                        last4=last4,
                        holder_name=holder,
                        currency=currency,
                        balance=balance,
                        status=_card_state_to_status(state),
                        card_status=_card_status_code(state),
                        expired_at=expired_at,
                    )
                    db.add(placeholder)
                    await db.flush()
                await self._update_linked_issue_orders(db, user.id, placeholder, "processing")
                synced_local_card_ids.add(placeholder.id)
                logger.info(
                    "Synced processing placeholder card: local_card_id=%s user_id=%s ravana_id=%s state=%s",
                    placeholder.id,
                    user.id,
                    ravana_id,
                    state,
                )
                continue

            existing_result = await db.execute(
                select(Card).where(Card.aifory_card_id == card_id)
            )
            card = existing_result.scalar_one_or_none()

            if not card:
                card = await self._find_processing_placeholder_card(db, user.id, ravana_id, holder)
                if card:
                    card.aifory_card_id = card_id

            if card:
                card.balance = balance
                card.status = _card_state_to_status(state)
                card.card_status = _card_status_code(state)
                card.last4 = last4 or card.last4
                card.holder_name = holder or card.holder_name
                card.expired_at = expired_at or card.expired_at
                card.currency = currency or card.currency
                card.offer_id = ravana_id or card.offer_id
                await self._update_linked_issue_orders(db, user.id, card, "completed")
                synced_local_card_ids.add(card.id)
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
                    card_status=_card_status_code(state),
                    expired_at=expired_at,
                )
                db.add(card)
                await db.flush()
                await self._update_linked_issue_orders(db, user.id, card, "completed")
                synced_local_card_ids.add(card.id)

        for existing_card in existing_cards:
            if existing_card.id in synced_local_card_ids:
                continue
            await self._detach_card_from_orders(
                db,
                user.id,
                existing_card.id,
                issue_order_status="failed" if not existing_card.aifory_card_id else None,
            )
            await db.delete(existing_card)
            logger.info(
                "Deleted stale local card for user_id=%s local_card_id=%s external_card_id=%s",
                user.id,
                existing_card.id,
                existing_card.aifory_card_id,
            )

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
        if not _card_is_active(card.status):
            raise ValueError("Card is not active yet")

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
        if not _card_is_active(card.status):
            return []

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
            amount=float(base_amount),
        )
        payment_uuid = result.get("uuid") or result.get("id") or str(uuid.uuid4())

        if not skip_balance_check:
            user.balance = Decimal(str(user.balance)) - user_total

        order = Order(
            user_id=user.id,
            partner_order_id=payment_uuid,
            card_id=card.id,
            type="topup",
            amount=base_amount,
            fee=our_profit,
            status="pending",
            description=f"Card top-up: ${amount:.2f} to card ...{card.aifory_card_id[-8:]}",
        )
        db.add(order)
        await db.flush()

        topup_payment = await self._follow_payment(client_id, payment_uuid, "topup")
        topup_payment_state = str(topup_payment.get("state") or "").upper() if topup_payment else ""
        if topup_payment:
            logger.info(
                "O-Plata final topup payment snapshot for %s: uuid=%s state=%s currentAction=%s",
                client_id,
                payment_uuid,
                topup_payment.get("state"),
                topup_payment.get("currentAction"),
            )
        if topup_payment_state == "COMPLETED":
            order.status = "completed"
        elif topup_payment_state in {"CANCELED", "FAILED", "REFUNDED"}:
            order.status = "failed"

        try:
            await notify_topup_result(
                db=db, user=user,
                card_last4=card.last4 or "",
                amount=float(amount),
                fee=float(our_profit),
                success=topup_payment_state == "COMPLETED",
                error_msg="" if topup_payment_state == "COMPLETED" else (topup_payment_state or "Top-up payment is still pending"),
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
