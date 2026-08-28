"""
Admin panel API — authentication, dashboard, CRUD users/cards/orders/payments, analytics, settings.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.integrations.oplata_client import oplata_client
from app.models.admin_setting import AdminSetting
from app.models.card import Card
from app.models.faq import FAQ
from app.models.order import Order
from app.models.topup import BalanceTopUpRequest
from app.models.user import User
from app.seed.faq_seed import seed_faqs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# --------------- helpers ---------------

SETTINGS_KEYS: Dict[str, Dict[str, Any]] = {
    "CARD_ONLINE_ENABLED": {"desc": "Карта Online — доступна для выпуска", "type": bool},
    "CARD_ONLINE_PLUS_ENABLED": {"desc": "Карта Online+Pay — доступна для выпуска", "type": bool},
    "CARD_PAY_ENABLED": {"desc": "Карта Pay (универсальная) — доступна для выпуска", "type": bool},
    "CARD_ISSUANCE_PRICE_RUB": {"desc": "Цена выпуска карты Online (руб) — итоговая сумма к оплате через СБП", "type": float},
    "CARD_ISSUANCE_PRICE_PAY_RUB": {"desc": "Цена выпуска карты Online+Pay (руб) — итоговая сумма к оплате через СБП", "type": float},
    "CARD_ISSUANCE_PRICE_UNIV_RUB": {"desc": "Цена выпуска карты Pay (руб) — итоговая сумма к оплате через СБП", "type": float},
    "ONLINE_TOPUP_MARKUP_PERCENT": {"desc": "Online card top-up markup (%)", "type": float},
    "ONLINE_PLUS_TOPUP_MARKUP_PERCENT": {"desc": "Online+Pay card top-up markup (%)", "type": float},
    "UNIV_TOPUP_MARKUP_PERCENT": {"desc": "Pay card top-up markup (%) — витрина", "type": float},
    "UNIV_OPERATION_FEE_USD": {"desc": "Pay card operation fee (USD) — витрина", "type": float},
    "UNIV_CARD_VALIDITY_TEXT": {"desc": "Pay card validity text", "type": str},
    # Промо-плашки на главной (все поля редактируемые)
    "CARD_ONLINE_PROMO_TITLE": {"desc": "Online: заголовок плашки", "type": str},
    "CARD_ONLINE_PROMO_DESC": {"desc": "Online: описание плашки", "type": str},
    "CARD_ONLINE_PROMO_BADGE": {"desc": "Online: зелёный бейдж", "type": str},
    "CARD_ONLINE_PROMO_PAYS": {"desc": "Online: текст блока «Оплачивайте»", "type": str},
    "CARD_ONLINE_PROMO_BIN": {"desc": "Online: страна BIN", "type": str},
    "CARD_ONLINE_PLUS_PROMO_TITLE": {"desc": "Online+Pay: заголовок плашки", "type": str},
    "CARD_ONLINE_PLUS_PROMO_DESC": {"desc": "Online+Pay: описание плашки", "type": str},
    "CARD_ONLINE_PLUS_PROMO_BADGE": {"desc": "Online+Pay: зелёный бейдж", "type": str},
    "CARD_ONLINE_PLUS_PROMO_PAYS": {"desc": "Online+Pay: текст блока «Оплачивайте»", "type": str},
    "CARD_ONLINE_PLUS_PROMO_BIN": {"desc": "Online+Pay: страна BIN", "type": str},
    "CARD_PAY_PROMO_TITLE": {"desc": "Pay: заголовок плашки", "type": str},
    "CARD_PAY_PROMO_DESC": {"desc": "Pay: описание плашки", "type": str},
    "CARD_PAY_PROMO_BADGE": {"desc": "Pay: зелёный бейдж", "type": str},
    "CARD_PAY_PROMO_PAYS": {"desc": "Pay: текст блока «Оплачивайте»", "type": str},
    "CARD_PAY_PROMO_BIN": {"desc": "Pay: страна BIN", "type": str},
    "SBP_BITBANKER_FEE_PERCENT": {"desc": "Процент Битбанкера в курсе (2.1 → множитель 1.021)", "type": float},
    "SBP_OUR_FEE_PERCENT": {"desc": "Наш процент в курсе (1.9 → множитель 1.019)", "type": float},
    "SBP_CLARUS_FEE_PERCENT": {"desc": "Процент Clarus в курсе (2.8 → множитель 1.028)", "type": float},
    "SBP_BB_MIN_FEE_RUB": {"desc": "Мин. комиссия Битбанкера за QR (₽) — фолбэк, если их API недоступен (сейчас 21, будет 210)", "type": float},
    "CARD_BILLING_ADDRESS": {"desc": "Биллинговый адрес карт (блок «Информация по карте»)", "type": str},
    "ONLINE_CARD_VALIDITY_TEXT": {"desc": "Online card validity text", "type": str},
    "ONLINE_PLUS_CARD_VALIDITY_TEXT": {"desc": "Online+ card validity text", "type": str},
    "ONLINE_OPERATION_FEE_USD": {"desc": "Online card operation fee (USD)", "type": float},
    "ONLINE_PLUS_OPERATION_FEE_USD": {"desc": "Online+ card operation fee (USD)", "type": float},
}


def _cast_setting_value(value: Any, target_type: type) -> Any:
    if target_type is bool:
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        return s in ("1", "true", "yes", "on")
    return target_type(value)


def _type_name(t: type) -> str:
    if t is bool:
        return "bool"
    if t is int:
        return "int"
    if t is float:
        return "float"
    return "string"


def _user_dict(u: User, cards_count: int = 0) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "telegram_user_id": u.telegram_user_id,
        "balance": float(u.balance),
        "is_active": u.is_active,
        "cards_count": cards_count,
    }


def _card_dict(c: Card) -> dict:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "aifory_card_id": c.aifory_card_id,
        "category": c.category,
        "card_status": c.card_status,
        "expired_at": c.expired_at,
        "last4": c.last4,
        "holder_name": c.holder_name,
        "currency": c.currency,
        "currency_id": c.currency_id,
        "payment_system_id": c.payment_system_id,
        "status": c.status,
        "balance": float(c.balance) if c.balance else 0,
        "offer_id": c.offer_id,
    }


def _order_dict(o: Order) -> dict:
    return {
        "id": o.id,
        "user_id": o.user_id,
        "partner_order_id": o.partner_order_id,
        "card_id": o.card_id,
        "type": o.type,
        "amount": float(o.amount),
        "fee": float(o.fee),
        "status": o.status,
        "description": o.description,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def _topup_dict(t: BalanceTopUpRequest) -> dict:
    return {
        "id": t.id,
        "user_id": t.user_id,
        "amount": float(t.amount),
        "status": t.status,
        "payment_reference": t.payment_reference,
        "comment": t.comment,
    }


# =====================  AUTH  =====================

class AdminLoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/login", summary="Admin login")
async def admin_login(body: AdminLoginRequest):
    if body.email != settings.ADMIN_EMAIL or body.password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    token = create_access_token("admin", timedelta(hours=24))
    return {"access_token": token}


# =====================  DASHBOARD  =====================

@router.get("/dashboard", summary="Dashboard stats")
async def dashboard(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    users_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar() or 0
    cards_count = (await db.execute(select(func.count(Card.id)))).scalar() or 0
    orders_count = (await db.execute(select(func.count(Order.id)))).scalar() or 0
    total_revenue = float((await db.execute(select(func.coalesce(func.sum(Order.fee), 0)))).scalar() or 0)
    total_order_volume = float((await db.execute(select(func.coalesce(func.sum(Order.amount), 0)))).scalar() or 0)

    # Recent 10 orders
    recent_orders_q = await db.execute(select(Order).order_by(Order.created_at.desc()).limit(10))
    recent_orders = [_order_dict(o) for o in recent_orders_q.scalars().all()]

    return {
        "users_count": users_count,
        "active_users": active_users,
        "banned_users": users_count - active_users,
        "cards_count": cards_count,
        "orders_count": orders_count,
        "total_revenue": total_revenue,
        "total_order_volume": total_order_volume,
        "recent_orders": recent_orders,
    }


# =====================  USERS  =====================

@router.get("/users", summary="List users")
async def list_users(
    search: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_admin),
):
    q = select(User)
    if search:
        q = q.where(or_(
            User.username.ilike(f"%{search}%"),
            User.telegram_user_id.ilike(f"%{search}%"),
        ))
    q = q.order_by(User.id.desc()).offset(offset).limit(limit)
    users = (await db.execute(q)).scalars().all()

    # cards count per user
    result = []
    for u in users:
        cc = (await db.execute(select(func.count(Card.id)).where(Card.user_id == u.id))).scalar() or 0
        result.append(_user_dict(u, cc))
    total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    return {"items": result, "total": total}


@router.get("/users/{user_id}", summary="Get user detail")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    cc = (await db.execute(select(func.count(Card.id)).where(Card.user_id == user.id))).scalar() or 0
    return _user_dict(user, cc)


class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    balance: Optional[float] = None
    is_active: Optional[bool] = None
    telegram_user_id: Optional[str] = None


@router.put("/users/{user_id}", summary="Update user")
async def update_user(user_id: int, body: UserUpdateRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if body.username is not None:
        user.username = body.username
    if body.balance is not None:
        user.balance = Decimal(str(body.balance))
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.telegram_user_id is not None:
        user.telegram_user_id = body.telegram_user_id
    return _user_dict(user)


@router.post("/users/{user_id}/ban", summary="Ban user")
async def ban_user(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    user.is_active = False
    return {"ok": True}


@router.post("/users/{user_id}/unban", summary="Unban user")
async def unban_user(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    user.is_active = True
    return {"ok": True}


@router.get("/users/{user_id}/cards", summary="User cards")
async def user_cards(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    cards = (await db.execute(select(Card).where(Card.user_id == user_id))).scalars().all()
    return [_card_dict(c) for c in cards]


@router.get("/users/{user_id}/orders", summary="User orders")
async def user_orders(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    orders = (await db.execute(select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()))).scalars().all()
    return [_order_dict(o) for o in orders]


@router.get("/users/{user_id}/topup-requests", summary="User topup requests")
async def user_topup_requests(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    reqs = (await db.execute(
        select(BalanceTopUpRequest).where(BalanceTopUpRequest.user_id == user_id)
    )).scalars().all()
    return [_topup_dict(t) for t in reqs]


class AdminIssueCardRequest(BaseModel):
    offer_id: str


@router.get("/users/{user_id}/issue-offers", summary="Card types available to issue for this user")
async def user_issue_offers(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    from app.services.card_service import card_service
    offers = await card_service.get_offers(user)
    return {
        "items": [
            {
                "offer_id": o["id"],
                "name": o["name"],
                "display_name": o["display_name"],
                "currency": o["currency"],
                "current_count": o["current_count"],
                "max_issued_count": o["max_issued_count"],
            }
            for o in offers
        ]
    }


@router.post("/users/{user_id}/issue-card", summary="Issue a card of the chosen type for a user (admin, free of charge)")
async def admin_issue_card(user_id: int, body: AdminIssueCardRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    """Fire-and-forget: full issuance (KYC/registration, funding from the
    parent wallet, provider issue, materialization wait, user notification)
    runs in the background — it can take several minutes. Track progress via
    the user's issue order and cards list."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    offer_id = (body.offer_id or "").strip()
    if not offer_id:
        raise HTTPException(400, "offer_id is required")

    # Fail fast on obvious blockers so the admin sees them in the UI instead
    # of a silently failed background task.
    from app.services.card_service import card_service, _is_univ_ravana, _is_univ_email_ok
    ravana_id = offer_id.rsplit(":", 1)[0]
    if _is_univ_ravana(ravana_id):
        if not _is_univ_email_ok(user.email or ""):
            raise HTTPException(400, "У пользователя должна быть почта Gmail/iCloud (раздел верификации)")
        if user.kyc_status != "success":
            raise HTTPException(400, "Пользователь не прошёл KYC-верификацию")

    name_parts = (user.kyc_first_name or user.username or "User").strip().split()
    holder_first = name_parts[0] if name_parts else "User"
    holder_last = " ".join(name_parts[1:]) if len(name_parts) > 1 else "User"

    import asyncio as _asyncio
    from app.core.database import AsyncSessionLocal

    async def _run():
        async with AsyncSessionLocal() as bg_db:
            try:
                bg_user = (await bg_db.execute(select(User).where(User.id == user_id))).scalar_one()
                await card_service.issue_card(
                    db=bg_db,
                    user=bg_user,
                    offer_id=offer_id,
                    holder_first_name=holder_first,
                    holder_last_name=holder_last,
                    email=bg_user.email,
                    skip_balance_check=True,
                )
                await bg_db.commit()
                logger.info("[ADMIN] Issue card completed for user_id=%s offer=%s", user_id, offer_id)
            except Exception as exc:
                logger.error("[ADMIN] Issue card failed for user_id=%s offer=%s: %s", user_id, offer_id, exc)
                try:
                    await bg_db.rollback()
                except Exception:
                    pass

    _asyncio.create_task(_run())
    return {"ok": True, "message": "Выпуск запущен в фоне (обычно 2–5 минут). Следите за картами и ордерами пользователя."}


