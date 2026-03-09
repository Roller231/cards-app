from pydantic import BaseModel
from typing import Optional, List


class TransactionResponse(BaseModel):
    transaction_id: str
    type: int  # 1=Deposit, 2=Payment, 3=Fee
    amount: str
    status_id: int  # 1=Pending, 2=Success, 3=Failed
    created_at: int


class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]


class TransactionDetailResponse(BaseModel):
    transaction_id: str
    type: int
    status_id: int
    card_id: str
    amount: str
    currency_id: int
    created_at: int
    merchant: Optional[str] = None
    failure_reason: Optional[str] = None
