from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, String

from app.core.database import Base


class PendingAutoTopup(Base):
    """Persistent queue for auto top-up requests after card issuance.

    Survives backend restarts: a background worker picks up rows with
    status='pending' and attempts < max_attempts, runs the topup flow, and
    updates status to 'completed' / 'failed' or bumps attempts on retryable error.
    """

    __tablename__ = "pending_auto_topups"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    card_id = Column(BigInteger, ForeignKey("cards.id"), nullable=False, index=True)
    # Snapshot of provider identifiers so we can fire topup even if the local
    # card row is partially synced. Both filled at insert time.
    aifory_card_id = Column(String(255), nullable=False, index=True)
    ravana_server_id = Column(String(255), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=10, nullable=False)
    # pending | in_progress | completed | failed
    status = Column(String(20), default="pending", nullable=False, index=True)
    last_error = Column(String(500), nullable=True)
    notify_on_success = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
