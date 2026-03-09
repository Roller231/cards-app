from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class OrderResponse(BaseModel):
    id: int
    partner_order_id: str
    type: str
    amount: float
    fee: float
    status: int
    card_id: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class OrderStatusResponse(BaseModel):
    order_id: str
    type: int  # 1=CreateCard, 2=Deposit
    status_id: int  # 1=Pending, 2=Success, 3=Failed, 5=Canceled
    amount: str
    fee_percent: Optional[str] = None
    fixed_fee: Optional[str] = None
    client_amount: Optional[str] = None
    currency_id: Optional[int] = None
    card_id: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
