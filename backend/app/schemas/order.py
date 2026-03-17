from typing import Optional
from pydantic import BaseModel


class OrderResponse(BaseModel):
    id: int
    partner_order_id: Optional[str]
    card_id: Optional[int]
    type: str
    amount: float
    fee: float
    status: str
    description: Optional[str]

    class Config:
        from_attributes = True


class OrderStatusResponse(BaseModel):
    local_order_id: int
    partner_order_id: Optional[str]
    status: str
    aifory_status: Optional[dict] = None
