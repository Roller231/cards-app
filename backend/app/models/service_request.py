from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Numeric, String, Text

from app.core.database import Base


class ServiceRequest(Base):
    """A user's request for a payment service (Alipay / WeChat Pay / other).

    The app only collects the request; managers get it in Telegram and in the
    admin panel and handle the payment manually.

    status: new | in_progress | done | rejected
    """
    __tablename__ = "service_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    service = Column(String(32), nullable=False)          # alipay | wechat | other
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(8), nullable=False)          # CNY | USD | EUR
    note = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="new", index=True)
    admin_comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
