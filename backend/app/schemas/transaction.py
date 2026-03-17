from typing import Optional, List
from pydantic import BaseModel


class TransactionItem(BaseModel):
    transaction_id: Optional[str]
    date: Optional[str]
    amount: Optional[float]
    currency: Optional[str]
    merchant: Optional[str]
    status: Optional[str]
    description: Optional[str]


class TransactionListResponse(BaseModel):
    card_id: int
    aifory_card_id: Optional[str]
    transactions: List[TransactionItem]
