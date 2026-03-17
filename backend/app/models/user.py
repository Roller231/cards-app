from sqlalchemy import BigInteger, Boolean, Column, Numeric, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)
    telegram_user_id = Column(String(64), unique=True, nullable=True, index=True)
    balance = Column(Numeric(18, 2), default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    cards = relationship("Card", back_populates="user", lazy="select")
    orders = relationship("Order", back_populates="user", lazy="select")
    topup_requests = relationship("BalanceTopUpRequest", back_populates="user", lazy="select")
