"""Cryptoway payment API. Amounts and fulfillment targets are server-owned."""
from decimal import Decimal
import json
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_admin
from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.crypto_payment import CryptoPayment
from app.integrations.cryptoway_client import CryptowayError, cryptoway_client, verify_webhook
from app.services import crypto_payment_service as service

router = APIRouter(tags=["crypto"])


class QuoteRequest(BaseModel):
    request_id: str = Field(min_length=16, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    purpose: Literal["card_issue", "card_topup", "china_payment"]
    service_request_id: Optional[int] = Field(default=None, gt=0)
    offer_id: Optional[str] = Field(default=None, max_length=255)
    card_id: Optional[int] = Field(default=None, gt=0)
    amount_usd: Optional[Decimal] = Field(default=None, gt=0, le=10000, max_digits=7, decimal_places=2, allow_inf_nan=False)


class InvoiceRequest(BaseModel):
    quote_id: int = Field(gt=0)
    symbol_id: str = Field(min_length=4, max_length=32, pattern=r"^USDT[A-Z0-9]+$")


class ContactRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(min_length=7, max_length=32)


@router.put("/crypto/contact")
async def save_contact(body: ContactRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.card_kyc import normalize_contacts
    service.require_enabled()
    try:
        user.email, user.phone = normalize_contacts(body.email, body.phone)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return {"ok": True, "email": user.email, "phone": user.phone}


@router.get("/crypto/networks")
async def list_networks(user: User = Depends(get_current_user)):
    service.require_enabled()
    try:
        return {"networks": await service.networks(), "topup_fee_percent": settings.CRYPTOWAY_TOPUP_MARKUP_PERCENT}
    except CryptowayError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/crypto/quotes")
async def quote(body: QuoteRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        row = await service.create_quote(db, user, body)
    except CryptowayError as exc:
        raise HTTPException(502, str(exc)) from exc
    return service.payment_view(row, user)


@router.post("/crypto/invoices")
async def create_invoice(body: InvoiceRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        row = await service.create_invoice(db, user, body.quote_id, body.symbol_id)
    except CryptowayError as exc:
        raise HTTPException(502, str(exc)) from exc
    return service.payment_view(row, user)


@router.get("/crypto/payments/{payment_id}")
async def payment_status(payment_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await service.reconcile_payment(db, user, payment_id)
    return service.payment_view(row, user)


@router.post("/crypto/payments/{payment_id}/cancel")
async def cancel_payment(payment_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await service.owned_payment(db, user.id, payment_id, lock=True)
    if row.status == "paid":
        raise HTTPException(409, "Оплаченный счёт нельзя отменить.")
    if not row.provider_invoice_id and row.status == "quoted":
        row.status = "cancelled"
        await db.commit()
    elif row.provider_invoice_id:
        try:
            await db.commit()
            await cryptoway_client.cancel(row.provider_invoice_id)
            row = await service.reconcile_payment(db, user, payment_id, force=True)
        except CryptowayError as exc:
            raise HTTPException(502, "Не удалось отменить счёт. Проверьте статус оплаты.") from exc
    else:
        raise HTTPException(409, "Создание счёта ещё проверяется. Дождитесь результата.")
    return service.payment_view(row, user)


@router.post("/webhooks/cryptoway")
async def cryptoway_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.CRYPTOWAY_CALLBACK_KEY:
        raise HTTPException(503, "Webhook is not configured")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(413, "Payload too large")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON")
    if not isinstance(payload, dict) or not verify_webhook(payload, request.url.query,
            request.headers.get("X-Timestamp"), request.headers.get("X-Signature")):
        raise HTTPException(401, "Invalid signature")
    event = payload.get("body", payload)
    if not isinstance(event, dict) or event.get("type") not in ("invoice", "deposit"):
        return {"ok": True}
    invoice_ref = event.get("invoice") or {}
    invoice_id = event.get("id") if event["type"] == "invoice" else invoice_ref.get("id") if isinstance(invoice_ref, dict) else None
    if not invoice_id:
        return {"ok": True}
    row = (await db.execute(select(CryptoPayment).where(CryptoPayment.provider_invoice_id == str(invoice_id)))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Unknown invoice")
    user = await db.get(User, row.user_id)
    await service.reconcile_payment(db, user, row.id, force=True)
    return {"ok": True}


@router.get("/admin/cryptoway/payments")
async def admin_payments(status: str = "", limit: int = Query(100, ge=1, le=200),
        db: AsyncSession = Depends(get_db), admin=Depends(get_admin)):
    query = select(CryptoPayment).order_by(CryptoPayment.id.desc()).limit(limit)
    if status:
        query = query.where(CryptoPayment.status == status)
    rows = (await db.execute(query)).scalars().all()
    return {"items": [{
        "id": r.id, "user_id": r.user_id, "purpose": r.purpose, "amount_usd": str(r.amount_usd),
        "service_request_id": r.service_request_id, "amount_cny": str(r.amount_cny) if r.amount_cny is not None else None,
        "total_usdt": str(r.charge_usdt), "received_usdt": str(r.received_usdt), "symbol_id": r.symbol_id,
        "status": r.status, "fulfillment_status": r.fulfillment_status, "order_id": r.order_id,
        "refund_credited": r.refund_credited, "last_error": r.last_error,
        "provider_invoice_id": r.provider_invoice_id, "created_at": r.created_at.isoformat() + "Z",
    } for r in rows]}
