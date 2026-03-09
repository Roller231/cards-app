from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import (
    TelegramAuthRequest,
    AuthResponse,
    UserResponse,
    OnboardingCompleteRequest,
    OnboardingCompleteResponse,
)
from app.services.auth_service import auth_service
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/telegram", response_model=AuthResponse)
async def authenticate_telegram(
    request: TelegramAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user via Telegram WebApp initData.
    Validates signature and creates/returns user with JWT token.
    """
    user_data = auth_service.validate_telegram_init_data(request.init_data)
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram initData signature",
        )
    
    telegram_user_id = user_data.get("id")
    if not telegram_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing user ID in initData",
        )
    
    user = await auth_service.get_or_create_user(db, telegram_user_id)
    access_token = auth_service.create_access_token(user.id, telegram_user_id)
    
    return AuthResponse(
        access_token=access_token,
        user=UserResponse(
            id=user.id,
            telegram_user_id=user.telegram_user_id,
            balance=float(user.balance),
            onboarding_completed=user.onboarding_completed,
            created_at=user.created_at,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current authenticated user info."""
    return UserResponse(
        id=current_user.id,
        telegram_user_id=current_user.telegram_user_id,
        balance=float(current_user.balance),
        onboarding_completed=current_user.onboarding_completed,
        created_at=current_user.created_at,
    )


@router.post("/onboarding/complete", response_model=OnboardingCompleteResponse)
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark user onboarding as completed."""
    await auth_service.complete_onboarding(db, current_user.id)
    return OnboardingCompleteResponse(
        success=True,
        message="Onboarding completed successfully",
    )
