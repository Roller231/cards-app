"""
Telegram Bot service.
  - Handles /start command → sends customizable welcome message (photo + HTML text + inline buttons)
  - Provides broadcast_message() for admin broadcasts
  - poll_once() is called in a background loop from main.py
"""
import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_setting import AdminSetting
from app.models.user import User

logger = logging.getLogger(__name__)

UPLOADS_DIR = Path(__file__).parent.parent.parent / "static" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

WELCOME_IMAGE_PATH = UPLOADS_DIR / "bot_welcome.jpg"

_last_update_id: int = 0


# ─── low-level Telegram API wrappers ───────────────────────────────────────

def _token() -> str:
    from app.core.config import settings
    tok = settings.TELEGRAM_BOT_TOKEN
    if not tok:
        raise ValueError("TELEGRAM_BOT_TOKEN not configured")
    return tok


async def _tg_post(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{_token()}/{method}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload)
    return r.json()


async def _tg_post_file(method: str, data: dict, file_bytes: bytes, filename: str) -> dict:
    """Send a request with a file via multipart (for photo uploads)."""
    url = f"https://api.telegram.org/bot{_token()}/{method}"
    files = {"photo": (filename, file_bytes, "image/jpeg")}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, data=data, files=files)
    return r.json()


# ─── helpers ───────────────────────────────────────────────────────────────

async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    res = await db.execute(select(AdminSetting).where(AdminSetting.key == key))
    s = res.scalar_one_or_none()
    return s.value if s else default


async def _save_setting(db: AsyncSession, key: str, value: str, desc: str = "") -> None:
    res = await db.execute(select(AdminSetting).where(AdminSetting.key == key))
    existing = res.scalar_one_or_none()
    if existing:
        existing.value = value
    else:
        db.add(AdminSetting(key=key, value=value, description=desc))
    try:
        await db.commit()
    except Exception:
        await db.rollback()


def _build_markup(buttons: List[Dict]) -> Optional[dict]:
    if not buttons:
        return None
    return {"inline_keyboard": [[{"text": b["text"], "url": b["url"]}] for b in buttons]}


async def _ensure_user_from_start(db: AsyncSession, message: dict, chat_id: int) -> User:
    """Create (or return existing) local user by Telegram ID when /start is received."""
    tg_id = str(chat_id)
    result = await db.execute(select(User).where(User.telegram_user_id == tg_id))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    from_user = message.get("from", {})
    username_hint = (from_user.get("username") or "").strip()
    first_name = (from_user.get("first_name") or "").strip().lower().replace(" ", "_")
    base_username = username_hint or (f"tg_{first_name}" if first_name else f"tg_{tg_id}")

    candidate = base_username
    suffix = 1
    while True:
        check = await db.execute(select(User).where(User.username == candidate))
        if not check.scalar_one_or_none():
            break
        suffix += 1
        candidate = f"{base_username}_{suffix}"

    user = User(username=candidate, hashed_password=None, telegram_user_id=tg_id)
    db.add(user)
    await db.flush()
    await db.commit()
    await db.refresh(user)
    logger.info("Created local user from /start: id=%s tg_id=%s username=%s", user.id, tg_id, candidate)
    return user


# ─── send welcome ──────────────────────────────────────────────────────────

async def send_welcome(chat_id: int, db: AsyncSession) -> None:
    """Send configured welcome message to a chat_id."""
    text = await _get_setting(db, "BOT_WELCOME_TEXT", "Добро пожаловать!")
    parse_mode = await _get_setting(db, "BOT_WELCOME_PARSE_MODE", "HTML")
    buttons_json = await _get_setting(db, "BOT_WELCOME_BUTTONS", "[]")
    cached_fid = await _get_setting(db, "BOT_WELCOME_FILE_ID", "")

    try:
        buttons = json.loads(buttons_json)
    except Exception:
        buttons = []

    markup = _build_markup(buttons)

    if WELCOME_IMAGE_PATH.exists():
        base_data: dict = {"chat_id": str(chat_id), "caption": text, "parse_mode": parse_mode}
        if markup:
            base_data["reply_markup"] = json.dumps(markup)

        if cached_fid:
            # Reuse previously uploaded file_id — no re-upload needed
            payload: dict = {"chat_id": chat_id, "photo": cached_fid, "caption": text, "parse_mode": parse_mode}
            if markup:
                payload["reply_markup"] = markup
            r = await _tg_post("sendPhoto", payload)
        else:
            file_bytes = WELCOME_IMAGE_PATH.read_bytes()
            r = await _tg_post_file("sendPhoto", base_data, file_bytes, WELCOME_IMAGE_PATH.name)
            # Cache file_id for future sends
            if r.get("ok"):
                photos = r.get("result", {}).get("photo", [])
                if photos:
                    await _save_setting(db, "BOT_WELCOME_FILE_ID", photos[-1]["file_id"],
                                        "Telegram file_id (кеш, не менять вручную)")
    else:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if markup:
            payload["reply_markup"] = markup
        await _tg_post("sendMessage", payload)


