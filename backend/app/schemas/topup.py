from typing import Optional
from pydantic import BaseModel


class TopUpRequestCreate(BaseModel):
    amount: float
    comment: Optional[str] = None


class TopUpRequestResponse(BaseModel):
    id: int
    user_id: int
    amount: float
    status: str
    payment_reference: Optional[str]
    comment: Optional[str]

    class Config:
        from_attributes = True


class TopUpConfirmRequest(BaseModel):
    payment_reference: Optional[str] = None
