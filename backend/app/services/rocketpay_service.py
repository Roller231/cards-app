"""Rocketpay cards ("Pay": Apple Pay capable) — second card provider.

Model differences from O-Plata:
- One company USD pool ("balance") pays card prices and funds cards; topped
  up with USDT TRC20 to our deposit address. No per-user wallets.
- Cards are issued to Rocketpay's pool of verified clients (not to our
  users): we never send user KYC; a card goes to whichever client has room.
- Funding/withdrawal/closure move money pool <-> card; closing a card returns
  its balance to the pool automatically.
- No webhooks: card status, movements and transactions are polled.

Local storage reuses the `cards` table: offer_id = RP_RAVANA ("ROCKETPAY"),
aifory_card_id = Rocketpay card id ("card_…"). Orders keep the O-Plata
description formats so auto-recovery and history keep working.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.integrations.rocketpay_client import RocketpayError, is_configured, money, rocketpay_client
from app.models.card import Card
from app.models.order import Order
from app.models.user import User

logger = logging.getLogger(__name__)

RP_RAVANA = "ROCKETPAY"
RP_TYPE = "pay"
RP_OFFER_ID = f"{RP_RAVANA}:{RP_TYPE}"
RP_CARD_NAME = "Pay"            # internal type name: price / promo / toggle of the "Pay" card

ISSUE_POLL_SECONDS = 600        # how long the follow-up waits for `active`
MOVEMENT_POLL_SECONDS = 900     # how long a funding is followed
CLOSURE_POLL_SECONDS = 600

_FINAL_MOVEMENT = {"completed", "failed", "cancelled"}
_FAILED_CARD = {"failed", "closed", "expired"}


def is_rocketpay(offer_or_ravana: Any) -> bool:
    return str(offer_or_ravana or "").upper().startswith(RP_RAVANA)


def tester_ids() -> set:
    raw = str(settings.ROCKETPAY_TEST_USER_IDS or "")
    return {p.strip() for p in raw.replace(";", ",").split(",") if p.strip()}


def is_tester(user: Optional[User]) -> bool:
    return bool(user and user.telegram_user_id and str(user.telegram_user_id) in tester_ids())


def available_for(user: Optional[User]) -> bool:
    """The Pay card is offered when the API is configured and the card type
    is switched on — or, while it's off, to the tester Telegram ids."""
    if not is_configured():
        return False
    return bool(settings.CARD_PAY_ENABLED) or is_tester(user)


def _status_local(rp_status: Any) -> str:
    s = str(rp_status or "").lower()
    if s == "active":
        return "active"
    if s in ("pending", "under_review"):
        return "processing"
    return s or "inactive"


def _status_code(local: str) -> int:
    return 2 if local == "active" else (1 if local == "processing" else 0)


def _expiry_str(card: Dict[str, Any]) -> Optional[str]:
    e = card.get("expiry") or {}
    try:
        return f"{int(e.get('month')):02d}.{int(e.get('year'))}"
    except Exception:
        return None


def _holder(card: Dict[str, Any]) -> Optional[str]:
    c = card.get("client") or {}
    name = f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip()
    return name.upper() or None


def _balance(card: Dict[str, Any]) -> Optional[Decimal]:
    b = card.get("balances") or {}
    v = b.get("available") if b.get("available") is not None else b.get("balance")
    try:
        return Decimal(str(v)) if v is not None else None
    except Exception:
        return None


def _apply_card(local: Card, rp: Dict[str, Any]) -> None:
    status = _status_local(rp.get("status"))
    local.status = status
    local.card_status = _status_code(status)
    local.last4 = rp.get("last4") or local.last4
    local.expired_at = _expiry_str(rp) or local.expired_at
    local.holder_name = _holder(rp) or local.holder_name
    local.currency = (rp.get("currency") or local.currency or "USD")
    bal = _balance(rp)
    if bal is not None:
        local.balance = bal


async def _alert_admins(text: str) -> None:
    try:
        from app.services.recovery_service import _alert
        await _alert(text)
    except Exception as exc:
        logger.warning("[RP] admin alert failed: %s", exc)


