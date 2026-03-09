from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.transaction import (
    TransactionResponse,
    TransactionListResponse,
    TransactionDetailResponse,
)
from app.services.transaction_service import transaction_service
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/cards/{card_id}/transactions", tags=["Transactions"])


@router.get("", response_model=TransactionListResponse)
async def get_transactions(
    card_id: int,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get transactions for a card with pagination."""
    try:
        transactions = await transaction_service.get_card_transactions(
            db=db,
            user_id=current_user.id,
            card_id=card_id,
            limit=limit,
            offset=offset,
        )
        return TransactionListResponse(
            transactions=[TransactionResponse(**tx) for tx in transactions]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{transaction_id}", response_model=TransactionDetailResponse)
async def get_transaction_details(
    card_id: int,
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get transaction details including merchant and failure reason."""
    try:
        details = await transaction_service.get_transaction_details(
            db=db,
            user_id=current_user.id,
            card_id=card_id,
            transaction_id=transaction_id,
        )
        return TransactionDetailResponse(**details)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
