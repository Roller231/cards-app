import asyncio
import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routers import auth, admin, cards, faq, orders, balance, sbp, kyc, profile
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
app.include_router(profile.router)


# Static uploads (bot welcome image, broadcast images)
_UPLOADS_DIR = Path(__file__).parent.parent / "static" / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")


async def _bot_poll_loop() -> None:
    """Long-poll Telegram getUpdates so the bot handles /start."""
    from app.services.telegram_bot_service import poll_once
    while True:
        try:
            if not (settings.TELEGRAM_BOT_TOKEN or "").strip():
                # No token (e.g. local dev): poll_once would return instantly and
                # this loop would busy-spin, starving the event loop entirely.
                await asyncio.sleep(30)
                continue
            await poll_once()
        except Exception as exc:
            logger.error("Bot poll loop error: %s", exc)
            await asyncio.sleep(5)


async def _auto_recover_loop() -> None:
    """Re-trigger paid invoices whose card issue / deposit never landed."""
    from app.services.recovery_service import scan_and_recover
    while True:
        try:
            await scan_and_recover()
        except Exception as exc:
            logger.error("Auto-recover loop error: %s", exc)
        await asyncio.sleep(120)


async def _scheduled_broadcast_loop() -> None:
    """Send due scheduled broadcasts (admin-queued, stored in DB)."""
    from datetime import datetime as _dt
    from pathlib import Path as _Path
    from sqlalchemy import select as _sel
    from app.core.database import AsyncSessionLocal
    from app.models.broadcast import ScheduledBroadcast
    while True:
        try:
            async with AsyncSessionLocal() as db:
                due = (await db.execute(
                    _sel(ScheduledBroadcast).where(
                        ScheduledBroadcast.status == "scheduled",
                        ScheduledBroadcast.scheduled_at <= _dt.utcnow(),
                    ).order_by(ScheduledBroadcast.id.asc()).limit(3)
                )).scalars().all()
                for row in due:
                    row.status = "sending"
                    await db.commit()
                    try:
                        import json as _json
                        from app.services.telegram_bot_service import broadcast_message
                        try:
                            buttons = _json.loads(row.buttons or "[]")
                        except Exception:
                            buttons = []
                        image_path = None
                        if row.image_key:
                            cand = _UPLOADS_DIR / row.image_key
                            if cand.exists():
                                image_path = cand
                        result = await broadcast_message(
                            db, row.text, row.parse_mode, buttons, image_path, segment=row.segment,
                        )
                        row.sent = int(result.get("sent") or 0)
                        row.failed = int(result.get("failed") or 0)
                        row.status = "done"
                        if image_path and image_path.exists():
                            try:
                                image_path.unlink()
                            except Exception:
                                pass
                    except Exception as exc:
                        logger.error("Scheduled broadcast %s failed: %s", row.id, exc)
                        row.status = "failed"
                    await db.commit()
                    logger.info("Scheduled broadcast %s finished: status=%s sent=%s failed=%s",
                                row.id, row.status, row.sent, row.failed)
        except Exception as exc:
            logger.error("Scheduled broadcast loop error: %s", exc)
        await asyncio.sleep(30)


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
            'sbp_qr_reset_at': 'DATETIME NULL',
            'univ_client_seq': 'INT NOT NULL DEFAULT 0',
            'client_seq': 'INT NOT NULL DEFAULT 0',
            'referral_code': 'VARCHAR(16) NULL',
            'referrer_id': 'BIGINT NULL',
            'referred_at': 'DATETIME NULL',
        }
        for col_name, col_def in new_user_cols.items():
            if col_name not in user_cols:
                logger.info("Adding column '%s' to 'users' table", col_name)
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def};"))
        if 'referral_code' not in user_cols:
            conn.execute(text("CREATE UNIQUE INDEX ux_users_referral_code ON users (referral_code);"))
            conn.execute(text("CREATE INDEX ix_users_referrer_id ON users (referrer_id);"))

    # Internal balance ledger (the table itself is created by create_all /
    # the block below). ONE-TIME reset of users.balance, guarded by an
    # admin_settings marker: until now every paid SBP invoice was credited to
    # the balance and never spent (the money bought a card / top-up), so the
    # stored balances are phantom. Each reset is recorded in the ledger.
    tables = inspector.get_table_names()
    if 'balance_transactions' not in tables:
        logger.info("Creating 'balance_transactions' table")
        conn.execute(text("""
            CREATE TABLE balance_transactions (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                user_id BIGINT NOT NULL,
                type VARCHAR(24) NOT NULL,
                amount DECIMAL(18,2) NOT NULL,
                balance_after DECIMAL(18,2) NOT NULL,
                description VARCHAR(255) NULL,
                ref_invoice_id BIGINT NULL,
                ref_order_id BIGINT NULL,
                ref_user_id BIGINT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX ix_bt_user_id (user_id),
                INDEX ix_bt_type (type),
                INDEX ix_bt_ref_invoice_id (ref_invoice_id),
                INDEX ix_bt_ref_order_id (ref_order_id),
                INDEX ix_bt_ref_user_id (ref_user_id),
                INDEX ix_bt_created_at (created_at),
                CONSTRAINT fk_bt_user FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """))
    if 'users' in tables and 'admin_settings' in tables:
        done = conn.execute(
            text("SELECT 1 FROM admin_settings WHERE `key` = 'BALANCE_LEDGER_RESET_DONE' LIMIT 1")
        ).fetchone()
        if not done:
            rows = conn.execute(text("SELECT id, balance FROM users WHERE balance <> 0")).fetchall()
            for uid, bal in rows:
                conn.execute(
                    text("INSERT INTO balance_transactions (user_id, type, amount, balance_after, description) "
                         "VALUES (:uid, 'admin_adjust', :amt, 0, 'Сброс фантомного баланса (миграция внутреннего баланса)')"),
                    {"uid": uid, "amt": -float(bal)},
                )
            conn.execute(text("UPDATE users SET balance = 0 WHERE balance <> 0"))
            conn.execute(
                text("INSERT INTO admin_settings (`key`, value, description) VALUES "
                     "('BALANCE_LEDGER_RESET_DONE', '1', 'Marker: phantom balances zeroed when the internal balance ledger was introduced')")
            )
            logger.info("Reset phantom balances for %d users (recorded in balance_transactions)", len(rows))

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
    asyncio.create_task(_scheduled_broadcast_loop())
    asyncio.create_task(_auto_recover_loop())
    logger.info("Database tables created (if not existed) and schema updated")


@app.on_event("shutdown")
async def shutdown_db_client():
    await engine.dispose()
    logger.info("Database connection closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