async def _check_capacity() -> None:
    """Warn admins when Rocketpay's pool of verified clients runs low:
    issuing fails with no_client_available once it's empty."""
    try:
        cap = await rocketpay_client.capacity()
        left = int(cap.get("cards_left") or 0)
        if left <= int(settings.ROCKETPAY_LOW_CAPACITY_ALERT or 0):
            await _alert_admins(f"⚠️ Rocketpay: осталось мест под карты — {left}. Попросите Rocketpay зарегистрировать новых клиентов.")
    except Exception as exc:
        logger.debug("[RP] capacity check failed: %s", exc)


# ======================================================================== offers

async def offer_for(db: AsyncSession, user: Optional[User], force: bool = False) -> Optional[Dict[str, Any]]:
    """force: admin manual issuing — show whenever the API is configured."""
    if not (available_for(user) or (force and is_configured())):
        return None
    current = 0
    if user is not None:
        current = (await db.execute(
            select(func.count(Card.id)).where(
                Card.user_id == user.id, Card.offer_id == RP_RAVANA,
                Card.status.in_(("active", "processing", "blocked")),
            )
        )).scalar() or 0
    name = RP_CARD_NAME
    return {
        "id": RP_OFFER_ID,
        "name": name,
        "display_name": settings.CARD_PAY_PROMO_TITLE or name,
        "payment_system": "visa",
        "currency": "USD",
        "issue_fee": 0.0,
        "minimum_card_balance": 0.0,
        "monthly_fee": 0.0,
        "ravana_server_id": RP_RAVANA,
        "type_uuid": RP_TYPE,
        "max_issued_count": int(settings.ROCKETPAY_MAX_CARDS_PER_USER or 1),
        "current_count": int(current),
        "description": f"{name} | Rocketpay",
    }


# ======================================================================== issue

