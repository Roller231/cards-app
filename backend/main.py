import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import create_tables
from app.api.routers import auth, cards, orders, balance, transactions, aifory_dev
from app.api.routers import crypto_payments

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Cards App API",
    description=(
        "Backend for virtual card management via Aifory parent account.\n\n"
        "**Swagger testing flow:**\n"
        "1. `POST /auth/register` – create a test user\n"
        "2. Click **Authorize** and paste the returned `access_token`\n"
        "3. `POST /balance/topup-requests` – request balance top-up\n"
        "4. `POST /balance/topup-requests/{id}/confirm` – manually confirm & credit balance\n"
        "5. `GET /cards/offers` – pick an offer_id\n"
        "6. `POST /cards/issue` – issue a virtual card\n"
        "7. `GET /cards` – sync & list your cards\n"
        "8. `GET /cards/{id}/requisites` – view PAN/CVV\n"
        "9. `GET /transactions/cards/{id}` – view transaction history\n"
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


async def _crypto_poll_loop() -> None:
    from app.services.crypto_payment_service import poll_pending_payments
    while True:
        try:
            await poll_pending_payments()
        except Exception as exc:
            logging.getLogger(__name__).error("Crypto poll loop error: %s", exc)
        await asyncio.sleep(20)


@app.on_event("startup")
async def startup():
    await create_tables()
    asyncio.create_task(_crypto_poll_loop())


app.include_router(auth.router)
app.include_router(cards.router)
app.include_router(orders.router)
app.include_router(balance.router)
app.include_router(transactions.router)
app.include_router(aifory_dev.router)
app.include_router(crypto_payments.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
