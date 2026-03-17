from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.order import OrderResponse, OrderStatusResponse
from app.services.order_service import order_service

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=List[OrderResponse], summary="List all orders for current user")
async def list_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    orders = await order_service.get_user_orders(db, current_user.id)
    return [
        OrderResponse(
            id=o.id,
            partner_order_id=o.partner_order_id,
            card_id=o.card_id,
            type=o.type,
            amount=float(o.amount),
            fee=float(o.fee),
            status=o.status,
            description=o.description,
        )
        for o in orders
    ]


@router.get("/{order_id}", response_model=OrderResponse, summary="Get a specific order by local ID")
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = await order_service.get_user_order(db, current_user.id, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse(
        id=order.id,
        partner_order_id=order.partner_order_id,
        card_id=order.card_id,
        type=order.type,
        amount=float(order.amount),
        fee=float(order.fee),
        status=order.status,
        description=order.description,
    )


@router.post(
    "/{order_id}/sync",
    response_model=OrderStatusResponse,
    summary="Pull latest order status from Aifory and update local record",
)
async def sync_order_status(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await order_service.refresh_order_status(db, current_user.id, order_id)
        return OrderStatusResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