async def issue_card(
    db: AsyncSession,
    user: User,
    *,
    sbp_invoice_id: Optional[int] = None,
    balance_charge_usd: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """Issue a Rocketpay card for `user`. Creates the order and a local card
    row right away (status processing), then follows the card to `active`
    in the background and notifies the user."""
    from app.services.card_service import card_service

    limit_cards = int(settings.ROCKETPAY_MAX_CARDS_PER_USER or 1)
    current = (await db.execute(
        select(func.count(Card.id)).where(
            Card.user_id == user.id, Card.offer_id == RP_RAVANA,
            Card.status.in_(("active", "processing", "blocked")),
        )
    )).scalar() or 0
    if current >= limit_cards:
        raise ValueError(f"Достигнут лимит карт Pay: {current} из {limit_cards}")

    order = Order(
        user_id=user.id,
        type="issue",
        amount=Decimal("0"),
        fee=Decimal("0"),
        status="processing",
        description=(
            f"Card issuance: {RP_OFFER_ID}"
            + (f" sbp_invoice:{sbp_invoice_id}" if sbp_invoice_id else "")
            + card_service._balance_charge_tag(balance_charge_usd)
        ),
    )
    db.add(order)
    await db.flush()

    external_id = f"pp-u{user.id}-o{order.id}"
    limit_type = (settings.ROCKETPAY_CARD_LIMIT_TYPE or "monthly").strip()
    try:
        rp = await rocketpay_client.issue_card(
            external_id=external_id,
            limits={limit_type: settings.ROCKETPAY_CARD_LIMIT_USD},
            metadata={"user_id": str(user.id), "tg_id": str(user.telegram_user_id or ""), "order_id": str(order.id)},
            idempotency_key=f"issue-{external_id}",
        )
    except RocketpayError as exc:
        # The background runner that called us refunds a balance charge and
        # notifies the user when we raise — don't do it twice here.
        order.status = "failed"
        await db.commit()
        if exc.code == "no_client_available":
            await _alert_admins("⛔ Rocketpay: нет свободных клиентов под карты (no_client_available). Выпуск карт Pay не работает.")
        elif exc.code == "insufficient_funds":
            await _alert_admins("⛔ Rocketpay: на балансе компании не хватает денег на выпуск карты.")
        raise ValueError(_human_error(exc)) from exc

    if "approval" in rp:
        # Company requires a second approval in the dashboard
        order.description = (order.description or "") + " rp_approval:" + str((rp.get("approval") or {}).get("id"))
        await db.commit()
        await _alert_admins(f"Rocketpay: выпуск карты для #{user.id} ждёт подтверждения в кабинете Rocketpay.")
        return {"local_order_id": order.id, "partner_order_id": None}

    card = Card(
        user_id=user.id,
        aifory_card_id=rp.get("id"),
        offer_id=RP_RAVANA,
        currency=rp.get("currency") or "USD",
        balance=Decimal("0"),
        status="processing",
        card_status=1,
    )
    _apply_card(card, rp)
    db.add(card)
    await db.flush()
    order.card_id = card.id
    order.partner_order_id = rp.get("id")
    fee_mv = rp.get("fee_movement") or {}
    try:
        order.fee = Decimal(str(fee_mv.get("fee") or (fee_mv.get("amount") or {}).get("amount") or 0))
    except Exception:
        pass
    if card.status == "active":
        order.status = "completed"
    await db.commit()
    logger.info("[RP] card issued: user_id=%s order_id=%s rp_card=%s status=%s", user.id, order.id, card.aifory_card_id, card.status)

    asyncio.create_task(_follow_issue(user.id, order.id, card.id))
    asyncio.create_task(_check_capacity())
    return {"local_order_id": order.id, "partner_order_id": card.aifory_card_id}


async def _follow_issue(user_id: int, order_id: int, local_card_id: int) -> None:
    from app.services.card_service import card_service
    from app.services.telegram_bot_service import notify_card_issued

    deadline = asyncio.get_event_loop().time() + ISSUE_POLL_SECONDS
    delay = 3.0
    while True:
        async with AsyncSessionLocal() as db:
            card = (await db.execute(select(Card).where(Card.id == local_card_id))).scalar_one_or_none()
            order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if not card or not order or not user:
                return
            try:
                rp = await rocketpay_client.get_card(card.aifory_card_id)
            except RocketpayError as exc:
                rp = None
                logger.info("[RP] issue follow-up poll failed for %s: %s", card.aifory_card_id, exc)
            if rp is not None:
                _apply_card(card, rp)
                rp_status = str(rp.get("status") or "").lower()
                if rp_status == "active":
                    order.status = "completed"
                    if not order.notified:
                        await notify_card_issued(db=db, user=user, card_amount=0.0, card_last4=card.last4 or "",
                                                 fee=float(order.fee or 0), success=True)
                        order.notified = True
                    await db.commit()
                    logger.info("[RP] card active: user_id=%s card=%s ...%s", user.id, card.aifory_card_id, card.last4)
                    return
                if rp_status in _FAILED_CARD:
                    order.status = "failed"
                    await card_service._refund_balance_charge(db, user, order, f"выпуск карты не выполнен ({rp_status})")
                    if not order.notified:
                        await notify_card_issued(db=db, user=user, card_amount=0.0, card_last4="", fee=0.0,
                                                 success=False, error_msg="Банк не выпустил карту")
                        order.notified = True
                    await db.commit()
                    await _alert_admins(f"⚠️ Rocketpay: карта {card.aifory_card_id} для #{user.id} не выпущена (status={rp_status}).")
                    return
                await db.commit()
        if asyncio.get_event_loop().time() > deadline:
            await _alert_admins(f"⚠️ Rocketpay: карта для #{user_id} (order {order_id}) не стала активной за {ISSUE_POLL_SECONDS // 60} мин. Проверьте вручную.")
            return
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 30.0)


# ======================================================================== fund

