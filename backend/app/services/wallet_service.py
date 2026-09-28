"""Internal USD balance (users.balance) + referral program.

All balance changes go through here so every cent is explained by a
BalanceTransaction row. Debits are atomic UPDATE ... WHERE balance >= amount,
so two parallel purchases can't both succeed on the same money.
"""
import logging
import secrets
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.balance_tx import BalanceTransaction
from app.models.user import User

logger = logging.getLogger(__name__)

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
CENT = Decimal("0.01")


def q2(v) -> Decimal:
    return Decimal(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)


# --- balance ledger ---------------------------------------------------------

async def credit(
    db: AsyncSession,
    user: User,
    amount,
    tx_type: str,
    description: str = "",
    ref_invoice_id: Optional[int] = None,
    ref_order_id: Optional[int] = None,
    ref_user_id: Optional[int] = None,
) -> BalanceTransaction:
    """Add `amount` (>0) to the user's balance and record it."""
    amt = q2(amount)
    if amt <= 0:
        raise ValueError("credit amount must be positive")
    await db.execute(
        update(User).where(User.id == user.id).values(balance=User.balance + amt)
    )
    await db.refresh(user, attribute_names=["balance"])
    row = BalanceTransaction(
        user_id=user.id, type=tx_type, amount=amt, balance_after=q2(user.balance),
        description=(description or "")[:255], ref_invoice_id=ref_invoice_id,
        ref_order_id=ref_order_id, ref_user_id=ref_user_id,
    )
    db.add(row)
    await db.flush()
    logger.info("[WALLET] +%s USD user_id=%s type=%s balance=%s (%s)", amt, user.id, tx_type, user.balance, description)
    return row


async def debit(
    db: AsyncSession,
    user: User,
    amount,
    tx_type: str,
    description: str = "",
    ref_order_id: Optional[int] = None,
) -> BalanceTransaction:
    """Take `amount` (>0) from the balance. Raises ValueError('INSUFFICIENT')
    when the user can't afford it — checked atomically in the UPDATE."""
    amt = q2(amount)
    if amt <= 0:
        raise ValueError("debit amount must be positive")
    res = await db.execute(
        update(User)
        .where(User.id == user.id, User.balance >= amt)
        .values(balance=User.balance - amt)
    )
    if res.rowcount != 1:
        await db.refresh(user, attribute_names=["balance"])
        raise ValueError("INSUFFICIENT")
    await db.refresh(user, attribute_names=["balance"])
    row = BalanceTransaction(
        user_id=user.id, type=tx_type, amount=-amt, balance_after=q2(user.balance),
        description=(description or "")[:255], ref_order_id=ref_order_id,
    )
    db.add(row)
    await db.flush()
    logger.info("[WALLET] -%s USD user_id=%s type=%s balance=%s (%s)", amt, user.id, tx_type, user.balance, description)
    return row


async def refund_order_charge(db: AsyncSession, user: User, order_id: int, charge_usd, reason: str = "") -> bool:
    """Return a balance charge for a failed balance-paid operation. Idempotent
    per order: a second call for the same order does nothing."""
    amt = q2(charge_usd)
    if amt <= 0:
        return False
    existing = (await db.execute(
        select(BalanceTransaction.id).where(
            BalanceTransaction.user_id == user.id,
            BalanceTransaction.type == "refund",
            BalanceTransaction.ref_order_id == order_id,
        ).limit(1)
    )).scalar_one_or_none()
    if existing:
        return False
    desc = f"Возврат: {reason}" if reason else "Возврат на баланс"
    await credit(db, user, amt, "refund", desc[:255], ref_order_id=order_id)
    return True


