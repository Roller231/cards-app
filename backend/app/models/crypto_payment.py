import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class CryptoPayment(Base):
    __tablename__ = "crypto_payments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    address = Column(String(255), nullable=False, index=True)
    network = Column(String(20), default="TRX", nullable=False)
    amount_usd = Column(Numeric(18, 2), nullable=False)   # base card amount (goes to Aifory)
    total_usdt = Column(Numeric(18, 4), nullable=False)   # what user must pay (amount + fee)
    offer_id = Column(String(255), nullable=False)
    type = Column(String(10), default="issue", nullable=False)  # issue | topup
    card_aifory_id = Column(String(255), nullable=True)          # target card for topup
    status = Column(String(20), default="pending", nullable=False, index=True)
    # pending | completed | failed | expired
    tx_id = Column(String(255), nullable=True)           # ABCEX transaction ID on match
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="crypto_payments")
    order = relationship("Order", foreign_keys=[order_id])
