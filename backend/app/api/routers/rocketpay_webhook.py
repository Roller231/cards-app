"""Rocketpay webhooks: POST /webhooks/rocketpay (public: /api/webhooks/rocketpay).

The one event we can't get any other way is `card.otp`: the one-time code the
card issuer sends when a card is added to Apple Pay / Google Pay or an online
purchase needs confirming. It never appears in the API or the events feed, so
without this endpoint the code is simply lost. We forward it to the card's
owner in Telegram.

Signed per Standard Webhooks: HMAC-SHA256 of "{id}.{timestamp}.{body}" keyed
with the base64-decoded part of the endpoint secret after "whsec_"
(ROCKETPAY_WEBHOOK_SECRET, server env only). Answer 2xx fast, work after.
"""
import asyncio
import base64
import hashlib
import hmac
import html
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.card import Card
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_TOLERANCE_S = 5 * 60
_seen_ids: "OrderedDict[str, float]" = OrderedDict()  # webhook-id dedupe


def _verify(headers, body: bytes) -> bool:
    secret = (settings.ROCKETPAY_WEBHOOK_SECRET or "").strip()
    if not secret:
        return False
    msg_id = headers.get("webhook-id") or ""
    ts = headers.get("webhook-timestamp") or ""
    sig_header = headers.get("webhook-signature") or ""
    try:
        if abs(time.time() - int(ts)) > _TOLERANCE_S:
            return False
        key = base64.b64decode(secret[len("whsec_"):] if secret.startswith("whsec_") else secret)
    except Exception:
        return False
    signed = f"{msg_id}.{ts}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    # After a secret rotation the header holds two "v1,<sig>" entries
    for part in sig_header.split():
        version, _, sig = part.partition(",")
        if version == "v1" and hmac.compare_digest(sig, expected):
            return True
    return False


def _money(m: Optional[Dict[str, Any]]) -> str:
    if not m:
        return ""
    return f"{m.get('amount')} {m.get('currency') or ''}".strip()


async def _forward_otp(event: Dict[str, Any]) -> None:
    from app.services.recovery_service import _alert
    from app.services.telegram_bot_service import send_notification

    data = event.get("data") or {}
    rp_card = data.get("object") or {}
    otp = data.get("otp") or {}
    code = otp.get("code")
    card_id = rp_card.get("id")
    if not code or not card_id:
        logger.warning("[RP-WH] card.otp without code/card: event=%s", event.get("id"))
        return

    async with AsyncSessionLocal() as db:
        card = (await db.execute(select(Card).where(Card.aifory_card_id == card_id))).scalars().first()
        user = await db.get(User, card.user_id) if card else None

    last4 = (card.last4 if card else None) or rp_card.get("last4") or ""
    merchant = (otp.get("merchant") or {}).get("name")
    amount = _money(otp.get("amount"))
    if amount or merchant:
        purpose = "Подтверждение покупки" + (f": {html.escape(amount)}" if amount else "") + \
                  (f", {html.escape(merchant)}" if merchant else "")
    else:
        purpose = "Если вы добавляете карту в Apple Pay или Google Pay, введите этот код."
    text = (
        f"🔐 Код подтверждения для карты •••• {html.escape(last4)}\n\n"
        f"<code>{html.escape(str(code))}</code>\n\n"
        f"{purpose}\nКод действует несколько минут. Никому его не сообщайте."
    )

    if user and user.telegram_user_id:
        ok = await send_notification(str(user.telegram_user_id), text)
        logger.info("[RP-WH] otp forwarded: user_id=%s card=%s delivered=%s", user.id, card_id, ok)
        if ok:
            return
    # Unknown card or undeliverable: admins pass it on by hand (the code is
    # useless to anyone without the card details).
    logger.warning("[RP-WH] otp for card=%s could not reach the owner (local card=%s)", card_id, bool(card))
    await _alert(
        f"⚠️ Код Rocketpay не доставлен владельцу карты {card_id} (•••• {last4}"
        f"{f', user_id={user.id}' if user else ', карта не найдена у нас'}): {code}"
    )


@router.post("/rocketpay", include_in_schema=False)
async def rocketpay_webhook(request: Request):
    body = await request.body()
    if not _verify(request.headers, body):
        logger.warning("[RP-WH] rejected: bad signature/timestamp (id=%s)", request.headers.get("webhook-id"))
        raise HTTPException(status_code=401, detail="bad signature")

    msg_id = request.headers.get("webhook-id") or ""
    if msg_id in _seen_ids:
        return {"ok": True, "duplicate": True}
    _seen_ids[msg_id] = time.time()
    while len(_seen_ids) > 2000:
        _seen_ids.popitem(last=False)

    try:
        event = json.loads(body)
    except ValueError:
        return {"ok": True}
    etype = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    logger.info("[RP-WH] %s id=%s object=%s", etype, event.get("id"), obj.get("id"))

    if etype == "card.otp":
        asyncio.create_task(_forward_otp(event))
    # Other events: the pollers (issue/fund follow-ups, 5-min transaction
    # watcher) already handle them; logged above for now.
    return {"ok": True}
