import asyncio
import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routers import auth, admin, cards, faq, orders, balance, sbp, kyc
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
app.include_router(faq.router)
app.include_router(orders.router)
app.include_router(balance.router)
app.include_router(sbp.router)
app.include_router(kyc.router)


# Static uploads (bot welcome image, broadcast images)
_UPLOADS_DIR = Path(__file__).parent.parent / "static" / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")


async def _bot_poll_loop() -> None:
    """Long-poll Telegram getUpdates so the bot handles /start."""
    from app.services.telegram_bot_service import poll_once
    while True:
        try:
            await poll_once()
        except Exception as exc:
            logger.error("Bot poll loop error: %s", exc)
            await asyncio.sleep(5)


async def _gmail_poll_loop() -> None:
    """Poll Gmail for Apple Pay verification code emails."""
    from app.services.gmail_service import check_gmail_once
    while True:
        try:
            await check_gmail_once()
        except Exception as exc:
            logger.error("Gmail poll loop error: %s", exc)
        await asyncio.sleep(10)


async def _load_admin_settings() -> None:
    """Load admin setting overrides from DB into the in-memory settings object."""
    from sqlalchemy import select as sa_select
    from app.core.database import AsyncSessionLocal
    from app.models.admin_setting import AdminSetting
    try:
        async with AsyncSessionLocal() as db:
            default_settings = {
                "CARD_ISSUANCE_PRICE_USD": ("10.0", "Card issuance price (USD) - user pays this fixed amount, card issued with zero balance"),
            }
            for key, (value, description) in default_settings.items():
                result = await db.execute(sa_select(AdminSetting).where(AdminSetting.key == key))
                if not result.scalar_one_or_none():
                    db.add(AdminSetting(key=key, value=value, description=description))
                    logger.info("Created default admin setting: %s = %s", key, value)
            await db.commit()

            result = await db.execute(sa_select(AdminSetting))
            for s in result.scalars().all():
                key_upper = s.key.upper()
                if hasattr(settings, key_upper):
                    cur = getattr(settings, key_upper)
                    try:
                        if isinstance(cur, bool):
                            # bool("False") is True — parse explicitly
                            typed = str(s.value).strip().lower() in ("1", "true", "yes", "on")
                        else:
                            typed = type(cur)(s.value)
                        setattr(settings, key_upper, typed)
                        logger.info("Admin setting loaded: %s = %s", key_upper, s.value)
                    except (ValueError, TypeError):
                        pass
    except Exception as exc:
        logger.warning("Could not load admin settings: %s", exc)


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
    
    # Check for new KYC/contact columns in users table
    if 'users' in inspector.get_table_names():
        user_cols = [col['name'] for col in inspector.get_columns('users')]
        new_user_cols = {
            'email': 'VARCHAR(255) NULL',
            'phone': 'VARCHAR(32) NULL',
            'gender': 'VARCHAR(8) NULL',
            'kyc_status': 'VARCHAR(16) NULL',
            'kyc_first_name': 'VARCHAR(100) NULL',
            'kyc_last_name': 'VARCHAR(100) NULL',
            'kyc_patronymic': 'VARCHAR(100) NULL',
            'kyc_birth_date': 'VARCHAR(20) NULL',
            'kyc_passport': 'VARCHAR(20) NULL',
            'kyc_passport_issue_date': 'VARCHAR(20) NULL',
            'kyc_session_id': 'VARCHAR(100) NULL',
        }
        for col_name, col_def in new_user_cols.items():
            if col_name not in user_cols:
                logger.info("Adding column '%s' to 'users' table", col_name)
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def};"))

    # Check for offer_id column in bb_invoices table
    if 'bb_invoices' in inspector.get_table_names():
        inv_cols = [col['name'] for col in inspector.get_columns('bb_invoices')]
        if 'offer_id' not in inv_cols:
            logger.info("Adding column 'offer_id' to 'bb_invoices' table")
            conn.execute(text("ALTER TABLE bb_invoices ADD COLUMN offer_id VARCHAR(256) NULL;"))
        if 'card_id' not in inv_cols:
            logger.info("Adding column 'card_id' to 'bb_invoices' table")
            conn.execute(text("ALTER TABLE bb_invoices ADD COLUMN card_id VARCHAR(256) NULL;"))
        if 'amount_usd_requested' not in inv_cols:
            logger.info("Adding column 'amount_usd_requested' to 'bb_invoices' table")
            conn.execute(text("ALTER TABLE bb_invoices ADD COLUMN amount_usd_requested DECIMAL(18,6) NULL;"))
        if 'created_at' not in inv_cols:
            logger.info("Adding column 'created_at' to 'bb_invoices' table")
            conn.execute(text("ALTER TABLE bb_invoices ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP;"))
            # Backdate existing invoices so they don't count against today's QR limit
            conn.execute(text("UPDATE bb_invoices SET created_at = DATE_SUB(NOW(), INTERVAL 2 DAY);"))

    if 'orders' in inspector.get_table_names():
        ord_cols = [col['name'] for col in inspector.get_columns('orders')]
        if 'notified' not in ord_cols:
            logger.info("Adding column 'notified' to 'orders' table")
            conn.execute(text("ALTER TABLE orders ADD COLUMN notified TINYINT(1) NOT NULL DEFAULT 0;"))
            # Mark all existing completed/failed orders as already notified to prevent duplicate notifications
            conn.execute(text("UPDATE orders SET notified = 1 WHERE status IN ('completed', 'failed');"))
            logger.info("Marked existing completed/failed orders as notified")

    return


@app.on_event("startup")
async def startup_db_client():
    async with engine.begin() as conn:
        # Create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)
        # Check and update schema for existing tables
        await conn.run_sync(check_and_update_schema)
    # Apply admin setting overrides from DB (prices, rates, headers)
    await _load_admin_settings()
    # Start persistent auto-topup worker (drains pending_auto_topups across restarts)
    from app.services.card_service import card_service as _cs
    asyncio.create_task(_cs.run_pending_auto_topups_worker())
    # Telegram bot long-polling (/start handler) and Gmail Apple Pay code polling
    asyncio.create_task(_bot_poll_loop())
    asyncio.create_task(_gmail_poll_loop())
    logger.info("Database tables created (if not existed) and schema updated")


@app.on_event("shutdown")
async def shutdown_db_client():
    await engine.dispose()
    logger.info("Database connection closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
