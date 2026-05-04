import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order

logger = logging.getLogger(__name__)


class OrderService:
    async def get_user_orders(self, db: AsyncSession, user_id: int) -> List[Order]:
        result = await db.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.id.desc())
        )
        return list(result.scalars().all())

    async def get_user_order(self, db: AsyncSession, user_id: int, order_id: int) -> Optional[Order]:
        result = await db.execute(
            select(Order).where(Order.id == order_id, Order.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def refresh_order_status(
        self, db: AsyncSession, user_id: int, order_id: int
    ) -> Dict[str, Any]:
        """Return local order status (external status refresh not available for O-Plata orders)."""
        order = await self.get_user_order(db, user_id, order_id)
        if not order:
            raise ValueError("Order not found")
        return {
            "local_order_id": order.id,
            "partner_order_id": order.partner_order_id,
            "status": order.status,
        }


order_service = OrderService()
