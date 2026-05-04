import asyncio
import logging

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.database import create_tables
from app.api.routers import auth, cards, orders, balance, faq
from app.api.routers import crypto_payments
from app.api.routers import admin as admin_router_mod

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Cards App API",
    description=(
        "Backend for virtual card management via O-Plata API.\n\n"
        "**Swagger testing flow (admin):**\n"
        "1. `POST /admin/auth/login` – get admin token (Authorize with it)\n"
        "2. `GET /admin/oplata/card-types` – see available card types (offers)\n"
        "3. `POST /admin/oplata/register-client` – register a client (e.g. `user_1`)\n"
        "4. `GET /admin/oplata/client-balance` – check client balance\n"
        "5. `GET /admin/oplata/client-cards` – list client\'s virtual cards\n"
        "6. `POST /admin/oplata/sync-user/{user_id}` – sync cards to local DB\n\n"
        "**Swagger testing flow (user):**\n"
        "1. `POST /auth/register` – create a test user\n"
        "2. Click **Authorize** and paste the returned `access_token`\n"
        "3. `GET /cards/offers` – pick an `offer_id`\n"
        "4. `POST /cards/issue` – issue a virtual card (requires balance or `skip_balance_check`)\n"
        "5. `GET /cards` – sync & list your cards\n"
        "6. `GET /cards/{id}/requisites` – view PAN/CVV\n"
        "7. `GET /cards/{id}/transactions` – view card transactions\n"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _bot_poll_loop() -> None:
    from app.services.telegram_bot_service import poll_once
    while True:
        try:
            await poll_once()
        except Exception as exc:
            logging.getLogger(__name__).error("Bot poll loop error: %s", exc)
            await asyncio.sleep(5)


async def _gmail_poll_loop() -> None:
    from app.services.gmail_service import check_gmail_once
    while True:
        try:
            await check_gmail_once()
        except Exception as exc:
            logging.getLogger(__name__).error("Gmail poll loop error: %s", exc)
        await asyncio.sleep(10)


async def _crypto_poll_loop() -> None:
    from app.services.crypto_payment_service import poll_pending_payments
    while True:
        try:
            await poll_pending_payments()
        except Exception as exc:
            logging.getLogger(__name__).error("Crypto poll loop error: %s", exc)
        await asyncio.sleep(20)


async def _load_admin_settings() -> None:
    """Load admin setting overrides from DB into the in-memory settings object."""
    from sqlalchemy import select as sa_select
    from app.core.database import AsyncSessionLocal
    from app.core.config import settings as cfg
    from app.models.admin_setting import AdminSetting
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(sa_select(AdminSetting))
            for s in result.scalars().all():
                key_upper = s.key.upper()
                if hasattr(cfg, key_upper):
                    cur = getattr(cfg, key_upper)
                    try:
                        setattr(cfg, key_upper, type(cur)(s.value))
                        logging.getLogger(__name__).info("Admin setting loaded: %s = %s", key_upper, s.value)
                    except (ValueError, TypeError):
                        pass
    except Exception as exc:
        logging.getLogger(__name__).warning("Could not load admin settings: %s", exc)


_UPLOADS_DIR = Path(__file__).parent / "static" / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")


@app.on_event("startup")
async def startup():
    await create_tables()
    await _load_admin_settings()
    asyncio.create_task(_crypto_poll_loop())
    asyncio.create_task(_bot_poll_loop())
    asyncio.create_task(_gmail_poll_loop())


app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(orders.router)
app.include_router(balance.router)
app.include_router(crypto_payments.router)
app.include_router(admin_router_mod.router)
app.include_router(faq.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
