from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.integrations.oplata_client import oplata_client
from app.models.card import Card
from app.models.user import User
from app.schemas.transaction import TransactionItem, TransactionListResponse
from app.services.card_service import _client_id

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get(
    "/cards/{card_id}",
    response_model=TransactionListResponse,
    summary="Get transaction history for a card (fetched from O-Plata)",
)
async def get_card_transactions(
    card_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if isinstance(card_id, str) and not card_id.isdigit():
        result = await db.execute(
            select(Card).where(Card.aifory_card_id == card_id, Card.user_id == current_user.id)
        )
    else:
        result = await db.execute(
            select(Card).where(Card.id == int(card_id), Card.user_id == current_user.id)
        )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if not card.aifory_card_id:
        raise HTTPException(status_code=400, detail="Card has no external ID (issuance may still be pending)")
    if not card.offer_id:
        raise HTTPException(status_code=400, detail="Card has no ravanaServerId stored")

    client_id = _client_id(current_user)
    page_number = offset // limit if limit > 0 else 0
    try:
        response = await oplata_client.get_card_transaction_list(
            client_id=client_id,
            card_id=card.aifory_card_id,
            ravana_server_id=card.offer_id,
            page_number=page_number,
            page_size=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    raw_txns = response.get("data") or response.get("content") or (response if isinstance(response, list) else [])
    transactions = [
        TransactionItem(
            transaction_id=str(t.get("id") or t.get("uuid") or ""),
            date=str(t.get("transactionAt") or t.get("createdAt") or ""),
            amount=float(t.get("amount") or 0),
            currency=str(t.get("currency") or "USD"),
            merchant=str(t.get("merchantName") or t.get("description") or ""),
            status=str(t.get("status") or ""),
            description=str(t.get("merchantName") or t.get("description") or ""),
        )
        for t in raw_txns
    ]

    return TransactionListResponse(
        card_id=card.id,
        aifory_card_id=card.aifory_card_id,
        transactions=transactions,
    )


@router.get(
    "/cards/{card_id}/{transaction_uuid}",
    summary="Get details of a single transaction from O-Plata",
)
async def get_transaction_detail(
    card_id: str,
    transaction_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if isinstance(card_id, str) and not card_id.isdigit():
        result = await db.execute(
            select(Card).where(Card.aifory_card_id == card_id, Card.user_id == current_user.id)
        )
    else:
        result = await db.execute(
            select(Card).where(Card.id == int(card_id), Card.user_id == current_user.id)
        )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if not card.aifory_card_id:
        raise HTTPException(status_code=400, detail="Card has no external ID")
    if not card.offer_id:
        raise HTTPException(status_code=400, detail="Card has no ravanaServerId stored")

    client_id = _client_id(current_user)
    try:
        return await oplata_client.get_card_transaction_details(
            client_id=client_id,
            card_id=card.aifory_card_id,
            ravana_server_id=card.offer_id,
            transaction_id=transaction_uuid,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
