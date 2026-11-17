"""Read-only, paginated journal of payments and their execution events."""
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import DateTime, Numeric, String, cast, case, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin
from app.core.database import get_db
from app.models.balance_tx import BalanceTransaction
from app.models.bb_invoice import BbInvoice
from app.models.crypto_payment import CryptoPayment
from app.models.order import Order
from app.models.service_request import ServiceRequest
from app.models.topup import BalanceTopUpRequest
from app.models.user import User
from app.services.wallet_service import utc_timestamp

router = APIRouter(prefix="/payments", tags=["admin"])
Source = Literal["sbp", "crypto", "order", "balance", "china", "legacy"]
FIELDS = ("source", "id", "user_id", "purpose", "amount", "currency", "fee", "status",
          "execution_status", "description", "created_at", "paid_at", "provider_id",
          "order_id", "invoice_id", "service_request_id", "last_error",
          "recover_attempts", "last_recover_at", "balance_after")


def _event(source, model, **values):
    values = dict(source=literal(source), id=model.id, user_id=model.user_id, **values)
    columns = []
    for name in FIELDS:
        value = values.get(name, literal(None))
        if name in ("amount", "fee", "balance_after"):
            value = cast(value, Numeric(24, 8))
        if name in ("created_at", "paid_at", "last_recover_at") and name not in values:
            value = cast(value, DateTime)
        columns.append(value.label(name))
    return select(*columns)


def invoice_orders(invoice):
    """Match a complete reference token: invoice 207 must not match 2070."""
    pattern = (literal("(^| )sbp_invoice:") + cast(invoice.id, String) + literal("($| )")).collate("utf8mb4_unicode_ci")
    return (Order.user_id == invoice.user_id) & Order.description.regexp_match(pattern)


def _feed(source=None):
    inv = BbInvoice
    latest_order = (select(Order.status).where(invoice_orders(inv), Order.type == "issue")
                    .order_by(Order.id.desc()).limit(1).correlate(inv).scalar_subquery())
    latest_order_id = (select(Order.id).where(invoice_orders(inv), Order.type == "issue")
                       .order_by(Order.id.desc()).limit(1).correlate(inv).scalar_subquery())
    request_status = (select(ServiceRequest.status).where(
        ServiceRequest.id == inv.service_request_id, ServiceRequest.user_id == inv.user_id
    ).correlate(inv).scalar_subquery())
    execution = case(
        (inv.status.notin_(("captured", "authorized")), literal(None)),
        (inv.purpose == "card_issue", func.coalesce(latest_order, "missing_order")),
        (inv.purpose == "balance_deposit", case((inv.amount_usd > 0, "completed"), else_="missing_booking")),
        (inv.purpose == "china_payment", request_status),
        else_=literal(None),
    )
    queries = {
        "sbp": _event("sbp", inv, purpose=inv.purpose, amount=inv.amount_rub,
            currency=literal("RUB"), status=inv.status, execution_status=execution,
            description=literal("Оплата по СБП"), created_at=inv.created_at,
            provider_id=inv.bb_invoice_id, invoice_id=inv.id, order_id=latest_order_id,
            service_request_id=inv.service_request_id, recover_attempts=inv.recover_attempts,
            last_recover_at=inv.last_recover_at),
        "crypto": _event("crypto", CryptoPayment, purpose=CryptoPayment.purpose,
            amount=CryptoPayment.charge_usdt, currency=literal("USDT"), status=CryptoPayment.status,
            execution_status=CryptoPayment.fulfillment_status, description=CryptoPayment.network_name,
            created_at=CryptoPayment.created_at, paid_at=CryptoPayment.paid_at,
            provider_id=CryptoPayment.provider_invoice_id, order_id=CryptoPayment.order_id,
            service_request_id=CryptoPayment.service_request_id, last_error=CryptoPayment.last_error),
        "order": _event("order", Order, purpose=case((Order.type == "issue", "card_issue"),
            (Order.type == "topup", "card_topup"), else_=Order.type), amount=Order.amount,
            currency=literal("USD"), fee=Order.fee, status=Order.status,
            execution_status=Order.status, description=Order.description, created_at=Order.created_at,
            order_id=Order.id, provider_id=Order.partner_order_id),
        "balance": _event("balance", BalanceTransaction, purpose=BalanceTransaction.type,
            amount=BalanceTransaction.amount, currency=literal("USD"), status=literal("completed"),
            description=BalanceTransaction.description, created_at=BalanceTransaction.created_at,
            order_id=BalanceTransaction.ref_order_id, invoice_id=BalanceTransaction.ref_invoice_id,
            balance_after=BalanceTransaction.balance_after),
        "china": _event("china", ServiceRequest, purpose=literal("china_payment"),
            amount=ServiceRequest.amount, currency=ServiceRequest.currency, status=ServiceRequest.status,
            execution_status=ServiceRequest.status, description=ServiceRequest.service,
            created_at=ServiceRequest.created_at, paid_at=ServiceRequest.paid_at,
            invoice_id=ServiceRequest.invoice_id, service_request_id=ServiceRequest.id),
        "legacy": _event("legacy", BalanceTopUpRequest, purpose=literal("balance_deposit"),
            amount=BalanceTopUpRequest.amount, currency=literal("USD"), status=BalanceTopUpRequest.status,
            description=BalanceTopUpRequest.comment, provider_id=BalanceTopUpRequest.payment_reference),
    }
    if source:
        return queries[source].subquery("payment_events")
    return union_all(*queries.values()).subquery("payment_events")


