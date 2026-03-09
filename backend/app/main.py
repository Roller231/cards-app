from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.api.routers import auth, cards, offers, topup, orders, transactions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    await init_db()
    yield
    # Shutdown


app = FastAPI(
    title="Virtual Cards API",
    description="""
    Backend API for Telegram Mini App - Virtual Cards.
    
    ## Features
    - Telegram WebApp authentication
    - Virtual card issuance via Aifory
    - Card top-up/deposit
    - Transaction history
    
    ## Authentication
    All endpoints (except /api/auth/telegram) require Bearer token authentication.
    Obtain token via POST /api/auth/telegram with Telegram initData.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(cards.router, prefix="/api")
app.include_router(offers.router, prefix="/api")
app.include_router(topup.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Virtual Cards API",
        "version": "1.0.0",
        "docs": "/docs",
    }
