from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Numeric, String, Text

from app.core.database import Base


class ServiceRequest(Base):
    """An Alipay / WeChat Pay payment: the user pays rubles by SBP, the team
    sends yuan to the recipient.

    status: awaiting_payment | paid | in_progress | done | rejected
            ('new' — legacy, before the payment step existed)
    recipient_type: phone (Alipay: phone + Latin name) | qr (receiving QR image)
    """
    __tablename__ = "service_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    service = Column(String(32), nullable=False)          # alipay | wechat
    amount = Column(Numeric(18, 2), nullable=False)       # in `currency` (CNY)
    currency = Column(String(8), nullable=False)
    amount_rub = Column(Numeric(18, 2), nullable=True)    # SBP amount the user pays
    rate_rub = Column(Numeric(18, 4), nullable=True)      # RUB per 1 CNY used
    recipient_type = Column(String(8), nullable=True)
    recipient_phone = Column(String(32), nullable=True)
    recipient_name = Column(String(100), nullable=True)
    qr_path = Column(String(255), nullable=True)          # file name in static/private/service_qr
    note = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="awaiting_payment", index=True)
    admin_comment = Column(Text, nullable=True)
    invoice_id = Column(BigInteger, nullable=True, index=True)   # bb_invoices.id that paid it
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
