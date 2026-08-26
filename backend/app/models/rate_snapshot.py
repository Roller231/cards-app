from datetime import datetime

from sqlalchemy import BigInteger, Column, Date, DateTime, Float

from app.core.database import Base


class RateSnapshot(Base):
    """First observed app exchange rate (RUB per USD) for each MSK day.

    Written lazily by GET /sbp/rate; used to show the day-over-day change
    badge on the home screen.
    """
    __tablename__ = "rate_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    day = Column(Date, unique=True, nullable=False, index=True)  # MSK calendar day
    rate = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
