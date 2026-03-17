from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.topup import TopUpConfirmRequest, TopUpRequestCreate, TopUpRequestResponse
from app.services.balance_service import balance_service

router = APIRouter(prefix="/balance", tags=["balance"])


@router.get(
    "/topup-requests",
    response_model=List[TopUpRequestResponse],
    summary="List all balance top-up requests for current user",
)
async def list_topup_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reqs = await balance_service.get_user_topup_requests(db, current_user.id)
    return [
        TopUpRequestResponse(
            id=r.id,
            user_id=r.user_id,
            amount=float(r.amount),
            status=r.status,
            payment_reference=r.payment_reference,
            comment=r.comment,
        )
        for r in reqs
    ]


@router.post(
    "/topup-requests",
    response_model=TopUpRequestResponse,
    summary="Create a balance top-up request (payment gateway will be wired later)",
)
async def create_topup_request(
    body: TopUpRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    req = await balance_service.create_topup_request(db, current_user, body.amount, body.comment)
    return TopUpRequestResponse(
        id=req.id,
        user_id=req.user_id,
        amount=float(req.amount),
        status=req.status,
        payment_reference=req.payment_reference,
        comment=req.comment,
    )


@router.post(
    "/topup-requests/{request_id}/confirm",
    response_model=TopUpRequestResponse,
    summary="[DEV] Manually confirm a top-up request and credit user balance",
)
async def confirm_topup(
    request_id: int,
    body: TopUpConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        req = await balance_service.confirm_topup(
            db, current_user, request_id, body.payment_reference
        )
        return TopUpRequestResponse(
            id=req.id,
            user_id=req.user_id,
            amount=float(req.amount),
            status=req.status,
            payment_reference=req.payment_reference,
            comment=req.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/topup-requests/{request_id}/cancel",
    response_model=TopUpRequestResponse,
    summary="Cancel a pending top-up request",
)
async def cancel_topup(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        req = await balance_service.cancel_topup(db, current_user, request_id)
        return TopUpRequestResponse(
            id=req.id,
            user_id=req.user_id,
            amount=float(req.amount),
            status=req.status,
            payment_reference=req.payment_reference,
            comment=req.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
