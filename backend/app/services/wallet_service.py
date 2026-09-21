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


async def referral_stats(db: AsyncSession, user_id: int) -> dict:
    count = (await db.execute(select(func.count(User.id)).where(User.referrer_id == user_id))).scalar() or 0
    earned = (await db.execute(
        select(func.coalesce(func.sum(BalanceTransaction.amount), 0)).where(
            BalanceTransaction.user_id == user_id, BalanceTransaction.type == "referral",
        )
    )).scalar() or 0
    return {"referrals_count": int(count), "referral_earned_usd": float(q2(earned))}


async def award_referral(
    db: AsyncSession,
    buyer: User,
    paid_usd,
    kind: str,
    ref_invoice_id: Optional[int] = None,
    ref_order_id: Optional[int] = None,
) -> Optional[BalanceTransaction]:
    """Credit the buyer's inviter with REFERRAL_PERCENT of `paid_usd`.
    kind: 'card_issue' | 'card_topup' (human label for the ledger / message).
    Idempotent per invoice / order reference."""
    if not buyer.referrer_id:
        return None
    pct = Decimal(str(settings.REFERRAL_PERCENT or 0))
    base = q2(paid_usd)
    if pct <= 0 or base <= 0:
        return None
    reward = q2(base * pct / Decimal("100"))
    if reward <= 0:
        return None

    # Idempotency: one reward per paid thing
    dup_q = select(BalanceTransaction.id).where(
        BalanceTransaction.type == "referral",
        BalanceTransaction.ref_user_id == buyer.id,
    )
    if ref_invoice_id:
        dup_q = dup_q.where(BalanceTransaction.ref_invoice_id == ref_invoice_id)
    elif ref_order_id:
        dup_q = dup_q.where(BalanceTransaction.ref_order_id == ref_order_id)
    else:
        dup_q = None
    if dup_q is not None and (await db.execute(dup_q.limit(1))).scalar_one_or_none():
        return None

    referrer = (await db.execute(select(User).where(User.id == buyer.referrer_id))).scalar_one_or_none()
    if not referrer or not referrer.is_active:
        return None

    label = "выпуск карты" if kind == "card_issue" else "пополнение карты"
    pct_str = f"{pct.normalize():f}"
    row = await credit(
        db, referrer, reward, "referral",
        f"Реферал @{buyer.username}: {label} ${base:.2f} x {pct_str}%",
        ref_invoice_id=ref_invoice_id, ref_order_id=ref_order_id, ref_user_id=buyer.id,
    )
    try:
        from app.services.telegram_bot_service import notify_referral_reward
        await notify_referral_reward(referrer, buyer, float(reward), float(base), label, float(referrer.balance))
    except Exception as exc:
        logger.warning("[REF] reward notification failed for user_id=%s: %s", referrer.id, exc)
    return row