async def deposit_card(
    db: AsyncSession,
    user: User,
    card: Card,
    amount: float,
    *,
    balance_charge_usd: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """Move `amount` USD from the company pool to the card."""
    from app.services.card_service import card_service
    from app.services.telegram_bot_service import notify_topup_result

    base_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    order = Order(
        user_id=user.id,
        card_id=card.id,
        type="topup",
        amount=base_amount,
        fee=Decimal("0"),
        status="processing",
        description=f"Card top-up: ${float(base_amount):.2f} to card ...{(card.aifory_card_id or '')[-8:]}"
                    + card_service._balance_charge_tag(balance_charge_usd),
    )
    db.add(order)
    await db.flush()
    external_id = f"pp-topup-o{order.id}"
    try:
        mv = await rocketpay_client.fund_card(
            card.aifory_card_id, base_amount, external_id=external_id,
            idempotency_key=f"fund-{external_id}",
            metadata={"user_id": str(user.id), "order_id": str(order.id)},
        )
    except RocketpayError as exc:
        # The background runner refunds a balance charge and notifies the
        # user when we raise — don't do it twice here.
        order.status = "failed"
        order.notified = True
        await db.commit()
        if exc.code == "insufficient_funds":
            await _alert_admins(f"⛔ Rocketpay: на балансе компании не хватает денег на пополнение карты #{user.id} на ${float(base_amount):.2f}.")
        raise ValueError(_human_error(exc)) from exc

    if "approval" in mv:
        order.description = (order.description or "") + " rp_approval:" + str((mv.get("approval") or {}).get("id"))
        await db.commit()
        await _alert_admins(f"Rocketpay: пополнение карты #{user.id} на ${float(base_amount):.2f} ждёт подтверждения в кабинете.")
        return {"local_order_id": order.id, "partner_order_id": None}

    order.partner_order_id = mv.get("id")
    try:
        order.fee = Decimal(str(mv.get("fee") or 0))
    except Exception:
        pass
    status = str(mv.get("status") or "").lower()
    if status == "completed":
        order.status = "completed"
        order.notified = True  # success is announced by the transaction watcher
    await db.commit()
    logger.info("[RP] funding %s for card %s: $%s status=%s", mv.get("id"), card.aifory_card_id, base_amount, status)
    if status != "completed":
        asyncio.create_task(_follow_movement(user.id, order.id, card.id, mv.get("id")))
    return {"local_order_id": order.id, "partner_order_id": mv.get("id")}


async def _follow_movement(user_id: int, order_id: int, local_card_id: int, movement_id: str) -> None:
    from app.services.card_service import card_service
    from app.services.telegram_bot_service import notify_topup_result

    deadline = asyncio.get_event_loop().time() + MOVEMENT_POLL_SECONDS
    delay = 3.0
    while True:
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 30.0)
        try:
            mv = await rocketpay_client.get_movement(movement_id)
        except RocketpayError as exc:
            logger.info("[RP] movement poll %s failed: %s", movement_id, exc)
            mv = None
        status = str((mv or {}).get("status") or "").lower()
        if status in _FINAL_MOVEMENT or asyncio.get_event_loop().time() > deadline:
            async with AsyncSessionLocal() as db:
                order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
                user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
                card = (await db.execute(select(Card).where(Card.id == local_card_id))).scalar_one_or_none()
                if not order or not user:
                    return
                if status == "completed":
                    order.status = "completed"
                    order.notified = True
                    if card:
                        try:
                            _apply_card(card, await rocketpay_client.get_card(card.aifory_card_id))
                        except Exception:
                            pass
                elif status in ("failed", "cancelled"):
                    order.status = "failed"
                    await card_service._refund_balance_charge(db, user, order, f"пополнение карты не выполнено ({status})")
                    if not order.notified:
                        await notify_topup_result(db=db, user=user, card_last4=(card.last4 if card else "") or "",
                                                  amount=float(order.amount or 0), fee=0.0, success=False,
                                                  error_msg="Банк отклонил пополнение")
                        order.notified = True
                else:
                    await _alert_admins(f"⚠️ Rocketpay: пополнение {movement_id} (order {order_id}) не завершилось за {MOVEMENT_POLL_SECONDS // 60} мин (status={status or '?'}).")
                await db.commit()
                logger.info("[RP] funding %s final: %s", movement_id, status)
            return


