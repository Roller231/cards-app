from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.topup import (
    TopUpOfferResponse,
    TopUpCalculateRequest,
    TopUpCalculateResponse,
    TopUpRequest,
    TopUpResponse,
)
from app.services.deposit_service import deposit_service
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/cards/{card_id}/topup", tags=["Top Up"])


@router.get("/offer", response_model=TopUpOfferResponse)
async def get_topup_offer(
    card_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get top-up offer for a card (min/max amounts, fee percent)."""
    try:
        offer = await deposit_service.get_deposit_offer(db, current_user.id, card_id)
        return TopUpOfferResponse(**offer)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/calculate", response_model=TopUpCalculateResponse)
async def calculate_topup(
    card_id: int,
    request: TopUpCalculateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Calculate fees for card top-up."""
    try:
        result = await deposit_service.calculate_deposit(
            db=db,
            user_id=current_user.id,
            card_id=card_id,
            amount=request.amount,
            account_id=request.account_id,
        )
        return TopUpCalculateResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("", response_model=TopUpResponse)
async def create_topup(
    card_id: int,
    request: TopUpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create top-up order for a card.
    Deducts amount from user balance and creates deposit order in Aifory.
    """
    try:
        result = await deposit_service.create_deposit(
            db=db,
            user_id=current_user.id,
            card_id=card_id,
            amount=request.amount,
            account_id=request.account_id,
        )
        return TopUpResponse(
            order_id=result.get("order_id"),
            message="Top-up started. Poll order status for updates.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
