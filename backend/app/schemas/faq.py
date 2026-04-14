from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FAQBase(BaseModel):
    question: str
    answer: str


class FAQCreate(FAQBase):
    pass


class FAQUpdate(FAQBase):
    question: Optional[str] = None
    answer: Optional[str] = None


class FAQItem(FAQBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class FAQListResponse(BaseModel):
    faqs: list[FAQItem]

    class Config:
        orm_mode = True
