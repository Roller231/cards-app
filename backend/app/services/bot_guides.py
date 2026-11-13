"""Editable instructions below the bot greeting. Videos are sent on demand."""
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.models.admin_setting import AdminSetting

logger = logging.getLogger(__name__)
GUIDES_KEY = "BOT_GUIDES"
MAX_VIDEO_BYTES = 50 * 1024 * 1024
UPLOADS_DIR = Path(__file__).parent.parent.parent / "static" / "uploads"
DEFAULT_GUIDES = [
    {"id": "yuan", "title": "Как оплатить юани", "enabled": True,
     "text": "<b>Как оплатить Alipay / WeChat Pay</b>\n\nОткройте ProntoPay → Alipay / WeChat Pay. Выберите сервис, укажите сумму в юанях и реквизиты получателя, затем оплатите заявку. После оплаты перевод выполнит менеджер.\n\nUSDT и внутренний баланс доступны без NeuroVision; для СБП нужна верификация.",
     "video_key": "bot_guides/yuan.mp4"},
    {"id": "services", "title": "Как оплатить сервис", "enabled": True,
     "text": "<b>Как оплачивать зарубежные сервисы</b>\n\nВыпустите карту ProntoPay, пополните её и используйте реквизиты для оплаты сервиса. Выбирайте карту с учётом поддерживаемых способов оплаты и ограничений сервиса.",
     "video_key": "bot_guides/services.mp4"},
    {"id": "card", "title": "Как выпустить карту", "enabled": True,
     "text": "<b>Как выпустить карту ProntoPay</b>\n\nНажмите «Открыть ProntoPay» → «Оформить карту», выберите доступный тип карты и способ оплаты, затем подтвердите выпуск.\n\nДля Online нужны действующие email и телефон. NeuroVision требуется при оплате по СБП; USDT и внутренний баланс доступны без него.",
     "video_key": "bot_guides/card.mp4"},
]


class BotGuide(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    title: str = Field(min_length=1, max_length=64)
    text: str = Field(default="", max_length=4096)
    enabled: bool = True
    video_key: Optional[str] = Field(default=None, pattern=r"^bot_guides/[a-z0-9_-]+\.mp4$")

    @model_validator(mode="after")
    def has_content(self):
        if not self.text and not self.video_key:
            raise ValueError("Добавьте текст или видео инструкции")
        return self


def serialize_guides(guides) -> str:
    if len(guides) > 20:
        raise ValueError("Можно добавить не более 20 инструкций")
    items = [g.model_dump() if isinstance(g, BotGuide) else BotGuide.model_validate(g).model_dump() for g in guides]
    if len({g["id"] for g in items}) != len(items):
        raise ValueError("Идентификаторы инструкций должны быть уникальными")
    value = json.dumps(items, ensure_ascii=False)
    if len(value.encode("utf-8")) > 60000:
        raise ValueError("Слишком большой общий объём инструкций. Сократите тексты.")
    return value


async def get_guides(db):
    row = (await db.execute(select(AdminSetting).where(AdminSetting.key == GUIDES_KEY))).scalar_one_or_none()
    if row is None:
        return [dict(g) for g in DEFAULT_GUIDES]
    try:
        return json.loads(serialize_guides(json.loads(row.value)))
    except (ValueError, TypeError):
        logger.error("Invalid bot instructions configuration")
        return []


def video_path(key):
    if not key or not re.fullmatch(r"bot_guides/[a-z0-9_-]+\.mp4", key):
        return None
    path = (UPLOADS_DIR / key).resolve()
    return path if path.is_relative_to(UPLOADS_DIR.resolve()) else None


def admin_guide(guide):
    path = video_path(guide.get("video_key"))
    present = bool(path and path.is_file())
    return {**guide, "has_video": present, "video_url": "/uploads/" + guide["video_key"] if present else None}


def video_cache_key(path):
    stat = path.stat()
    signature = f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"
    return "BOT_GUIDE_VIDEO_" + hashlib.sha256(signature.encode()).hexdigest()[:48]
