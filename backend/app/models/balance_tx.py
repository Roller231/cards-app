from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Numeric, String

from app.core.database import Base


class BalanceTransaction(Base):
    """Ledger of the user's internal USD balance (users.balance).

    Every change of users.balance goes through wallet_service and leaves one
    row here, so the balance is always explainable:

    type:
      'deposit'      — SBP payment credited to the balance (invoice ref)
      'card_issue'   — card issued and paid from the balance (order ref)
      'card_topup'   — card top-up paid from the balance (order ref)
      'refund'       — a balance-paid operation failed, money returned
      'referral'     — referral reward (ref_user_id = the referred buyer)
      'admin_adjust' — manual change from the admin panel / migrations
    amount is signed: positive = credit, negative = debit.
    """
    __tablename__ = "balance_transactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(24), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    balance_after = Column(Numeric(18, 2), nullable=False)
    description = Column(String(255), nullable=True)
    ref_invoice_id = Column(BigInteger, nullable=True, index=True)   # bb_invoices.id
    ref_order_id = Column(BigInteger, nullable=True, index=True)     # orders.id
    ref_user_id = Column(BigInteger, nullable=True, index=True)      # referral: the buyer
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
