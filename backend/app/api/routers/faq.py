from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, delete
from typing import List

from app.api.deps import get_current_user, get_db
from app.models.faq import FAQ
from app.models.user import User
from app.schemas.faq import FAQCreate, FAQUpdate, FAQItem, FAQListResponse

router = APIRouter(prefix="/faq", tags=["faq"])


@router.post("/", response_model=FAQItem)
async def create_faq(
    faq: FAQCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = insert(FAQ).values(**faq.dict())
    result = await db.execute(stmt)
    await db.commit()
    faq_id = result.inserted_primary_key[0]
    result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    new_faq = result.scalar_one_or_none()
    if not new_faq:
        raise HTTPException(status_code=404, detail="FAQ item not found after creation")
    return new_faq


@router.get("/", response_model=FAQListResponse)
async def get_faqs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FAQ))
    faqs = result.scalars().all()
    return {"faqs": faqs}


@router.get("/{faq_id}", response_model=FAQItem)
async def get_faq(faq_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    faq = result.scalar_one_or_none()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ item not found")
    return faq


@router.put("/{faq_id}", response_model=FAQItem)
async def update_faq(
    faq_id: int,
    faq_update: FAQUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    existing_faq = result.scalar_one_or_none()
    if not existing_faq:
        raise HTTPException(status_code=404, detail="FAQ item not found")

    update_data = faq_update.dict(exclude_unset=True)
    update_data = {k: v for k, v in update_data.items() if v is not None}
    if update_data:
        stmt = update(FAQ).where(FAQ.id == faq_id).values(**update_data)
        await db.execute(stmt)
        await db.commit()

    result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    updated_faq = result.scalar_one_or_none()
    return updated_faq


@router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(
    faq_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    existing_faq = result.scalar_one_or_none()
    if not existing_faq:
        raise HTTPException(status_code=404, detail="FAQ item not found")

    stmt = delete(FAQ).where(FAQ.id == faq_id)
    await db.execute(stmt)
    await db.commit()
