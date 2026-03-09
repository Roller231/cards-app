from sqlalchemy import Column, BigInteger, String, Integer, DateTime, ForeignKey, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    partner_order_id = Column(String(255), unique=True, nullable=False, index=True)
    card_id = Column(BigInteger, ForeignKey("cards.id"), nullable=True)
    type = Column(String(20), nullable=False)  # 'issue' or 'topup'
    amount = Column(Numeric(18, 2), nullable=False)
    fee = Column(Numeric(18, 2), default=0.00, nullable=False)
    status = Column(Integer, default=1, nullable=False)  # 1=Pending, 2=Success, 3=Failed, 5=Canceled
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    user = relationship("User", backref="orders")
    card = relationship("Card", backref="orders")
