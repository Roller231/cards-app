from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.integrations.aifory_client import aifory_client
from app.models.card import Card
from app.models.user import User
from app.schemas.transaction import TransactionItem, TransactionListResponse

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get(
    "/cards/{card_id}",
    response_model=TransactionListResponse,
    summary="Get transaction history for a card (fetched from Aifory)",
)
async def get_card_transactions(
    card_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Card).where(Card.id == card_id, Card.user_id == current_user.id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if not card.aifory_card_id:
        raise HTTPException(
            status_code=400,
            detail="Card is not yet linked to Aifory (issuance may still be pending)",
        )

    try:
        raw_txns = await aifory_client.get_card_transactions(card.aifory_card_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    transactions = [
        TransactionItem(
            transaction_id=t.get("id") or t.get("transactionId") or t.get("transactionID"),
            date=t.get("date") or t.get("createdAt") or t.get("created_at"),
            amount=t.get("amount"),
            currency=t.get("currency"),
            merchant=t.get("merchant") or t.get("merchantName") or t.get("description"),
            status=t.get("status"),
            description=t.get("description") or t.get("comment"),
        )
        for t in raw_txns
    ]

    return TransactionListResponse(
        card_id=card.id,
        aifory_card_id=card.aifory_card_id,
        transactions=transactions,
    )


@router.get(
    "/cards/{card_id}/{transaction_id}",
    summary="Get details of a single transaction",
)
async def get_transaction_detail(
    card_id: int,
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Card).where(Card.id == card_id, Card.user_id == current_user.id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if not card.aifory_card_id:
        raise HTTPException(status_code=400, detail="Card not yet linked to Aifory")

    try:
        return await aifory_client.get_card_transaction_details(card.aifory_card_id, transaction_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
