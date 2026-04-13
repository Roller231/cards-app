"""
Gmail polling service — Gmail API (OAuth2).
Polls every 10 seconds for Apple Pay verification code emails from SUNRATE.
For each card (by last4) sends ONLY the newest code found.
"""
import base64
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ── token cache ───────────────────────────────────────────────────────────
_cached_access_token: Optional[str] = None
_token_expires_at: float = 0


async def _get_refresh_token() -> str:
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.admin_setting import AdminSetting

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(AdminSetting).where(AdminSetting.key == "GMAIL_REFRESH_TOKEN")
        )).scalar_one_or_none()
        return row.value if row else ""


async def _get_access_token() -> Optional[str]:
    global _cached_access_token, _token_expires_at

    if _cached_access_token and time.time() < _token_expires_at - 60:
        return _cached_access_token

    from app.core.config import settings
    refresh_token = await _get_refresh_token()
    if not refresh_token or not settings.GMAIL_CLIENT_ID or not settings.GMAIL_CLIENT_SECRET:
        return None

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
    if resp.status_code != 200:
        logger.warning("Gmail token refresh failed: %s", resp.text)
        _cached_access_token = None
        return None

    data = resp.json()
    _cached_access_token = data["access_token"]
    _token_expires_at = time.time() + data.get("expires_in", 3600)
    return _cached_access_token


# ── Gmail API helpers ─────────────────────────────────────────────────────
_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


async def _gmail_get(path: str, params: dict = None) -> Optional[dict]:
    token = await _get_access_token()
    if not token:
        return None
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{_BASE}/{path}", params=params,
                        headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        logger.warning("Gmail GET %s → %s %s", path, r.status_code, r.text[:200])
        return None
    return r.json()


async def _gmail_post(path: str, json_body: dict = None) -> Optional[dict]:
    token = await _get_access_token()
    if not token:
        return None
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{_BASE}/{path}", json=json_body,
                         headers={"Authorization": f"Bearer {token}"})
    if r.status_code not in (200, 204):
        logger.warning("Gmail POST %s → %s %s", path, r.status_code, r.text[:200])
        return None
    return r.json() if r.text else {}


# ── parsing ───────────────────────────────────────────────────────────────
def _decode_body(payload: dict) -> str:
    body = ""
    mime = payload.get("mimeType", "")
    if mime in ("text/plain", "text/html") and payload.get("body", {}).get("data"):
        decoded = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
        if mime == "text/html":
            decoded = re.sub(r"<[^>]+>", " ", decoded)
        body += decoded
    for part in payload.get("parts", []):
        body += _decode_body(part)
    return body


def _extract_apple_pay_code(text: str) -> Tuple[str, str]:
    """Return (last4, code) or ('', '') if not an Apple Pay code email."""
    last4_m = (
        re.search(r"ending\s+(?:in|with)\s*[:#-]?\s*(\d{4})", text, re.IGNORECASE)
        or re.search(r"card\D{0,25}(\d{4})", text, re.IGNORECASE)
        or re.search(r"(?:\*|•|x){2,}\s*(\d{4})", text, re.IGNORECASE)
    )
    code_m = (
        re.search(r"(?:code|verification|one[-\s]?time|otp)\D{0,20}(\d{6})", text, re.IGNORECASE)
        or re.search(r"\b(\d{6})\b", text)
    )
    if last4_m and code_m:
        return last4_m.group(1), code_m.group(1)
    return "", ""


def _mime_tree(payload: dict, depth: int = 0) -> List[str]:
    mime = payload.get("mimeType", "")
    out = [f"{'  ' * depth}- {mime}"]
    for part in payload.get("parts", []) or []:
        out.extend(_mime_tree(part, depth + 1))
    return out


