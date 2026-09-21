"""Profile section of the mini app: internal balance, referral program."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services import wallet_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", summary="Profile: balance, referral code/link/stats")
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    code = await wallet_service.ensure_referral_code(db, current_user)
    await db.commit()
    stats = await wallet_service.referral_stats(db, current_user.id)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "telegram_user_id": current_user.telegram_user_id,
        "balance": float(current_user.balance or 0),
        "phone": current_user.phone,
        "email": current_user.email,
        "kyc_status": current_user.kyc_status,
        "referral_code": code,
        "referral_link": wallet_service.referral_link(code),
        "referral_percent": settings.REFERRAL_PERCENT,
        "referred": bool(current_user.referrer_id),
        **stats,
    }


@router.get("/balance/history", summary="Internal balance ledger (newest first)")
async def get_balance_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = await wallet_service.history(db, current_user.id, limit=limit, offset=offset)
    return {"items": items, "balance": float(current_user.balance or 0)}
