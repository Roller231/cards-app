"""Durable Cryptoway quotes, invoices and exactly-once fulfillment claims."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from app.core.database import Base


class CryptoPayment(Base):
    __tablename__ = "cryptoway_payments"
    __table_args__ = (UniqueConstraint("user_id", "request_id", name="uq_cryptoway_user_request"),)

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    request_id = Column(String(80), nullable=False)
    external_id = Column(String(80), nullable=False, unique=True)
    provider_invoice_id = Column(String(36), nullable=True, unique=True)
    purpose = Column(String(24), nullable=False)  # card_issue | card_topup | china_payment
    service_request_id = Column(BigInteger, ForeignKey("service_requests.id"), nullable=True, index=True)
    amount_cny = Column(Numeric(18, 2), nullable=True)
    cny_per_usdt = Column(Numeric(18, 6), nullable=True)
    offer_id = Column(String(255), nullable=True)
    card_id = Column(BigInteger, ForeignKey("cards.id"), nullable=True)
    amount_usd = Column(Numeric(18, 2), nullable=False)
    fee_percent = Column(Numeric(9, 4), nullable=False, default=0)
    charge_usdt = Column(Numeric(18, 8), nullable=False)
    price_rub = Column(Numeric(18, 2), nullable=True)
    base_rate = Column(Numeric(18, 6), nullable=True)
    discount_percent = Column(Numeric(9, 4), nullable=False, default=0)
    symbol_id = Column(String(32), nullable=True)
    network_name = Column(String(64), nullable=True)
    wallet_address = Column(String(255), nullable=True)
    pay_url = Column(String(512), nullable=True)
    status = Column(String(24), nullable=False, default="quoted", index=True)
    fulfillment_status = Column(String(24), nullable=False, default="not_started")
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=True, unique=True)
    refund_credited = Column(Boolean, nullable=False, default=False)
    paid_notified = Column(Boolean, nullable=False, default=False)
    review_notified = Column(Boolean, nullable=False, default=False)
    received_usdt = Column(Numeric(24, 8), nullable=False, default=0)
    provider_payload = Column(Text, nullable=True)
    last_error = Column(String(500), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    last_checked_at = Column(DateTime, nullable=True, index=True)
    creation_started_at = Column(DateTime, nullable=True)
    fulfillment_started_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
