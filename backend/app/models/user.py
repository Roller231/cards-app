from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Numeric
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    partner_client_id = Column(String(255), nullable=True)
    balance = Column(Numeric(18, 2), default=0.00, nullable=False)
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
