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
    """Derive O-Plata clientId for a given local user.

    Each Telegram user gets its own O-Plata client (e.g. `tg_<telegram_user_id>`).
    Funds are transferred from the parent funded client (`OPLATA_PARENT_CLIENT_ID`)
    to the user's wallet on demand before issuing/topping up cards.
    """
    prefix = (settings.OPLATA_USER_CLIENT_PREFIX or "tg_").strip()
    tg_id = str(getattr(user, "telegram_user_id", "") or "").strip()
    if tg_id:
        return f"{prefix}{tg_id}"
    # Non-Telegram users (dev/admin/web-only) get their own isolated O-Plata client
    # under the same prefix so they go through register + KYC + funded wallet
    # just like real Telegram users.
    return f"{prefix}dev_{user.id}"


def _parent_client_id() -> str:
    """O-Plata client id of the funded parent used to top up per-user wallets."""
    return (
        settings.OPLATA_PARENT_CLIENT_ID
        or settings.OPLATA_TEST_CLIENT_ID
        or "Developer"
    ).strip()


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
    # Per-user lock to serialize sync_cards calls and avoid race-condition
    # IntegrityError on cards.aifory_card_id when /cards bg sync and the
    # post-issue follow-up poll run concurrently.
    _sync_locks: Dict[int, asyncio.Lock] = {}

    @classmethod
    def _get_sync_lock(cls, user_id: int) -> asyncio.Lock:
        lock = cls._sync_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            cls._sync_locks[user_id] = lock
        return lock

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

    async def _wait_for_card_active_in_oplata(
        self,
        client_id: str,
        card_external_id: str,
        ravana_server_id: str,
        max_attempts: int = 600,
        sleep_seconds: float = 2.0,
    ) -> bool:
        """Poll O-Plata directly until the given card's state is ACTIVE.

        Up to ``max_attempts × sleep_seconds`` seconds (default ~20 min).
        Returns True once the card is ACTIVE, False if the window is exhausted.
        """
        for attempt in range(max_attempts):
            try:
                providers = await oplata_client.get_virtual_card_list(client_id)
            except Exception as exc:
                logger.debug(
                    "wait_for_card_active: provider list fetch failed (attempt=%s) for %s: %s",
                    attempt, client_id, exc,
                )
                await asyncio.sleep(sleep_seconds)
                continue
            for provider in providers or []:
                pid = str(provider.get("ravanaServerId") or provider.get("ravanaId") or "")
                if pid != ravana_server_id:
                    continue
                for raw in provider.get("cardsList") or []:
                    if str(raw.get("cardId") or "") == card_external_id:
                        state = str(raw.get("state") or "").upper()
                        if state == "ACTIVE":
                            logger.info(
                                "wait_for_card_active: card %s is ACTIVE on %s after %s attempts",
                                card_external_id, ravana_server_id, attempt + 1,
                            )
                            return True
                        if attempt % 10 == 0:
                            logger.info(
                                "wait_for_card_active: card %s on %s state=%s (attempt %s/%s)",
                                card_external_id, ravana_server_id, state, attempt + 1, max_attempts,
                            )
                        break
            await asyncio.sleep(sleep_seconds)
        logger.warning(
            "wait_for_card_active: card %s on %s did not reach ACTIVE within %s attempts",
            card_external_id, ravana_server_id, max_attempts,
        )
        return False

    async def _auto_topup_after_issue(self, client_id: str, card: Card, amount: Decimal) -> bool:
        """Top-up freshly issued card with `amount` from the user's O-Plata wallet.

        Strategy:
        1. Wait until the card actually reports state=ACTIVE in O-Plata (up to ~20 min).
        2. Fire topup_card; retry up to 3 times on transient errors.
        3. Follow the resulting payment to COMPLETED.

        Returns True if the topup payment reached COMPLETED, False otherwise.
        Never raises; logs warnings on failure so the issue flow stays alive.
        """
        try:
            amount_dec = Decimal(str(amount or 0))
        except Exception:
            amount_dec = Decimal("0")
        if amount_dec <= 0:
            return True
        if not card or not card.aifory_card_id or not card.offer_id:
            logger.info(
                "Skipping auto-topup: card not materialized yet client=%s amount=%s",
                client_id, amount_dec,
            )
            return False

        # 1. Wait for ACTIVE state on O-Plata directly (does not depend on local sync).
        is_active = await self._wait_for_card_active_in_oplata(
            client_id=client_id,
            card_external_id=card.aifory_card_id,
            ravana_server_id=card.offer_id,
        )
        if not is_active:
            return False

        # 2. Fire topup_card with retries on transient errors.
        topup_uuid = ""
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                topup_result = await oplata_client.topup_card(
                    client_id=client_id,
                    card_id=card.aifory_card_id,
                    ravana_server_id=card.offer_id,
                    amount=float(amount_dec),
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Auto-topup attempt %s/3 failed for client=%s card=%s amount=%s: %s",
                    attempt + 1, client_id, card.aifory_card_id, amount_dec, exc,
                )
                await asyncio.sleep(3)
                continue
            if isinstance(topup_result, dict):
                topup_uuid = str(topup_result.get("uuid") or topup_result.get("id") or "")
            if topup_uuid:
                logger.info(
                    "Auto-topup created uuid=%s client=%s card=%s amount=%s (attempt %s)",
                    topup_uuid, client_id, card.aifory_card_id, amount_dec, attempt + 1,
                )
                break
            logger.warning(
                "Auto-topup attempt %s/3 returned no uuid for client=%s card=%s",
                attempt + 1, client_id, card.aifory_card_id,
            )
            await asyncio.sleep(3)
        if not topup_uuid:
            logger.warning(
                "Auto-topup gave up after 3 attempts for client=%s card=%s last_error=%s",
                client_id, card.aifory_card_id, last_error,
            )
            return False

        # 3. Follow payment to COMPLETED.
        try:
            payment_data = await self._follow_payment(client_id, topup_uuid, "auto-topup")
        except Exception as exc:
            logger.warning("Auto-topup follow_payment failed for uuid=%s: %s", topup_uuid, exc)
            return False
        state = str((payment_data or {}).get("state") or "").upper()
        if state != "COMPLETED":
            logger.warning(
                "Auto-topup did not COMPLETE for client=%s card=%s uuid=%s state=%s",
                client_id, card.aifory_card_id, topup_uuid, state,
            )
            return False
        return True

    async def _wait_for_card_materialization(
        self,
        db: AsyncSession,
        user: User,
        order: Order,
        client_id: str,
        payment_uuid: str,
    ) -> None:
        # Wait for the card to be both materialized (has aifory_card_id) AND active.
        # Auto-topup needs an ACTIVE card; firing it during CREATING/PROCESSING state
        # results in silent failures or stuck payments on the O-Plata side.
        got_external_id = False
        for _attempt in range(400):
            try:
                await self.sync_cards(db, user)
            except Exception as exc:
                logger.debug("Post-issue sync failed for %s: %s", client_id, exc)
            if order.card_id:
                linked_card = await self._resolve_card(db, user.id, str(order.card_id))
                if linked_card.aifory_card_id and not got_external_id:
                    got_external_id = True
                    logger.info(
                        "O-Plata card got external id for %s: payment_uuid=%s local_card_id=%s external_card_id=%s status=%s",
                        client_id,
                        payment_uuid,
                        order.card_id,
                        linked_card.aifory_card_id,
                        linked_card.status,
                    )
                if linked_card.aifory_card_id and _card_is_active(linked_card.status):
                    logger.info(
                        "O-Plata card materialized & active for %s: payment_uuid=%s local_card_id=%s external_card_id=%s",
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
                    # Auto-topup polls O-Plata directly and waits for ACTIVE itself,
                    # so we only require the external id to be present here.
                    if linked_card.aifory_card_id and Decimal(str(card_amount)) > 0:
                        topup_ok = await self._auto_topup_after_issue(
                            client_id=client_id,
                            card=linked_card,
                            amount=Decimal(str(card_amount)),
                        )
                        if topup_ok:
                            try:
                                refreshed = await db.execute(select(Card).where(Card.id == linked_card.id))
                                linked_card = refreshed.scalar_one_or_none() or linked_card
                            except Exception:
                                pass
                            logger.info(
                                "Auto-topup after issue completed for user_id=%s card_id=%s amount=%s",
                                user.id, linked_card.aifory_card_id, card_amount,
                            )
                        else:
                            logger.warning(
                                "Auto-topup after issue did NOT complete for user_id=%s card_id=%s amount=%s",
                                user.id, linked_card.aifory_card_id, card_amount,
                            )
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
    # Per-user wallet funding (parent -> user) via O-Plata transfer
    # ------------------------------------------------------------------

    async def _resolve_client_wallet_id(self, client_id: str) -> str:
        """Return clientWalletId for given O-Plata clientId (registers if needed)."""
        try:
            info = await oplata_client.get_client_info(client_id)
            wallet_id = str(info.get("clientWalletId") or "")
            if wallet_id:
                return wallet_id
        except Exception as exc:
            logger.info("get_client_info for %s failed (will try register): %s", client_id, exc)
        result = await oplata_client.register_client(client_id)
        wallet_id = str(result.get("clientWalletId") or "")
        if not wallet_id:
            raise ValueError(f"Could not resolve clientWalletId for {client_id}")
        return wallet_id

    async def _fund_user_wallet(
        self,
        user_client_id: str,
        currency_code: str,
        amount: Decimal,
    ) -> None:
        """Transfer `amount` of `currency_code` from parent funded client to user's wallet."""
        if amount is None or Decimal(str(amount)) <= 0:
            return
        parent = _parent_client_id()
        if user_client_id == parent:
            return
        wallet_id = await self._resolve_client_wallet_id(user_client_id)

        # Snapshot the user's pre-transfer balance so we can detect arrival of the funded amount.
        prev_balance = await self._get_user_currency_balance(user_client_id, currency_code)

        result: Any = None
        last_exc: Optional[Exception] = None
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                result = await oplata_client.create_transfer(
                    client_id=parent,
                    currency_code=currency_code,
                    amount=float(amount),
                    wallet_id=wallet_id,
                )
                logger.info(
                    "Parent->User transfer ok (attempt %s/%s): from=%s to=%s wallet=%s amount=%s %s result=%s",
                    attempt, max_attempts, parent, user_client_id, wallet_id, amount, currency_code, result,
                )
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Parent->User transfer attempt %s/%s failed: from=%s to=%s wallet=%s amount=%s %s: %s",
                    attempt, max_attempts, parent, user_client_id, wallet_id, amount, currency_code, exc,
                )
                if attempt < max_attempts:
                    backoff = min(2 ** (attempt - 1), 8)  # 1s, 2s, 4s, 8s, 8s
                    await asyncio.sleep(backoff)
        if last_exc is not None:
            logger.error(
                "Parent->User transfer FAILED after %s attempts: from=%s to=%s wallet=%s amount=%s %s: %s",
                max_attempts, parent, user_client_id, wallet_id, amount, currency_code, last_exc,
            )
            raise ValueError(
                f"Не удалось перевести средства с родительского клиента: {last_exc}"
            )

        # Confirm the transfer on parent side so it leaves WAIT_FOR_CONFIRMATION.
        transfer_uuid = ""
        if isinstance(result, dict):
            transfer_uuid = str(result.get("uuid") or result.get("id") or "")
        if transfer_uuid:
            try:
                confirm_result = await oplata_client.confirm_payment(parent, transfer_uuid)
                logger.info(
                    "Parent transfer confirmed: parent=%s uuid=%s state=%s",
                    parent, transfer_uuid,
                    (confirm_result or {}).get("state") if isinstance(confirm_result, dict) else confirm_result,
                )
            except Exception as exc:
                logger.warning(
                    "Parent transfer confirm failed for parent=%s uuid=%s: %s",
                    parent, transfer_uuid, exc,
                )

        # Wait until the transferred amount actually lands on the user's wallet.
        await self._wait_for_user_balance(
            user_client_id=user_client_id,
            currency_code=currency_code,
            min_balance=Decimal(str(prev_balance)) + Decimal(str(amount)),
            timeout_seconds=120,
        )

    async def _get_user_currency_balance(self, user_client_id: str, currency_code: str) -> Decimal:
        """Best-effort fetch of a single-currency balance for a user's O-Plata wallet."""
        try:
            data = await oplata_client.get_balance_currency(user_client_id, currency_code)
        except Exception as exc:
            logger.debug("get_balance_currency(%s, %s) failed: %s", user_client_id, currency_code, exc)
            return Decimal("0")
        # Numeric/string scalar response: just parse it directly.
        if isinstance(data, (int, float, str)):
            try:
                return Decimal(str(data))
            except Exception:
                return Decimal("0")
        if not isinstance(data, dict):
            return Decimal("0")

        balance_keys = (
            "amountNormalized",
            "availableAmount",
            "availableBalance",
            "amount",
            "balance",
            "available",
            "value",
            "total",
        )
        for key in balance_keys:
            if key in data and data[key] is not None:
                try:
                    return Decimal(str(data[key]))
                except Exception:
                    continue

        amounts = data.get("amountsByCurrency")
        if isinstance(amounts, dict):
            for key in (currency_code, currency_code.upper(), currency_code.lower()):
                if key in amounts and amounts[key] is not None:
                    val = amounts[key]
                    if isinstance(val, dict):
                        for inner_key in balance_keys:
                            if inner_key in val and val[inner_key] is not None:
                                try:
                                    return Decimal(str(val[inner_key]))
                                except Exception:
                                    continue
                    try:
                        return Decimal(str(val))
                    except Exception:
                        continue

        # As a last resort, fallback to /balance/all and look up the currency there.
        try:
            all_data = await oplata_client.get_balance_all(user_client_id)
        except Exception:
            all_data = None
        if isinstance(all_data, dict):
            amounts = all_data.get("amountsByCurrency") or {}
            if isinstance(amounts, dict):
                for key in (currency_code, currency_code.upper(), currency_code.lower()):
                    if key in amounts and amounts[key] is not None:
                        val = amounts[key]
                        if isinstance(val, dict):
                            for inner_key in balance_keys:
                                if inner_key in val and val[inner_key] is not None:
                                    try:
                                        return Decimal(str(val[inner_key]))
                                    except Exception:
                                        continue
                        try:
                            return Decimal(str(val))
                        except Exception:
                            continue

        logger.info(
            "Unrecognized balance response shape for client=%s currency=%s: %s",
            user_client_id, currency_code, data,
        )
        return Decimal("0")

    async def _wait_for_user_balance(
        self,
        user_client_id: str,
        currency_code: str,
        min_balance: Decimal,
        timeout_seconds: int = 120,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        """Poll user wallet balance until it reaches `min_balance` or timeout expires."""
        deadline_attempts = max(1, int(timeout_seconds / max(poll_interval_seconds, 0.5)))
        last_balance = Decimal("0")
        for _attempt in range(deadline_attempts):
            last_balance = await self._get_user_currency_balance(user_client_id, currency_code)
            if last_balance >= min_balance:
                logger.info(
                    "User wallet funding confirmed: client=%s currency=%s balance=%s required=%s",
                    user_client_id, currency_code, last_balance, min_balance,
                )
                return
            await asyncio.sleep(poll_interval_seconds)
        logger.warning(
            "User wallet funding not confirmed in time: client=%s currency=%s last_balance=%s required=%s",
            user_client_id, currency_code, last_balance, min_balance,
        )
        raise ValueError(
            f"Средства не поступили на дочерний кошелёк за {timeout_seconds}с (баланс {last_balance} < {min_balance} {currency_code})"
        )

    async def _provider_balance_currency(
        self,
        ravana_server_id: str,
        type_uuid: str = "",
    ) -> str:
        """Fetch balanceCurrency (e.g. USDT) for a provider via parent client list."""
        try:
            providers = await oplata_client.get_virtual_card_list(_parent_client_id())
        except Exception as exc:
            logger.warning("Could not fetch parent virtual card list for currency lookup: %s", exc)
            return "USDT"
        for p in providers:
            if str(p.get("ravanaServerId") or p.get("ravanaId") or "") == ravana_server_id:
                return str(p.get("balanceCurrency") or p.get("cardCurrency") or "USDT")
        return "USDT"

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

        # 1. Register client on O-Plata (idempotent) and push MDM data
        await self._ensure_client(
            client_id,
            email=email,
            document_number=document_number,
            holder_first_name=holder_first_name,
            holder_last_name=holder_last_name,
        )

        # 1b. Inspect provider availability and capture funding params (issue fee, balance currency).
        provider_issue_fee_usdt = Decimal("0")
        provider_balance_currency = "USDT"
        try:
            providers = await oplata_client.get_virtual_card_list(client_id)
            provider = next(
                (p for p in providers if str(p.get("ravanaServerId") or p.get("ravanaId") or "") == ravana_server_id),
                None,
            )
            if not provider:
                # Fallback: check via parent client to distinguish "not registered yet" from "unavailable".
                try:
                    parent_providers = await oplata_client.get_virtual_card_list(_parent_client_id())
                    provider = next(
                        (p for p in parent_providers if str(p.get("ravanaServerId") or p.get("ravanaId") or "") == ravana_server_id),
                        None,
                    )
                except Exception:
                    provider = None
            if not provider:
                raise ValueError(f"O-Plata provider {ravana_server_id} is unavailable for this client")
            provider_issue_fee_usdt = Decimal(str(provider.get("issueConstantFee") or 0))
            provider_balance_currency = str(provider.get("balanceCurrency") or provider.get("cardCurrency") or "USDT")
            logger.info(
                "O-Plata provider requirements for %s on %s: clientMDMDataTypes=%s registered=%s issueConstantFee=%s balanceCurrency=%s",
                client_id,
                ravana_server_id,
                provider.get("clientMDMDataTypes"),
                provider.get("registered"),
                provider_issue_fee_usdt,
                provider_balance_currency,
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
        if bool(settings.ISSUE_APPLY_TOPUP_MARKUP):
            markup_percent = Decimal(str(settings.ONLINE_TOPUP_MARKUP_PERCENT))
            user_total += card_amount * markup_percent / Decimal("100")

        # 3. Check user balance
        if not skip_balance_check and Decimal(str(user.balance)) < user_total:
            raise ValueError(
                f"Insufficient balance. Required: {user_total:.2f} USD, available: {user.balance}"
            )

        # 3b. Fund the user's O-Plata wallet from the parent client (USDT) for amount + provider issue fee.
        funding_amount = card_amount + provider_issue_fee_usdt
        if funding_amount > 0:
            await self._fund_user_wallet(
                user_client_id=client_id,
                currency_code=provider_balance_currency,
                amount=funding_amount,
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

        # 7b. Auto top-up the freshly issued card with the user-requested amount.
        if order.card_id:
            materialized_card = await self._resolve_card(db, user.id, str(order.card_id))
            # Auto-topup itself waits for ACTIVE on O-Plata; just require aifory_card_id.
            if materialized_card.aifory_card_id and card_amount > 0:
                topup_ok = await self._auto_topup_after_issue(
                    client_id=client_id,
                    card=materialized_card,
                    amount=card_amount,
                )
                if topup_ok:
                    logger.info(
                        "Auto-topup after issue completed for user_id=%s card_id=%s amount=%s",
                        user.id, materialized_card.aifory_card_id, card_amount,
                    )
                else:
                    logger.warning(
                        "Auto-topup after issue did NOT complete for user_id=%s card_id=%s amount=%s",
                        user.id, materialized_card.aifory_card_id, card_amount,
                    )

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
        """Pull all virtual cards from O-Plata into local DB.

        Serialised per-user via asyncio.Lock to avoid concurrent INSERTs racing
        on cards.aifory_card_id (which is UNIQUE) when multiple sync paths run
        in parallel (background /cards sync, deferred issue follow-up poll, etc.).
        """
        lock = self._get_sync_lock(user.id)
        async with lock:
            return await self._sync_cards_impl(db, user)

    async def _sync_cards_impl(self, db: AsyncSession, user: User) -> List[Card]:
        client_id = _client_id(user)
        # Lazily register the user's O-Plata client (idempotent) so listing
        # endpoints don't return 403 "Access denied for client" on first access.
        try:
            await oplata_client.register_client(client_id)
        except Exception as exc:
            logger.debug("register_client during sync for %s failed (will continue): %s", client_id, exc)
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
                    # Only materialize a brand-new placeholder if this user actually has a
                    # pending issue order without a card. Otherwise an O-Plata "creating"
                    # entry would spam new local placeholders on every refresh.
                    pending_order_result = await db.execute(
                        select(Order).where(
                            Order.user_id == user.id,
                            Order.type == "issue",
                            Order.card_id.is_(None),
                        ).order_by(Order.id.asc())
                    )
                    if pending_order_result.scalars().first() is None:
                        logger.debug(
                            "Skipping placeholder creation for user_id=%s ravana_id=%s state=%s: no pending issue order",
                            user.id, ravana_id, state,
                        )
                        continue
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

        # Ensure user is registered (idempotent) and fund the wallet from parent before top-up.
        await self._ensure_client(client_id)
        topup_currency = await self._provider_balance_currency(card.offer_id)
        await self._fund_user_wallet(
            user_client_id=client_id,
            currency_code=topup_currency,
            amount=base_amount,
        )

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

        # Only notify on terminal states. Intermediate states like WITHDRAWAL_SENT /
        # DEPOSIT_SENT mean the payment is still in progress, not a failure.
        if topup_payment_state == "COMPLETED":
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
        elif topup_payment_state in {"CANCELED", "FAILED", "REFUNDED"}:
            try:
                await notify_topup_result(
                    db=db, user=user,
                    card_last4=card.last4 or "",
                    amount=float(amount),
                    fee=float(our_profit),
                    success=False,
                    error_msg=topup_payment_state or "Top-up failed",
                )
            except Exception as _n:
                logger.debug("Topup notification error: %s", _n)
        else:
            logger.info(
                "Topup still in progress (state=%s) for user_id=%s card=%s uuid=%s: notification deferred",
                topup_payment_state, user.id, card.aifory_card_id, payment_uuid,
            )

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


    # ------------------------------------------------------------------
    # Background runners (used by API routes to return immediately)
    # ------------------------------------------------------------------

    async def _run_issue_in_background(
        self,
        user_id: int,
        offer_id: str,
        holder_first_name: str,
        holder_last_name: str,
        amount: Optional[float],
        email: Optional[str],
        document_number: Optional[str],
        skip_balance_check: bool,
    ) -> None:
        async with AsyncSessionLocal() as db:
            try:
                user_result = await db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user:
                    logger.error("Background issue: user %s not found", user_id)
                    return
                await self.issue_card(
                    db=db,
                    user=user,
                    offer_id=offer_id,
                    holder_first_name=holder_first_name,
                    holder_last_name=holder_last_name,
                    amount=amount,
                    email=email,
                    document_number=document_number,
                    skip_balance_check=skip_balance_check,
                    defer_follow_up=True,
                )
                await db.commit()
            except Exception as exc:
                logger.error(
                    "Background issue failed for user_id=%s offer_id=%s amount=%s: %s",
                    user_id, offer_id, amount, exc,
                )
                try:
                    await db.rollback()
                except Exception:
                    pass
                try:
                    user_result = await db.execute(select(User).where(User.id == user_id))
                    user = user_result.scalar_one_or_none()
                    if user:
                        await notify_card_issued(
                            db=db,
                            user=user,
                            card_amount=float(amount or 0),
                            card_last4="",
                            fee=float(settings.ONLINE_ISSUE_FEE_USD),
                            success=False,
                            error_msg=str(exc),
                        )
                except Exception as _n:
                    logger.debug("Background issue failure notification error: %s", _n)

    async def _run_sync_in_background(self, user_id: int) -> None:
        async with AsyncSessionLocal() as db:
            try:
                user_result = await db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user:
                    return
                await self.sync_cards(db, user)
                await db.commit()
            except Exception as exc:
                logger.warning("Background sync_cards failed for user_id=%s: %s", user_id, exc)
                try:
                    await db.rollback()
                except Exception:
                    pass

    def schedule_sync_in_background(self, user_id: int) -> None:
        asyncio.create_task(self._run_sync_in_background(user_id=user_id))

    def schedule_issue_in_background(
        self,
        user_id: int,
        offer_id: str,
        holder_first_name: str,
        holder_last_name: str,
        amount: Optional[float] = None,
        email: Optional[str] = None,
        document_number: Optional[str] = None,
        skip_balance_check: bool = False,
    ) -> None:
        asyncio.create_task(
            self._run_issue_in_background(
                user_id=user_id,
                offer_id=offer_id,
                holder_first_name=holder_first_name,
                holder_last_name=holder_last_name,
                amount=amount,
                email=email,
                document_number=document_number,
                skip_balance_check=skip_balance_check,
            )
        )

    async def _run_deposit_in_background(
        self,
        user_id: int,
        card_id: str,
        amount: float,
        skip_balance_check: bool,
    ) -> None:
        async with AsyncSessionLocal() as db:
            try:
                user_result = await db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user:
                    logger.error("Background deposit: user %s not found", user_id)
                    return
                await self.deposit_card(
                    db=db,
                    user=user,
                    card_id=card_id,
                    amount=amount,
                    skip_balance_check=skip_balance_check,
                )
                await db.commit()
            except Exception as exc:
                logger.error(
                    "Background deposit failed for user_id=%s card_id=%s amount=%s: %s",
                    user_id, card_id, amount, exc,
                )
                try:
                    await db.rollback()
                except Exception:
                    pass
                try:
                    user_result = await db.execute(select(User).where(User.id == user_id))
                    user = user_result.scalar_one_or_none()
                    if user:
                        await notify_topup_result(
                            db=db,
                            user=user,
                            card_last4="",
                            amount=float(amount),
                            fee=0.0,
                            success=False,
                            error_msg=str(exc),
                        )
                except Exception as _n:
                    logger.debug("Background deposit failure notification error: %s", _n)

    def schedule_deposit_in_background(
        self,
        user_id: int,
        card_id: str,
        amount: float,
        skip_balance_check: bool = False,
    ) -> None:
        asyncio.create_task(
            self._run_deposit_in_background(
                user_id=user_id,
                card_id=card_id,
                amount=amount,
                skip_balance_check=skip_balance_check,
            )
        )


card_service = CardService()
