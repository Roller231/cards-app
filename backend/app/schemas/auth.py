from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TelegramAuthRequest(BaseModel):
    init_data: str  # Raw initData string from Telegram WebApp


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: int
    telegram_user_id: int
    balance: float
    onboarding_completed: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class OnboardingCompleteRequest(BaseModel):
    pass


class OnboardingCompleteResponse(BaseModel):
    success: bool
    message: str
