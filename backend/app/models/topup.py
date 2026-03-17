from sqlalchemy import BigInteger, Column, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class BalanceTopUpRequest(Base):
    __tablename__ = "balance_topup_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending / confirmed / cancelled
    payment_reference = Column(String(255), nullable=True)
    comment = Column(String(500), nullable=True)

    user = relationship("User", back_populates="topup_requests")
