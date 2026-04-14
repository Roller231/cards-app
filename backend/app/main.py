import asyncio
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, admin, cards, transactions, crypto_payments, faq, orders, balance, aifory_dev
from app.core.config import settings
from app.core.database import engine
from app.models import Base

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Cards App API",
    description="API for managing virtual cards and payments",
    version="1.0.0",
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(cards.router)
app.include_router(transactions.router)
app.include_router(crypto_payments.router)
app.include_router(faq.router)
app.include_router(orders.router)
app.include_router(balance.router)
app.include_router(aifory_dev.router)


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
            logger.info("Adding missing 'last_notified_transaction_id' column to 'cards' table")
            conn.execute(text("ALTER TABLE cards ADD COLUMN last_notified_transaction_id VARCHAR(255) NULL;"))
            logger.info("Column 'last_notified_transaction_id' added to 'cards' table")
    
    # Check if 'faqs' table exists, create if not
    if 'faqs' not in inspector.get_table_names():
        logger.info("Creating 'faqs' table")
        conn.execute(text("""
            CREATE TABLE faqs (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                question VARCHAR(255) NOT NULL,
                answer TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            );
        """))
        logger.info("Table 'faqs' created")
    
    # Add similar checks for other tables and columns if needed in the future
    return


@app.on_event("startup")
async def startup_db_client():
    async with engine.begin() as conn:
        # Create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)
        # Check and update schema for existing tables
        await conn.run_sync(check_and_update_schema)
    logger.info("Database tables created (if not existed) and schema updated")


@app.on_event("shutdown")
async def shutdown_db_client():
    await engine.dispose()
    logger.info("Database connection closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
