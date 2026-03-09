from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.card import (
    CardOffersResponse,
    CardOfferResponse,
    IssueCardCalculateRequest,
    IssueCardCalculateResponse,
    IssueCardRequest,
    IssueCardResponse,
)
from app.services.card_service import card_service
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/offers", tags=["Card Offers"])


@router.get("", response_model=CardOffersResponse)
async def get_offers(
    current_user: User = Depends(get_current_user),
):
    """Get available card offers (bins) from Aifory."""
    offers_data = await card_service.get_offers()
    
    offers = []
    for offer in offers_data.get("offers", []):
        offers.append(CardOfferResponse(
            bin=offer.get("bin"),
            category=offer.get("category"),
            min_amount=offer.get("minAmount"),
            max_amount=offer.get("maxAmount"),
            create_card_currency=offer.get("createCardCurrency"),
            create_card_fixed_fee=offer.get("createCardFixedFee"),
            create_card_fee_percent=offer.get("createCardFeePercent"),
            operation_fixed_fee=offer.get("operationFixedFee"),
            operation_fee_percent=offer.get("operationFeePercent"),
            operation_limit=offer.get("operationLimit"),
            all_time_limit=offer.get("allTimeLimit"),
        ))
    
    return CardOffersResponse(
        offers=offers,
        limits=offers_data.get("limits", {}),
    )


@router.post("/calculate", response_model=IssueCardCalculateResponse)
async def calculate_issue(
    request: IssueCardCalculateRequest,
    current_user: User = Depends(get_current_user),
):
    """Calculate fees for card issuance."""
    try:
        result = await card_service.calculate_issue(
            bin=request.bin,
            amount=request.amount,
            account_id=request.account_id,
        )
        return IssueCardCalculateResponse(
            amount=result.get("amount"),
            fee=result.get("fee"),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/issue", response_model=IssueCardResponse)
async def issue_card(
    request: IssueCardRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Issue a new card.
    Deducts amount from user balance and creates order in Aifory.
    """
    try:
        result = await card_service.issue_card(
            db=db,
            user_id=current_user.id,
            bin=request.bin,
            amount=request.amount,
            email=request.email,
            account_id=request.account_id,
        )
        return IssueCardResponse(
            order_id=result.get("order_id"),
            message="Card issuance started. Poll order status for updates.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
