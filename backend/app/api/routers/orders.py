from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.order import OrderResponse, OrderStatusResponse
from app.services.order_service import order_service
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get order by ID."""
    order = await order_service.get_user_order(db, current_user.id, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return OrderResponse(
        id=order.id,
        partner_order_id=order.partner_order_id,
        type=order.type,
        amount=float(order.amount),
        fee=float(order.fee),
        status=order.status,
        card_id=order.card_id,
        created_at=order.created_at,
    )


@router.get("/{order_id}/status", response_model=OrderStatusResponse)
async def get_order_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Poll order status from Aifory and update local DB.
    Use this for polling after card issuance or top-up.
    """
    order = await order_service.get_user_order(db, current_user.id, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    try:
        status_data = await order_service.update_order_status(db, order.partner_order_id)
        return OrderStatusResponse(**status_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
