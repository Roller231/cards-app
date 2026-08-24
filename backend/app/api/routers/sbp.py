"""SBP payment flow via Bitbanker gateway.

Endpoints:
  POST /sbp/kyc                — start KYC session (returns kyc_url)
  GET  /sbp/kyc/status         — check is_verified_for_sbp
  GET  /sbp/prediction         — current limits/fees
  GET  /sbp/exchange-prediction — exchange rate for given RUB amount
  POST /sbp/invoice            — create invoice (returns QR + payment_url)
  GET  /sbp/invoice/{invoice_id} — poll invoice status
  POST /sbp/webhook            — Bitbanker webhook receiver (no auth required)
"""
from __future__ import annotations

import json
import logging
import math
import time as _time
import uuid as _uuid
from datetime import datetime, timedelta, timezone as _dt_timezone
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db, AsyncSessionLocal
from app.integrations.bitbanker_client import bitbanker_client, humanize_bb_error, verify_webhook_signature
from app.models.bb_invoice import BbInvoice
from app.models.user import User
from app.services.telegram_bot_service import notify_sbp_payment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sbp", tags=["sbp"])

RUB_TO_USD_FALLBACK = Decimal("0.011")  # rough fallback if no exchange rate available

# Bitbanker prod limits (see partner docs): 1000..50000 RUB per transfer,
# max 2 paid QR codes per day, account block after 3 consecutive unpaid QRs.
SBP_MIN_AMOUNT_RUB = 1000
SBP_MAX_AMOUNT_RUB = 50000
SBP_MAX_QR_PER_DAY = 2
_PAID_STATUSES = ("captured", "authorized")


def _msk_day_start_utc() -> datetime:
    """Start of the current Moscow day as naive UTC (DB stores naive UTC)."""
    msk = _dt_timezone(timedelta(hours=3))
    day_start_msk = datetime.now(msk).replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start_msk.astimezone(_dt_timezone.utc).replace(tzinfo=None)


def _external_ref(user: User) -> str:
    """Stable external ID for this user in Bitbanker."""
    return f"u{user.id}"


