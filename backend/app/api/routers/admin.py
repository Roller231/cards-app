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
from app.integrations.aifory_client import aifory_client
from app.integrations.oplata_client import oplata_client
from app.models.admin_setting import AdminSetting
from app.models.card import Card
from app.models.crypto_payment import CryptoPayment
from app.models.faq import FAQ
from app.models.order import Order
from app.models.topup import BalanceTopUpRequest
from app.models.user import User
from app.seed.faq_seed import seed_faqs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# --------------- helpers ---------------

SETTINGS_KEYS: Dict[str, Dict[str, Any]] = {
    "ONLINE_ISSUE_FEE_USD": {"desc": "Online card issue fee (USD)", "type": float},
    "ONLINE_TOPUP_MARKUP_PERCENT": {"desc": "Online card top-up markup (%)", "type": float},
    "ONLINE_PLUS_ISSUE_FEE_USD": {"desc": "Online+ card issue fee (USD)", "type": float},
    "ONLINE_PLUS_TOPUP_MARKUP_PERCENT": {"desc": "Online+ card top-up markup (%)", "type": float},
    "ISSUE_APPLY_TOPUP_MARKUP": {"desc": "Apply top-up markup percent during card issue", "type": bool},
    "ONLINE_CARD_VALIDITY_TEXT": {"desc": "Online card validity text", "type": str},
    "ONLINE_PLUS_CARD_VALIDITY_TEXT": {"desc": "Online+ card validity text", "type": str},
    "ONLINE_OPERATION_FEE_USD": {"desc": "Online card operation fee (USD)", "type": float},
    "ONLINE_PLUS_OPERATION_FEE_USD": {"desc": "Online+ card operation fee (USD)", "type": float},
    "ABCEX_CRYPTO_PAYMENT_EXPIRY_MINUTES": {"desc": "Crypto payment expiry (minutes)", "type": int},
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


def _cp_dict(p: CryptoPayment) -> dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "address": p.address,
        "network": p.network,
        "amount_usd": float(p.amount_usd),
        "total_usdt": float(p.total_usdt),
        "offer_id": p.offer_id,
        "type": p.type,
        "card_aifory_id": p.card_aifory_id,
        "status": p.status,
        "tx_id": p.tx_id,
        "order_id": p.order_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "expires_at": p.expires_at.isoformat() if p.expires_at else None,
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

    cp_total = (await db.execute(select(func.count(CryptoPayment.id)))).scalar() or 0
    cp_pending = (await db.execute(select(func.count(CryptoPayment.id)).where(CryptoPayment.status == "pending"))).scalar() or 0
    cp_completed = (await db.execute(select(func.count(CryptoPayment.id)).where(CryptoPayment.status == "completed"))).scalar() or 0
    cp_failed = (await db.execute(select(func.count(CryptoPayment.id)).where(CryptoPayment.status == "failed"))).scalar() or 0

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
        "crypto_payments": {"total": cp_total, "pending": cp_pending, "completed": cp_completed, "failed": cp_failed},
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


@router.get("/users/{user_id}/crypto-payments", summary="User crypto payments")
async def user_crypto_payments(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    payments = (await db.execute(
        select(CryptoPayment).where(CryptoPayment.user_id == user_id).order_by(CryptoPayment.created_at.desc())
    )).scalars().all()
    return [_cp_dict(p) for p in payments]


@router.get("/users/{user_id}/topup-requests", summary="User topup requests")
async def user_topup_requests(user_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    reqs = (await db.execute(
        select(BalanceTopUpRequest).where(BalanceTopUpRequest.user_id == user_id)
    )).scalars().all()
    return [_topup_dict(t) for t in reqs]


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


@router.get("/cards/aifory-unassigned", summary="Aifory cards not assigned to any local user")
async def aifory_unassigned(db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    try:
        aifory_cards = await aifory_client.get_cards("")
    except Exception as exc:
        raise HTTPException(502, f"Aifory error: {exc}")

    assigned_ids_result = await db.execute(select(Card.aifory_card_id).where(Card.aifory_card_id.isnot(None)))
    assigned_ids = {r[0] for r in assigned_ids_result.all()}

    unassigned = []
    for c in aifory_cards:
        cid = str(c.get("cardID") or c.get("cardId") or c.get("id") or "")
        if cid and cid not in assigned_ids:
            unassigned.append({
                "aifory_card_id": cid,
                "last4": str(c.get("cardNumberLastDigits") or ""),
                "category": c.get("category"),
                "card_status": c.get("cardStatus"),
                "expired_at": c.get("expiredAt"),
                "currency_id": c.get("currencyID"),
                "payment_system_id": c.get("paymentSystemID"),
                "balance": float(c.get("balance") or 0),
            })
    return unassigned


class CardAssignRequest(BaseModel):
    user_id: int
    aifory_card_id: str


@router.post("/cards/assign", summary="Assign an Aifory card to a user")
async def assign_card(body: CardAssignRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    # Check user exists
    user = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    # Check not already assigned
    existing = (await db.execute(
        select(Card).where(Card.aifory_card_id == body.aifory_card_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(400, f"Card already assigned to user {existing.user_id}")

    # Fetch card details from Aifory
    try:
        aifory_cards = await aifory_client.get_cards("")
    except Exception as exc:
        raise HTTPException(502, f"Aifory error: {exc}")

    raw = None
    for c in aifory_cards:
        cid = str(c.get("cardID") or c.get("cardId") or c.get("id") or "")
        if cid == body.aifory_card_id:
            raw = c
            break
    if not raw:
        raise HTTPException(404, "Card not found in Aifory")

    currency_id = raw.get("currencyID")
    currency_str = "USD" if currency_id == 1010 else ("EUR" if currency_id == 1020 else str(currency_id or ""))

    card = Card(
        user_id=body.user_id,
        aifory_card_id=body.aifory_card_id,
        category=raw.get("category"),
        card_status=raw.get("cardStatus"),
        expired_at=raw.get("expiredAt"),
        last4=str(raw.get("cardNumberLastDigits") or ""),
        currency=currency_str,
        currency_id=currency_id,
        payment_system_id=raw.get("paymentSystemID"),
        balance=Decimal(str(raw.get("balance") or 0)),
        status="active" if raw.get("cardStatus") == 2 else "inactive",
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


@router.delete("/cards/{card_id}", summary="Delete card assignment")
async def delete_card(card_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    card = (await db.execute(select(Card).where(Card.id == card_id))).scalar_one_or_none()
    if not card:
        raise HTTPException(404, "Card not found")
    await db.delete(card)
    return {"ok": True}


@router.get("/cards/{card_id}/transactions", summary="Card transactions from Aifory")
async def card_transactions(card_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    card = (await db.execute(select(Card).where(Card.id == card_id))).scalar_one_or_none()
    if not card or not card.aifory_card_id:
        raise HTTPException(404, "Card not found or not linked to Aifory")
    try:
        return await aifory_client.get_card_transactions(card.aifory_card_id, limit=100, offset=0)
    except Exception as exc:
        raise HTTPException(502, f"Aifory error: {exc}")


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


# =====================  CRYPTO PAYMENTS  =====================

@router.get("/crypto-payments", summary="All crypto payments")
async def list_crypto_payments(
    status_filter: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_admin),
):
    q = select(CryptoPayment)
    if status_filter:
        q = q.where(CryptoPayment.status == status_filter)
    q = q.order_by(CryptoPayment.created_at.desc()).offset(offset).limit(limit)
    payments = (await db.execute(q)).scalars().all()
    total = (await db.execute(select(func.count(CryptoPayment.id)))).scalar() or 0
    result = []
    for p in payments:
        d = _cp_dict(p)
        u = (await db.execute(select(User.username).where(User.id == p.user_id))).scalar()
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


@router.post("/oplata/register-client", summary="Register test client in O-Plata and return wallet id")
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


@router.post("/bot/broadcast", summary="Broadcast message to all users with Telegram IDs")
async def send_broadcast(body: BroadcastRequest, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    from app.services.telegram_bot_service import broadcast_message

    try:
        buttons = json.loads(body.buttons)
    except Exception:
        buttons = []

    image_path: Optional[Path] = None
    if body.image_key:
        candidate = _UPLOADS_DIR / body.image_key
        if candidate.exists():
            image_path = candidate

    result = await broadcast_message(db, body.text, body.parse_mode, buttons, image_path)

    if image_path and image_path.exists():
        try:
            image_path.unlink()
        except Exception:
            pass

    return result


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
