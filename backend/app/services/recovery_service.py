"""Auto-recovery of paid SBP invoices whose outcome never materialized.

Covers the failure classes seen in production: provider 500s on
card/virtual/issue, funding waits lost to slow EON transfers, background
tasks killed by deploy restarts. A paid invoice must always end in a card
(card_issue) or a card deposit (balance_topup); when it hasn't after a grace
period, the worker re-triggers the same post-payment flow the webhook runs.

Safety rails:
- only invoices younger than RECOVER_MAX_AGE_H (old stuck ones stay manual
  via the admin's "Довести" button);
- grace period after payment before the first retry (the normal flow may
  still be running);
- at most RECOVER_MAX_ATTEMPTS attempts, spaced RECOVER_MIN_INTERVAL_MIN
  apart; the issue flow's own idempotency guard additionally refuses to run
  while a previous attempt is in flight;
- every attempt and the final give-up are reported to the admin Telegram
  chat (ADMIN_ALERT_CHAT_ID), so nothing fails silently.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.bb_invoice import BbInvoice
from app.models.card import Card
from app.models.order import Order

logger = logging.getLogger(__name__)

RECOVER_GRACE_MIN = 10          # let the normal flow finish first
RECOVER_MIN_INTERVAL_MIN = 15   # pause between attempts
RECOVER_MAX_ATTEMPTS = 3
RECOVER_MAX_AGE_H = 48


async def _alert(text: str) -> None:
    """Send to every admin chat: ADMIN_ALERT_CHAT_ID holds one or more
    comma-separated chat ids ('123, 456')."""
    raw = (settings.ADMIN_ALERT_CHAT_ID or "").strip()
    if not raw:
        return
    from app.services.telegram_bot_service import send_notification
    for chat_id in [p.strip() for p in raw.split(",") if p.strip()]:
        try:
            await send_notification(chat_id, text)
        except Exception as exc:
            logger.warning("[RECOVER] admin alert to %s failed: %s", chat_id, exc)


async def _issue_outcome(db, inv: BbInvoice) -> Optional[str]:
    """'done' | 'in_flight' | None (= needs recovery) for a card_issue invoice."""
    orders = (await db.execute(
        select(Order).where(
            Order.user_id == inv.user_id,
            Order.type == "issue",
            Order.description.like(f"%sbp_invoice:{inv.id}%"),
        )
    )).scalars().all()
    for o in orders:
        if o.card_id is not None:
            return "done"
        if o.status in ("pending", "processing"):
            return "in_flight"
    return None


async def _topup_outcome(db, inv: BbInvoice) -> Optional[str]:
    """'done' | 'in_flight' | None for a balance_topup invoice."""
    if not inv.card_id:
        return "done"  # nothing we can do without a card reference
    tail = inv.card_id[-8:]
    orders = (await db.execute(
        select(Order).where(
            Order.user_id == inv.user_id,
            Order.type == "topup",
            Order.created_at >= inv.created_at,
        )
    )).scalars().all()
    for o in orders:
        if tail not in (o.description or ""):
            continue
        if o.status == "completed":
            return "done"
        if o.status in ("pending", "processing"):
            return "in_flight"
    return None


async def scan_and_recover() -> None:
    if not settings.AUTO_RECOVER_ENABLED:
        return
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        candidates = (await db.execute(
            select(BbInvoice).where(
                BbInvoice.status.in_(("captured", "authorized")),
                BbInvoice.purpose.in_(("card_issue", "balance_topup")),
                BbInvoice.created_at >= now - timedelta(hours=RECOVER_MAX_AGE_H),
                BbInvoice.created_at <= now - timedelta(minutes=RECOVER_GRACE_MIN),
            ).order_by(BbInvoice.id.asc())
        )).scalars().all()

        for inv in candidates:
            attempts = int(inv.recover_attempts or 0)
            if attempts >= RECOVER_MAX_ATTEMPTS:
                continue
            if inv.last_recover_at and inv.last_recover_at > now - timedelta(minutes=RECOVER_MIN_INTERVAL_MIN):
                continue

            outcome = await (_issue_outcome(db, inv) if inv.purpose == "card_issue" else _topup_outcome(db, inv))
            if outcome == "done":
                if attempts > 0 and inv.last_recover_at:
                    # A previous auto-attempt finished the job — say so once.
                    inv.recover_attempts = RECOVER_MAX_ATTEMPTS + 1  # stop re-checking
                    await db.commit()
                    await _alert(
                        f"✅ Авто-дожим: инвойс #{inv.id} ({'выпуск' if inv.purpose == 'card_issue' else 'пополнение'}, "
                        f"user {inv.user_id}, {float(inv.amount_rub):.0f} ₽) успешно доведён."
                    )
                continue
            if outcome == "in_flight":
                continue

            inv.recover_attempts = attempts + 1
            inv.last_recover_at = now
            await db.commit()

            kind = "выпуск карты" if inv.purpose == "card_issue" else "пополнение карты"
            logger.warning("[RECOVER] invoice %s (%s, user %s): attempt %s/%s",
                           inv.id, inv.purpose, inv.user_id, attempts + 1, RECOVER_MAX_ATTEMPTS)
            await _alert(
                f"⚠️ Авто-дожим: {kind} по инвойсу #{inv.id} (user {inv.user_id}, "
                f"{float(inv.amount_rub):.0f} ₽) не завершился — запускаю попытку {attempts + 1}/{RECOVER_MAX_ATTEMPTS}."
            )
            try:
                from app.api.routers.sbp import _trigger_post_payment
                await _trigger_post_payment(inv.id)
            except Exception as exc:
                logger.error("[RECOVER] invoice %s attempt failed: %s", inv.id, str(exc)[:300])

            if attempts + 1 >= RECOVER_MAX_ATTEMPTS:
                await _alert(
                    f"🆘 Авто-дожим: инвойс #{inv.id} (user {inv.user_id}) не доведён за "
                    f"{RECOVER_MAX_ATTEMPTS} попытки. Нужно ручное вмешательство: админка → "
                    f"пользователь → СБП-платежи → «Довести», либо смотреть логи."
                )
