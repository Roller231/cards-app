from typing import Optional
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    telegram_user_id: Optional[str] = None
    password: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: Optional[str] = None


class TelegramLoginRequest(BaseModel):
    telegram_user_id: str
    username: Optional[str] = None


class TelegramWebAppRequest(BaseModel):
    init_data: str  # Raw Telegram.WebApp.initData string


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    telegram_user_id: Optional[str]
    balance: float
    is_active: bool

    class Config:
        from_attributes = True
