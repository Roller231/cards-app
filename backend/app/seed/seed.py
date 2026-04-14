import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.database import Base
from app.core.config import settings
from app.seed.faq_seed import seed_faqs


async def init_db(db: AsyncSession):
    async with db.begin():
        await db.run_sync(Base.metadata.create_all)


async def seed_data(db: AsyncSession):
    await seed_faqs(db)


async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        await init_db(session)
        await seed_data(session)


if __name__ == "__main__":
    asyncio.run(main())
