from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class PromoCode(Base):
    """Admin-managed promo code.

    type:
      'rate_discount'  — percent off the SBP exchange rate (balance top-ups):
                         the user pays percent_off% fewer RUB for the same USD
      'issue_discount' — discount on card issuance price: percent_off% OR a
                         fixed fixed_off_rub amount (whichever is set; if both,
                         the larger discount wins)
      'no_small_fee'   — waives the small-payment fee (210 RUB) applied to
                         top-ups below the threshold
    """
    __tablename__ = "promo_codes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False, index=True)  # stored uppercase
    type = Column(String(32), nullable=False)
    percent_off = Column(Float, nullable=True)        # e.g. 10 => -10%
    fixed_off_rub = Column(Float, nullable=True)      # e.g. 100 => -100 RUB
    card_type = Column(String(32), nullable=True)     # issue_discount only: 'Online' | 'Online+Pay' | 'Pay' | NULL=any
    max_uses = Column(Integer, nullable=False, default=0)   # 0 = unlimited
    used_count = Column(Integer, nullable=False, default=0)
    one_per_user = Column(Boolean, nullable=False, default=True)
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    comment = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    redemptions = relationship("PromoRedemption", back_populates="promo", lazy="select")


class PromoRedemption(Base):
    """One use of a promo code by a user.

    Created as 'pending' when an invoice with the code is created; becomes
    'applied' (and increments PromoCode.used_count) when the invoice is paid;
    'canceled' when the invoice expires/fails. one_per_user counts pending +
    applied so a user can't stack several open invoices with the same code.
    """
    __tablename__ = "promo_redemptions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    promo_id = Column(BigInteger, ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    invoice_id = Column(BigInteger, nullable=True, index=True)  # bb_invoices.id
    discount_rub = Column(Float, nullable=False, default=0.0)
    status = Column(String(16), nullable=False, default="pending")  # pending | applied | canceled
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    promo = relationship("PromoCode", back_populates="redemptions")
