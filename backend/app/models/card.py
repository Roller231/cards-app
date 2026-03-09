from sqlalchemy import Column, BigInteger, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Card(Base):
    __tablename__ = "cards"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    partner_card_id = Column(String(255), unique=True, nullable=False, index=True)
    last4 = Column(String(4), nullable=False)
    category = Column(Integer, nullable=True)  # 1=Advertisement, 2=Purchases, 3=ApplePay
    status = Column(Integer, default=1, nullable=False)  # 1=Pending, 2=Success, 5=Canceled
    expired_at = Column(String(10), nullable=True)  # MM/YY format from Aifory
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    user = relationship("User", backref="cards")
