from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TelegramLoginRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    summary="Register a new local user (no Telegram required – for dev/Swagger testing)",
)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password) if body.password else None,
        telegram_user_id=body.telegram_user_id,
    )
    db.add(user)
    await db.flush()

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse, summary="Login and get JWT token")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Passwordless-friendly login for dev / mini app: if no password provided,
    # allow login as long as the user exists and is active.
    if body.password:
        if not user.hashed_password or not verify_password(body.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse, summary="Get current user info")
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        telegram_user_id=current_user.telegram_user_id,
        balance=float(current_user.balance),
        is_active=current_user.is_active,
    )


@router.post(
    "/telegram-login",
    response_model=TokenResponse,
    summary="Passwordless auth: login or create user by Telegram ID",
)
async def telegram_login(body: TelegramLoginRequest, db: AsyncSession = Depends(get_db)):
    # Try to find by telegram_user_id first
    result = await db.execute(select(User).where(User.telegram_user_id == body.telegram_user_id))
    user = result.scalar_one_or_none()

    if not user:
        # Ensure a unique username
        base_username = body.username or f"tg_{body.telegram_user_id}"
        candidate = base_username
        suffix = 1
        while True:
            check = await db.execute(select(User).where(User.username == candidate))
            if not check.scalar_one_or_none():
                break
            suffix += 1
            candidate = f"{base_username}_{suffix}"

        user = User(
            username=candidate,
            hashed_password=None,
            telegram_user_id=body.telegram_user_id,
        )
        db.add(user)
        await db.flush()

    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)
