"""Alipay / WeChat Pay payments.

Flow: the user picks the service, enters the amount in yuan and the recipient
(Alipay: phone + name in Latin letters, or a receiving QR; WeChat: a receiving
QR), then pays in rubles by SBP (Bitbanker invoice, purpose china_payment).
Once the payment is captured the request becomes 'paid' and the managers get
it in Telegram (a dedicated bot when CHINA_BOT_TOKEN is set) together with
the QR image; they send the yuan and mark it done in the admin panel.
"""
import html as _html
import logging
import math
import re
import time as _time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.service_request import ServiceRequest
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["services"])

SERVICES = {"alipay": "Alipay", "wechat": "WeChat Pay"}
STATUS_LABELS = {
    "awaiting_payment": "Ожидает оплаты",
    "paid": "Оплачена",
    "in_progress": "В работе",
    "done": "Выполнена",
    "rejected": "Отклонена",
    "new": "Новая",  # legacy (before payment was built in)
}
OPEN_STATUSES = ("awaiting_payment", "paid", "in_progress", "new")

MAX_OPEN_REQUESTS = 3
MIN_INTERVAL = timedelta(seconds=30)
UNPAID_TTL = timedelta(hours=2)        # an unpaid request stops blocking after this
MAX_QR_BYTES = 6 * 1024 * 1024
QR_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static" / "private" / "service_qr"
QR_DIR.mkdir(parents=True, exist_ok=True)
_LATIN_NAME = re.compile(r"^[A-Za-z][A-Za-z' .-]{1,98}[A-Za-z.]$")


# --------------------------------------------------------------------- rate

async def cny_quote() -> dict:
    """Yuan rate.

    base_rate = Bitbanker exchange rate (RUB per USDT, no fees) / CHINA_CNY_DIVISOR
    (6.6 by default, editable in the admin panel) — shown on the China screen.
    rate      = base_rate + Bitbanker fee — what the user pays per yuan; the fee
    is shown separately in the payment breakdown.
    """
    from app.api.routers.sbp import SBP_MAX_AMOUNT_RUB, _get_bb_fee_params, _min_transfer_rub
    from app.services.rate_service import RateUnavailable, get_bb_index
    divisor = float(settings.CHINA_CNY_DIVISOR or 0)
    if divisor <= 0:
        raise HTTPException(502, "Курс юаня не настроен")
    try:
        index = await get_bb_index()
    except RateUnavailable as exc:
        raise HTTPException(502, str(exc))
    base = index / divisor
    bb_pct = float(settings.SBP_BITBANKER_FEE_PERCENT or 0)
    rate = base * (1 + bb_pct / 100.0)
    bb_fee, bb_min = await _get_bb_fee_params()
    return {
        "base_rate": round(base, 4),
        "rate": round(rate, 4),
        "fees": [{"label": settings.SBP_BITBANKER_FEE_LABEL, "percent": bb_pct}],
        "small_payment_fee_rub": settings.SBP_SMALL_PAYMENT_FEE_RUB,
        "small_payment_threshold_rub": settings.SBP_SMALL_PAYMENT_THRESHOLD_RUB,
        "min_transfer_rub": _min_transfer_rub(bb_fee, bb_min),
        "max_transfer_rub": SBP_MAX_AMOUNT_RUB,
        "min_cny": min_cny_map(),
    }


def min_cny_map() -> dict:
    return {
        "alipay": float(settings.CHINA_MIN_CNY_ALIPAY or 0),
        "wechat": float(settings.CHINA_MIN_CNY_WECHAT or 0),
    }


def rub_for_cny(amount_cny: Decimal, rate: float) -> tuple:
    """(base_rub, fee_rub, total_rub) — same rounding as the app."""
    base = math.ceil(float(amount_cny) * rate)
    fee = float(settings.SBP_SMALL_PAYMENT_FEE_RUB) if base < float(settings.SBP_SMALL_PAYMENT_THRESHOLD_RUB) else 0.0
    return base, fee, base + fee


@router.get("/rate", summary="Yuan rate for Alipay / WeChat Pay payments")
async def get_rate(_: User = Depends(get_current_user)):
    return await cny_quote()


# --------------------------------------------------------------------- helpers

