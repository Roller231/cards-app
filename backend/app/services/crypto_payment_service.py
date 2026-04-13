import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.integrations import abcex_client
from app.models.crypto_payment import CryptoPayment
from app.models.user import User
from app.services.card_service import card_service

logger = logging.getLogger(__name__)


def _fixed_fee(offer_id: str) -> Decimal:
    if str(offer_id) == "525847":
        return Decimal(str(settings.ONLINE_PLUS_ISSUE_FEE_USD))
    return Decimal(str(settings.ONLINE_ISSUE_FEE_USD))


def _topup_total(offer_id: str, amount: Decimal) -> Decimal:
    if str(offer_id) == "525847":
        markup = Decimal(str(settings.ONLINE_PLUS_TOPUP_MARKUP_PERCENT))
    else:
        markup = Decimal(str(settings.ONLINE_TOPUP_MARKUP_PERCENT))
    return amount + amount * markup / Decimal("100")


async def _make_payment(
    db: AsyncSession,
    user: User,
    amount_decimal: Decimal,
    total_usdt: Decimal,
    offer_id: str,
    payment_type: str,
    card_aifory_id: str | None = None,
    network: str = "TRC-20",
) -> Dict[str, Any]:
    address = await abcex_client.generate_address(network)
    logger.info(
        "Generated ABCEX TRC address=%s user_id=%s type=%s total=%s",
        address, user.id, payment_type, total_usdt,
    )
    payment_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(
        minutes=settings.ABCEX_CRYPTO_PAYMENT_EXPIRY_MINUTES
    )
    payment = CryptoPayment(
        id=payment_id,
        user_id=user.id,
        address=address,
        network=network,
        amount_usd=amount_decimal,
        total_usdt=total_usdt,
        offer_id=offer_id,
        type=payment_type,
        card_aifory_id=card_aifory_id,
        status="pending",
        expires_at=expires_at,
    )
    db.add(payment)
    await db.flush()
    return {
        "payment_id": payment_id,
        "address": address,
        "network": network,
        "type": payment_type,
        "amount_usd": float(amount_decimal),
        "total_usdt": float(total_usdt),
        "expires_at": expires_at.isoformat(),
    }


# ------------------------------------------------------------------
# Initiate a crypto payment for card issuance
# ------------------------------------------------------------------

async def initiate_payment(
    db: AsyncSession,
    user: User,
    offer_id: str,
    amount_usd: float,
    network: str = "TRC-20",
) -> Dict[str, Any]:
    amount_decimal = Decimal(str(amount_usd))
    total_usdt = amount_decimal + _fixed_fee(offer_id)
    return await _make_payment(db, user, amount_decimal, total_usdt, offer_id, "issue", network=network)


# ------------------------------------------------------------------
# Initiate a crypto payment for card top-up
# ------------------------------------------------------------------

async def initiate_topup(
    db: AsyncSession,
    user: User,
    card_aifory_id: str,
    offer_id: str,
    amount_usd: float,
    network: str = "TRC-20",
) -> Dict[str, Any]:
    amount_decimal = Decimal(str(amount_usd))
    total_usdt = _topup_total(offer_id, amount_decimal)
    return await _make_payment(
        db, user, amount_decimal, total_usdt, offer_id, "topup",
        card_aifory_id=card_aifory_id, network=network,
    )


# ------------------------------------------------------------------
# Get payment status
# ------------------------------------------------------------------

