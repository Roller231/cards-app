from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from app.core.database import Base


class BroadcastPreset(Base):
    """Saved broadcast template: text + markup + buttons + optional image."""
    __tablename__ = "broadcast_presets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    text = Column(Text, nullable=False, default="")
    parse_mode = Column(String(16), nullable=False, default="HTML")
    buttons = Column(Text, nullable=False, default="[]")   # JSON [{text,url}]
    image_key = Column(String(128), nullable=True)          # file in static/uploads (kept, not temp)
    segment = Column(String(32), nullable=False, default="all")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ScheduledBroadcast(Base):
    """Broadcast queued for a specific time; a worker sends due ones."""
    __tablename__ = "scheduled_broadcasts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    text = Column(Text, nullable=False, default="")
    parse_mode = Column(String(16), nullable=False, default="HTML")
    buttons = Column(Text, nullable=False, default="[]")
    image_key = Column(String(128), nullable=True)
    segment = Column(String(32), nullable=False, default="all")
    scheduled_at = Column(DateTime, nullable=False, index=True)  # UTC
    status = Column(String(16), nullable=False, default="scheduled")  # scheduled | sending | done | canceled | failed
    sent = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