def request_dict(r: ServiceRequest) -> dict:
    return {
        "id": r.id,
        "service": r.service,
        "service_label": SERVICES.get(r.service, r.service),
        "amount": float(r.amount),
        "currency": r.currency,
        "amount_rub": float(r.amount_rub) if r.amount_rub is not None else None,
        "rate_rub": float(r.rate_rub) if r.rate_rub is not None else None,
        "recipient_type": r.recipient_type,
        "recipient_phone": r.recipient_phone,
        "recipient_name": r.recipient_name,
        "has_qr": bool(r.qr_path),
        "note": r.note,
        "status": r.status,
        "status_label": STATUS_LABELS.get(r.status, r.status),
        "admin_comment": r.admin_comment,
        "invoice_id": r.invoice_id,
        "paid_at": r.paid_at.isoformat() if r.paid_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def manager_chat_ids() -> list:
    raw = str(settings.SERVICE_REQUEST_MANAGER_IDS or "")
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def qr_file(r: ServiceRequest) -> Optional[Path]:
    if not r.qr_path:
        return None
    p = QR_DIR / Path(r.qr_path).name
    return p if p.exists() else None


def _china_token() -> str:
    return (settings.CHINA_BOT_TOKEN or "").strip() or (settings.TELEGRAM_BOT_TOKEN or "").strip()


async def _tg_request(method: str, data: dict, photo: Optional[Path] = None) -> Optional[dict]:
    """Telegram call through the dedicated managers bot when CHINA_BOT_TOKEN is
    set, otherwise through the main bot. Returns `result` or None."""
    token = _china_token()
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    import json as _json
    async with httpx.AsyncClient(timeout=30) as c:
        if photo is not None:
            with open(photo, "rb") as fh:
                r = await c.post(url, data=data, files={"photo": (photo.name, fh.read(), "image/jpeg")})
        else:
            r = await c.post(url, json=data)
    try:
        j = r.json()
    except Exception:
        j = {}
    if not j.get("ok"):
        desc = str(j.get("description") or r.text)[:300]
        if "message is not modified" not in desc:
            logger.warning("[CHINA] Telegram %s to %s rejected: %s", method, data.get("chat_id"), desc)
        return None
    return j.get("result") if j.get("result") is not None else {}


async def _tg_call(method: str, data: dict, photo: Optional[Path] = None) -> bool:
    return (await _tg_request(method, data, photo)) is not None


def manager_keyboard(r: ServiceRequest, confirm_cancel: bool = False) -> Optional[dict]:
    """Inline buttons under the managers' message, by request status."""
    if r.status in ("done", "rejected"):
        return None
    if confirm_cancel:
        return {"inline_keyboard": [
            [{"text": "Да, отменить заявку", "callback_data": f"sr:cancel_yes:{r.id}"}],
            [{"text": "« Назад", "callback_data": f"sr:back:{r.id}"}],
        ]}
    rows = [[
        {"text": "✅ Выполнено", "callback_data": f"sr:done:{r.id}"},
        {"text": "❌ Отменить", "callback_data": f"sr:cancel:{r.id}"},
    ]]
    if r.status != "in_progress":
        rows.append([{"text": "💬 Отправить клиента в поддержку", "callback_data": f"sr:support:{r.id}"}])
    return {"inline_keyboard": rows}


async def send_to_managers(text: str, photo: Optional[Path] = None, reply_markup: Optional[dict] = None) -> dict:
    """chat_id -> message_id (None when not delivered)."""
    results = {}
    for chat_id in manager_chat_ids():
        try:
            payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
            if reply_markup:
                payload["reply_markup"] = reply_markup
            res = await _tg_request("sendMessage", payload)
            if res is not None and photo is not None:
                await _tg_request("sendPhoto", {"chat_id": chat_id, "caption": "QR-код получателя"}, photo=photo)
            results[chat_id] = (res or {}).get("message_id") if res is not None else None
        except Exception as exc:
            logger.warning("[CHINA] manager notify %s failed: %s", chat_id, exc)
            results[chat_id] = None
    return results


STATUS_FOOTER = {
    "paid": "",
    "in_progress": "💬 Клиент отправлен в поддержку",
    "done": "✅ Выполнено",
    "rejected": "❌ Отменено",
}


async def refresh_manager_messages(r: ServiceRequest, user: User, who: str = "") -> None:
    """Rewrite every manager's message for this request: status line + buttons."""
    if not r.manager_msgs:
        return
    text = manager_text(r, user)
    footer = STATUS_FOOTER.get(r.status, "")
    if footer:
        stamp = datetime.utcnow() + timedelta(hours=3)
        text += f"\n\n<b>{footer}</b>" + (f" — {_html.escape(who)}" if who else "") + f" · {stamp:%d.%m %H:%M} МСК"
    markup = manager_keyboard(r) or {"inline_keyboard": []}
    for pair in r.manager_msgs.split(","):
        chat_id, _, msg_id = pair.partition(":")
        if not chat_id or not msg_id:
            continue
        await _tg_request("editMessageText", {
            "chat_id": chat_id, "message_id": int(msg_id), "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": markup,
        })


async def _notify_user(user: User, text: str) -> None:
    try:
        from app.services.telegram_bot_service import send_notification
        if user.telegram_user_id:
            await send_notification(user.telegram_user_id, text)
    except Exception as exc:
        logger.warning("[CHINA] user notify failed: %s", exc)


async def apply_status_change(db: AsyncSession, r: ServiceRequest, new_status: str, who: str = "") -> None:
    """Status change from the manager buttons or the admin panel: tell the
    user and update the managers' messages."""
    old = r.status
    r.status = new_status
    if who:
        line = f"{STATUS_LABELS.get(new_status, new_status)}: {who} ({datetime.utcnow():%d.%m %H:%M} UTC)"
        r.admin_comment = f"{r.admin_comment}\n{line}" if r.admin_comment else line
    await db.commit()
    user = (await db.execute(select(User).where(User.id == r.user_id))).scalar_one_or_none()
    if not user:
        return
    amount = f"{float(r.amount):,.2f}".replace(",", " ")
    service = SERVICES.get(r.service, r.service)
    support = _html.escape(settings.SUPPORT_CONTACT or "")
    if new_status != old:
        if new_status == "done":
            await _notify_user(user, f"<b>✅ Перевод по заявке №{r.id} выполнен</b>\n\n{service}: {amount} ¥ отправлены получателю.")
        elif new_status == "rejected":
            await _notify_user(user, f"<b>❌ Заявка №{r.id} отменена</b>\n\n{service}: {amount} ¥.\nНапишите в поддержку {support}, укажите номер заявки — поможем с возвратом средств.")
        elif new_status == "in_progress":
            await _notify_user(user, f"<b>💬 Заявка №{r.id}: нужна помощь поддержки</b>\n\nПо переводу {amount} ¥ в {service} нужно уточнить детали. Пожалуйста, напишите в поддержку {support} и укажите номер заявки.")
    await refresh_manager_messages(r, user, who)


async def handle_manager_callback(cb: dict) -> None:
    """Inline button pressed under a managers' message (callback_data sr:<action>:<id>)."""
    from app.core.database import AsyncSessionLocal
    cb_id = cb.get("id")
    data = str(cb.get("data") or "")
    frm = cb.get("from") or {}
    msg = cb.get("message") or {}

    async def answer(text: str, alert: bool = False) -> None:
        await _tg_request("answerCallbackQuery", {"callback_query_id": cb_id, "text": text, "show_alert": alert})

    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "sr" or not parts[2].isdigit():
        await answer("Неизвестная команда")
        return
    action, request_id = parts[1], int(parts[2])
    if str(frm.get("id")) not in manager_chat_ids():
        await answer("Нет доступа: вы не менеджер заявок", alert=True)
        return
    who = f"@{frm['username']}" if frm.get("username") else (frm.get("first_name") or str(frm.get("id")))

    async with AsyncSessionLocal() as db:
        r = (await db.execute(select(ServiceRequest).where(ServiceRequest.id == request_id))).scalar_one_or_none()
        if not r:
            await answer("Заявка не найдена (удалена?)", alert=True)
            return
        user = (await db.execute(select(User).where(User.id == r.user_id))).scalar_one_or_none()
        if r.status in ("done", "rejected"):
            await answer(f"Заявка уже: {STATUS_LABELS.get(r.status, r.status)}")
            if user:
                await refresh_manager_messages(r, user)
            return
        chat_id, message_id = (msg.get("chat") or {}).get("id"), msg.get("message_id")
        if action == "cancel":
            await _tg_request("editMessageReplyMarkup", {
                "chat_id": chat_id, "message_id": message_id, "reply_markup": manager_keyboard(r, confirm_cancel=True),
            })
            await answer("Подтвердите отмену")
            return
        if action == "back":
            await _tg_request("editMessageReplyMarkup", {
                "chat_id": chat_id, "message_id": message_id, "reply_markup": manager_keyboard(r),
            })
            await answer("")
            return
        new_status = {"done": "done", "cancel_yes": "rejected", "support": "in_progress"}.get(action)
        if not new_status:
            await answer("Неизвестная команда")
            return
        await apply_status_change(db, r, new_status, who)
        await answer({"done": "Отмечено как выполненное", "rejected": "Заявка отменена",
                      "in_progress": "Клиенту отправлено сообщение про поддержку"}[new_status])
        logger.info("[CHINA] request #%s -> %s by %s", r.id, new_status, who)


def manager_text(r: ServiceRequest, user: User) -> str:
    handle = f"@{_html.escape(user.username)}" if user.username and not user.username.startswith("tg_") else "без username"
    tg = user.telegram_user_id or "—"
    if r.recipient_type == "phone":
        recipient = f"📱 {_html.escape(r.recipient_phone or '')} · {_html.escape(r.recipient_name or '')}"
    else:
        recipient = "🔳 QR-код (следующим сообщением)"
    amount_cny = f"{float(r.amount):,.2f}".replace(",", " ")
    amount_rub = f"{float(r.amount_rub or 0):,.0f}".replace(",", " ")
    return (
        f"<b>🧧 Оплаченная заявка №{r.id}: {SERVICES.get(r.service, r.service)}</b>\n\n"
        f"💴 К переводу: <b>{amount_cny} ¥</b>\n"
        f"💳 Оплачено по СБП: {amount_rub} ₽ (курс {float(r.rate_rub or 0):.4f})\n"
        f"👤 Получатель: {recipient}\n"
        f"📝 Примечание: {_html.escape(r.note or '—')}\n\n"
        f"Клиент: {handle} · ID <code>{tg}</code> · #{user.id} в админке"
    )


async def on_request_paid(db: AsyncSession, request_id: int, invoice_id: int) -> None:
    """Called once when the SBP invoice of a request is captured."""
    r = (await db.execute(select(ServiceRequest).where(ServiceRequest.id == request_id))).scalar_one_or_none()
    if not r or r.status not in ("awaiting_payment", "new"):
        return
    r.status = "paid"
    r.invoice_id = invoice_id
    r.paid_at = datetime.utcnow()
    await db.commit()
    user = (await db.execute(select(User).where(User.id == r.user_id))).scalar_one_or_none()
    if not user:
        return
    results = await send_to_managers(manager_text(r, user), qr_file(r), manager_keyboard(r))
    delivered = [f"{cid}:{mid}" for cid, mid in results.items() if mid]
    if delivered:
        r.manager_msgs = ",".join(delivered)
        await db.commit()
    if not delivered:
        logger.error("[CHINA] paid request #%s was NOT delivered to any manager (ids=%r)", r.id, settings.SERVICE_REQUEST_MANAGER_IDS)
        try:
            from app.services.recovery_service import _alert
            await _alert(f"⚠️ Оплаченная заявка Китай №{r.id} не доставлена менеджерам — проверьте SERVICE_REQUEST_MANAGER_IDS / бота.")
        except Exception:
            pass
    try:
        from app.services.telegram_bot_service import send_notification
        if user.telegram_user_id:
            await send_notification(
                user.telegram_user_id,
                f"<b>✅ Оплата по заявке №{r.id} получена</b>\n\n"
                f"{SERVICES.get(r.service, r.service)}: {float(r.amount):,.2f} ¥\n".replace(",", " ")
                + "Перевод получателю выполняется. Если возникнут вопросы, менеджер напишет вам в Telegram.",
            )
    except Exception as exc:
        logger.warning("[CHINA] user notify failed for request #%s: %s", r.id, exc)


# --------------------------------------------------------------------- user endpoints

@router.post("/requests", summary="Create an Alipay / WeChat Pay payment request (then pay it by SBP)")
async def create_request(
    service: str = Form(...),
    amount: str = Form(...),
    recipient_type: str = Form("qr"),
    recipient_phone: Optional[str] = Form(None),
    recipient_name: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    qr: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = (service or "").strip().lower()
    if service not in SERVICES:
        raise HTTPException(400, "Выберите сервис")
    try:
        amount_cny = Decimal(str(amount).replace(",", ".")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "Укажите сумму в юанях")
    if amount_cny <= 0:
        raise HTTPException(400, "Укажите сумму в юанях")
    _min = min_cny_map().get(service, 0)
    if _min > 0 and float(amount_cny) < _min:
        raise HTTPException(400, f"Минимальная сумма перевода в {SERVICES[service]} — {_min:g} ¥")

    recipient_type = "phone" if (service == "alipay" and recipient_type == "phone") else "qr"
    phone = name = None
    if recipient_type == "phone":
        phone = re.sub(r"[^\d+]", "", recipient_phone or "")
        if not re.fullmatch(r"\+?\d{7,15}", phone):
            raise HTTPException(400, "Укажите номер телефона Alipay полностью, с кодом страны")
        name = re.sub(r"\s+", " ", (recipient_name or "").strip())
        if not _LATIN_NAME.fullmatch(name) or " " not in name:
            raise HTTPException(400, "Укажите фамилию и имя латиницей, как в Alipay")
        name = name.upper()
    elif qr is None:
        raise HTTPException(400, "Загрузите QR-код для получения платежа")

    # Price check against the limits of an SBP payment
    quote = await cny_quote()
    base_rub, fee_rub, total_rub = rub_for_cny(amount_cny, quote["rate"])
    if total_rub < quote["min_transfer_rub"]:
        raise HTTPException(400, f"Минимальная сумма оплаты по СБП — {quote['min_transfer_rub']:,} ₽. Увеличьте сумму в юанях.".replace(",", " "))
    if total_rub > quote["max_transfer_rub"]:
        raise HTTPException(400, f"Максимальная сумма оплаты по СБП — {quote['max_transfer_rub']:,} ₽. Уменьшите сумму в юанях.".replace(",", " "))

    # Anti-spam: fresh open requests only (an abandoned unpaid one expires)
    fresh_after = datetime.utcnow() - UNPAID_TTL
    open_count = (await db.execute(
        select(func.count(ServiceRequest.id)).where(
            ServiceRequest.user_id == current_user.id,
            ServiceRequest.status.in_(OPEN_STATUSES),
            (ServiceRequest.status != "awaiting_payment") | (ServiceRequest.created_at >= fresh_after),
        )
    )).scalar() or 0
    if open_count >= MAX_OPEN_REQUESTS:
        raise HTTPException(429, "У вас уже есть незавершённые заявки. Дождитесь их выполнения.")
    last = (await db.execute(
        select(func.max(ServiceRequest.created_at)).where(ServiceRequest.user_id == current_user.id)
    )).scalar()
    if last and datetime.utcnow() - last < MIN_INTERVAL:
        raise HTTPException(429, "Слишком часто. Подождите полминуты.")

    qr_name = None
    if recipient_type == "qr" and qr is not None:
        data = await qr.read()
        if not data:
            raise HTTPException(400, "Файл QR-кода пустой")
        if len(data) > MAX_QR_BYTES:
            raise HTTPException(400, "Файл слишком большой (до 6 МБ)")
        if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[8:12] == b"WEBP" or data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1")):
            raise HTTPException(400, "Загрузите изображение QR-кода (JPG, PNG, WEBP или HEIC)")
        ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
        qr_name = f"{uuid.uuid4().hex}{ext}"
        (QR_DIR / qr_name).write_bytes(data)

    req = ServiceRequest(
        user_id=current_user.id, service=service, amount=amount_cny, currency="CNY",
        amount_rub=Decimal(str(total_rub)), rate_rub=Decimal(str(quote["rate"])),
        recipient_type=recipient_type, recipient_phone=phone, recipient_name=name, qr_path=qr_name,
        note=((note or "").strip()[:1000] or None), status="awaiting_payment",
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    logger.info("[CHINA] request #%s user_id=%s %s %s CNY = %s RUB", req.id, current_user.id, service, amount_cny, total_rub)
    out = request_dict(req)
    out.update({"base_rub": base_rub, "fee_rub": fee_rub})
    return out


@router.get("/requests", summary="My Alipay / WeChat Pay requests")
async def my_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(ServiceRequest).where(ServiceRequest.user_id == current_user.id)
        .order_by(ServiceRequest.id.desc()).limit(20)
    )).scalars().all()
    return {"items": [request_dict(r) for r in rows]}