async def history(db: AsyncSession, user_id: int, limit: int = 50, offset: int = 0):
    rows = (await db.execute(
        select(BalanceTransaction)
        .where(BalanceTransaction.user_id == user_id)
        .order_by(BalanceTransaction.id.desc())
        .offset(offset).limit(limit)
    )).scalars().all()
    return [
        {
            "id": r.id,
            "type": r.type,
            "amount": float(r.amount),
            "balance_after": float(r.balance_after),
            "description": r.description,
            "ref_invoice_id": r.ref_invoice_id,
            "ref_order_id": r.ref_order_id,
            "ref_user_id": r.ref_user_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# --- referral program -------------------------------------------------------

async def ensure_referral_code(db: AsyncSession, user: User) -> str:
    """Lazily assign a unique invite code to the user."""
    if user.referral_code:
        return user.referral_code
    for _ in range(20):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        taken = (await db.execute(select(User.id).where(User.referral_code == code))).scalar_one_or_none()
        if not taken:
            user.referral_code = code
            await db.flush()
            return code
    raise RuntimeError("could not allocate a referral code")


def referral_link(code: str) -> str:
    return f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}/{settings.TELEGRAM_MINIAPP_SHORT_NAME}?startapp={code}"


def parse_start_param(raw: Optional[str]) -> Optional[str]:
    """Invite code from a start_param / /start payload. Accepts 'CODE' and
    'ref_CODE' / 'ref-CODE'; anything else is not an invite."""
    if not raw:
        return None
    s = str(raw).strip()
    for prefix in ("ref_", "ref-", "REF_", "REF-"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.upper()
    if 4 <= len(s) <= 16 and all(ch in _CODE_ALPHABET for ch in s):
        return s
    return None


async def attach_referrer(db: AsyncSession, new_user: User, start_param: Optional[str]) -> Optional[User]:
    """Bind a JUST-CREATED user to the inviter encoded in start_param.
    Rules: only for brand-new accounts (callers guarantee), never self,
    never overwritten later, unknown codes are silently ignored."""
    if new_user.referrer_id:
        return None
    code = parse_start_param(start_param)
    if not code:
        return None
    referrer = (await db.execute(select(User).where(User.referral_code == code))).scalar_one_or_none()
    if not referrer or referrer.id == new_user.id:
        return None
    if (new_user.telegram_user_id and referrer.telegram_user_id
            and new_user.telegram_user_id == referrer.telegram_user_id):
        return None
    new_user.referrer_id = referrer.id
    new_user.referred_at = datetime.utcnow()
    await db.flush()
    logger.info("[REF] user_id=%s referred by user_id=%s (code %s)", new_user.id, referrer.id, code)
    return referrer


async def has_issued_card(db: AsyncSession, user_id: int) -> bool:
    """The user has (or had) a real card: a completed issue order, or a card
    materialized at the provider. A later closed card still counts."""
    from app.models.card import Card
    from app.models.order import Order
    done = (await db.execute(
        select(Order.id).where(
            Order.user_id == user_id, Order.type == "issue", Order.status == "completed",
        ).limit(1)
    )).scalar_one_or_none()
    if done:
        return True
    card = (await db.execute(
        select(Card.id).where(Card.user_id == user_id, Card.aifory_card_id.is_not(None)).limit(1)
    )).scalar_one_or_none()
    return bool(card)


async def invitee_discount_percent(db: AsyncSession, user: User) -> float:
    """Discount on card issuance for an invited user: only for the FIRST card
    (no issue order that is completed or still in progress)."""
    pct = float(settings.REFERRAL_INVITEE_DISCOUNT_PERCENT or 0)
    if not user.referrer_id or pct <= 0:
        return 0.0
    from app.models.order import Order
    started = (await db.execute(
        select(Order.id).where(
            Order.user_id == user.id, Order.type == "issue",
            Order.status.in_(("completed", "pending", "processing")),
        ).limit(1)
    )).scalar_one_or_none()
    if started:
        return 0.0
    return pct


def apply_discount_rub(price_rub: float, pct: float) -> float:
    """Discounted RUB price, whole rubles (same rounding in app and backend)."""
    if pct <= 0:
        return float(price_rub)
    return float(round(float(price_rub) * (1 - pct / 100.0)))


async def _bonus_awarded(db: AsyncSession, referred_id: int) -> bool:
    return bool((await db.execute(
        select(BalanceTransaction.id).where(
            BalanceTransaction.type == "referral",
            BalanceTransaction.ref_user_id == referred_id,
        ).limit(1)
    )).scalar_one_or_none())


async def try_award_referral_bonus(db: AsyncSession, referred: User) -> Optional[BalanceTransaction]:
    """Fixed bonus for the inviter once BOTH the inviter and the invited user
    have a card. One bonus per invited user (idempotent)."""
    if not referred.referrer_id:
        return None
    bonus = q2(settings.REFERRAL_INVITER_BONUS_USD or 0)
    if bonus <= 0:
        return None
    if await _bonus_awarded(db, referred.id):
        return None
    referrer = (await db.execute(select(User).where(User.id == referred.referrer_id))).scalar_one_or_none()
    if not referrer or not referrer.is_active:
        return None
    if not await has_issued_card(db, referred.id) or not await has_issued_card(db, referrer.id):
        return None
    row = await credit(
        db, referrer, bonus, "referral",
        f"Бонус за приглашение @{referred.username}",
        ref_user_id=referred.id,
    )
    logger.info("[REF] bonus %s USD to user_id=%s for referred user_id=%s", bonus, referrer.id, referred.id)
    try:
        from app.services.telegram_bot_service import notify_referral_reward
        await notify_referral_reward(referrer, referred, float(bonus), float(referrer.balance))
    except Exception as exc:
        logger.warning("[REF] bonus notification failed for user_id=%s: %s", referrer.id, exc)
    return row


async def check_referral_bonuses_for(db: AsyncSession, user: User) -> None:
    """Called after the user's cards are synced: the user may have just got a
    card, which can unlock a bonus either as the invited one or as the inviter
    of people who already have cards."""
    if user.referrer_id:
        await try_award_referral_bonus(db, user)
    awarded_ids = select(BalanceTransaction.ref_user_id).where(
        BalanceTransaction.type == "referral", BalanceTransaction.ref_user_id.is_not(None),
    )
    waiting = (await db.execute(
        select(User).where(User.referrer_id == user.id, User.id.not_in(awarded_ids))
    )).scalars().all()
    if waiting and await has_issued_card(db, user.id):
        for referred in waiting:
            await try_award_referral_bonus(db, referred)


async def referral_stats(db: AsyncSession, user_id: int) -> dict:
    count = (await db.execute(select(func.count(User.id)).where(User.referrer_id == user_id))).scalar() or 0
    earned = (await db.execute(
        select(func.coalesce(func.sum(BalanceTransaction.amount), 0)).where(
            BalanceTransaction.user_id == user_id, BalanceTransaction.type == "referral",
        )
    )).scalar() or 0
    rewarded = (await db.execute(
        select(func.count(BalanceTransaction.id)).where(
            BalanceTransaction.user_id == user_id, BalanceTransaction.type == "referral",
        )
    )).scalar() or 0
    return {
        "referrals_count": int(count),
        "referrals_rewarded": int(rewarded),
        "referrals_waiting": max(int(count) - int(rewarded), 0),
        "referral_earned_usd": float(q2(earned)),
    }