async def get_sbp_qr_status(db: AsyncSession, user: User) -> Dict[str, Any]:
    """Compute this user's QR-code guard status (see the two guards below).

    Shared by the /sbp/invoice guard and the admin panel, so both always agree
    on what's blocking a user. `user.sbp_qr_reset_at`, when set by an admin,
    makes invoices created before it invisible to both guards — i.e. it resets
    both the daily-count and the consecutive-unpaid limit at once.
    """
    reset_at = user.sbp_qr_reset_at

    day_start = _msk_day_start_utc()
    if reset_at and reset_at > day_start:
        day_start = reset_at
    today_count_res = await db.execute(
        select(func.count()).select_from(BbInvoice).where(
            BbInvoice.user_id == user.id,
            BbInvoice.created_at >= day_start,
        )
    )
    today_count = today_count_res.scalar() or 0

    window_start = datetime.utcnow() - timedelta(days=30)
    if reset_at and reset_at > window_start:
        window_start = reset_at
    last_two_res = await db.execute(
        select(BbInvoice).where(
            BbInvoice.user_id == user.id,
            BbInvoice.created_at >= window_start,
        ).order_by(BbInvoice.id.desc()).limit(2)
    )
    last_two = list(last_two_res.scalars().all())
    consecutive_unpaid_blocked = len(last_two) == 2 and all(inv.status not in _PAID_STATUSES for inv in last_two)

    return {
        "today_qr_count": today_count,
        "max_qr_per_day": SBP_MAX_QR_PER_DAY,
        "daily_limit_reached": today_count >= SBP_MAX_QR_PER_DAY,
        "consecutive_unpaid_blocked": consecutive_unpaid_blocked,
        "last_invoices": [
            {
                "id": inv.id,
                "status": inv.status,
                "purpose": inv.purpose,
                "amount_rub": float(inv.amount_rub),
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
            for inv in last_two
        ],
        "sbp_qr_reset_at": reset_at.isoformat() if reset_at else None,
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class KycRequest(BaseModel):
    pass  # nothing required from client; we derive external_client_ref from JWT


class InvoiceCreateRequest(BaseModel):
    amount_rub: float
    purpose: str = "balance_topup"  # "balance_topup" | "card_issue"
    offer_id: Optional[str] = None  # required when purpose=card_issue
    card_id: Optional[str] = None   # required when purpose=balance_topup (local card UUID)
    amount_usd_requested: Optional[float] = None  # exact USD amount user wants deposited to card
    promo_code: Optional[str] = None  # optional promo code; discount is applied server-side


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/usd-to-rub-rate", summary="Get current USD to RUB exchange rate")
async def get_usd_to_rub_rate(_: User = Depends(get_current_user)):
    """Returns the admin-configured USD to RUB rate for SBP payments."""
    return {"usd_to_rub_rate": settings.USD_TO_RUB_RATE}


@router.get("/rate", summary="App exchange rate: BB index × bitbFee × myFee × clarusFee")
async def get_sbp_rate(_: User = Depends(get_current_user)):
    """Rate formula (always applies): [Bitbanker index] × three admin-configured
    multipliers. Also returns the fixed fee applied to payments below threshold."""
    try:
        pred = await bitbanker_client.get_exchange_prediction(10000)
        index = float(pred.get("approximate_rate") or 0)
    except Exception as exc:
        logger.warning("[SBP] rate: exchange prediction failed: %s", str(exc)[:200])
        index = 0.0
    if index <= 0:
        raise HTTPException(status_code=502, detail="Курс временно недоступен. Попробуйте позже.")
    rate = (
        index
        * (1 + settings.SBP_BITBANKER_FEE_PERCENT / 100)
        * (1 + settings.SBP_OUR_FEE_PERCENT / 100)
        * (1 + settings.SBP_CLARUS_FEE_PERCENT / 100)
    )
    bb_fee, bb_fee_min = await _get_bb_fee_params()
    return {
        "index": round(index, 4),
        "rate": round(rate, 4),
        "small_payment_fee_rub": settings.SBP_SMALL_PAYMENT_FEE_RUB,
        "small_payment_threshold_rub": settings.SBP_SMALL_PAYMENT_THRESHOLD_RUB,
        "min_transfer_rub": _min_transfer_rub(bb_fee, bb_fee_min),
        "max_transfer_rub": SBP_MAX_AMOUNT_RUB,
        "bb_fee_pct": round(bb_fee * 100, 4),
        "bb_fee_min_rub": bb_fee_min,
    }


@router.post("/kyc-session", summary="Create Bitbanker KYC session")
async def create_kyc_session(current_user: User = Depends(get_current_user)):
    """Generate KYC URL for user verification via Bitbanker widget."""
    ext_ref = _external_ref(current_user)
    try:
        result = await bitbanker_client.create_kyc_session(ext_ref)
        return {
            "kyc_url": result.get("kyc_url"),
            "partner_client_id": result.get("partner_client_id"),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bitbanker KYC error: {exc}")


@router.get("/kyc-status", summary="Check KYC verification status")
async def get_kyc_status(current_user: User = Depends(get_current_user)):
    """Check if user is verified for SBP payments."""
    ext_ref = _external_ref(current_user)
    try:
        result = await bitbanker_client.get_partner_client(ext_ref)
        return {
            "client_id": result.get("client_id"),
            "is_verified_for_sbp": result.get("is_verified_for_sbp", False),
        }
    except Exception as exc:
        # Client doesn't exist yet
        return {
            "client_id": ext_ref,
            "is_verified_for_sbp": False,
            "error": str(exc)[:200],
        }


@router.get("/prediction", summary="SBP limits and fee info")
async def sbp_prediction(_: User = Depends(get_current_user)):
    try:
        return await bitbanker_client.get_sbp_prediction()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/exchange-prediction", summary="Exchange rate prediction for RUB -> USDT")
async def exchange_prediction(
    amount_rub: float = 1000.0,
    _: User = Depends(get_current_user),
):
    try:
        return await bitbanker_client.get_exchange_prediction(amount_rub)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# Bitbanker QR commission = max(pct × QR, min_abs), charged ON TOP of the
# invoice amount. Live values come from their prediction-sbp endpoint
# (sbp_fee_pct / sbp_fee_abs) and are cached; config values are the fallback.
_bb_fee_cache: Dict[str, Any] = {"ts": 0.0, "pct": None, "abs": None}
_BB_FEE_CACHE_TTL = 300  # seconds


async def _get_bb_fee_params() -> tuple[float, float]:
    """Returns (pct_fraction, min_abs_rub) of Bitbanker's QR commission."""
    now = _time.time()
    if _bb_fee_cache["pct"] is not None and now - _bb_fee_cache["ts"] < _BB_FEE_CACHE_TTL:
        return _bb_fee_cache["pct"], _bb_fee_cache["abs"]
    pct = settings.SBP_BITBANKER_FEE_PERCENT / 100.0
    min_abs = float(settings.SBP_BB_MIN_FEE_RUB)
    try:
        pred = await bitbanker_client.get_sbp_prediction()
        live_pct = float(pred.get("sbp_fee_pct") or 0)
        if live_pct > 0:
            pct = live_pct / 100.0
            min_abs = float(pred.get("sbp_fee_abs") or 0)
    except Exception as exc:
        logger.warning("[SBP] prediction-sbp unavailable, using config fee fallback: %s", str(exc)[:200])
    _bb_fee_cache.update(ts=now, pct=pct, abs=min_abs)
    return pct, min_abs


def _discounted_invoice_rub(shown_rub: float, pct: float, min_abs: float) -> float:
    """Invert Bitbanker's QR grossing so the user pays exactly `shown_rub`:
    percent branch: QR = invoice / (1 − pct); flat branch: QR = invoice + min_abs.
    Kopeck precision (BB accepts fractional amounts) — floor to 2 decimals so
    the QR never exceeds the shown amount."""
    d_shown = Decimal(str(shown_rub))
    if shown_rub * pct >= min_abs:
        inv = (d_shown * (Decimal("1") - Decimal(str(pct)))).quantize(
            Decimal("0.01"), rounding=ROUND_FLOOR
        )
    else:
        inv = (d_shown - Decimal(str(min_abs))).quantize(Decimal("0.01"))
    return float(inv)


def _min_transfer_rub(pct: float, min_abs: float) -> int:
    """Smallest payable amount: the discounted invoice must stay ≥ BB's minimum."""
    return max(math.ceil(SBP_MIN_AMOUNT_RUB / (1 - pct)), int(SBP_MIN_AMOUNT_RUB + min_abs))


@router.post("/invoice", summary="Create SBP invoice and get QR code")
async def create_invoice(
    body: InvoiceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Promo code (if any) is validated and applied FIRST: every check and the
    # Bitbanker invoice below run on the discounted amount the user really pays.
    promo_row = None
    promo_discount = 0.0
    promo_amount_before = float(body.amount_rub)
    if (body.promo_code or "").strip():
        from app.services.card_service import CARD_NAME_BY_OFFER as _CN
        from app.services.promo_service import PromoError, compute_discount_rub, get_valid_promo
        _ct = _CN.get(body.offer_id) if body.offer_id else None
        try:
            promo_row = await get_valid_promo(db, body.promo_code, current_user, body.purpose, _ct)
        except PromoError as _pe:
            raise HTTPException(status_code=400, detail=str(_pe))
        promo_discount = compute_discount_rub(promo_row, body.purpose, body.amount_rub)
        if promo_discount > 0:
            body.amount_rub = round(float(body.amount_rub) - promo_discount, 2)
            logger.info("[SBP] Promo %s applied for user_id=%s: %s -> %s (-%s ₽)",
                        promo_row.code, current_user.id, promo_amount_before, body.amount_rub, promo_discount)

    # Bitbanker charges max(pct × QR, min_abs) ON TOP of the invoice. We create
    # the invoice discounted so the QR the user pays equals exactly the amount
    # shown in the app.
    bb_fee, bb_fee_min = await _get_bb_fee_params()
    invoice_amount_rub = _discounted_invoice_rub(body.amount_rub, bb_fee, bb_fee_min)

    min_transfer = _min_transfer_rub(bb_fee, bb_fee_min)
    if body.amount_rub < min_transfer or invoice_amount_rub < SBP_MIN_AMOUNT_RUB:
        raise HTTPException(
            status_code=400,
            detail=f"Минимальная сумма перевода по СБП — {min_transfer:,} ₽.".replace(",", " "),
        )
    if body.amount_rub > SBP_MAX_AMOUNT_RUB:
        raise HTTPException(
            status_code=400,
            detail=f"Максимальная сумма перевода по СБП — {SBP_MAX_AMOUNT_RUB:,} ₽.".replace(",", " "),
        )
    if body.purpose not in ("balance_topup", "card_issue"):
        raise HTTPException(status_code=400, detail="purpose must be balance_topup or card_issue")

    # Admin toggles: refuse payment for a disabled card type
    if body.purpose == "card_issue" and body.offer_id:
        from app.services.card_service import CARD_NAME_BY_OFFER, _is_univ_email_ok, _is_univ_ravana
        _card_name = CARD_NAME_BY_OFFER.get(body.offer_id)
        if (
            (_card_name == "Online" and not settings.CARD_ONLINE_ENABLED)
            or (_card_name == "Online+Pay" and not settings.CARD_ONLINE_PLUS_ENABLED)
            or (_card_name == "Pay" and not settings.CARD_PAY_ENABLED)
        ):
            raise HTTPException(status_code=400, detail="Выпуск этого типа карты временно недоступен. Попробуйте позже.")
        # Universal-BIN cards (RT-8, отдельный univ-клиент) require a gmail/icloud
        # email BEFORE payment — otherwise the issue would fail after the user paid.
        _ravana = body.offer_id.rsplit(":", 1)[0]
        if _is_univ_ravana(_ravana) and not _is_univ_email_ok(current_user.email or ""):
            raise HTTPException(
                status_code=400,
                detail="Для этой карты нужна почта Gmail или iCloud — на неё придёт код подтверждения. Укажите её в разделе верификации.",
            )

    # --- Our own QR guards: keep users well inside Bitbanker's prod limits ---
    # 1) No more than 2 created QR codes per Moscow day (BB allows 2 paid/day;
    #    we cap creation so users can't even approach the block).
    # 2) Never let a user create a 3rd consecutive unpaid QR — Bitbanker blocks
    #    the account after 3 unpaid QRs in a row, and unblocking goes through
    #    their support with compliance questions. Intentionally NOT tied to the
    #    Moscow day: a stale/expired unpaid QR can't be paid anymore, so this
    #    stays blocking (30-day window) until support/cleanup resolves it —
    #    or until an admin resets it (User.sbp_qr_reset_at, see admin panel).
    qr_status = await get_sbp_qr_status(db, current_user)
    if qr_status["daily_limit_reached"]:
        raise HTTPException(
            status_code=429,
            detail="Можно создавать не более 2 QR-кодов в сутки. Лимит обновится в 00:00 по Москве.",
        )
    if qr_status["consecutive_unpaid_blocked"]:
        raise HTTPException(
            status_code=429,
            detail=(
                "У вас два неоплаченных QR-кода подряд. Чтобы не допустить блокировки "
                "пополнений по СБП, создание нового QR временно недоступно — "
                "пожалуйста, обратитесь в службу поддержки."
            ),
        )

    ext_ref = _external_ref(current_user)
    
    # Register client with KYC data — use real NeuroVision data if available, else env fallback
    if current_user.kyc_status != "success" or not current_user.kyc_passport:
        raise HTTPException(
            status_code=403,
            detail="KYC verification required. Please complete identity verification first."
        )

    # Step 1: Check if client already exists
    is_verified = False
    client_exists = False
    try:
        status = await bitbanker_client.get_partner_client(ext_ref)
        client_exists = True
        is_verified = status.get("is_verified_for_sbp", False)
        if settings.DETAILED_DEV_LOGS:
            logger.info("[SBP] Existing client: %s | is_verified_for_sbp=%s", ext_ref, is_verified)
    except Exception as e:
        if settings.DETAILED_DEV_LOGS:
            logger.info("[SBP] Client not found: %s | %s", ext_ref, str(e)[:100])
    
    # Step 2: Register client if doesn't exist
    if not client_exists:
        try:
            reg_result = await bitbanker_client.register_partner_client(
                client_id=ext_ref,
                email=current_user.email or f"{ext_ref}@prontopay.local",
                phone=current_user.phone or settings.BB_TEST_PHONE,
                first_name=current_user.kyc_first_name,
                last_name=current_user.kyc_last_name,
                patronymic=current_user.kyc_patronymic or "",
                birth_date=current_user.kyc_birth_date,
                passport=current_user.kyc_passport,
                passport_issue_date=current_user.kyc_passport_issue_date,
                country_of_passport_issue="RUS",
            )
            is_verified = reg_result.get("is_verified_for_sbp", False)
            if settings.DETAILED_DEV_LOGS:
                logger.info("[SBP] Client registered: %s | is_verified_for_sbp=%s", 
                           ext_ref, is_verified)
        except Exception as e:
            logger.error("[SBP] Client registration failed: %s | %s", ext_ref, str(e)[:400])
            raise HTTPException(status_code=502, detail=humanize_bb_error(e))
    
    # Block invoice creation if client not verified by Bitbanker
    if not is_verified:
        raise HTTPException(
            status_code=403,
            detail="Верификация ещё обрабатывается. Пожалуйста, подождите несколько минут и попробуйте снова. Если проблема сохраняется, обратитесь в поддержку."
        )
    
    idempotency_key = f"inv-{current_user.id}-{_uuid.uuid4().hex[:16]}"

    description = (
        "Выпуск карты ProntoPay" if body.purpose == "card_issue"
        else f"Пополнение баланса {int(body.amount_rub)} руб."
    )
    try:
        # Discounted amount goes to Bitbanker; the bank grosses it back up by the
        # acquiring fee, so the user's QR ≈ body.amount_rub (what the app showed).
        if settings.DETAILED_DEV_LOGS:
            logger.info("[SBP] Invoice discount | shown=%s -> invoice=%s (fee=%.2f%%)",
                        body.amount_rub, invoice_amount_rub, bb_fee * 100)
        result = await bitbanker_client.create_invoice(
            amount_rub=invoice_amount_rub,
            partner_client_external_id=ext_ref,
            idempotency_key=idempotency_key,
            description=description,
        )
    except Exception as exc:
        logger.error("[SBP] Invoice creation failed for %s: %s", ext_ref, str(exc)[:400])
        raise HTTPException(status_code=502, detail=humanize_bb_error(exc))

    bb_id = str(result.get("id") or result.get("invoice_id") or "")
    sbp_info = result.get("sbp_info") or {}
    payment_url = result.get("payment_url") or sbp_info.get("qr_url") or ""
    qr_b64 = result.get("sbp_qr") or sbp_info.get("sbp_qr") or ""
    status = sbp_info.get("status") or "initiated"

    invoice = BbInvoice(
        user_id=current_user.id,
        bb_invoice_id=bb_id,
        idempotency_key=idempotency_key,
        external_client_ref=ext_ref,
        purpose=body.purpose,
        offer_id=body.offer_id,
        card_id=body.card_id,
        amount_usd_requested=Decimal(str(body.amount_usd_requested)) if body.amount_usd_requested else None,
        amount_rub=Decimal(str(body.amount_rub)),
        status=status,
        payment_url=payment_url,
        qr_base64=qr_b64,
        raw_response=json.dumps(result, ensure_ascii=False)[:4000],
    )
    db.add(invoice)
    await db.flush()
    if promo_row is not None:
        from app.models.promo import PromoRedemption
        db.add(PromoRedemption(
            promo_id=promo_row.id, user_id=current_user.id,
            invoice_id=invoice.id, discount_rub=promo_discount, status="pending",
        ))
        await db.flush()
    await db.commit()

    if settings.DETAILED_DEV_LOGS:
        logger.info("[SBP] Invoice created | user_id=%s bb_id=%s amount_rub=%s status=%s",
                    current_user.id, bb_id, body.amount_rub, status)

    return {
        "local_invoice_id": invoice.id,
        "bb_invoice_id": bb_id,
        "status": status,
        "payment_url": payment_url,
        "qr_base64": qr_b64,
        "amount_rub": body.amount_rub,
        "promo": (
            {"code": promo_row.code, "discount_rub": promo_discount, "amount_before_rub": promo_amount_before}
            if promo_row is not None and promo_discount > 0 else None
        ),
        "expires_at": result.get("dt_expiration") or sbp_info.get("dt_expiration"),
    }


@router.get("/invoice/{local_invoice_id}", summary="Poll invoice status")
async def get_invoice_status(
    local_invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(BbInvoice).where(BbInvoice.id == local_invoice_id, BbInvoice.user_id == current_user.id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # If terminal — return cached status
    if invoice.status in ("captured", "authorized", "declined", "failed", "cancelled", "expired"):
        return {"local_invoice_id": invoice.id, "bb_invoice_id": invoice.bb_invoice_id,
                "status": invoice.status, "amount_rub": float(invoice.amount_rub)}

    # Poll Bitbanker for live status — only update status, no post-payment side effects
    # Post-payment actions (balance credit, card issue/topup) are handled exclusively by webhook
    if invoice.bb_invoice_id:
        try:
            live = await bitbanker_client.get_invoice(invoice.bb_invoice_id)
            sbp_info = live.get("sbp_info") or {}
            live_status = sbp_info.get("status") or live.get("status") or invoice.status
            if live_status != invoice.status:
                old_status = invoice.status
                invoice.status = live_status
                invoice.raw_response = json.dumps(live, ensure_ascii=False)[:4000]
                # Release the promo use if the payment died (webhook may never come)
                if live_status in ("declined", "failed", "cancelled", "expired"):
                    try:
                        from app.services.promo_service import settle_redemption
                        await settle_redemption(db, invoice.id, paid=False)
                    except Exception as _pr:
                        logger.warning("[SBP] Promo settle (poll) failed for invoice_id=%s: %s", invoice.id, _pr)
                await db.commit()
                # Failure statuses may never arrive via webhook (e.g. expired) —
                # notify the user here on the first transition detected by polling.
                if live_status in ("declined", "failed", "cancelled", "expired") and old_status != live_status:
                    try:
                        await notify_sbp_payment(
                            db, current_user,
                            amount_rub=float(invoice.amount_rub),
                            purpose=invoice.purpose,
                            success=False,
                            status=live_status,
                        )
                    except Exception as _n:
                        logger.warning("[SBP] Poll failure notification error for invoice_id=%s: %s", invoice.id, _n)
        except Exception as exc:
            logger.warning("[SBP] Poll invoice %s error: %s", invoice.bb_invoice_id, exc)

    return {
        "local_invoice_id": invoice.id,
        "bb_invoice_id": invoice.bb_invoice_id,
        "status": invoice.status,
        "amount_rub": float(invoice.amount_rub),
        "amount_usd": float(invoice.amount_usd) if invoice.amount_usd else None,
    }


@router.post("/webhook", summary="Bitbanker webhook receiver", include_in_schema=False)
async def bitbanker_webhook(request: Request):
    """Receives payment status updates from Bitbanker.
    Signature is verified using BITBANKER_API_SECRET.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if settings.BITBANKER_API_SECRET:
        if not verify_webhook_signature(payload, settings.BITBANKER_API_SECRET):
            logger.warning("[SBP] Webhook signature mismatch — rejected")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    sbp_info = payload.get("sbp_info") or {}
    status = sbp_info.get("status") or payload.get("status") or "unknown"
    bb_invoice_id = str(payload.get("id") or "")
    ext_ref = str(payload.get("partner_client_external_id") or "")

    logger.info("[SBP] Webhook | bb_invoice_id=%s ext_ref=%s status=%s", bb_invoice_id, ext_ref, status)

    if not bb_invoice_id:
        return {"ok": True}

    import asyncio as _asyncio
    local_invoice_id: Optional[int] = None
    is_captured = status in ("captured", "authorized")
    failed_statuses = ("declined", "failed", "cancelled", "expired")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BbInvoice).where(BbInvoice.bb_invoice_id == bb_invoice_id))
        invoice = result.scalar_one_or_none()
        if not invoice:
            logger.warning("[SBP] Webhook: no local invoice for bb_id=%s", bb_invoice_id)
            return {"ok": True}

        already_processed = bool(invoice.amount_usd) or invoice.status in ("captured", "authorized")
        old_status = invoice.status
        invoice.status = status
        invoice.raw_response = json.dumps(payload, ensure_ascii=False)[:4000]
        local_invoice_id = invoice.id
        purpose = invoice.purpose
        amount_rub = float(invoice.amount_rub)
        user_result = await db.execute(select(User).where(User.id == invoice.user_id))
        user = user_result.scalar_one_or_none()
        # Promo bookkeeping: count the use on first capture, release on failure.
        try:
            from app.services.promo_service import settle_redemption
            if is_captured and not already_processed:
                await settle_redemption(db, invoice.id, paid=True)
            elif status in failed_statuses and old_status != status:
                await settle_redemption(db, invoice.id, paid=False)
        except Exception as _pr:
            logger.warning("[SBP] Promo settle failed for invoice_id=%s: %s", invoice.id, _pr)
        await db.commit()

        # Notify user about the payment outcome (only on the first transition,
        # so repeated webhooks with the same status don't spam).
        try:
            if user:
                if is_captured and not already_processed:
                    await notify_sbp_payment(
                        db, user, amount_rub=amount_rub, purpose=purpose, success=True,
                    )
                elif status in failed_statuses and old_status != status:
                    await notify_sbp_payment(
                        db, user, amount_rub=amount_rub, purpose=purpose, success=False, status=status,
                    )
        except Exception as _n:
            logger.warning("[SBP] Payment notification failed for invoice_id=%s: %s", local_invoice_id, _n)

    # Trigger post-payment in background ONLY on first captured transition
    if is_captured and not already_processed:
        _asyncio.create_task(_credit_and_trigger(local_invoice_id, payload))

    return {"ok": True}


async def _credit_and_trigger(invoice_id: int, bb_payload: Dict[str, Any]) -> None:
    """Background: credit user balance then trigger card issue/topup. Single entry point from webhook."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(BbInvoice).where(BbInvoice.id == invoice_id))
            invoice = result.scalar_one_or_none()
            if not invoice:
                return
            # Double-check idempotency under lock
            if invoice.amount_usd:
                logger.info("[SBP] _credit_and_trigger: already processed invoice_id=%s — skipping", invoice_id)
            else:
                await _credit_user_balance(db, invoice, bb_payload)
                await db.commit()
        except Exception as exc:
            logger.error("[SBP] _credit_and_trigger balance credit failed for invoice_id=%s: %s", invoice_id, exc)

    # Trigger post-payment in separate session (may take minutes for card issue)
    await _trigger_post_payment(invoice_id)


async def _trigger_post_payment(invoice_id: int) -> None:
    """Background task: runs after SBP payment captured.
    - For balance_topup: call deposit_card directly on O-Plata (skip user.balance).
    - For card_issue: auto-issue the card using the stored offer_id.
    """
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(BbInvoice).where(BbInvoice.id == invoice_id))
            invoice = result.scalar_one_or_none()
            if not invoice:
                return
            user_result = await db.execute(select(User).where(User.id == invoice.user_id))
            user = user_result.scalar_one_or_none()
            if not user:
                return

            from app.services.card_service import card_service

            if invoice.purpose == "balance_topup":
                if not invoice.card_id:
                    logger.warning("[SBP] balance_topup invoice %s has no card_id — cannot deposit", invoice_id)
                    return
                # Use exact requested USD amount, fallback to received amount_usd
                deposit_amount = float(invoice.amount_usd_requested or invoice.amount_usd or 0)
                if deposit_amount <= 0:
                    logger.warning("[SBP] balance_topup invoice %s has no deposit amount — skipping", invoice_id)
                    return
                logger.info("[SBP] Auto-depositing card for user_id=%s card_id=%s amount=%s (invoice_id=%s)",
                            user.id, invoice.card_id, deposit_amount, invoice_id)
                card_service.schedule_deposit_in_background(
                    user_id=user.id,
                    card_id=invoice.card_id,
                    amount=deposit_amount,
                    skip_balance_check=True,
                )

            elif invoice.purpose == "card_issue":
                if not invoice.offer_id:
                    logger.warning("[SBP] card_issue invoice %s has no offer_id — cannot auto-issue", invoice_id)
                    return
                # Idempotency: skip only if this invoice already produced a
                # LIVE issue attempt (order linked to a card, or still in
                # flight). A failed attempt (provider rejected/deleted the
                # card — order has no card and status failed) must NOT block a
                # retry, otherwise support has to delete orders by hand.
                from app.models.order import Order
                existing_order_result = await db.execute(
                    select(Order).where(
                        Order.user_id == user.id,
                        Order.type == "issue",
                        Order.description.like(f"%sbp_invoice:{invoice_id}%"),
                    ).order_by(Order.id.desc()).limit(1)
                )
                existing_order = existing_order_result.scalars().first()
                _in_flight = existing_order is not None and (
                    existing_order.card_id is not None
                    or existing_order.status in ("pending", "processing")
                )
                if _in_flight:
                    logger.info("[SBP] Card already issued for invoice_id=%s (order %s, status=%s) — skipping duplicate",
                                invoice_id, existing_order.id, existing_order.status)
                    return
                if existing_order:
                    logger.info("[SBP] Previous issue attempt for invoice_id=%s left no card (order %s, status=%s) — retrying",
                                invoice_id, existing_order.id, existing_order.status)
                logger.info("[SBP] Auto-issuing card for user_id=%s offer_id=%s (invoice_id=%s)",
                            user.id, invoice.offer_id, invoice_id)
                usernameParts = (user.kyc_first_name or user.username or "User").strip().split()
                holder_first = usernameParts[0] if usernameParts else "User"
                holder_last = " ".join(usernameParts[1:]) if len(usernameParts) > 1 else "User"
                await card_service.issue_card(
                    db=db,
                    user=user,
                    offer_id=invoice.offer_id,
                    holder_first_name=holder_first,
                    holder_last_name=holder_last,
                    email=user.email,
                    skip_balance_check=True,
                    defer_follow_up=False,
                    sbp_invoice_id=invoice_id,
                )
                # Persist the issue order and linked card. Without this the
                # session closes with an implicit rollback and the order is
                # lost, even though the card was really created on O-Plata
                # (which also breaks the duplicate-issue guard above).
                await db.commit()
                logger.info("[SBP] Auto-issue card completed for user_id=%s", user.id)

        except Exception as exc:
            logger.error("[SBP] Post-payment trigger failed for invoice_id=%s: %s", invoice_id, exc)
            try:
                await db.rollback()
            except Exception:
                pass


async def _credit_user_balance(db: AsyncSession, invoice: BbInvoice, bb_payload: Dict[str, Any]) -> None:
    """Credit user's local USD balance based on the exchange_deal in the Bitbanker response."""
    # Refresh to get latest state and avoid race condition
    await db.refresh(invoice)
    if invoice.amount_usd:
        return  # already credited

    exchange_deals = bb_payload.get("exchange_deal") or []
    usd_received = Decimal("0")
    if isinstance(exchange_deals, list):
        for deal in exchange_deals:
            if str(deal.get("take_currency", "")).upper() == "USDT":
                usd_received += Decimal(str(deal.get("volume_take_final") or deal.get("volume_take") or 0))
    
    if usd_received <= 0:
        # Fallback: rough estimate from RUB amount
        usd_received = invoice.amount_rub * RUB_TO_USD_FALLBACK
        logger.info("[SBP] No exchange_deal in payload, using fallback rate. usd=%s", usd_received)

    user_result = await db.execute(select(User).where(User.id == invoice.user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.balance = Decimal(str(user.balance or 0)) + usd_received
        invoice.amount_usd = usd_received
        logger.info("[SBP] Credited user_id=%s +%s USD (invoice_id=%s)", user.id, usd_received, invoice.id)


# =====================  PROMO CODES (user side)  =====================

class PromoValidateRequest(BaseModel):
    code: str
    purpose: str = "balance_topup"      # balance_topup | card_issue
    offer_id: Optional[str] = None      # for card_issue: resolves the card type
    amount_rub: Optional[float] = None  # undiscounted amount for a live preview


@router.post("/promo/validate", summary="Validate a promo code and preview the discount")
async def validate_promo(
    body: PromoValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.card_service import CARD_NAME_BY_OFFER as _CN
    from app.services.promo_service import (
        PromoError, TYPE_LABELS, compute_discount_rub, describe_discount, get_valid_promo,
    )
    if body.purpose not in ("balance_topup", "card_issue"):
        raise HTTPException(status_code=400, detail="purpose must be balance_topup or card_issue")
    _ct = _CN.get(body.offer_id) if body.offer_id else None
    try:
        promo = await get_valid_promo(db, body.code, current_user, body.purpose, _ct)
    except PromoError as exc:
        return {"valid": False, "error": str(exc)}

    out = {
        "valid": True,
        "code": promo.code,
        "type": promo.type,
        "label": TYPE_LABELS.get(promo.type, "Промокод"),
        "description": describe_discount(promo),
    }
    if body.amount_rub and body.amount_rub > 0:
        discount = compute_discount_rub(promo, body.purpose, float(body.amount_rub))
        out["discount_rub"] = discount
        out["final_amount_rub"] = round(float(body.amount_rub) - discount, 2)
    return out
