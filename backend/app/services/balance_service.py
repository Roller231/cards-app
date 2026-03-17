import logging
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.topup import BalanceTopUpRequest
from app.models.user import User

logger = logging.getLogger(__name__)


class BalanceService:
    async def create_topup_request(
        self,
        db: AsyncSession,
        user: User,
        amount: float,
        comment: Optional[str] = None,
    ) -> BalanceTopUpRequest:
        """Create a pending balance top-up request."""
        req = BalanceTopUpRequest(
            user_id=user.id,
            amount=Decimal(str(amount)),
            status="pending",
            comment=comment,
        )
        db.add(req)
        await db.flush()
        return req

    async def confirm_topup(
        self,
        db: AsyncSession,
        user: User,
        request_id: int,
        payment_reference: Optional[str] = None,
    ) -> BalanceTopUpRequest:
        """
        Manually confirm a top-up request (admin / dev endpoint).
        Credits the user balance and marks the request as confirmed.
        """
        result = await db.execute(
            select(BalanceTopUpRequest).where(
                BalanceTopUpRequest.id == request_id,
                BalanceTopUpRequest.user_id == user.id,
            )
        )
        req = result.scalar_one_or_none()
        if not req:
            raise ValueError("Top-up request not found")
        if req.status != "pending":
            raise ValueError(f"Request is already {req.status}")

        req.status = "confirmed"
        if payment_reference:
            req.payment_reference = payment_reference

        user.balance = Decimal(str(user.balance)) + req.amount
        return req

    async def cancel_topup(
        self,
        db: AsyncSession,
        user: User,
        request_id: int,
    ) -> BalanceTopUpRequest:
        """Cancel a pending top-up request."""
        result = await db.execute(
            select(BalanceTopUpRequest).where(
                BalanceTopUpRequest.id == request_id,
                BalanceTopUpRequest.user_id == user.id,
            )
        )
        req = result.scalar_one_or_none()
        if not req:
            raise ValueError("Top-up request not found")
        if req.status != "pending":
            raise ValueError(f"Request is already {req.status}")

        req.status = "cancelled"
        return req

    async def get_user_topup_requests(
        self, db: AsyncSession, user_id: int
    ) -> List[BalanceTopUpRequest]:
        result = await db.execute(
            select(BalanceTopUpRequest)
            .where(BalanceTopUpRequest.user_id == user_id)
            .order_by(BalanceTopUpRequest.id.desc())
        )
        return list(result.scalars().all())


balance_service = BalanceService()
