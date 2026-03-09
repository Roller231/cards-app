from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CardResponse(BaseModel):
    id: int
    partner_card_id: str
    last4: str
    category: Optional[int] = None
    status: int
    balance: Optional[str] = None
    expired_at: Optional[str] = None
    payment_system_id: Optional[int] = None
    currency_id: Optional[int] = None
    decline_rate: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class CardListResponse(BaseModel):
    cards: List[CardResponse]


class CardRequisitesResponse(BaseModel):
    card_number: str
    cvv: str
    card_holder_name: str
    country: Optional[int] = None
    country_name: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None


class CardOfferResponse(BaseModel):
    bin: str
    category: int
    min_amount: str
    max_amount: str
    create_card_currency: int
    create_card_fixed_fee: str
    create_card_fee_percent: str
    operation_fixed_fee: str
    operation_fee_percent: str
    operation_limit: str
    all_time_limit: str


class CardOffersResponse(BaseModel):
    offers: List[CardOfferResponse]
    limits: dict


class IssueCardCalculateRequest(BaseModel):
    bin: str
    amount: str
    account_id: Optional[str] = None


class IssueCardCalculateResponse(BaseModel):
    amount: str
    fee: str


class IssueCardRequest(BaseModel):
    bin: str
    amount: str
    email: str
    account_id: Optional[str] = None


class IssueCardResponse(BaseModel):
    order_id: str
    message: str = "Card issuance started"
