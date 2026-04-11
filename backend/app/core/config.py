from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/cards_app"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    AIFORY_BASE_URL: str = "https://srv.aifory.pro/lk"
    AIFORY_API_PREFIX: str = "/v1"
    AIFORY_EMAIL: str = ""
    AIFORY_PASSWORD: str = ""
    AIFORY_PIN: str = ""
    AIFORY_TOTP_SECRET: str = ""
    AIFORY_COOKIE_FILE: str = ".aifory_cookies.json"
    AIFORY_IMPERSONATE: str = "chrome110"  # e.g. chrome124, edge101, safari17_0; empty -> auto select

    # Per-card-type commission settings
    ONLINE_ISSUE_FEE_USD: float = 0.0  # Fixed fee for Online card issuance
    ONLINE_TOPUP_MARKUP_PERCENT: float = 3.8
    ONLINE_PLUS_ISSUE_FEE_USD: float = 0.0  # Fixed fee for Online + Pay card issuance
    ONLINE_PLUS_TOPUP_MARKUP_PERCENT: float = 4.0
    
    # USDT account settings (move from hardcoded logic)
    USDT_ERC20_ACCOUNT_ID: str = ""  # currencyID=2000, will auto-detect if empty
    USDT_TRC20_ACCOUNT_ID: str = ""  # currencyID=2001, will auto-detect if empty

    ADMIN_EMAIL: str = "exprontopay@gmail.com"
    ADMIN_PASSWORD: str = "exprontoPay2026."

    TELEGRAM_BOT_TOKEN: str = ""  # Required for Telegram WebApp initData verification

    # ABCEX crypto payment gateway
    ABCEX_API_KEY: str = ""  # Bearer JWT token for ABCEX API
    ABCEX_CRYPTO_PAYMENT_EXPIRY_MINUTES: int = 30  # Payment window before expiry

    class Config:
        env_file = ".env"


settings = Settings()
