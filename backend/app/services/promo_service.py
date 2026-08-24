"""Promo code logic: validation, discount math, redemption lifecycle.

All discount amounts are computed HERE (server-side). The frontend only shows
previews from /promo/validate; the authoritative discounted invoice amount is
produced in create_invoice via apply_promo().
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.promo import PromoCode, PromoRedemption
from app.models.user import User

logger = logging.getLogger(__name__)

PROMO_TYPES = ("rate_discount", "issue_discount", "no_small_fee")

TYPE_LABELS = {
    "rate_discount": "Скидка на курс пополнения",
    "issue_discount": "Скидка на выпуск карты",
    "no_small_fee": "Без комиссии за пополнение до порога",
}


class PromoError(Exception):
    """User-facing validation error (message is shown as-is)."""


def promo_status(p: PromoCode, now: Optional[datetime] = None) -> str:
    """'active' | 'scheduled' | 'expired' | 'exhausted' | 'disabled'"""
    now = now or datetime.utcnow()
    if not p.is_active:
        return "disabled"
    if p.valid_from and now < p.valid_from:
        return "scheduled"
    if p.valid_until and now > p.valid_until:
        return "expired"
    if p.max_uses and p.used_count >= p.max_uses:
        return "exhausted"
    return "active"


def describe_discount(p: PromoCode) -> str:
    if p.type == "rate_discount":
        return f"-{p.percent_off or 0:g}% к курсу пополнения"
    if p.type == "issue_discount":
        parts = []
        if p.percent_off:
            parts.append(f"-{p.percent_off:g}%")
        if p.fixed_off_rub:
            parts.append(f"-{p.fixed_off_rub:g} ₽")
        suffix = f" на выпуск {p.card_type}" if p.card_type else " на выпуск карты"
        return (" или ".join(parts) or "скидка") + suffix
    if p.type == "no_small_fee":
        return f"без комиссии {settings.SBP_SMALL_PAYMENT_FEE_RUB:g} ₽ за пополнение до {settings.SBP_SMALL_PAYMENT_THRESHOLD_RUB:g} ₽"
    return "скидка"


async def get_valid_promo(
    db: AsyncSession,
    code: str,
    user: User,
    purpose: str,                      # 'balance_topup' | 'card_issue'
    card_type: Optional[str] = None,   # internal card name for card_issue
) -> PromoCode:
    """Load the code and raise PromoError with a human message if unusable."""
    code_norm = (code or "").strip().upper()
    if not code_norm:
        raise PromoError("Введите промокод")
    promo = (await db.execute(select(PromoCode).where(PromoCode.code == code_norm))).scalar_one_or_none()
    if not promo:
        raise PromoError("Такого промокода не существует")

    status = promo_status(promo)
    if status == "disabled":
        raise PromoError("Промокод отключён")
    if status == "scheduled":
        raise PromoError("Промокод ещё не начал действовать")
    if status == "expired":
        raise PromoError("Срок действия промокода истёк")
    if status == "exhausted":
        raise PromoError("Промокод уже израсходован")

    # Purpose match
    if purpose == "card_issue" and promo.type not in ("issue_discount",):
        raise PromoError("Этот промокод не действует на выпуск карты")
    if purpose == "balance_topup" and promo.type not in ("rate_discount", "no_small_fee"):
        raise PromoError("Этот промокод не действует на пополнение")
    if promo.type == "issue_discount" and promo.card_type and card_type and promo.card_type != card_type:
        raise PromoError(f"Промокод действует только на карту {promo.card_type}")

    if promo.one_per_user:
        used = (await db.execute(
            select(func.count(PromoRedemption.id)).where(
                PromoRedemption.promo_id == promo.id,
                PromoRedemption.user_id == user.id,
                PromoRedemption.status.in_(("pending", "applied")),
            )
        )).scalar() or 0
        if used > 0:
            raise PromoError("Вы уже использовали этот промокод")

    return promo


def compute_discount_rub(promo: PromoCode, purpose: str, amount_rub: float) -> float:
    """RUB discount this promo gives on the given (undiscounted) invoice amount.

    For no_small_fee the discount equals the small-payment fee, but only when
    the amount actually falls under the threshold (fee included in amount_rub).
    """
    amount = float(amount_rub or 0)
    if amount <= 0:
        return 0.0
    if promo.type == "rate_discount" and purpose == "balance_topup":
        return round(amount * float(promo.percent_off or 0) / 100.0, 2)
    if promo.type == "issue_discount" and purpose == "card_issue":
        pct = round(amount * float(promo.percent_off or 0) / 100.0, 2)
        fixed = float(promo.fixed_off_rub or 0)
        return min(max(pct, fixed), amount)  # larger of the two, never above the price
    if promo.type == "no_small_fee" and purpose == "balance_topup":
        fee = float(settings.SBP_SMALL_PAYMENT_FEE_RUB)
        # amount_rub arrives WITH the fee already added by the app when the
        # payment is below the threshold; the fee itself is the discount.
        if amount - fee < float(settings.SBP_SMALL_PAYMENT_THRESHOLD_RUB):
            return fee
        return 0.0
    return 0.0


async def apply_promo(
    db: AsyncSession,
    promo: PromoCode,
    user: User,
    purpose: str,
    amount_rub: float,
) -> Dict[str, Any]:
    """Compute final amount and create a pending redemption. Flush, no commit."""
    discount = compute_discount_rub(promo, purpose, amount_rub)
    final_amount = round(float(amount_rub) - discount, 2)
    redemption = PromoRedemption(
        promo_id=promo.id, user_id=user.id,
        discount_rub=discount, status="pending",
    )
    db.add(redemption)
    await db.flush()
    return {"discount_rub": discount, "final_amount_rub": final_amount, "redemption_id": redemption.id}


async def settle_redemption(db: AsyncSession, invoice_id: int, paid: bool) -> None:
    """Mark the invoice's redemption applied (and count the use) or canceled."""
    row = (await db.execute(
        select(PromoRedemption).where(
            PromoRedemption.invoice_id == invoice_id,
            PromoRedemption.status == "pending",
        )
    )).scalars().first()
    if not row:
        return
    if paid:
        row.status = "applied"
        promo = (await db.execute(select(PromoCode).where(PromoCode.id == row.promo_id))).scalar_one_or_none()
        if promo:
            promo.used_count = int(promo.used_count or 0) + 1
    else:
        row.status = "canceled"
    await db.flush()
