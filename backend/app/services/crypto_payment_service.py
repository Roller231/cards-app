"""USDT invoices. Payment confirmation and the fulfillment claim are durable.

An uncertain provider call is never repeated automatically. This avoids
double issuance/funding after a timeout; those invoices go to manual review.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_UP
import json
import logging
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import select, or_, and_

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.integrations.cryptoway_client import cryptoway_client, CryptowayError, trusted_pay_url
from app.models.crypto_payment import CryptoPayment
from app.models.card import Card
from app.models.order import Order
from app.models.user import User
from app.services.card_kyc import kyc_ready

logger = logging.getLogger(__name__)
CENT = Decimal("0.01")
_networks = {"at": 0, "items": []}


def money(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Invalid amount")
    return result


def round_charge(value):
    return money(value).quantize(CENT, rounding=ROUND_UP)


def enabled():
    return settings.CRYPTOWAY_ENABLED and cryptoway_client.is_configured()


def require_enabled():
    if not enabled():
        raise HTTPException(503, "Оплата USDT временно недоступна.")


def requires_kyc(offer_id):
    from app.services.rocketpay_service import is_rocketpay
    return not (is_rocketpay(offer_id) and settings.CRYPTOWAY_PAY_WITHOUT_KYC)


async def networks():
    if _networks["items"] and time.time() - _networks["at"] < 120:
        return _networks["items"]
    rows = []
    for page in range(1, 11):
        response = await cryptoway_client.symbols(page)
        rows.extend(response.get("data") or [])
        if page >= int(response.get("pages_count") or 1):
            break
    fees = {r["symbol_id"]: r for r in await cryptoway_client.fees()}
    result = []
    for row in rows:
        if row.get("short_name") != "USDT" or row.get("is_virtual") or not row.get("is_active") or not row.get("blockchain"):
            continue
        result.append({
            "symbol_id": row["id"], "name": row["blockchain"].get("full_name") or row["blockchain"].get("name"),
            "network": row["blockchain"]["id"], "precision": row.get("precision", 2),
            "min_amount": str(fees.get(row["id"], {}).get("min_deposit_amount") or "1"),
        })
    _networks.update(at=time.time(), items=result)
    return result


def payment_view(row, user):
    return {
        "id": row.id, "purpose": row.purpose, "status": row.status,
        "fulfillment_status": row.fulfillment_status, "order_id": row.order_id,
        "amount_usd": str(row.amount_usd), "fee_percent": str(row.fee_percent),
        "total_usdt": str(row.charge_usdt), "price_rub": str(row.price_rub) if row.price_rub is not None else None,
        "base_rate": str(row.base_rate) if row.base_rate is not None else None,
        "discount_percent": str(row.discount_percent), "symbol_id": row.symbol_id,
        "network_name": row.network_name, "address": row.wallet_address,
        "received_usdt": str(row.received_usdt or 0), "refund_credited": row.refund_credited,
        "overpaid_usdt": str(max(money(row.received_usdt or 0) - row.charge_usdt, Decimal("0"))),
        "expires_at": row.expires_at.replace(tzinfo=timezone.utc).isoformat(),
        "kyc_required": requires_kyc(row.offer_id), "kyc_verified": kyc_ready(user),
        "last_error": row.last_error if row.status in ("error", "review") or row.fulfillment_status in ("failed", "review") else None,
    }


async def owned_payment(db, user_id, payment_id, lock=False):
    query = select(CryptoPayment).where(CryptoPayment.id == payment_id, CryptoPayment.user_id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Счёт не найден.")
    return row


async def create_quote(db, user, body):
    require_enabled()
    from app.services.card_service import card_service, CARD_NAME_BY_OFFER, OFFER_REPLACEMENTS
    from app.services.wallet_service import apply_discount_rub, invitee_discount_percent
    from app.api.routers.cards import _issue_price_rub
    from app.services.rate_service import get_bb_index, RateUnavailable

    offer_id = OFFER_REPLACEMENTS.get(body.offer_id, body.offer_id) if body.offer_id else None
    card_id = None
    requested = money(body.amount_usd or 0)
    if body.purpose == "card_topup":
        card = (await db.execute(select(Card).where(Card.id == body.card_id, Card.user_id == user.id))).scalar_one_or_none()
        if not card or card.status != "active" or not card.aifory_card_id or not card.offer_id:
            raise HTTPException(400, "Карта недоступна для пополнения.")
        if card.currency != "USD":
            raise HTTPException(400, "Оплата USDT доступна для долларовых карт.")
        card_id, offer_id = card.id, card.offer_id
        if not (Decimal("1") <= requested <= Decimal("10000")) or requested != requested.quantize(CENT):
            raise HTTPException(400, "Укажите сумму от $1 до $10 000, не более двух знаков после запятой.")
    else:
        offers = await card_service.get_offers(user)
        if not offer_id or offer_id not in CARD_NAME_BY_OFFER or not any(o["id"] == offer_id for o in offers):
            raise HTTPException(400, "Этот тип карты недоступен для выпуска.")

    # Serializes quote creation for this user, including browser retries.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing = (await db.execute(select(CryptoPayment).where(
        CryptoPayment.user_id == user.id, CryptoPayment.request_id == body.request_id,
    ).with_for_update())).scalar_one_or_none()
    if existing:
        if existing.purpose != body.purpose or existing.offer_id != offer_id or existing.card_id != card_id or (body.purpose == "card_topup" and existing.amount_usd != requested):
            raise HTTPException(409, "Запрос уже использован для другой суммы или карты.")
        return existing
    # Resume an unpaid invoice for the same purchase instead of showing a
    # second address when the user closes/reopens the payment sheet.
    pending = (await db.execute(select(CryptoPayment).where(
        CryptoPayment.user_id == user.id, CryptoPayment.purpose == body.purpose,
        CryptoPayment.offer_id == offer_id, CryptoPayment.card_id == card_id,
        CryptoPayment.status.in_(("creating", "active")), CryptoPayment.expires_at > datetime.utcnow(),
    ).order_by(CryptoPayment.id.desc()).with_for_update())).scalars().all()
    for row in pending:
        if body.purpose == "card_issue" or row.amount_usd == requested:
            return row

    rate = price_rub = None
    discount = Decimal("0")
    if body.purpose == "card_issue":
        discount = money(await invitee_discount_percent(db, user))
        price_rub = money(apply_discount_rub(await _issue_price_rub(db, offer_id), float(discount)))
        try:
            rate = money(await get_bb_index())  # Raw index, no SBP or app markup.
        except RateUnavailable as exc:
            raise HTTPException(502, str(exc)) from exc
        requested = round_charge(price_rub / rate)
        percent, charge = Decimal("0"), requested
    else:
        percent = money(settings.CRYPTOWAY_TOPUP_MARKUP_PERCENT)
        if not Decimal("0") <= percent <= Decimal("100"):
            raise HTTPException(503, "Неверная настройка комиссии USDT.")
        charge = round_charge(requested * (1 + percent / 100))
    row = CryptoPayment(
        user_id=user.id, request_id=body.request_id, external_id="pp-cw-" + uuid.uuid4().hex,
        purpose=body.purpose, offer_id=offer_id, card_id=card_id, amount_usd=requested,
        fee_percent=percent, charge_usdt=charge, price_rub=price_rub, base_rate=rate,
        discount_percent=discount, status="quoted", fulfillment_status="not_started",
        received_usdt=0, refund_credited=False, paid_notified=False, review_notified=False,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.add(row)
    await db.flush()
    await db.commit()
    return row


def check_invoice_identity(row, invoice):
    wallet = invoice.get("target_wallet") or {}
    if str(invoice.get("id")) != row.provider_invoice_id or invoice.get("external_id") != row.external_id:
        raise ValueError("Счёт не соответствует заказу.")
    if wallet.get("symbol_id") != row.symbol_id:
        raise ValueError("Валюта или сеть оплаты не соответствует счёту.")
    if money(invoice.get("target_value_symbol")) != row.charge_usdt or money(invoice.get("payer_amount")) != row.charge_usdt:
        raise ValueError("Сумма счёта отличается от согласованной.")
    if money(invoice.get("fee_split_percent", 0)) != 0 or money(invoice.get("markup_percent", 0)) != 0:
        raise ValueError("В проекте Cryptoway включена дополнительная комиссия для клиента.")
    if not wallet.get("value") or not trusted_pay_url(invoice.get("pay_url")):
        raise ValueError("Cryptoway вернул некорректные реквизиты счёта.")


async def attach_invoice(row, invoice):
    row.provider_invoice_id = str(invoice["id"])
    check_invoice_identity(row, invoice)
    row.wallet_address = invoice["target_wallet"]["value"]
    row.pay_url = invoice["pay_url"]
    row.provider_payload = json.dumps(invoice, ensure_ascii=False)
    row.status = "active"


async def create_invoice(db, user, payment_id, symbol_id):
    require_enabled()
    selected = next((n for n in await networks() if n["symbol_id"] == symbol_id), None)
    if selected is None:
        raise HTTPException(400, "Выберите доступную сеть USDT.")
    row = await owned_payment(db, user.id, payment_id, lock=True)
    if row.status != "quoted":
        if row.symbol_id and row.symbol_id != symbol_id:
            raise HTTPException(409, "Для этого счёта уже выбрана другая сеть. Сначала отмените счёт.")
        return row
    if row.expires_at <= datetime.utcnow():
        raise HTTPException(409, "Расчёт устарел. Откройте оплату заново.")
    if requires_kyc(row.offer_id) and not kyc_ready(user):
        raise HTTPException(403, "Для этой карты требуется верификация личности перед оплатой.")
    if row.charge_usdt < money(selected["min_amount"]):
        raise HTTPException(400, f"Минимальный платёж в этой сети — {selected['min_amount']} USDT.")
    row.status, row.symbol_id, row.network_name = "creating", symbol_id, selected["name"]
    row.creation_started_at = datetime.utcnow()
    row.expires_at = datetime.utcnow() + timedelta(minutes=max(15, min(settings.CRYPTOWAY_INVOICE_MINUTES, 120)))
    await db.commit()  # Persist the at-most-once creation claim before POST.
    try:
        invoice = await cryptoway_client.create_invoice({
            "name": "ProntoPay — " + ("выпуск карты" if row.purpose == "card_issue" else "пополнение карты"),
            "description": f"ProntoPay order {row.external_id}", "external_id": row.external_id,
            "symbol_id": symbol_id, "target_value_symbol": str(row.charge_usdt), "is_payer_fee": False,
            "deadline_at": row.expires_at.replace(tzinfo=timezone.utc).isoformat(),
            "callback_url": settings.PUBLIC_BASE_URL.rstrip("/") + "/api/webhooks/cryptoway",
        })
        await attach_invoice(row, invoice)
    except CryptowayError as exc:
        # Network timeout/5xx may have created a real invoice. Find it by
        # external_id later; never repeat the creation POST automatically.
        if exc.status and 400 <= exc.status < 500:
            row.status, row.last_error = "error", "Cryptoway не создал счёт. Попробуйте позже."
        await db.commit()
        if row.status == "error":
            raise HTTPException(502, row.last_error) from exc
        return row
    except (ValueError, KeyError, InvalidOperation) as exc:
        row.status, row.last_error = "error", str(exc)[:500]
        if row.provider_invoice_id:
            try:
                await cryptoway_client.cancel(row.provider_invoice_id)
            except CryptowayError:
                row.status = "review"
        await db.commit()
        raise HTTPException(502, "Счёт не соответствует согласованной сумме. Оплата не открыта.") from exc
    await db.commit()
    return row


def invoice_payment_state(row, invoice, transactions):
    """Decide from a fresh invoice AND confirmed on-chain deposits."""
    check_invoice_identity(row, invoice)
    received = Decimal("0")
    for tx in transactions:
        if tx.get("type") != "deposit":
            continue
        if tx.get("symbol_id") != row.symbol_id:
            raise ValueError("В счёте обнаружен перевод в другой валюте или сети.")
        if tx.get("status") == "dirty_lock":
            return "review", received, "Платёж ожидает проверки платёжным сервисом."
        if tx.get("status") == "executed":
            received += money(tx.get("net_amount"))  # Gross on-chain amount, includes merchant fee.
    state = invoice.get("status")
    if state == "executed":
        if received >= row.charge_usdt and money(invoice.get("current_value")) >= row.charge_usdt:
            return "paid", received, None
        return "review", received, "Счёт закрыт, но полная оплата не подтверждена. Обратитесь в поддержку."
    if state in ("expired", "cancelled"):
        if received > 0:
            return "review", received, "Средства поступили по закрытому счёту. Обратитесь в поддержку."
        return state, received, None
    return "active", received, None


async def alert_review(row):
    if row.review_notified:
        return
    row.review_notified = True
    from app.services.recovery_service import _alert
    await _alert(f"⚠️ Криптооплата #{row.id}: требуется проверка. User {row.user_id}. {row.last_error or 'Проверьте статус операции.'}")


async def fulfill_payment(payment_id):
    from app.services.card_service import card_service
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(CryptoPayment).where(CryptoPayment.id == payment_id).with_for_update())).scalar_one_or_none()
        if not row or row.status != "paid" or row.fulfillment_status != "not_started":
            return
        row.fulfillment_status = "processing"
        row.fulfillment_started_at = datetime.utcnow()
        await db.commit()  # All retries see the durable claim.
        user = await db.get(User, row.user_id)
        if not row.paid_notified and getattr(user, "telegram_user_id", None):
            row.paid_notified = True
            await db.commit()
            try:
                from app.services.telegram_bot_service import send_notification
                await send_notification(user.telegram_user_id,
                    f"✅ <b>Оплата USDT получена</b>\n\nСумма: <b>{row.charge_usdt:.2f} USDT</b>.\n"
                    + ("Начинаем выпуск карты." if row.purpose == "card_issue" else f"Пополняем карту на <b>${row.amount_usd:.2f}</b>.")
                    + " Обработка обычно занимает до 5 минут.")
            except Exception as exc:
                logger.warning("Crypto receipt notification failed: %s", type(exc).__name__)
        try:
            if row.purpose == "card_issue":
                result = await card_service.issue_card(
                    db, user, row.offer_id, user.kyc_first_name or user.username or "ProntoPay",
                    user.kyc_last_name or "User", skip_balance_check=True, email=user.email,
                    defer_follow_up=True, crypto_payment_id=row.id,
                )
            else:
                result = await card_service.deposit_card(db, user, str(row.card_id), float(row.amount_usd),
                    skip_balance_check=True, crypto_payment_id=row.id)
            row.order_id = result["local_order_id"]
            await db.commit()
        except Exception as exc:
            await db.rollback()
            row = (await db.execute(select(CryptoPayment).where(CryptoPayment.id == payment_id).with_for_update())).scalar_one()
            # A provider may have accepted a request before the exception.
            # Reconcile the linked order or request manual review, never retry.
            if not row.order_id:
                row.fulfillment_status, row.last_error = "review", "Оплата получена. Требуется проверка выпуска или пополнения."
                logger.error("Crypto fulfillment needs review: payment=%s error_type=%s", payment_id, type(exc).__name__)
                await alert_review(row)
            else:
                cause = exc.__cause__
                if cause is None or getattr(cause, "retryable", True) or not (400 <= (getattr(cause, "status", 0) or 0) < 500):
                    row.fulfillment_status, row.last_error = "review", "Провайдер карты не подтвердил результат запроса. Поддержка проверяет операцию."
                    await alert_review(row)
            await db.commit()


async def update_order_outcome(db, row):
    started_at = row.fulfillment_started_at or row.paid_at or row.created_at
    if not row.order_id:
        if row.fulfillment_status == "processing" and started_at < datetime.utcnow() - timedelta(minutes=15):
            row.fulfillment_status, row.last_error = "review", "Оплата получена, операция требует проверки поддержки."
            await alert_review(row)
        return
    order = await db.get(Order, row.order_id)
    if order and order.status == "completed":
        row.fulfillment_status = "completed"
    elif row.fulfillment_status == "review":
        return  # A timeout must not trigger a refund for a possibly completed operation.
    elif order and order.status == "failed":
        row.fulfillment_status = "failed"
        if not row.refund_credited:
            from app.services.wallet_service import credit
            user = await db.get(User, row.user_id)
            await credit(db, user, row.charge_usdt, "crypto_refund", "Возврат криптооплаты: операция по карте не выполнена", ref_order_id=order.id)
            row.refund_credited = True
        row.last_error = "Операция не выполнена. Оплаченная сумма возвращена на внутренний баланс."
    elif order and started_at < datetime.utcnow() - timedelta(minutes=30):
        row.fulfillment_status, row.last_error = "review", "Оплата получена. Поддержка проверяет статус операции по карте."
        await alert_review(row)


async def reconcile_payment(db, user, payment_id, force=False):
    row = await owned_payment(db, user.id, payment_id, lock=True)
    if row.status == "paid":
        await update_order_outcome(db, row)
        row.last_checked_at = datetime.utcnow()
        await db.commit()
        if force and row.provider_invoice_id:
            try:
                invoice = await cryptoway_client.invoice(row.provider_invoice_id)
                transactions = await cryptoway_client.transactions(row.provider_invoice_id)
                state, received, error = invoice_payment_state(row, invoice, transactions)
                if state == "paid" and received > money(row.received_usdt or 0):
                    row = await owned_payment(db, user.id, payment_id, lock=True)
                    row.received_usdt = max(received, money(row.received_usdt or 0))
                    if received > row.charge_usdt:
                        row.last_error = f"Переплата {received - row.charge_usdt} USDT. Требуется возврат разницы клиенту."
                        await alert_review(row)
                    await db.commit()
            except (CryptowayError, ValueError, KeyError, InvalidOperation):
                pass  # The confirmed payment and its fulfillment remain valid.
        if row.fulfillment_status == "not_started":
            asyncio.create_task(fulfill_payment(row.id))
        return row
    if row.status in ("quoted", "error"):
        return row
    now = datetime.utcnow()
    if not force and row.last_checked_at and row.last_checked_at > now - timedelta(seconds=10):
        return row
    row.last_checked_at = now
    await db.commit()
    try:
        if not row.provider_invoice_id:
            found = await cryptoway_client.find_invoice(row.external_id)
            if not found:
                if (row.creation_started_at or row.created_at) < now - timedelta(minutes=5):
                    row.status, row.last_error = "review", "Не удалось подтвердить создание счёта. Обратитесь в поддержку."
                    await db.commit()
                return row
            await attach_invoice(row, found)
            await db.commit()
        invoice = await cryptoway_client.invoice(row.provider_invoice_id)
        transactions = await cryptoway_client.transactions(row.provider_invoice_id)
        state, received, error = invoice_payment_state(row, invoice, transactions)
    except CryptowayError:
        return row  # Retriable, keep the invoice and its frozen price.
    except (ValueError, KeyError, InvalidOperation):
        state, received, error = "review", money(row.received_usdt or 0), "Данные оплаты требуют проверки поддержки."
    row = await owned_payment(db, user.id, payment_id, lock=True)
    if row.status == "paid":
        await db.commit()
        return row  # Another callback confirmed it while this GET was in flight.
    row.status, row.received_usdt, row.last_error = state, received, error
    if state == "paid":
        row.paid_at = now
        if received > row.charge_usdt:
            row.last_error = f"Переплата {received - row.charge_usdt} USDT. Требуется возврат разницы клиенту."
            await alert_review(row)
    elif state == "review":
        await alert_review(row)
    await db.commit()
    if state == "paid":
        asyncio.create_task(fulfill_payment(row.id))
    return row


async def poll_payments():
    """Polling covers lost callbacks, AML completion, and backend restarts."""
    while True:
        try:
            if cryptoway_client.is_configured():
                async with AsyncSessionLocal() as db:
                    rows = (await db.execute(select(CryptoPayment).where(
                        or_(
                            CryptoPayment.status == "paid",
                            and_(CryptoPayment.status.in_(("creating", "active", "review")), CryptoPayment.created_at > datetime.utcnow() - timedelta(days=7)),
                            and_(CryptoPayment.status.in_(("expired", "cancelled")), CryptoPayment.provider_invoice_id.is_not(None),
                                CryptoPayment.created_at > datetime.utcnow() - timedelta(days=1),
                                or_(CryptoPayment.last_checked_at.is_(None), CryptoPayment.last_checked_at < datetime.utcnow() - timedelta(minutes=5))),
                        ),
                        CryptoPayment.fulfillment_status.not_in(("completed", "failed")),
                    ).order_by(CryptoPayment.last_checked_at.asc()).limit(10))).scalars().all()
                    for row in rows:
                        user = await db.get(User, row.user_id)
                        if user:
                            await reconcile_payment(db, user, row.id)
        except Exception as exc:
            logger.error("Crypto reconciliation failed: %s", type(exc).__name__)
        await asyncio.sleep(30)
