from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
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

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("/offers", response_model=List[CardOfferItem], summary="List available card products from Aifory")
async def list_offers(_: User = Depends(get_current_user)):
    try:
        return await card_service.get_offers()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/issue", response_model=IssueCardResponse, summary="Issue a new virtual card")
async def issue_card(
    body: IssueCardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await card_service.issue_card(
            db, current_user, body.offer_id, body.holder_first_name, body.holder_last_name,
            amount=body.amount,
        )
        return IssueCardResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("", response_model=List[CardResponse], summary="Get current user's cards (optionally sync with Aifory)")
async def get_cards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sync: bool = True,
):
    try:
        if sync:
            await card_service.sync_cards(db, current_user)
        cards = await card_service.get_user_cards(db, current_user.id)
        return [
            CardResponse(
                id=c.id,
                aifory_card_id=c.aifory_card_id,
                category=c.category,
                card_status=c.card_status,
                expired_at=c.expired_at,
                last4=c.last4,
                holder_name=c.holder_name,
                currency=c.currency,
                currency_id=c.currency_id,
                payment_system_id=c.payment_system_id,
                status=c.status,
                balance=float(c.balance),
                offer_id=c.offer_id,
            )
            for c in cards
        ]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{card_id}/requisites", response_model=CardRequisitesResponse, summary="Get card PAN / expiry / CVV")
async def get_requisites(
    card_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await card_service.get_card_requisites(db, current_user.id, card_id)
        return CardRequisitesResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{card_id}/deposit-offers", summary="List deposit (top-up) offers available for a card")
async def get_deposit_offers(
    card_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await card_service.get_deposit_offers(db, current_user.id, card_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/{card_id}/transactions", summary="Get card transaction history from Aifory")
async def get_card_transactions(
    card_id: int,
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
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/{card_id}/deposit", response_model=IssueCardResponse, summary="Top up a card balance via Aifory")
async def deposit_card(
    card_id: int,
    body: CardDepositRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await card_service.deposit_card(db, current_user, card_id, body.amount)
        return IssueCardResponse(**result, message="Card top-up order created")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