async def get_payment_status(
    db: AsyncSession,
    payment_id: str,
    user_id: int,
) -> Dict[str, Any]:
    result = await db.execute(
        select(CryptoPayment).where(
            CryptoPayment.id == payment_id,
            CryptoPayment.user_id == user_id,
        )
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise ValueError("Payment not found")

    return {
        "payment_id": payment.id,
        "status": payment.status,
        "type": payment.type,
        "address": payment.address,
        "network": payment.network,
        "total_usdt": float(payment.total_usdt),
        "amount_usd": float(payment.amount_usd),
        "expires_at": payment.expires_at.isoformat(),
        "order_id": payment.order_id,
    }


# ------------------------------------------------------------------
# Try to match a pending payment against ABCEX transactions
# ------------------------------------------------------------------

async def _try_confirm_payment(payment: CryptoPayment, db: AsyncSession) -> bool:
    """
    Query ABCEX transactions and look for a completed incoming USDT transfer
    to the payment address with amount >= total_usdt (allowing 1% tolerance).
    Returns True when payment was confirmed and card issued.
    """
    try:
        txs = await abcex_client.get_transactions(limit=200)
    except Exception as exc:
        logger.warning("ABCEX transaction fetch failed: %s", exc)
        return False

    threshold = float(payment.total_usdt) * 0.99  # 1% tolerance for dust

    for tx in txs:
        direction = (tx.get("direction") or "").lower()
        status = (tx.get("status") or "").lower()
        address_to = tx.get("addressTo") or tx.get("address_to") or ""
        currency = (tx.get("currencyId") or tx.get("currency") or "").upper()
        tx_amount = float(tx.get("amount") or 0)
        tx_id = str(tx.get("id") or tx.get("txId") or "")

        if (
            direction == "in"
            and status == "completed"
            and address_to == payment.address
            and "USDT" in currency
            and tx_amount >= threshold
        ):
            logger.info(
                "Matched ABCEX tx_id=%s for payment_id=%s user_id=%s amount=%s",
                tx_id, payment.id, payment.user_id, tx_amount,
            )
            payment.tx_id = tx_id
            payment.status = "processing"
            await db.flush()
            return True

    return False


async def _execute_payment(payment: CryptoPayment, db: AsyncSession) -> None:
    """Execute the card action (issue or topup) after confirmed crypto payment."""
    user_result = await db.execute(select(User).where(User.id == payment.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        logger.error("User %s not found for crypto payment %s", payment.user_id, payment.id)
        payment.status = "failed"
        return

    try:
        if payment.type == "topup":
            result = await card_service.deposit_card(
                db=db,
                user=user,
                card_id=payment.card_aifory_id,
                amount=float(payment.amount_usd),
                skip_balance_check=True,
            )
        else:
            result = await card_service.issue_card(
                db=db,
                user=user,
                offer_id=payment.offer_id,
                holder_first_name="Card",
                holder_last_name="Holder",
                amount=float(payment.amount_usd),
                skip_balance_check=True,
            )
        payment.order_id = result.get("local_order_id")
        payment.status = "completed"
        logger.info(
            "Crypto payment_id=%s type=%s completed order_id=%s",
            payment.id, payment.type, payment.order_id,
        )
    except Exception as exc:
        logger.error("Failed to execute payment %s type=%s: %s", payment.id, payment.type, exc)
        payment.status = "failed"
        # Notify user about failure
        try:
            from app.services.telegram_bot_service import notify_card_issued, notify_topup_result
            if payment.type == "topup":
                await notify_topup_result(
                    db=db, user=user,
                    card_last4="",
                    amount=float(payment.amount_usd),
                    fee=0.0,
                    success=False,
                    error_msg=str(exc),
                )
            else:
                await notify_card_issued(
                    db=db, user=user,
                    card_amount=float(payment.amount_usd),
                    card_last4="",
                    fee=0.0,
                    success=False,
                    error_msg=str(exc),
                )
        except Exception as _n:
            logger.debug("Failure notification error: %s", _n)


# ------------------------------------------------------------------
# Background polling task — called every 30 s from main.py
# ------------------------------------------------------------------

async def poll_pending_payments() -> None:
    """Scan all pending crypto payments and try to confirm each one."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(CryptoPayment).where(
                    CryptoPayment.status.in_(["pending", "processing"])
                )
            )
            payments = result.scalars().all()

            if not payments:
                return

            logger.info("Polling %d pending crypto payments", len(payments))

            for payment in payments:
                if payment.status == "pending":
                    matched = await _try_confirm_payment(payment, db)
                    if not matched:
                        continue

                # status is now "processing" — execute card action
                if payment.status == "processing":
                    await _execute_payment(payment, db)

            await db.commit()

        except Exception as exc:
            logger.error("Error in poll_pending_payments: %s", exc)
            await db.rollback()
