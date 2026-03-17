import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.aifory_client import aifory_client
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

    async def get_order_aifory_status(self, partner_order_id: str) -> Dict[str, Any]:
        """Poll Aifory for the latest order status."""
        return await aifory_client.get_order_details(partner_order_id)

    async def refresh_order_status(
        self, db: AsyncSession, user_id: int, order_id: int
    ) -> Dict[str, Any]:
        """Fetch latest status from Aifory and update local order."""
        order = await self.get_user_order(db, user_id, order_id)
        if not order:
            raise ValueError("Order not found")

        aifory_data: Optional[Dict] = None
        if order.partner_order_id:
            try:
                aifory_data = await self.get_order_aifory_status(order.partner_order_id)
                new_status_id = (
                    aifory_data.get("statusID")
                    or aifory_data.get("statusId")
                    or aifory_data.get("status_id")
                )
                if new_status_id is not None:
                    order.aifory_status_id = int(new_status_id)
                    if new_status_id == 2:
                        order.status = "active"
                    elif new_status_id == 3:
                        order.status = "failed"
                    else:
                        order.status = str(new_status_id)
                aifory_type = aifory_data.get("type")
                if aifory_type is not None:
                    order.aifory_type = int(aifory_type)
            except Exception as exc:
                logger.warning("Aifory status fetch failed for %s: %s", order.partner_order_id, exc)

        return {
            "local_order_id": order.id,
            "partner_order_id": order.partner_order_id,
            "status": order.status,
            "aifory_status": aifory_data,
        }


order_service = OrderService()