# ======================================================================== sync / read

async def sync_user_cards(db: AsyncSession, user: User) -> None:
    """Refresh status/balance of the user's Rocketpay cards (no deletes:
    a card that disappears upstream is marked, never dropped silently)."""
    if not is_configured():
        return
    cards = (await db.execute(
        select(Card).where(Card.user_id == user.id, Card.offer_id == RP_RAVANA, Card.aifory_card_id.is_not(None))
    )).scalars().all()
    for card in cards:
        if card.status in ("closed",):
            continue
        try:
            _apply_card(card, await rocketpay_client.get_card(card.aifory_card_id))
        except RocketpayError as exc:
            if exc.code == "not_found":
                card.status = "closed"
                card.card_status = 0
            logger.info("[RP] sync %s failed: %s", card.aifory_card_id, exc)


async def get_requisites(card: Card) -> Dict[str, Any]:
    if card.status != "active":
        raise ValueError("Card is not active yet")
    raw = await rocketpay_client.card_details(card.aifory_card_id)
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    exp = data.get("expiry") or {}
    if isinstance(exp, dict) and exp.get("month"):
        expiry = f"{int(exp['month']):02d}/{str(exp.get('year'))[-2:]}"
    else:
        expiry = data.get("expiry_date") or data.get("expiration") or (exp if isinstance(exp, str) else None) or card.expired_at
    return {
        "card_number": data.get("pan") or data.get("number") or data.get("card_number"),
        "expiry": expiry,
        "cvv": data.get("cvv") or data.get("cvc") or data.get("cvv2") or data.get("security_code"),
        "holder_name": data.get("holder_name") or data.get("cardholder_name") or data.get("name") or card.holder_name,
    }


def normalize_transaction(t: Dict[str, Any]) -> Dict[str, Any]:
    """Rocketpay TxnView -> the O-Plata-shaped dict the app and the watcher use."""
    typ = str(t.get("type") or "").lower()
    status = str(t.get("status") or "").lower()
    card_amt = (t.get("card_amount") or t.get("amount") or {})
    try:
        value = float(card_amt.get("amount") or 0)
    except (TypeError, ValueError):
        value = 0.0
    currency = card_amt.get("currency") or "USD"
    fees = t.get("fees") or {}
    try:
        fee = float(fees.get("total_fee") or 0)
    except (TypeError, ValueError):
        fee = 0.0
    if status in ("declined", "cancelled"):
        tx_type, display = "declined", 0.0
    elif typ == "fee":
        tx_type, display = "fee", -abs(value)
    elif typ in ("top_up", "refund"):
        tx_type, display = ("refund" if typ == "refund" else "topup"), abs(value)
    else:
        tx_type, display = "payment", -abs(value)
    merchant = (t.get("merchant") or {}).get("name") or ""
    decline = t.get("decline") or {}
    return {
        "id": t.get("id"),
        "type": typ,
        "status": status,
        "tx_type": tx_type,
        "display_amount": display,
        "display_currency": currency,
        "amount": value,
        "currency": currency,
        "settlementAmount": value,
        "settlementCurrency": currency,
        "feeAmount": fee if typ != "fee" else 0,
        "feeCurrency": fees.get("currency") or currency,
        "merchantName": merchant or (decline.get("title") if decline else "") or ("Комиссия" if typ == "fee" else ""),
        "declineReason": decline.get("title") if decline else None,
        "createdAt": t.get("transaction_at"),
        "transactionAt": t.get("transaction_at"),
        "displayStatus": t.get("display_status"),
    }


async def get_transactions(card: Card, limit: int = 50) -> List[Dict[str, Any]]:
    resp = await rocketpay_client.card_transactions(card.aifory_card_id, limit=limit)
    return [normalize_transaction(t) for t in (resp.get("items") or []) if isinstance(t, dict)]


# ======================================================================== close

