from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.crypto_payment_service import (
    get_payment_status,
    initiate_payment,
    initiate_topup,
)

router = APIRouter(prefix="/crypto-payments", tags=["crypto-payments"])


class InitiateRequest(BaseModel):
    offer_id: str
    amount_usd: float
    network: str = "TRC-20"


class InitiateResponse(BaseModel):
    payment_id: str
    address: str
    network: str
    type: str
    amount_usd: float
    total_usdt: float
    expires_at: str


class TopupInitiateRequest(BaseModel):
    card_aifory_id: str
    offer_id: str
    amount_usd: float
    network: str = "TRC-20"


class PaymentStatusResponse(BaseModel):
    payment_id: str
    status: str
    type: str = "issue"
    address: str
    network: str
    total_usdt: float
    amount_usd: float
    expires_at: str
    order_id: int | None = None


@router.post("/initiate", response_model=InitiateResponse, summary="Initiate crypto payment for card issuance")
async def initiate(
    body: InitiateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await initiate_payment(db, current_user, body.offer_id, body.amount_usd, body.network)
        return InitiateResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/topup-initiate", response_model=InitiateResponse, summary="Initiate crypto payment for card top-up")
async def topup_initiate(
    body: TopupInitiateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await initiate_topup(
            db, current_user, body.card_aifory_id, body.offer_id, body.amount_usd, body.network
        )
        return InitiateResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{payment_id}/status", response_model=PaymentStatusResponse, summary="Get crypto payment status")
async def status(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await get_payment_status(db, payment_id, current_user.id)
        return PaymentStatusResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
