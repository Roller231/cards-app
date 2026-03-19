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

    CARD_ISSUE_MARKUP_PERCENT: float = 0.0
    CARD_TOPUP_MARKUP_PERCENT: float = 0.0

    TELEGRAM_BOT_TOKEN: str = ""  # Required for Telegram WebApp initData verification

    class Config:
        env_file = ".env"


settings = Settings()