# ── notification ──────────────────────────────────────────────────────────
async def _send_apple_pay_notification(last4: str, code: str) -> None:
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.card import Card
    from app.models.user import User
    from app.models.admin_setting import AdminSetting
    from app.services.telegram_bot_service import _tg_post

    async with AsyncSessionLocal() as db:
        card = (await db.execute(select(Card).where(Card.last4 == last4))).scalars().first()
        if not card:
            logger.warning("Gmail: no card for last4=%s", last4)
            return

        user = (await db.execute(select(User).where(User.id == card.user_id))).scalar_one_or_none()
        if not user or not user.telegram_user_id:
            logger.warning("Gmail: no TG user for last4=%s", last4)
            return

        s = (await db.execute(
            select(AdminSetting).where(AdminSetting.key == "BOT_APPLE_PAY_CODE_HEADER")
        )).scalar_one_or_none()
        header = s.value if s else "🍎 Код активации Apple Pay"

        spaced_code = "  ".join(list(code))
        text = (
            f"<b>{header}</b>\n\n"
            f"💳 Карта: <b>•••• {last4}</b>\n\n"
            f"🔑 Ваш одноразовый код:\n\n"
            f"<code>    {spaced_code}    </code>\n\n"
            f"⏱ Действителен <b>5 минут</b>"
        )
        try:
            await _tg_post("sendMessage", {
                "chat_id": user.telegram_user_id,
                "text": text,
                "parse_mode": "HTML",
            })
            logger.info("Gmail: Apple Pay code → user_id=%s last4=%s", user.id, last4)
        except Exception as exc:
            logger.error("Gmail: TG send failed: %s", exc)


# ── main poll ─────────────────────────────────────────────────────────────
async def check_gmail_once() -> None:
    """Single Gmail API poll pass — called every 10 s from background loop."""
    from app.core.config import settings

    if not settings.GMAIL_CLIENT_ID or not settings.GMAIL_CLIENT_SECRET:
        return
    if not await _get_access_token():
        return  # no refresh token stored yet

    # Fetch unread messages from SUNRATE (Gmail returns newest first)
    result = await _gmail_get("messages", {
        "q": "from:support.sunrate.com is:unread",
        "maxResults": 20,
    })
    if not result or not result.get("messages"):
        return

    # For each card last4 keep ONLY the newest code (first match = newest)
    codes_by_last4: Dict[str, str] = {}
    ids_to_mark: List[str] = []

    for msg_ref in result["messages"]:
        msg_id = msg_ref["id"]
        msg = await _gmail_get(f"messages/{msg_id}", {"format": "full"})
        if not msg:
            continue

        payload = msg.get("payload", {})
        hdrs = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        subject = hdrs.get("subject", "")
        body = _decode_body(payload)
        full_text = f"{subject}\n{body}"
        combined = full_text.lower()

        if "apple pay" not in combined and "activate" not in combined:
            continue

        last4, code = _extract_apple_pay_code(full_text)
        if not last4 or not code:
            logger.info("Gmail API: parse miss for msg_id=%s subject=%r", msg_id, subject[:120])
            logger.info("Gmail API: snippet msg_id=%s snippet=%r", msg_id, (msg.get("snippet") or "")[:300])
            logger.info("Gmail API: mime tree msg_id=%s\n%s", msg_id, "\n".join(_mime_tree(payload)))
            logger.info("Gmail API: full_text preview msg_id=%s text=%r", msg_id, re.sub(r"\s+", " ", full_text)[:800])
            continue

        logger.info("Gmail API: parsed msg_id=%s last4=%s code=***%s", msg_id, last4, code[-2:])

        ids_to_mark.append(msg_id)
        if last4 not in codes_by_last4:
            codes_by_last4[last4] = code
            logger.info("Gmail API: newest code for last4=%s code=***%s", last4, code[-2:])

    # Mark ALL matching messages as read (old + new)
    if ids_to_mark:
        await _gmail_post("messages/batchModify", {
            "ids": ids_to_mark,
            "removeLabelIds": ["UNREAD"],
        })

    # Send only the newest code per card
    for last4, code in codes_by_last4.items():
        try:
            await _send_apple_pay_notification(last4, code)
        except Exception as exc:
            logger.error("Gmail: notification error last4=%s: %s", last4, exc)
