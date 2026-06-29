from sqlalchemy import BigInteger, Boolean, Column, Numeric, String, Text
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

    # Contact info (collected before KYC)
    email = Column(String(255), nullable=True)
    phone = Column(String(32), nullable=True)
    gender = Column(String(8), nullable=True)  # 'MALE' | 'FEMALE'

    # KYC status: None | 'pending' | 'success' | 'failed'
    kyc_status = Column(String(16), nullable=True)
    # Passport data extracted by NeuroVision (stored as JSON string)
    kyc_first_name = Column(String(100), nullable=True)
    kyc_last_name = Column(String(100), nullable=True)
    kyc_patronymic = Column(String(100), nullable=True)
    kyc_birth_date = Column(String(20), nullable=True)   # DD.MM.YYYY
    kyc_passport = Column(String(20), nullable=True)     # series+number, no spaces
    kyc_passport_issue_date = Column(String(20), nullable=True)  # DD.MM.YYYY
    kyc_session_id = Column(String(100), nullable=True)  # NeuroVision session ID

    cards = relationship("Card", back_populates="user", lazy="select")
    orders = relationship("Order", back_populates="user", lazy="select")
    topup_requests = relationship("BalanceTopUpRequest", back_populates="user", lazy="select")