def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return utc_timestamp(value)


def _view(row):
    out = dict(row)
    out["key"] = f"{out['source']}:{out['id']}"
    for key in ("created_at", "paid_at", "last_recover_at"):
        out[key] = _utc(out.get(key))
    for key in ("amount", "fee", "balance_after"):
        out[key] = str(out[key]) if out.get(key) is not None else None
    return out


def _base(feed):
    return select(feed, User.username, User.telegram_user_id).outerjoin(User, User.id == feed.c.user_id)


def _naive_utc(value):
    if value is None:
        return None
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc).replace(tzinfo=None)


@router.get("", summary="Complete payment and operation history")
async def payments(
    source: Optional[Source] = None, search: str = Query("", max_length=200),
    status: str = Query("", max_length=32), purpose: str = Query("", max_length=32),
    user_id: Optional[int] = Query(None, ge=1),
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db), _=Depends(get_admin),
):
    start, end = _naive_utc(date_from), _naive_utc(date_to)
    if start and end and start >= end:
        raise HTTPException(422, "Дата начала должна быть раньше даты окончания")
    feed = _feed(source)
    query = _base(feed)
    if user_id is not None:
        query = query.where(feed.c.user_id == user_id)
    if status:
        query = query.where(feed.c.status == status)
    if purpose:
        query = query.where(feed.c.purpose == purpose)
    if start:
        query = query.where(feed.c.created_at >= start)
    if end:
        query = query.where(feed.c.created_at < end)
    term = search.strip().lstrip("@#")
    if term:
        conditions = [func.lower(User.username).contains(term.lower(), autoescape=True),
                      User.telegram_user_id == term, feed.c.provider_id == term]
        if term.isascii() and term.isdigit():
            if len(term) <= 18:
                conditions.extend((feed.c.id == int(term), feed.c.user_id == int(term)))
        else:
            conditions.append(func.lower(feed.c.description).contains(term.lower(), autoescape=True))
        query = query.where(or_(*conditions))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(feed.c.created_at.desc(), feed.c.source.asc(), feed.c.id.desc())
                             .offset(offset).limit(limit))).mappings().all()
    return {"items": [_view(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/{source}/{event_id}", summary="Payment details and related history")
async def payment_detail(source: Source, event_id: int, db: AsyncSession = Depends(get_db), _=Depends(get_admin)):
    feed = _feed(source)
    row = (await db.execute(_base(feed).where(feed.c.id == event_id))).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Запись не найдена")
    owner = row["user_id"]
    related = set()
    if source == "sbp":
        inv = await db.get(BbInvoice, event_id)
        orders = (await db.execute(select(Order.id).where(invoice_orders(inv)))).scalars().all()
        related.update(("order", x) for x in orders)
        ledger = (await db.execute(select(BalanceTransaction.id).where(
            BalanceTransaction.user_id == owner, BalanceTransaction.ref_invoice_id == event_id
        ))).scalars().all()
        related.update(("balance", x) for x in ledger)
    if source == "order":
        order = await db.get(Order, event_id)
        import re
        for inv_id in re.findall(r"(?:^| )sbp_invoice:(\d+)(?= |$)", order.description or ""):
            related.add(("sbp", int(inv_id)))
        crypto = (await db.execute(select(CryptoPayment.id).where(
            CryptoPayment.user_id == owner, CryptoPayment.order_id == event_id))).scalars().all()
        related.update(("crypto", x) for x in crypto)
        ledger = (await db.execute(select(BalanceTransaction.id).where(
            BalanceTransaction.user_id == owner, BalanceTransaction.ref_order_id == event_id))).scalars().all()
        related.update(("balance", x) for x in ledger)
    if row["order_id"]:
        related.add(("order", row["order_id"]))
    if row["invoice_id"]:
        related.add(("sbp", row["invoice_id"]))
    if row["service_request_id"]:
        related.add(("china", row["service_request_id"]))
    if source == "china":
        for model, kind in ((BbInvoice, "sbp"), (CryptoPayment, "crypto")):
            ids = (await db.execute(select(model.id).where(
                model.user_id == owner, model.service_request_id == event_id))).scalars().all()
            related.update((kind, x) for x in ids)
    result = []
    for kind, pk in sorted(related - {(source, event_id)}):
        sub = _feed(kind)
        item = (await db.execute(_base(sub).where(sub.c.id == pk, sub.c.user_id == owner))).mappings().one_or_none()
        if item:
            result.append(_view(item))
    return {"item": _view(row), "related": result}
