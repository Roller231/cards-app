from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Numeric, String, event
from sqlalchemy.orm import relationship

from app.core.database import Base


class Card(Base):
    __tablename__ = "cards"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    aifory_card_id = Column(String(255), unique=True, nullable=True, index=True)
    category = Column(Integer, nullable=True)
    card_status = Column(Integer, nullable=True)
    expired_at = Column(String(10), nullable=True)
    last4 = Column(String(4), nullable=True)
    holder_name = Column(String(255), nullable=True)
    currency = Column(String(10), nullable=True)
    currency_id = Column(Integer, nullable=True)
    payment_system_id = Column(Integer, nullable=True)
    status = Column(String(50), nullable=True)
    balance = Column(Numeric(18, 2), default=0, nullable=False)
    offer_id = Column(String(255), nullable=True)
    last_notified_transaction_id = Column(String(255), nullable=True)
    # "Данные карты" sheet: random name + address in the card's country, set once on insert
    # (app.services.billing_identity); NULL on cards created before that.
    billing_name = Column(String(100), nullable=True)
    billing_address = Column(String(255), nullable=True)
    billing_postal = Column(String(10), nullable=True)
    billing_country = Column(String(50), nullable=True)

    user = relationship("User", back_populates="cards")
    orders = relationship("Order", back_populates="card", lazy="select")


@event.listens_for(Card, "before_insert")
def _set_billing_identity(mapper, connection, target):
    if not target.billing_address:
        from app.services import billing_identity
        for key, value in billing_identity.generate(target.offer_id).items():
            setattr(target, key, value)
