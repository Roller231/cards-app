from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.database import get_db
from app.models.faq import FAQ
from app.schemas.faq import FAQItem, FAQListResponse
from app.seed.faq_seed import seed_faqs

router = APIRouter(prefix="/faq", tags=["faq"])


@router.get("/", response_model=FAQListResponse, summary="Get all FAQ items")
async def get_faqs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FAQ).order_by(FAQ.id.asc()))
    faqs = result.scalars().all()
    if not faqs:
        await seed_faqs(db, only_if_empty=True)
        result = await db.execute(select(FAQ).order_by(FAQ.id.asc()))
        faqs = result.scalars().all()
    return {"faqs": faqs}


@router.get("/{faq_id}", response_model=FAQItem, summary="Get a single FAQ item")
async def get_faq(faq_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    faq = result.scalar_one_or_none()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ item not found")
    return faq
