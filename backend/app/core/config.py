from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+aiomysql://user:password@localhost:3306/cards_app"
    
    # Aifory API
    AIFORY_BASE_URL: str = "https://srv.aifory.pro/lk"
    AIFORY_TOKEN: str = ""
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    
    # JWT
    JWT_SECRET_KEY: str = "change_me_in_production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440
    
    # App
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
