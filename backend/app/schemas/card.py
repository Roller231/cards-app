from typing import Optional
from pydantic import BaseModel


class CardResponse(BaseModel):
    id: int
    aifory_card_id: Optional[str] = None
    category: Optional[int] = None
    card_status: Optional[int] = None
    expired_at: Optional[str] = None
    last4: Optional[str] = None
    holder_name: Optional[str] = None
    currency: Optional[str] = None
    currency_id: Optional[int] = None
    payment_system_id: Optional[int] = None
    status: Optional[str] = None
    balance: float = 0.0
    offer_id: Optional[str] = None

    class Config:
        from_attributes = True


class CardRequisitesResponse(BaseModel):
    card_number: Optional[str] = None
    expiry: Optional[str] = None
    cvv: Optional[str] = None
    holder_name: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country_name: Optional[str] = None


class CardOfferItem(BaseModel):
    id: str
    name: Optional[str] = None
    currency: Optional[str] = None
    currency_id: Optional[int] = None
    category: Optional[int] = None
    issue_fee: Optional[float] = None
    fee_percent: Optional[float] = None
    monthly_fee: Optional[float] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    description: Optional[str] = None


class IssueCardRequest(BaseModel):
    offer_id: str
    holder_first_name: str
    holder_last_name: str
    amount: Optional[float] = None


class IssueCardResponse(BaseModel):
    local_order_id: int
    partner_order_id: Optional[str]
    message: str = "Card issuance request created"


class CardDepositRequest(BaseModel):
    amount: float
