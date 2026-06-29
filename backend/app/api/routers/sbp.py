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
import uuid as _uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db, AsyncSessionLocal
from app.integrations.bitbanker_client import bitbanker_client, verify_webhook_signature
from app.models.bb_invoice import BbInvoice
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sbp", tags=["sbp"])

RUB_TO_USD_FALLBACK = Decimal("0.011")  # rough fallback if no exchange rate available


def _external_ref(user: User) -> str:
    """Stable external ID for this user in Bitbanker."""
    return f"u{user.id}"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class KycRequest(BaseModel):
    pass  # nothing required from client; we derive external_client_ref from JWT


class InvoiceCreateRequest(BaseModel):
    amount_rub: float
    purpose: str = "balance_topup"  # "balance_topup" | "card_issue"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/usd-to-rub-rate", summary="Get current USD to RUB exchange rate")
async def get_usd_to_rub_rate(_: User = Depends(get_current_user)):
    """Returns the admin-configured USD to RUB rate for SBP payments."""
    return {"usd_to_rub_rate": settings.USD_TO_RUB_RATE}


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


@router.post("/invoice", summary="Create SBP invoice and get QR code")
async def create_invoice(
    body: InvoiceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.amount_rub > 50000:
        raise HTTPException(status_code=400, detail="Maximum amount is 50000 RUB")
    if body.purpose not in ("balance_topup", "card_issue"):
        raise HTTPException(status_code=400, detail="purpose must be balance_topup or card_issue")

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
            logger.error("[SBP] Client registration failed: %s | %s", ext_ref, str(e)[:200])
            raise HTTPException(status_code=502, detail=f"Ошибка регистрации в платёжной системе: {str(e)[:100]}")
    
    # Block invoice creation if client not verified by Bitbanker
    if not is_verified:
        raise HTTPException(
            status_code=403,
            detail="Верификация ещё обрабатывается. Пожалуйста, подождите несколько минут и попробуйте снова. Если проблема сохраняется, обратитесь в поддержку."
        )
    
    idempotency_key = f"inv-{current_user.id}-{_uuid.uuid4().hex[:16]}"

    try:
        result = await bitbanker_client.create_invoice(
            amount_rub=body.amount_rub,
            partner_client_external_id=ext_ref,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bitbanker invoice error: {exc}")

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
        amount_rub=Decimal(str(body.amount_rub)),
        status=status,
        payment_url=payment_url,
        qr_base64=qr_b64,
        raw_response=json.dumps(result, ensure_ascii=False)[:4000],
    )
    db.add(invoice)
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

    # Poll Bitbanker for live status
    if invoice.bb_invoice_id:
        try:
            live = await bitbanker_client.get_invoice(invoice.bb_invoice_id)
            sbp_info = live.get("sbp_info") or {}
            live_status = sbp_info.get("status") or live.get("status") or invoice.status
            if live_status != invoice.status:
                invoice.status = live_status
                invoice.raw_response = json.dumps(live, ensure_ascii=False)[:4000]
                await db.commit()
                # If payment captured — credit user balance
                if live_status in ("captured", "authorized"):
                    await _credit_user_balance(db, invoice, live)
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

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BbInvoice).where(BbInvoice.bb_invoice_id == bb_invoice_id))
        invoice = result.scalar_one_or_none()
        if not invoice:
            logger.warning("[SBP] Webhook: no local invoice for bb_id=%s", bb_invoice_id)
            return {"ok": True}

        invoice.status = status
        invoice.raw_response = json.dumps(payload, ensure_ascii=False)[:4000]

        if status in ("captured", "authorized") and not invoice.amount_usd:
            await _credit_user_balance(db, invoice, payload)

        await db.commit()

    return {"ok": True}


async def _credit_user_balance(db: AsyncSession, invoice: BbInvoice, bb_payload: Dict[str, Any]) -> None:
    """Credit user's local USD balance based on the exchange_deal in the Bitbanker response."""
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