# ─── broadcast ─────────────────────────────────────────────────────────────

async def broadcast_message(
    db: AsyncSession,
    text: str,
    parse_mode: str = "HTML",
    buttons: Optional[List[Dict]] = None,
    image_path: Optional[Path] = None,
) -> dict:
    """Send a message to all active users who have a Telegram ID."""
    res = await db.execute(
        select(User).where(User.telegram_user_id.isnot(None), User.is_active == True)
    )
    users = res.scalars().all()

    markup = _build_markup(buttons or [])
    image_bytes = image_path.read_bytes() if (image_path and image_path.exists()) else None
    cached_fid: Optional[str] = None
    sent = failed = 0

    for user in users:
        if not user.telegram_user_id:
            continue
        try:
            if image_bytes:
                data = {"chat_id": str(user.telegram_user_id), "caption": text, "parse_mode": parse_mode}
                if markup:
                    data["reply_markup"] = json.dumps(markup)

                if cached_fid:
                    payload = {"chat_id": user.telegram_user_id, "photo": cached_fid,
                               "caption": text, "parse_mode": parse_mode}
                    if markup:
                        payload["reply_markup"] = markup
                    r = await _tg_post("sendPhoto", payload)
                else:
                    fn = image_path.name if image_path else "image.jpg"
                    r = await _tg_post_file("sendPhoto", data, image_bytes, fn)
                    if r.get("ok"):
                        photos = r.get("result", {}).get("photo", [])
                        if photos:
                            cached_fid = photos[-1]["file_id"]
            else:
                payload = {"chat_id": user.telegram_user_id, "text": text, "parse_mode": parse_mode}
                if markup:
                    payload["reply_markup"] = markup
                r = await _tg_post("sendMessage", payload)

            if r.get("ok"):
                sent += 1
            else:
                failed += 1
                logger.warning("Broadcast failed for %s: %s", user.telegram_user_id, r.get("description"))
        except Exception as exc:
            logger.error("Broadcast error for user %d: %s", user.id, exc)
            failed += 1

        await asyncio.sleep(0.05)  # Telegram rate limit ~20 msg/sec

    return {"sent": sent, "failed": failed, "total": len(users)}


# ─── polling loop ──────────────────────────────────────────────────────────

async def poll_once() -> None:
    """Long-poll Telegram for new updates; handle /start command."""
    global _last_update_id
    try:
        tok = _token()
    except ValueError:
        return  # Bot not configured

    url = f"https://api.telegram.org/bot{tok}/getUpdates"
    params = {"offset": _last_update_id + 1, "timeout": 25, "allowed_updates": ["message"]}

    try:
        async with httpx.AsyncClient(timeout=35) as client:
            r = await client.get(url, params=params)
        data = r.json()
    except Exception as exc:
        logger.warning("Bot getUpdates error: %s", exc)
        return

    if not data.get("ok"):
        logger.warning("getUpdates not ok: %s", data)
        return

    from app.core.database import AsyncSessionLocal

    for update in data.get("result", []):
        _last_update_id = update["update_id"]
        msg = update.get("message", {})
        text = msg.get("text", "")
        chat_id = msg.get("chat", {}).get("id")

        if chat_id and text.startswith("/start"):
            try:
                async with AsyncSessionLocal() as db:
                    await _ensure_user_from_start(db, msg, chat_id)
                    await send_welcome(chat_id, db)
            except Exception as exc:
                logger.exception("Error handling /start for chat %s", chat_id)