class AdminDepositCardRequest(BaseModel):
    card_id: str      # local card id or aifory card id
    amount: float


@router.post("/users/{user_id}/deposit-card", summary="Manually top up a user's card (admin, funded from parent)")
async def admin_deposit_card(user_id: int, body: AdminDepositCardRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    """Runs the full deposit flow in the background (funding from the parent
    wallet + provider top-up + user notification), free of charge for the user."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if body.amount <= 0:
        raise HTTPException(400, "Сумма должна быть больше нуля")
    from app.services.card_service import card_service
    card = None
    for c in (await db.execute(select(Card).where(Card.user_id == user_id))).scalars().all():
        if str(c.id) == body.card_id or c.aifory_card_id == body.card_id:
            card = c
    if not card or not card.aifory_card_id:
        raise HTTPException(404, "Карта не найдена или не материализована")
    card_service.schedule_deposit_in_background(
        user_id=user_id, card_id=card.aifory_card_id,
        amount=float(body.amount), skip_balance_check=True,
    )
    return {"ok": True, "message": f"Пополнение ${body.amount:.2f} карты ...{card.last4} запущено в фоне (1–3 минуты)."}


@router.get("/users/{user_id}/invoices", summary="User's SBP invoices with deposit-delivery status")
async def user_invoices(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    """Recent Bitbanker invoices. For captured balance_topup invoices also says
    whether the card deposit actually went through (a completed topup order
    created at/after the invoice), so the admin can see and retry stuck ones."""
    from app.models.bb_invoice import BbInvoice
    invoices = (await db.execute(
        select(BbInvoice).where(BbInvoice.user_id == user_id).order_by(BbInvoice.id.desc()).limit(30)
    )).scalars().all()
    orders = (await db.execute(
        select(Order).where(Order.user_id == user_id, Order.type == "topup").order_by(Order.id.desc()).limit(100)
    )).scalars().all()
    cards_by_aifory = {c.aifory_card_id: c for c in (await db.execute(select(Card).where(Card.user_id == user_id))).scalars().all()}

    def _delivered(inv) -> Optional[bool]:
        if inv.purpose != "balance_topup" or inv.status not in ("captured", "authorized"):
            return None
        tail = (inv.card_id or "")[-8:]
        for o in orders:
            if o.created_at and inv.created_at and o.created_at >= inv.created_at and tail and tail in (o.description or ""):
                if o.status == "completed":
                    return True
        return False

    out = []
    for inv in invoices:
        card = cards_by_aifory.get(inv.card_id)
        out.append({
            "id": inv.id, "purpose": inv.purpose, "status": inv.status,
            "amount_rub": float(inv.amount_rub),
            "amount_usd_requested": float(inv.amount_usd_requested) if inv.amount_usd_requested else None,
            "card_last4": card.last4 if card else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "deposit_delivered": _delivered(inv),
        })
    return {"items": out}


@router.post("/invoices/{invoice_id}/retry-deposit", summary="Re-run the card deposit for a paid top-up invoice")
async def retry_invoice_deposit(invoice_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    """For a captured balance_topup invoice whose card deposit failed/expired:
    re-runs the deposit in the background. Funds already sitting on the user's
    O-Plata wallet from previous attempts are reused (shortfall accounting)."""
    from app.models.bb_invoice import BbInvoice
    from app.services.card_service import card_service
    inv = (await db.execute(select(BbInvoice).where(BbInvoice.id == invoice_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Инвойс не найден")
    if inv.purpose != "balance_topup":
        raise HTTPException(400, "Это не инвойс пополнения карты")
    if inv.status not in ("captured", "authorized"):
        raise HTTPException(400, f"Инвойс не оплачен (статус {inv.status})")
    if not inv.card_id:
        raise HTTPException(400, "У инвойса нет карты")
    amount = float(inv.amount_usd_requested or 0)
    if amount <= 0:
        raise HTTPException(400, "У инвойса нет суммы депозита")
    # Free stuck pending/failed topup orders for this card so retry isn't blocked
    tail = (inv.card_id or "")[-8:]
    for o in (await db.execute(select(Order).where(Order.user_id == inv.user_id, Order.type == "topup", Order.status.in_(("pending", "processing"))))).scalars().all():
        if tail and tail in (o.description or ""):
            o.status = "failed"
    await db.flush()
    card_service.schedule_deposit_in_background(
        user_id=inv.user_id, card_id=inv.card_id,
        amount=amount, skip_balance_check=True,
    )
    return {"ok": True, "message": f"Доведение пополнения ${amount:.2f} запущено в фоне (1–3 минуты)."}


@router.get("/users/{user_id}/limits", summary="User's SBP QR-code limits and other rate limits")
async def user_limits(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    """Everything that can currently stop this user from creating an SBP QR code
    or otherwise hit a rate limit, in one place. Extend this dict (not a new
    endpoint) when a new per-user limit is added elsewhere in the app."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    from app.api.routers.sbp import get_sbp_qr_status
    sbp_qr = await get_sbp_qr_status(db, user)
    return {"sbp_qr": sbp_qr}


@router.post("/users/{user_id}/limits/reset-sbp-qr", summary="Reset user's SBP QR-code limits")
async def reset_user_sbp_qr_limit(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    """Unblocks a user stuck behind our own 'daily QR cap' / 'no 3rd consecutive
    unpaid QR' guards (see app/api/routers/sbp.py::get_sbp_qr_status) by making
    all their invoices created so far invisible to those guards. This is purely
    local bookkeeping — it does NOT touch any block Bitbanker itself may hold
    on the account; if Bitbanker has separately blocked the user, contact their
    support."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    user.sbp_qr_reset_at = datetime.utcnow()
    await db.flush()
    from app.api.routers.sbp import get_sbp_qr_status
    return {"ok": True, "sbp_qr": await get_sbp_qr_status(db, user)}


# =====================  CARDS  =====================

@router.get("/cards", summary="All local cards")
async def list_cards(
    search: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_admin),
):
    q = select(Card)
    if search:
        q = q.where(or_(
            Card.last4.ilike(f"%{search}%"),
            Card.holder_name.ilike(f"%{search}%"),
            Card.aifory_card_id.ilike(f"%{search}%"),
        ))
    q = q.order_by(Card.id.desc()).offset(offset).limit(limit)
    cards = (await db.execute(q)).scalars().all()
    total = (await db.execute(select(func.count(Card.id)))).scalar() or 0

    # Attach usernames
    result = []
    for c in cards:
        d = _card_dict(c)
        u = (await db.execute(select(User.username).where(User.id == c.user_id))).scalar()
        d["username"] = u
        result.append(d)
    return {"items": result, "total": total}


@router.get("/cards/unlinked", summary="Local card records with no external card ID")
async def unlinked_cards(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    """Return cards that have no external (O-Plata) card ID linked."""
    cards = (await db.execute(
        select(Card).where(Card.aifory_card_id.is_(None))
    )).scalars().all()
    return [_card_dict(c) for c in cards]


class CardAssignRequest(BaseModel):
    user_id: int
    external_card_id: str
    ravana_server_id: str = ""
    holder_name: str = ""
    last4: str = ""
    currency: str = "USD"
    balance: float = 0.0


@router.post("/cards/assign", summary="Manually assign an external card to a user")
async def assign_card(body: CardAssignRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    user = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    existing = (await db.execute(
        select(Card).where(Card.aifory_card_id == body.external_card_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(400, f"Card {body.external_card_id} already assigned to user {existing.user_id}")

    card = Card(
        user_id=body.user_id,
        aifory_card_id=body.external_card_id,
        offer_id=body.ravana_server_id or None,
        holder_name=body.holder_name or None,
        last4=body.last4 or None,
        currency=body.currency or "USD",
        balance=Decimal(str(body.balance)),
        status="active",
        card_status=2,
    )
    db.add(card)
    await db.flush()
    return _card_dict(card)


class CardUpdateRequest(BaseModel):
    user_id: Optional[int] = None
    holder_name: Optional[str] = None
    status: Optional[str] = None
    offer_id: Optional[str] = None


@router.put("/cards/{card_id}", summary="Update card")
async def update_card(card_id: int, body: CardUpdateRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    card = (await db.execute(select(Card).where(Card.id == card_id))).scalar_one_or_none()
    if not card:
        raise HTTPException(404, "Card not found")
    if body.user_id is not None:
        card.user_id = body.user_id
    if body.holder_name is not None:
        card.holder_name = body.holder_name
    if body.status is not None:
        card.status = body.status
    if body.offer_id is not None:
        card.offer_id = body.offer_id
    return _card_dict(card)


class CloseCardRequest(BaseModel):
    sweep_to_parent: bool = False


@router.post("/cards/{card_id}/close", summary="Close card at O-Plata (cashout balance, close, delete local)")
async def admin_close_card(card_id: int, body: CloseCardRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    """Background: cashout card balance to the user's wallet, close the card at
    the provider, delete the local row. With sweep_to_parent also returns the
    wallet balance to the parent client. Deleting only the local row is useless:
    sync re-adopts the live provider card on the user's next visit."""
    card = (await db.execute(select(Card).where(Card.id == card_id))).scalar_one_or_none()
    if not card:
        raise HTTPException(404, "Card not found")
    if not card.aifory_card_id:
        # Placeholder with no provider card — plain local delete is enough
        await db.delete(card)
        return {"ok": True, "message": "Локальный плейсхолдер удалён (у провайдера карты не было)."}
    from app.services.card_service import card_service
    import asyncio as _asyncio
    _asyncio.create_task(card_service.close_card_and_sweep(
        user_id=card.user_id, local_card_id=card.id, sweep_to_parent=body.sweep_to_parent,
    ))
    return {"ok": True, "message": "Закрытие запущено в фоне (1–3 минуты): вывод остатка"
            + (", возврат на родительский кошелёк" if body.sweep_to_parent else "")
            + ", закрытие у провайдера, удаление записи."}


@router.post("/cards/sync-all", summary="Sync cards from O-Plata for all users")
async def admin_sync_all_cards(_=Depends(get_admin)):
    from app.services.card_service import card_service
    import asyncio as _asyncio
    _asyncio.create_task(card_service.sync_all_users())
    return {"ok": True, "message": "Синхронизация всех пользователей запущена в фоне (по числу юзеров, до нескольких минут). Обновите список позже."}


@router.delete("/cards/{card_id}", summary="Delete card assignment")
async def delete_card(card_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    card = (await db.execute(select(Card).where(Card.id == card_id))).scalar_one_or_none()
    if not card:
        raise HTTPException(404, "Card not found")
    await db.delete(card)
    return {"ok": True}


@router.get("/cards/{card_id}/transactions", summary="Card transactions from O-Plata")
async def card_transactions(card_id: int, page: int = 0, page_size: int = 20, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    card = (await db.execute(select(Card).where(Card.id == card_id))).scalar_one_or_none()
    if not card or not card.aifory_card_id:
        raise HTTPException(404, "Card not found or has no external card ID")
    if not card.offer_id:
        raise HTTPException(400, "Card has no ravanaServerId (offer_id) stored — cannot fetch transactions")
    client_id = f"user_{card.user_id}"
    try:
        return await oplata_client.get_card_transaction_list(
            client_id=client_id,
            card_id=card.aifory_card_id,
            ravana_server_id=card.offer_id,
            page_number=page,
            page_size=page_size,
        )
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


# =====================  ORDERS  =====================

@router.get("/orders", summary="All orders")
async def list_orders(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_admin),
):
    orders = (await db.execute(select(Order).order_by(Order.created_at.desc()).offset(offset).limit(limit))).scalars().all()
    total = (await db.execute(select(func.count(Order.id)))).scalar() or 0
    result = []
    for o in orders:
        d = _order_dict(o)
        u = (await db.execute(select(User.username).where(User.id == o.user_id))).scalar()
        d["username"] = u
        result.append(d)
    return {"items": result, "total": total}


# =====================  ANALYTICS  =====================

@router.get("/analytics", summary="Analytics data")
async def analytics(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    now = datetime.utcnow()
    # Revenue by day (last 30 days)
    daily_revenue: List[dict] = []
    for i in range(29, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        rev = (await db.execute(
            select(func.coalesce(func.sum(Order.fee), 0)).where(
                Order.created_at >= day_start, Order.created_at < day_end
            )
        )).scalar()
        vol = (await db.execute(
            select(func.coalesce(func.sum(Order.amount), 0)).where(
                Order.created_at >= day_start, Order.created_at < day_end
            )
        )).scalar()
        count = (await db.execute(
            select(func.count(Order.id)).where(
                Order.created_at >= day_start, Order.created_at < day_end
            )
        )).scalar()
        daily_revenue.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "revenue": float(rev or 0),
            "volume": float(vol or 0),
            "orders": count or 0,
        })

    # Top users by order volume
    top_users_q = await db.execute(
        select(User.id, User.username, func.coalesce(func.sum(Order.amount), 0).label("total"))
        .join(Order, Order.user_id == User.id, isouter=True)
        .group_by(User.id)
        .order_by(func.sum(Order.amount).desc())
        .limit(10)
    )
    top_users = [{"id": r[0], "username": r[1], "total_volume": float(r[2])} for r in top_users_q.all()]

    # Orders by type
    issue_count = (await db.execute(select(func.count(Order.id)).where(Order.type == "issue"))).scalar() or 0
    topup_count = (await db.execute(select(func.count(Order.id)).where(Order.type == "topup"))).scalar() or 0

    # New users last 30 days — approximate by ID growth (no created_at on User)
    return {
        "daily_revenue": daily_revenue,
        "top_users": top_users,
        "orders_by_type": {"issue": issue_count, "topup": topup_count},
    }


# =====================  SETTINGS  =====================


class FAQCreateRequest(BaseModel):
    question: str
    answer: str


class OPlataRegisterClientRequest(BaseModel):
    client_id: str


class FAQUpdateRequest(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None


@router.get("/faq", summary="List FAQ items")
async def list_faq(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    faqs = (await db.execute(select(FAQ).order_by(FAQ.id.asc()))).scalars().all()
    return {
        "items": [
            {
                "id": f.id,
                "question": f.question,
                "answer": f.answer,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            }
            for f in faqs
        ],
        "total": len(faqs),
    }


@router.post("/faq/seed-default", summary="Seed default FAQ if empty")
async def seed_default_faq(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    inserted = await seed_faqs(db, only_if_empty=True)
    return {"inserted": inserted}


@router.post("/faq", summary="Create FAQ item")
async def create_faq(body: FAQCreateRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    item = FAQ(question=body.question, answer=body.answer)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return {
        "id": item.id,
        "question": item.question,
        "answer": item.answer,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.put("/faq/{faq_id}", summary="Update FAQ item")
async def update_faq(
    faq_id: int,
    body: FAQUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_admin),
):
    item = (await db.execute(select(FAQ).where(FAQ.id == faq_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "FAQ item not found")

    if body.question is not None:
        item.question = body.question
    if body.answer is not None:
        item.answer = body.answer

    await db.flush()
    await db.refresh(item)
    return {
        "id": item.id,
        "question": item.question,
        "answer": item.answer,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.delete("/faq/{faq_id}", summary="Delete FAQ item")
async def delete_faq(faq_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    item = (await db.execute(select(FAQ).where(FAQ.id == faq_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "FAQ item not found")
    await db.delete(item)
    return {"ok": True}


@router.post("/oplata/register-client", summary="Register client in O-Plata and return wallet id")
async def oplata_register_client(body: OPlataRegisterClientRequest, _=Depends(get_admin)):
    cid = (body.client_id or "").strip()
    if not cid:
        raise HTTPException(400, "client_id is required")
    try:
        data = await oplata_client.register_client(cid)
    except ValueError as exc:
        raise HTTPException(500, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")
    return {
        "clientId": data.get("clientId") if isinstance(data, dict) else cid,
        "clientWalletId": data.get("clientWalletId") if isinstance(data, dict) else None,
        "productId": data.get("productId") if isinstance(data, dict) else None,
        "raw": data,
    }


@router.get("/oplata/card-types", summary="List available virtual card types from O-Plata")
async def oplata_card_types(client_id: str = "", _=Depends(get_admin)):
    cid = client_id.strip() or settings.OPLATA_TEST_CLIENT_ID or "Developer"
    try:
        providers = await oplata_client.get_virtual_card_list(cid)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")
    offers = []
    for provider in providers:
        ravana_id = provider.get("ravanaServerId") or ""
        for ct in provider.get("cardTypesList") or []:
            type_uuid = ct.get("uuid") or ""
            if bool(ct.get("readOnly")):
                continue
            status = str(ct.get("status") or ct.get("state") or "").upper()
            if status and status not in {"ACTIVE", "ENABLED"}:
                continue
            offers.append({
                "offer_id": f"{ravana_id}:{type_uuid}",
                "ravana_server_id": ravana_id,
                "type_uuid": type_uuid,
                "name": ct.get("localizedName") or ct.get("paymentSystem"),
                "payment_system": ct.get("paymentSystem"),
                "currency": provider.get("cardCurrency"),
            })
    return {"providers": providers, "offers": offers}


@router.get("/oplata/client-info", summary="Get O-Plata client info")
async def oplata_client_info(client_id: str, _=Depends(get_admin)):
    try:
        return await oplata_client.get_client_info(client_id)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


@router.get("/oplata/client-balance", summary="Get all balances for an O-Plata client")
async def oplata_client_balance(client_id: str, _=Depends(get_admin)):
    try:
        return await oplata_client.get_balance_all(client_id)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


@router.get("/oplata/client-cards", summary="Get virtual cards for an O-Plata client")
async def oplata_client_cards(client_id: str, _=Depends(get_admin)):
    try:
        providers = await oplata_client.get_virtual_card_list(client_id)
        cards: List[Dict[str, Any]] = []
        for provider in providers:
            provider_ravana_id = str(provider.get("ravanaServerId") or provider.get("ravanaId") or "")
            provider_cards = []
            for raw_card in provider.get("cardsList") or []:
                card = dict(raw_card)
                if provider_ravana_id and not card.get("ravanaServerId"):
                    card["ravanaServerId"] = provider_ravana_id
                provider_cards.append(card)
                cards.append(card)

            provider["cardsList"] = provider_cards

        return {
            "clientId": client_id,
            "providers": providers,
            "cards": cards,
            "totalCount": len(cards),
        }
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


@router.post("/oplata/sync-user/{user_id}", summary="Sync O-Plata cards for a user into local DB")
async def oplata_sync_user(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.services.card_service import card_service
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    try:
        cards = await card_service.sync_cards(db, user)
        await db.commit()
        return {"synced": len(cards), "cards": [_card_dict(c) for c in cards]}
    except Exception as exc:
        raise HTTPException(502, f"Sync error: {exc}")


@router.get("/oplata/client-kyc", summary="Get KYC verification status for an O-Plata client")
async def oplata_get_kyc(client_id: str, _=Depends(get_admin)):
    try:
        return await oplata_client.kyc_info(client_id)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


@router.get("/oplata/client-validate", summary="Check what is missing before card issuance (EMAIL_ABSENT etc)")
async def oplata_validate_card(client_id: str, ravana_server_id: str, _=Depends(get_admin)):
    try:
        return await oplata_client.validate_card_registration(client_id, ravana_server_id)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


class OPlataKYCEmailRequest(BaseModel):
    client_id: str
    email: str


@router.post("/oplata/kyc-email", summary="Complete KYC email verification for a client (sets EMAIL MDM data)")
async def oplata_kyc_email(body: OPlataKYCEmailRequest, _=Depends(get_admin)):
    try:
        return await oplata_client.kyc_verify_email(body.client_id, body.email)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


class OPlataKYCPersonRequest(BaseModel):
    client_id: str
    first_name: str
    last_name: str
    date_of_birth: str
    middle_name: Optional[str] = None


@router.post("/oplata/kyc-person", summary="Complete KYC person verification for a client")
async def oplata_kyc_person(body: OPlataKYCPersonRequest, _=Depends(get_admin)):
    """date_of_birth format: YYYY-MM-DD (e.g. 1990-11-30)"""
    try:
        return await oplata_client.kyc_verify_person(
            body.client_id, body.first_name, body.last_name, body.date_of_birth, body.middle_name
        )
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


class OPlataMDMBatchEntry(BaseModel):
    type: str
    value: str
    extra: Optional[Dict[str, Any]] = None


class OPlataMDMBatchRequest(BaseModel):
    client_id: str
    entries: List[OPlataMDMBatchEntry]


class OPlataRawRequest(BaseModel):
    path: str
    body: Dict[str, Any]


@router.post("/oplata/raw-post", summary="[DEBUG] Raw signed POST to any O-Plata path — for endpoint discovery")
async def oplata_raw_post(body: OPlataRawRequest, _=Depends(get_admin)):
    """
    Use this to discover correct MDM endpoint. Example paths to try:
    - /product/rest/client/mdm/set
    - /product/rest/client/mdm
    - /product/rest/client/kyc/set
    - /product/rest/client/personal/set
    - /product/rest/client/update
    """
    try:
        return await oplata_client.raw_post(body.path, body.body)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


@router.post("/oplata/set-client-mdm-batch", summary="Set multiple MDM fields for an O-Plata client at once")
async def oplata_set_mdm_batch(body: OPlataMDMBatchRequest, _=Depends(get_admin)):
    entries = [{"type": e.type, "value": e.value, **(e.extra or {})} for e in body.entries]
    try:
        return await oplata_client.set_client_mdm_batch(body.client_id, entries)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


@router.get("/oplata/currencies", summary="List O-Plata currencies")
async def oplata_currencies(crypto_only: Optional[bool] = None, _=Depends(get_admin)):
    try:
        return await oplata_client.get_currencies(is_crypto_currency=crypto_only)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


@router.get("/oplata/transports", summary="List O-Plata deposit/withdrawal transports")
async def oplata_transports(currency_code: str = "", crypto_only: Optional[bool] = None, _=Depends(get_admin)):
    try:
        return await oplata_client.get_transports(
            currency_code=currency_code or None,
            is_crypto_currency=crypto_only,
        )
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


@router.get("/oplata/client-transactions", summary="Get O-Plata transaction list for a client")
async def oplata_client_transactions(
    client_id: str,
    page: int = 0,
    page_size: int = 20,
    _=Depends(get_admin),
):
    try:
        return await oplata_client.get_transaction_list(client_id, page_number=page, page_size=page_size)
    except Exception as exc:
        raise HTTPException(502, f"O-Plata error: {exc}")


# =====================  SETTINGS  =====================

@router.get("/settings", summary="Get current settings")
async def get_settings(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    result = (await db.execute(select(AdminSetting))).scalars().all()
    db_map = {s.key: s.value for s in result}

    out = []
    for key, meta in SETTINGS_KEYS.items():
        db_val = db_map.get(key)
        env_val = getattr(settings, key, None)
        target_type = meta["type"]
        raw = db_val if db_val is not None else env_val
        if raw is None:
            effective = ""
        elif target_type is bool:
            effective = bool(_cast_setting_value(raw, bool))
        else:
            effective = str(raw)
        out.append({
            "key": key,
            "value": effective,
            "description": meta["desc"],
            "type": _type_name(target_type),
            "source": "db" if db_val is not None else "env",
        })
    return out


class SettingsUpdateRequest(BaseModel):
    settings: List[Dict[str, Any]]  # [{ "key": "...", "value": "..." }]


@router.put("/settings", summary="Update settings")
async def update_settings(body: SettingsUpdateRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    for item in body.settings:
        key = item.get("key", "")
        value = item.get("value", "")
        if key not in SETTINGS_KEYS:
            continue

        meta = SETTINGS_KEYS[key]
        try:
            typed_val = _cast_setting_value(value, meta["type"])
        except (ValueError, TypeError):
            continue

        db_value = "true" if meta["type"] is bool and typed_val else ("false" if meta["type"] is bool else str(typed_val))

        existing = (await db.execute(select(AdminSetting).where(AdminSetting.key == key))).scalar_one_or_none()
        if existing:
            existing.value = db_value
        else:
            db.add(AdminSetting(key=key, value=db_value, description=SETTINGS_KEYS[key]["desc"]))

        # Update in-memory settings object
        try:
            setattr(settings, key, typed_val)
        except (ValueError, TypeError):
            pass

    return {"ok": True}


# =====================  BOT  =====================

_UPLOADS_DIR = Path(__file__).parent.parent.parent.parent / "static" / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_WELCOME_IMG = _UPLOADS_DIR / "bot_welcome.jpg"

_BOT_SETTING_DESCS = {
    "BOT_WELCOME_TEXT": "Текст приветственного сообщения",
    "BOT_WELCOME_BUTTONS": "Кнопки (JSON-массив [{text, url}])",
    "BOT_WELCOME_PARSE_MODE": "Режим форматирования (HTML / MarkdownV2)",
    "BOT_WELCOME_FILE_ID": "Telegram file_id (кеш — не менять вручную)",
}


async def _upsert_setting(db: AsyncSession, key: str, value: str, desc: str = "") -> None:
    existing = (await db.execute(select(AdminSetting).where(AdminSetting.key == key))).scalar_one_or_none()
    if existing:
        existing.value = value
    else:
        db.add(AdminSetting(key=key, value=value, description=desc or _BOT_SETTING_DESCS.get(key, "")))


@router.get("/bot/settings", summary="Get bot welcome-message settings")
async def get_bot_settings(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    keys = list(_BOT_SETTING_DESCS.keys())
    res = await db.execute(select(AdminSetting).where(AdminSetting.key.in_(keys)))
    sm = {s.key: s.value for s in res.scalars().all()}
    return {
        "text": sm.get("BOT_WELCOME_TEXT", "Добро пожаловать!"),
        "buttons": sm.get("BOT_WELCOME_BUTTONS", "[]"),
        "parse_mode": sm.get("BOT_WELCOME_PARSE_MODE", "HTML"),
        "has_image": _WELCOME_IMG.exists(),
        "image_url": "/uploads/bot_welcome.jpg" if _WELCOME_IMG.exists() else None,
    }


class BotSettingsUpdate(BaseModel):
    text: str
    buttons: str = "[]"
    parse_mode: str = "HTML"


@router.put("/bot/settings", summary="Update bot welcome-message settings")
async def update_bot_settings(body: BotSettingsUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    await _upsert_setting(db, "BOT_WELCOME_TEXT", body.text)
    await _upsert_setting(db, "BOT_WELCOME_BUTTONS", body.buttons)
    await _upsert_setting(db, "BOT_WELCOME_PARSE_MODE", body.parse_mode)
    await _upsert_setting(db, "BOT_WELCOME_FILE_ID", "")  # reset cache on text/button change
    return {"ok": True}


@router.post("/bot/upload-image", summary="Upload welcome image")
async def upload_bot_image(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    content = await file.read()
    _WELCOME_IMG.write_bytes(content)
    await _upsert_setting(db, "BOT_WELCOME_FILE_ID", "")
    return {"ok": True, "image_url": "/uploads/bot_welcome.jpg"}


@router.delete("/bot/image", summary="Delete welcome image")
async def delete_bot_image(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    if _WELCOME_IMG.exists():
        _WELCOME_IMG.unlink()
    await _upsert_setting(db, "BOT_WELCOME_FILE_ID", "")
    return {"ok": True}


@router.post("/bot/test-welcome", summary="Send test welcome to a specific chat_id")
async def test_welcome(chat_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.services.telegram_bot_service import send_welcome
    try:
        await send_welcome(chat_id, db)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(502, f"Telegram error: {exc}")


@router.post("/bot/upload-broadcast-image", summary="Upload a temporary broadcast image")
async def upload_broadcast_image(file: UploadFile = File(...), _=Depends(get_admin)):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    path = _UPLOADS_DIR / f"bc_{uuid.uuid4().hex}.{ext}"
    path.write_bytes(await file.read())
    return {"image_key": path.name}


class BroadcastRequest(BaseModel):
    text: str
    parse_mode: str = "HTML"
    buttons: str = "[]"
    image_key: Optional[str] = None
    segment: str = "all"
    scheduled_at: Optional[str] = None  # ISO datetime in MSK; when set, queue instead of sending


@router.get("/bot/segments", summary="Broadcast segments with user counts")
async def broadcast_segments(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.services.telegram_bot_service import BROADCAST_SEGMENTS, segment_counts
    counts = await segment_counts(db)
    return {"items": [
        {"key": k, "label": label, "count": counts.get(k, 0)}
        for k, label in BROADCAST_SEGMENTS.items()
    ]}


def _parse_msk(dt_str: str) -> datetime:
    """Admin enters Moscow time; DB stores naive UTC."""
    dt = datetime.fromisoformat(dt_str.replace("Z", ""))
    return dt - timedelta(hours=3)


@router.post("/bot/broadcast", summary="Broadcast now or schedule for later (segment-aware)")
async def send_broadcast(body: BroadcastRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.broadcast import ScheduledBroadcast
    from app.services.telegram_bot_service import BROADCAST_SEGMENTS, broadcast_message

    if body.segment not in BROADCAST_SEGMENTS:
        raise HTTPException(400, f"Unknown segment: {body.segment}")

    if body.scheduled_at:
        try:
            when_utc = _parse_msk(body.scheduled_at)
        except ValueError:
            raise HTTPException(400, "scheduled_at: invalid datetime")
        if when_utc <= datetime.utcnow():
            raise HTTPException(400, "Время отправки уже прошло")
        row = ScheduledBroadcast(
            text=body.text, parse_mode=body.parse_mode, buttons=body.buttons,
            image_key=body.image_key, segment=body.segment, scheduled_at=when_utc,
        )
        db.add(row)
        await db.flush()
        return {"scheduled": True, "id": row.id, "scheduled_at": body.scheduled_at, "segment": body.segment}

    try:
        buttons = json.loads(body.buttons)
    except Exception:
        buttons = []

    image_path: Optional[Path] = None
    if body.image_key:
        candidate = _UPLOADS_DIR / body.image_key
        if candidate.exists():
            image_path = candidate

    result = await broadcast_message(db, body.text, body.parse_mode, buttons, image_path, segment=body.segment)

    if image_path and image_path.exists():
        try:
            image_path.unlink()
        except Exception:
            pass

    return result


# =====================  BROADCAST PRESETS & SCHEDULE  =====================

class BroadcastPresetRequest(BaseModel):
    name: str
    text: str = ""
    parse_mode: str = "HTML"
    buttons: str = "[]"
    image_key: Optional[str] = None
    segment: str = "all"


def _preset_dict(p) -> dict:
    return {"id": p.id, "name": p.name, "text": p.text, "parse_mode": p.parse_mode,
            "buttons": p.buttons, "image_key": p.image_key, "segment": p.segment,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None}


@router.get("/bot/presets", summary="List broadcast presets")
async def list_presets(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.broadcast import BroadcastPreset
    rows = (await db.execute(select(BroadcastPreset).order_by(BroadcastPreset.updated_at.desc()))).scalars().all()
    return {"items": [_preset_dict(p) for p in rows]}


@router.post("/bot/presets", summary="Create broadcast preset")
async def create_preset(body: BroadcastPresetRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.broadcast import BroadcastPreset
    if not body.name.strip():
        raise HTTPException(400, "Название пресета обязательно")
    row = BroadcastPreset(name=body.name.strip(), text=body.text, parse_mode=body.parse_mode,
                          buttons=body.buttons, image_key=body.image_key, segment=body.segment)
    db.add(row)
    await db.flush()
    return _preset_dict(row)


@router.put("/bot/presets/{preset_id}", summary="Update broadcast preset")
async def update_preset(preset_id: int, body: BroadcastPresetRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.broadcast import BroadcastPreset
    row = (await db.execute(select(BroadcastPreset).where(BroadcastPreset.id == preset_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Preset not found")
    row.name = body.name.strip() or row.name
    row.text = body.text
    row.parse_mode = body.parse_mode
    row.buttons = body.buttons
    row.image_key = body.image_key
    row.segment = body.segment
    await db.flush()
    return _preset_dict(row)


@router.delete("/bot/presets/{preset_id}", summary="Delete broadcast preset")
async def delete_preset(preset_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.broadcast import BroadcastPreset
    row = (await db.execute(select(BroadcastPreset).where(BroadcastPreset.id == preset_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Preset not found")
    await db.delete(row)
    return {"ok": True}


@router.get("/bot/scheduled", summary="List scheduled broadcasts")
async def list_scheduled(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.broadcast import ScheduledBroadcast
    rows = (await db.execute(
        select(ScheduledBroadcast).order_by(ScheduledBroadcast.scheduled_at.desc()).limit(50)
    )).scalars().all()
    return {"items": [
        {"id": r.id, "text": r.text[:200], "segment": r.segment, "status": r.status,
         "sent": r.sent, "failed": r.failed,
         "scheduled_at_msk": (r.scheduled_at + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M") if r.scheduled_at else None}
        for r in rows
    ]}


@router.delete("/bot/scheduled/{sb_id}", summary="Cancel a scheduled broadcast")
async def cancel_scheduled(sb_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.broadcast import ScheduledBroadcast
    row = (await db.execute(select(ScheduledBroadcast).where(ScheduledBroadcast.id == sb_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Not found")
    if row.status != "scheduled":
        raise HTTPException(400, f"Рассылка уже в статусе {row.status}")
    row.status = "canceled"
    await db.flush()
    return {"ok": True}


# =====================  PROMO CODES  =====================

class PromoCodeRequest(BaseModel):
    code: str
    type: str                       # rate_discount | issue_discount | no_small_fee
    percent_off: Optional[float] = None
    fixed_off_rub: Optional[float] = None
    card_type: Optional[str] = None  # Online | Online+Pay | Pay (issue_discount only)
    max_uses: int = 0
    one_per_user: bool = True
    valid_from: Optional[str] = None   # ISO, MSK
    valid_until: Optional[str] = None  # ISO, MSK
    is_active: bool = True
    comment: Optional[str] = None


def _promo_dict(p) -> dict:
    from app.services.promo_service import TYPE_LABELS, describe_discount, promo_status
    return {
        "id": p.id, "code": p.code, "type": p.type,
        "type_label": TYPE_LABELS.get(p.type, p.type),
        "description": describe_discount(p),
        "percent_off": p.percent_off, "fixed_off_rub": p.fixed_off_rub,
        "card_type": p.card_type, "max_uses": p.max_uses, "used_count": p.used_count,
        "one_per_user": p.one_per_user, "is_active": p.is_active,
        "status": promo_status(p), "comment": p.comment,
        "valid_from_msk": (p.valid_from + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M") if p.valid_from else None,
        "valid_until_msk": (p.valid_until + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M") if p.valid_until else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _apply_promo_body(row, body: PromoCodeRequest):
    from app.services.promo_service import PROMO_TYPES
    if body.type not in PROMO_TYPES:
        raise HTTPException(400, f"type must be one of {PROMO_TYPES}")
    if body.type == "rate_discount" and not body.percent_off:
        raise HTTPException(400, "Для скидки на курс укажите процент")
    if body.type == "issue_discount" and not body.percent_off and not body.fixed_off_rub:
        raise HTTPException(400, "Для скидки на выпуск укажите процент или фиксированную сумму")
    row.code = body.code.strip().upper()
    row.type = body.type
    row.percent_off = body.percent_off
    row.fixed_off_rub = body.fixed_off_rub
    row.card_type = body.card_type or None
    row.max_uses = max(0, int(body.max_uses or 0))
    row.one_per_user = bool(body.one_per_user)
    row.is_active = bool(body.is_active)
    row.comment = (body.comment or "").strip() or None
    row.valid_from = _parse_msk(body.valid_from) if body.valid_from else None
    row.valid_until = _parse_msk(body.valid_until) if body.valid_until else None
    if not row.code:
        raise HTTPException(400, "Код обязателен")


@router.get("/promo-codes", summary="List promo codes with status and usage")
async def list_promo_codes(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.promo import PromoCode
    rows = (await db.execute(select(PromoCode).order_by(PromoCode.id.desc()))).scalars().all()
    return {"items": [_promo_dict(p) for p in rows]}


@router.post("/promo-codes", summary="Create promo code")
async def create_promo_code(body: PromoCodeRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.promo import PromoCode
    dup = (await db.execute(select(PromoCode).where(PromoCode.code == body.code.strip().upper()))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "Такой код уже существует")
    row = PromoCode(code="", type="rate_discount")
    _apply_promo_body(row, body)
    db.add(row)
    await db.flush()
    return _promo_dict(row)


@router.put("/promo-codes/{promo_id}", summary="Update promo code")
async def update_promo_code(promo_id: int, body: PromoCodeRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.promo import PromoCode
    row = (await db.execute(select(PromoCode).where(PromoCode.id == promo_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Промокод не найден")
    dup = (await db.execute(select(PromoCode).where(
        PromoCode.code == body.code.strip().upper(), PromoCode.id != promo_id
    ))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "Такой код уже существует")
    _apply_promo_body(row, body)
    await db.flush()
    return _promo_dict(row)


@router.delete("/promo-codes/{promo_id}", summary="Delete promo code")
async def delete_promo_code(promo_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.models.promo import PromoCode, PromoRedemption
    row = (await db.execute(select(PromoCode).where(PromoCode.id == promo_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Промокод не найден")
    for r in (await db.execute(select(PromoRedemption).where(PromoRedemption.promo_id == promo_id))).scalars().all():
        await db.delete(r)
    await db.delete(row)
    return {"ok": True}


# =====================  BOT NOTIFICATION SETTINGS  =====================

_NOTIF_DEFAULTS = {
    "BOT_APPLE_PAY_CODE_HEADER": "🍎 Код активации Apple Pay",
    "BOT_NOTIFY_CARD_ISSUED_HEADER": "✅ Карта успешно выпущена",
    "BOT_NOTIFY_CARD_FAILED_HEADER": "❌ Ошибка выпуска карты",
    "BOT_NOTIFY_TOPUP_SUCCESS_HEADER": "✅ Пополнение карты выполнено",
    "BOT_NOTIFY_TOPUP_FAILED_HEADER": "❌ Ошибка пополнения карты",
}


@router.get("/bot/notification-settings", summary="Get notification message headers")
async def get_notification_settings(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    keys = list(_NOTIF_DEFAULTS.keys())
    res = await db.execute(select(AdminSetting).where(AdminSetting.key.in_(keys)))
    sm = {s.key: s.value for s in res.scalars().all()}
    return {k: sm.get(k, v) for k, v in _NOTIF_DEFAULTS.items()}


class NotificationSettingsUpdate(BaseModel):
    BOT_APPLE_PAY_CODE_HEADER: str = "🍎 Код активации Apple Pay"
    BOT_NOTIFY_CARD_ISSUED_HEADER: str = "✅ Карта успешно выпущена"
    BOT_NOTIFY_CARD_FAILED_HEADER: str = "❌ Ошибка выпуска карты"
    BOT_NOTIFY_TOPUP_SUCCESS_HEADER: str = "✅ Пополнение карты выполнено"
    BOT_NOTIFY_TOPUP_FAILED_HEADER: str = "❌ Ошибка пополнения карты"


@router.put("/bot/notification-settings", summary="Update notification message headers")
async def update_notification_settings(
    body: NotificationSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_admin),
):
    for key in _NOTIF_DEFAULTS:
        value = getattr(body, key)
        await _upsert_setting(db, key, value, _NOTIF_DEFAULTS[key])
    await db.commit()
    return {"ok": True}


# =====================  GMAIL OAuth2  =====================

_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"


def _gmail_redirect_uri(request: Request) -> str:
    base = (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")
    if base:
        return f"{base}/api/admin/gmail/callback"
    return str(request.base_url).rstrip("/") + "/api/admin/gmail/callback"


@router.get("/gmail/status", summary="Gmail API connection status")
async def gmail_status(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.core.config import settings as cfg
    row = (await db.execute(
        select(AdminSetting).where(AdminSetting.key == "GMAIL_REFRESH_TOKEN")
    )).scalar_one_or_none()
    email_row = (await db.execute(
        select(AdminSetting).where(AdminSetting.key == "GMAIL_CONNECTED_EMAIL")
    )).scalar_one_or_none()
    return {
        "connected": bool(row and row.value),
        "email": email_row.value if email_row else None,
        "client_id_set": bool(cfg.GMAIL_CLIENT_ID),
    }


@router.get("/gmail/auth-url", summary="Get Google OAuth2 authorize URL")
async def gmail_auth_url(request: Request, _=Depends(get_admin)):
    from urllib.parse import urlencode
    from app.core.config import settings as cfg

    if not cfg.GMAIL_CLIENT_ID:
        raise HTTPException(400, "GMAIL_CLIENT_ID not configured in .env")

    redirect_uri = _gmail_redirect_uri(request)
    params = {
        "client_id": cfg.GMAIL_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _GMAIL_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    return {"auth_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"}


@router.get("/gmail/callback", summary="OAuth2 callback — exchanges code for tokens", include_in_schema=False)
async def gmail_callback(request: Request, code: str, db: AsyncSession = Depends(get_db)):
    import httpx
    from app.core.config import settings as cfg

    redirect_uri = _gmail_redirect_uri(request)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": cfg.GMAIL_CLIENT_ID,
            "client_secret": cfg.GMAIL_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
    if resp.status_code != 200:
        return HTMLResponse(f"<h3>❌ Ошибка авторизации</h3><pre>{resp.text}</pre>", status_code=400)

    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return HTMLResponse("<h3>❌ Google не вернул refresh_token. Попробуйте ещё раз.</h3>", status_code=400)

    await _upsert_setting(db, "GMAIL_REFRESH_TOKEN", refresh_token, "Gmail OAuth2 refresh token")

    # fetch connected email
    access_token = tokens.get("access_token", "")
    gmail_email = ""
    if access_token:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                profile = await client.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if profile.status_code == 200:
                gmail_email = profile.json().get("emailAddress", "")
        except Exception:
            pass
    if gmail_email:
        await _upsert_setting(db, "GMAIL_CONNECTED_EMAIL", gmail_email, "Gmail подключённый email")

    await db.commit()
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
        "<h2>✅ Gmail подключён!</h2>"
        f"<p>Аккаунт: <b>{gmail_email or '—'}</b></p>"
        "<p>Можете закрыть эту вкладку.</p>"
        "<script>window.opener&&window.opener.postMessage('gmail_connected','*');setTimeout(()=>window.close(),2000)</script>"
        "</body></html>"
    )


@router.delete("/gmail/disconnect", summary="Disconnect Gmail — remove refresh token")
async def gmail_disconnect(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    for key in ("GMAIL_REFRESH_TOKEN", "GMAIL_CONNECTED_EMAIL"):
        row = (await db.execute(select(AdminSetting).where(AdminSetting.key == key))).scalar_one_or_none()
        if row:
            await db.delete(row)
    await db.commit()
    # clear cached token in gmail_service
    from app.services.gmail_service import _cached_access_token, _token_expires_at
    import app.services.gmail_service as _gs
    _gs._cached_access_token = None
    _gs._token_expires_at = 0
    return {"ok": True}
