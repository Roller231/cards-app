from sqlalchemy import BigInteger, Column, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class BbInvoice(Base):
    """Tracks a Bitbanker SBP invoice created for a user.

    purpose: 'balance_topup' | 'card_issue'
    status mirrors Bitbanker SBP statuses: initiated, pending, captured, authorized,
                                           declined, failed, cancelled, expired, unknown
    """
    __tablename__ = "bb_invoices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    bb_invoice_id = Column(String(128), nullable=True, index=True)   # id returned by Bitbanker
    idempotency_key = Column(String(128), unique=True, nullable=False)
    external_client_ref = Column(String(128), nullable=False, index=True)  # our user id in BB
    purpose = Column(String(32), nullable=False, default="balance_topup")  # balance_topup | card_issue
    offer_id = Column(String(256), nullable=True)                     # card offer_id for card_issue purpose
    card_id = Column(String(256), nullable=True)                      # local card UUID for balance_topup purpose
    amount_rub = Column(Numeric(18, 2), nullable=False)               # RUB amount paid
    amount_usd_requested = Column(Numeric(18, 6), nullable=True)      # exact USD amount user wants on card
    amount_usd = Column(Numeric(18, 6), nullable=True)                # USD credited to user (after conversion)
    status = Column(String(32), nullable=False, default="initiated")
    payment_url = Column(String(512), nullable=True)
    qr_base64 = Column(Text, nullable=True)                           # sbp_qr base64 image
    raw_response = Column(Text, nullable=True)                        # last raw JSON from BB

    user = relationship("User", foreign_keys=[user_id])
