import hashlib
import hmac
import json
import logging as _logging
import urllib.parse

_auth_log = _logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TelegramLoginRequest,
    TelegramWebAppRequest,
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

    if not body.password or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@router.get("/config", summary="Get public app config (fixed issuance fees and topup percents)")
async def get_config():
    return {
        "online_issue_fee_usd": settings.ONLINE_ISSUE_FEE_USD,
        "online_topup_markup_percent": settings.ONLINE_TOPUP_MARKUP_PERCENT,
        "online_plus_issue_fee_usd": settings.ONLINE_PLUS_ISSUE_FEE_USD,
        "online_plus_topup_markup_percent": settings.ONLINE_PLUS_TOPUP_MARKUP_PERCENT,
        "issue_apply_topup_markup": settings.ISSUE_APPLY_TOPUP_MARKUP,
        "online_card_validity_text": settings.ONLINE_CARD_VALIDITY_TEXT,
        "online_plus_card_validity_text": settings.ONLINE_PLUS_CARD_VALIDITY_TEXT,
        "online_operation_fee_usd": settings.ONLINE_OPERATION_FEE_USD,
        "online_plus_operation_fee_usd": settings.ONLINE_PLUS_OPERATION_FEE_USD,
    }


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
    raise HTTPException(
        status_code=403,
        detail="Use /auth/telegram-webapp with valid Telegram initData",
    )


def _verify_telegram_init_data(init_data: str) -> dict:
    """Verify Telegram WebApp initData HMAC. Returns parsed user dict."""
    bot_token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not bot_token:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_TOKEN not configured")

    try:
        params = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid initData format")

    received_hash = params.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=400, detail="Missing hash in initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        _auth_log.warning("initData HMAC mismatch | expected=%s | received=%s | dcs=%r",
                         expected_hash[:12], received_hash[:12], data_check_string[:120])
        raise HTTPException(status_code=401, detail="Invalid Telegram initData signature")

    user_json = params.get("user")
    if not user_json:
        raise HTTPException(status_code=400, detail="No user data in initData")

    try:
        return json.loads(user_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user JSON in initData")


@router.post(
    "/telegram-webapp",
    response_model=TokenResponse,
    summary="Authenticate via Telegram WebApp initData (production flow)",
)
async def telegram_webapp_auth(body: TelegramWebAppRequest, db: AsyncSession = Depends(get_db)):
    """Verifies initData HMAC, then registers or logs in the user."""
    _auth_log.info("telegram-webapp called, initData length=%d", len(body.init_data))
    tg_user = _verify_telegram_init_data(body.init_data)

    tg_id = str(tg_user.get("id", ""))
    username = tg_user.get("username") or f"tg_{tg_id}"

    if not tg_id:
        raise HTTPException(status_code=400, detail="Could not extract Telegram user ID")

    result = await db.execute(select(User).where(User.telegram_user_id == tg_id))
    user = result.scalar_one_or_none()

    if not user:
        candidate = username
        suffix = 1
        while True:
            check = await db.execute(select(User).where(User.username == candidate))
            if not check.scalar_one_or_none():
                break
            suffix += 1
            candidate = f"{username}_{suffix}"

        user = User(username=candidate, hashed_password=None, telegram_user_id=tg_id)
        db.add(user)
        await db.flush()

    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)
