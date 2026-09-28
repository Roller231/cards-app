"""Payment service requests (Alipay / WeChat Pay): the user leaves a request,
managers are notified in Telegram and handle it from the admin panel."""
import html as _html
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.service_request import ServiceRequest
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["services"])

SERVICES = {"alipay": "Alipay", "wechat": "WeChat Pay", "other": "Другой сервис"}
CURRENCIES = {"CNY": "¥", "USD": "$", "EUR": "€"}
STATUS_LABELS = {"new": "Новая", "in_progress": "В работе", "done": "Выполнена", "rejected": "Отклонена"}

MAX_OPEN_REQUESTS = 3          # open (new / in_progress) requests per user
MIN_INTERVAL = timedelta(seconds=60)


class ServiceRequestCreate(BaseModel):
    service: str
    amount: float
    currency: str
    note: Optional[str] = None


def request_dict(r: ServiceRequest) -> dict:
    return {
        "id": r.id,
        "service": r.service,
        "service_label": SERVICES.get(r.service, r.service),
        "amount": float(r.amount),
        "currency": r.currency,
        "note": r.note,
        "status": r.status,
        "status_label": STATUS_LABELS.get(r.status, r.status),
        "admin_comment": r.admin_comment,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def manager_chat_ids() -> list:
    raw = str(settings.SERVICE_REQUEST_MANAGER_IDS or "")
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


async def notify_managers(req: ServiceRequest, user: User) -> int:
    """Send the new request to every manager. Returns how many got it."""
    from app.services.telegram_bot_service import send_notification
    handle = f"@{_html.escape(user.username)}" if user.username and not user.username.startswith("tg_") else "без username"
    tg = user.telegram_user_id or "—"
    note = _html.escape(req.note or "—")
    text = (
        f"<b>🧧 Новая заявка №{req.id}: {SERVICES.get(req.service, req.service)}</b>\n\n"
        f"💰 Сумма: <b>{float(req.amount):,.2f} {req.currency}</b>\n".replace(",", " ")
        + f"📝 Примечание: {note}\n\n"
        f"👤 {handle} · ID <code>{tg}</code>"
        + (f" · <a href=\"tg://user?id={tg}\">написать</a>" if user.telegram_user_id else "")
        + f"\n🆔 Пользователь в админке: #{user.id}"
    )
    sent = 0
    for chat_id in manager_chat_ids():
        try:
            if await send_notification(chat_id, text):
                sent += 1
        except Exception as exc:
            logger.warning("[SERVICES] manager notify %s failed: %s", chat_id, exc)
    return sent


@router.post("/requests", summary="Leave a payment service request")
async def create_request(
    body: ServiceRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = (body.service or "").strip().lower()
    currency = (body.currency or "").strip().upper()
    if service not in SERVICES:
        raise HTTPException(400, "Выберите сервис")
    if currency not in CURRENCIES:
        raise HTTPException(400, "Выберите валюту")
    try:
        amount = Decimal(str(body.amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "Укажите сумму")
    if amount <= 0 or amount > Decimal("10000000"):
        raise HTTPException(400, "Укажите корректную сумму")
    note = (body.note or "").strip()[:1000] or None
    if service == "other" and not note:
        raise HTTPException(400, "Опишите в примечании, какой сервис нужен")

    open_count = (await db.execute(
        select(func.count(ServiceRequest.id)).where(
            ServiceRequest.user_id == current_user.id,
            ServiceRequest.status.in_(("new", "in_progress")),
        )
    )).scalar() or 0
    if open_count >= MAX_OPEN_REQUESTS:
        raise HTTPException(429, "У вас уже есть открытые заявки. Дождитесь ответа менеджера.")
    last = (await db.execute(
        select(func.max(ServiceRequest.created_at)).where(ServiceRequest.user_id == current_user.id)
    )).scalar()
    if last and datetime.utcnow() - last < MIN_INTERVAL:
        raise HTTPException(429, "Заявка уже отправлена. Подождите минуту перед следующей.")

    req = ServiceRequest(
        user_id=current_user.id, service=service, amount=amount,
        currency=currency, note=note, status="new",
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    logger.info("[SERVICES] request #%s user_id=%s %s %s %s", req.id, current_user.id, service, amount, currency)

    sent = await notify_managers(req, current_user)
    if sent == 0:
        logger.warning("[SERVICES] request #%s: no manager was notified (SERVICE_REQUEST_MANAGER_IDS=%r)",
                       req.id, settings.SERVICE_REQUEST_MANAGER_IDS)
    try:
        from app.services.telegram_bot_service import send_notification
        if current_user.telegram_user_id:
            await send_notification(
                current_user.telegram_user_id,
                f"<b>✅ Заявка №{req.id} принята</b>\n\n"
                f"{SERVICES[service]} · {float(amount):,.2f} {currency}\n".replace(",", " ")
                + "Менеджер свяжется с вами в Telegram в ближайшее время.",
            )
    except Exception as exc:
        logger.warning("[SERVICES] user confirmation failed for request #%s: %s", req.id, exc)
    return request_dict(req)


@router.get("/requests", summary="My payment service requests")
async def my_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(ServiceRequest).where(ServiceRequest.user_id == current_user.id)
        .order_by(ServiceRequest.id.desc()).limit(20)
    )).scalars().all()
    return {"items": [request_dict(r) for r in rows]}
