"""
Gmail polling service.
Polls Gmail IMAP every 10 seconds for Apple Pay verification code emails from SUNRATE.
When found: extracts card last4 + code, finds the matching user, sends Telegram notification.
"""
import asyncio
import email as email_lib
import imaplib
import logging
import re
from typing import List, Set, Tuple

logger = logging.getLogger(__name__)

_processed_uids: Set[bytes] = set()


def _get_body_text(msg) -> str:
    """Extract plain text from an email.Message object."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body += part.get_payload(decode=True).decode("utf-8", errors="ignore")
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except Exception:
            pass
    return body


def _extract_apple_pay_code(body: str) -> Tuple[str, str]:
    """Return (last4, code) or ('', '') if not an Apple Pay code email."""
    last4_m = re.search(r"Ending in (\d{4})", body, re.IGNORECASE)
    code_m = re.search(r"\b(\d{6})\b", body)
    if last4_m and code_m:
        return last4_m.group(1), code_m.group(1)
    return "", ""


def _sync_fetch_codes(gmail_email: str, gmail_pass: str) -> List[Tuple[str, str]]:
    """Synchronous IMAP fetch — run inside executor. Returns list of (last4, code)."""
    global _processed_uids
    results: List[Tuple[str, str]] = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(gmail_email, gmail_pass)
        mail.select("INBOX")

        _, uids_data = mail.search(None, '(UNSEEN FROM "support.sunrate.com")')
        if not uids_data or not uids_data[0]:
            mail.logout()
            return results

        for uid in uids_data[0].split():
            if uid in _processed_uids:
                continue
            try:
                _, data = mail.fetch(uid, "(RFC822)")
                if not data or not data[0]:
                    continue
                msg = email_lib.message_from_bytes(data[0][1])
                subject = msg.get("Subject", "")
                body = _get_body_text(msg)
                combined = (subject + " " + body).lower()
                if "apple pay" in combined or "activate" in combined:
                    last4, code = _extract_apple_pay_code(body)
                    if last4 and code:
                        mail.store(uid, "+FLAGS", "\\Seen")
                        _processed_uids.add(uid)
                        results.append((last4, code))
                        logger.info("Gmail: Apple Pay code found last4=%s code=***%s", last4, code[-2:])
            except Exception as exc:
                logger.error("Gmail: error reading uid=%s: %s", uid, exc)

        mail.logout()
    except Exception as exc:
        logger.warning("Gmail IMAP error: %s", exc)
    return results


async def _send_apple_pay_notification(last4: str, code: str) -> None:
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.card import Card
    from app.models.user import User
    from app.models.admin_setting import AdminSetting
    from app.services.telegram_bot_service import _tg_post

    async with AsyncSessionLocal() as db:
        card_result = await db.execute(select(Card).where(Card.last4 == last4))
        card = card_result.scalars().first()
        if not card:
            logger.warning("Gmail: no card found for last4=%s", last4)
            return

        user_result = await db.execute(select(User).where(User.id == card.user_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.telegram_user_id:
            logger.warning("Gmail: no TG user for card last4=%s", last4)
            return

        s_result = await db.execute(
            select(AdminSetting).where(AdminSetting.key == "BOT_APPLE_PAY_CODE_HEADER")
        )
        s = s_result.scalar_one_or_none()
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
            logger.info("Gmail: Apple Pay code sent to user_id=%s last4=%s", user.id, last4)
        except Exception as exc:
            logger.error("Gmail: failed to send TG message: %s", exc)


async def check_gmail_once() -> None:
    """Single Gmail poll pass — called from background loop every 10 s."""
    from app.core.config import settings

    gmail_email = (settings.GMAIL_EMAIL or "").strip()
    gmail_pass = (settings.GMAIL_APP_PASSWORD or "").strip().replace(" ", "")
    if not gmail_email or not gmail_pass:
        return

    loop = asyncio.get_event_loop()
    try:
        found = await loop.run_in_executor(None, _sync_fetch_codes, gmail_email, gmail_pass)
    except Exception as exc:
        logger.warning("Gmail poll executor error: %s", exc)
        return

    for last4, code in found:
        try:
            await _send_apple_pay_notification(last4, code)
        except Exception as exc:
            logger.error("Gmail: notification error last4=%s: %s", last4, exc)
