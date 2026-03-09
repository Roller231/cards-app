from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.card import (
    CardResponse,
    CardListResponse,
    CardRequisitesResponse,
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

router = APIRouter(prefix="/cards", tags=["Cards"])


@router.get("", response_model=CardListResponse)
async def get_cards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all cards for current user."""
    cards = await card_service.get_user_cards(db, current_user.id)
    return CardListResponse(
        cards=[
            CardResponse(
                id=card.id,
                partner_card_id=card.partner_card_id,
                last4=card.last4,
                category=card.category,
                status=card.status,
                expired_at=card.expired_at,
                created_at=card.created_at,
            )
            for card in cards
        ]
    )


@router.get("/{card_id}", response_model=CardResponse)
async def get_card(
    card_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific card."""
    card = await card_service.get_card(db, current_user.id, card_id)
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found",
        )
    return CardResponse(
        id=card.id,
        partner_card_id=card.partner_card_id,
        last4=card.last4,
        category=card.category,
        status=card.status,
        expired_at=card.expired_at,
        created_at=card.created_at,
    )


@router.post("/{card_id}/requisites", response_model=CardRequisitesResponse)
async def get_card_requisites(
    card_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get card requisites (number, CVV, holder).
    These are fetched from Aifory and NOT stored locally.
    """
    try:
        requisites = await card_service.get_card_requisites(db, current_user.id, card_id)
        return CardRequisitesResponse(**requisites)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/sync", response_model=CardListResponse)
async def sync_cards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync cards from Aifory to local database."""
    cards = await card_service.sync_cards_from_aifory(db, current_user.id)
    return CardListResponse(
        cards=[
            CardResponse(
                id=card.id,
                partner_card_id=card.partner_card_id,
                last4=card.last4,
                category=card.category,
                status=card.status,
                expired_at=card.expired_at,
                created_at=card.created_at,
            )
            for card in cards
        ]
    )
