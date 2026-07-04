from decimal import Decimal
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.card import (
    CardDepositRequest,
    CardOfferItem,
    CardRequisitesResponse,
    CardResponse,
    IssueCardRequest,
    IssueCardResponse,
)
from app.services.card_service import card_service
from app.services.telegram_bot_service import notify_card_issued, notify_topup_result

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("/issuance-price", summary="Get card issuance price from admin settings")
async def get_issuance_price(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    from sqlalchemy import select as _select
    from app.models.admin_setting import AdminSetting

    keys = ["CARD_ISSUANCE_PRICE_RUB", "CARD_ISSUANCE_PRICE_PAY_RUB"]
    result = await db.execute(_select(AdminSetting).where(AdminSetting.key.in_(keys)))
    rows = {r.key: r.value for r in result.scalars().all()}

    price_rub = float(rows.get("CARD_ISSUANCE_PRICE_RUB") or 999)
    price_pay_rub = float(rows.get("CARD_ISSUANCE_PRICE_PAY_RUB") or 1999)

    return {
        "price_rub": price_rub,
        "price_pay_rub": price_pay_rub,
        "initial_balance": 0.0,
    }


@router.get("/offers", response_model=List[CardOfferItem], summary="List available virtual card types from O-Plata")
async def list_offers(current_user: User = Depends(get_current_user)):
    try:
        # current_count in each offer reflects THIS user's issued cards,
        # so the frontend can disable issuing when maxIssuedCount is reached
        return await card_service.get_offers(user=current_user)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/issue", response_model=IssueCardResponse, summary="Issue a new virtual card")
async def issue_card(
    body: IssueCardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import select as _select
    from app.models.admin_setting import AdminSetting
    
    # Quick synchronous validation only; heavy O-Plata pipeline runs in background.
    if not body.offer_id:
        raise HTTPException(status_code=400, detail="offer_id is required")
    
    # Require KYC verification before card issuance
    if current_user.kyc_status != "success" or not current_user.kyc_first_name or not current_user.kyc_last_name:
        raise HTTPException(
            status_code=403,
            detail="KYC verification required. Please complete identity verification before issuing a card."
        )
    
    # Get admin-configured price
    result = await db.execute(_select(AdminSetting).where(AdminSetting.key == "CARD_ISSUANCE_PRICE_USD"))
    price_setting = result.scalar_one_or_none()
    required = Decimal(str(price_setting.value if price_setting else "10.0"))
    
    skip_balance_check = (body.payment_method == "sbp")
    if not skip_balance_check:
        if Decimal(str(current_user.balance or 0)) < required:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Required: {required:.2f} USD, available: {current_user.balance}",
            )

    if settings.DETAILED_DEV_LOGS:
        log.info(
            "Card issuance requested | user_id=%s username=%s offer_id=%s price=%s payment_method=%s skip_balance=%s",
            current_user.id,
            current_user.username,
            body.offer_id,
            float(required),
            body.payment_method,
            skip_balance_check,
        )

    card_service.schedule_issue_in_background(
        user_id=current_user.id,
        offer_id=body.offer_id,
        holder_first_name=body.holder_first_name,
        holder_last_name=body.holder_last_name,
        email=body.email,
        document_number=body.document_number,
        skip_balance_check=skip_balance_check,
    )
    return IssueCardResponse(local_order_id=0, partner_order_id="")


@router.get("", response_model=List[CardResponse], summary="Get current user's cards (short sync with timeout, falls back to local)")
async def get_cards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import asyncio as _asyncio
    import logging as _logging
    _log = _logging.getLogger(__name__)
    # Start the sync in the background (own DB session). Briefly wait for it
    # so freshly created cards usually appear on this very call. If O-Plata is
    # slow, fall through — the background task continues running and the next
    # /cards poll will see the result.
    try:
        sync_task = _asyncio.create_task(card_service._run_sync_in_background(current_user.id))
        try:
            await _asyncio.wait_for(_asyncio.shield(sync_task), timeout=5.0)
        except _asyncio.TimeoutError:
            _log.info(
                "sync_cards inline exceeded 5s for user_id=%s; continuing in background",
                current_user.id,
            )
    except Exception as exc:
        _log.warning("sync schedule failed for user_id=%s: %s", current_user.id, exc)
    try:
        cards = await card_service.get_user_cards(db, current_user.id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [
        CardResponse(
            id=c.id,
            aifory_card_id=c.aifory_card_id,
            card_status=c.card_status,
            expired_at=c.expired_at,
            last4=c.last4,
            holder_name=c.holder_name,
            currency=c.currency,
            status=c.status,
            balance=float(c.balance),
            offer_id=c.offer_id,
        )
        for c in cards
    ]


@router.get("/{card_id}/requisites", response_model=CardRequisitesResponse, summary="Get card PAN / expiry / CVV")
async def get_requisites(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await card_service.get_card_requisites(db, current_user.id, card_id)
        return CardRequisitesResponse(**data)
    except ValueError as exc:
        if "not active yet" in str(exc).lower():
            raise HTTPException(status_code=503, detail="Карта ещё обрабатывается. Попробуйте позже.")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        if "illegal state" in str(exc).lower():
            raise HTTPException(status_code=503, detail="Карта ещё обрабатывается. Попробуйте позже.")
        raise HTTPException(status_code=502, detail=str(exc))



@router.get("/{card_id}/transactions", summary="Get card transaction history from O-Plata")
async def get_card_transactions(
    card_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await card_service.get_card_transactions(db, current_user.id, card_id, limit, offset)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        s = str(exc).lower()
        if "illegal state" in s or "technical error" in s:
            return []
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/{card_id}/deposit", response_model=IssueCardResponse, summary="Top up a card balance via O-Plata")
async def deposit_card(
    card_id: str,
    body: CardDepositRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.amount is None or float(body.amount) <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    skip_balance_check = (body.payment_method == "sbp")
    if not skip_balance_check:
        markup_pct = Decimal(str(settings.ONLINE_TOPUP_MARKUP_PERCENT))
        required = Decimal(str(body.amount)) + Decimal(str(body.amount)) * markup_pct / Decimal("100")
        if Decimal(str(current_user.balance or 0)) < required:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Required: {required:.2f} USD, available: {current_user.balance}",
            )

    card_service.schedule_deposit_in_background(
        user_id=current_user.id,
        card_id=card_id,
        amount=float(body.amount),
        skip_balance_check=skip_balance_check,
    )
    return IssueCardResponse(local_order_id=0, partner_order_id="", message="Card top-up scheduled")
