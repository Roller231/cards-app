import asyncio
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, admin, cards, transactions, crypto_payments, faq
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


@app.on_event("startup")
async def startup_db_client():
    async with engine.begin() as conn:
        # Create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created (if not existed)")


@app.on_event("shutdown")
async def shutdown_db_client():
    await engine.dispose()
    logger.info("Database connection closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