async def close_card(user_id: int, local_card_id: int) -> None:
    """Admin: close at Rocketpay; the remaining balance returns to our pool."""
    async with AsyncSessionLocal() as db:
        card = (await db.execute(select(Card).where(Card.id == local_card_id, Card.user_id == user_id))).scalar_one_or_none()
        if not card or not card.aifory_card_id:
            logger.error("[RP] close: card %s not found", local_card_id)
            return
        rp_card_id = card.aifory_card_id
    try:
        preview = await rocketpay_client.closure_preview(rp_card_id)
        logger.info("[RP] closure preview %s: %s", rp_card_id, {k: preview.get(k) for k in ("remaining_balance", "pending_transactions", "fee", "can_close", "blocked_by")})
        if not preview.get("can_close"):
            await _alert_admins(f"⚠️ Rocketpay: карту {rp_card_id} сейчас закрыть нельзя ({preview.get('blocked_by')}).")
            return
        res = await rocketpay_client.close_card(rp_card_id, "Closed by ProntoPay admin", idempotency_key=f"close-{rp_card_id}")
        if "approval" in res:
            await _alert_admins(f"Rocketpay: закрытие карты {rp_card_id} ждёт подтверждения в кабинете.")
            return
        closure_id = res.get("id")
        deadline = asyncio.get_event_loop().time() + CLOSURE_POLL_SECONDS
        status = str(res.get("status") or "").lower()
        while status not in ("completed", "failed", "manual_review") and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(5)
            status = str((await rocketpay_client.get_closure(closure_id)).get("status") or "").lower()
        if status != "completed":
            await _alert_admins(f"⚠️ Rocketpay: закрытие карты {rp_card_id} — статус {status}. Проверьте в кабинете.")
            return
    except RocketpayError as exc:
        await _alert_admins(f"⚠️ Rocketpay: закрытие карты {rp_card_id} не удалось: {exc.code} {exc.message}")
        return
    async with AsyncSessionLocal() as db:
        card = (await db.execute(select(Card).where(Card.id == local_card_id))).scalar_one_or_none()
        if card:
            for o in (await db.execute(select(Order).where(Order.card_id == card.id))).scalars().all():
                o.card_id = None
            await db.delete(card)
            await db.commit()
    logger.info("[RP] card %s closed, balance returned to pool", rp_card_id)


# ======================================================================== admin status

async def admin_status() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "configured": is_configured(),
        "enabled_for_all": bool(settings.CARD_PAY_ENABLED),
        "testers": sorted(tester_ids()),
    }
    if not is_configured():
        return out
    try:
        me = await rocketpay_client.me()
        out["environment"] = me.get("environment")
        out["permissions"] = me.get("permissions")
        out["api_user"] = me.get("email")
    except RocketpayError as exc:
        out["error"] = f"{exc.code}: {exc.message}"
        return out
    try:
        accounts = await rocketpay_client.accounts()
        out["accounts"] = [
            {"id": a.get("id"), "currency": a.get("currency"), "status": a.get("status"),
             "program": (a.get("program") or {}).get("name"), "pool": a.get("pool")}
            for a in accounts
        ]
    except RocketpayError as exc:
        out["accounts_error"] = exc.code
    try:
        out["capacity"] = await rocketpay_client.capacity()
    except RocketpayError as exc:
        out["capacity_error"] = exc.code
    try:
        out["programs"] = [
            {"id": p.get("id"), "name": p.get("name"), "card_type": p.get("card_type"), "currency": p.get("currency"),
             "bins": p.get("bins")}
            for p in await rocketpay_client.card_programs()
        ]
    except RocketpayError as exc:
        out["programs_error"] = exc.code
    return out


def _human_error(exc: RocketpayError) -> str:
    return {
        "no_client_available": "Сейчас нет возможности выпустить карту. Попробуйте позже или напишите в поддержку.",
        "insufficient_funds": "Временная техническая проблема у партнёра. Попробуйте позже.",
        "card_not_active": "Карта не активна.",
        "card_not_issued": "Карта ещё выпускается, попробуйте через пару минут.",
    }.get(exc.code, f"Ошибка банка-партнёра ({exc.code})")
