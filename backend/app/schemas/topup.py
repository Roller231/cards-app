from pydantic import BaseModel
from typing import Optional


class TopUpOfferResponse(BaseModel):
    min_deposit_amount: str
    max_deposit_amount: str
    card_deposit_fee_percent: str


class TopUpCalculateRequest(BaseModel):
    amount: str
    account_id: Optional[str] = None


class TopUpCalculateResponse(BaseModel):
    amount: str
    fee: str


class TopUpRequest(BaseModel):
    amount: str
    account_id: Optional[str] = None


class TopUpResponse(BaseModel):
    order_id: str
    message: str = "Top-up started"
