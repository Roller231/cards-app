from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    partner_order_id = Column(String(255), unique=True, nullable=True, index=True)
    card_id = Column(BigInteger, ForeignKey("cards.id"), nullable=True)
    type = Column(String(20), nullable=False)  # 'issue' or 'topup'
    amount = Column(Numeric(18, 2), nullable=False)
    fee = Column(Numeric(18, 2), default=0, nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    aifory_status_id = Column(Integer, nullable=True)
    aifory_type = Column(Integer, nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="orders")
    card = relationship("Card", back_populates="orders")
