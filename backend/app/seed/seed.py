import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.database import Base
from app.core.config import settings
from app.seed.faq_seed import seed_faqs


# Function to check and update database schema
def check_and_update_schema(conn):
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    
    # Check if 'cards' table exists
    if 'cards' in inspector.get_table_names():
        columns = inspector.get_columns('cards')
        column_names = [col['name'] for col in columns]
        
        # Check if 'last_notified_transaction_id' column exists
        if 'last_notified_transaction_id' not in column_names:
            print("Adding missing 'last_notified_transaction_id' column to 'cards' table")
            conn.execute(text("ALTER TABLE cards ADD COLUMN last_notified_transaction_id VARCHAR(255) NULL;"))
            print("Column 'last_notified_transaction_id' added to 'cards' table")
    
    # Check if 'faqs' table exists, create if not
    if 'faqs' not in inspector.get_table_names():
        print("Creating 'faqs' table")
        conn.execute(text("""
            CREATE TABLE faqs (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                question VARCHAR(255) NOT NULL,
                answer TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            );
        """))
        print("Table 'faqs' created")
    
    # Add similar checks for other tables and columns if needed in the future
    return


async def init_db(db: AsyncSession):
    async with db.begin():
        await db.run_sync(Base.metadata.create_all)
        # Check and update schema for existing tables
        await db.run_sync(check_and_update_schema)


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
