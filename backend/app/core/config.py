from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/cards_app"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    DETAILED_DEV_LOGS: bool = False  # Enable verbose development logging
    LOCAL_DEV_CLIENT_SUFFIX: str = ""  # Override fallback tg_dev_<suffix> for dev/testing

    # Per-card-type commission settings
    ONLINE_ISSUE_FEE_USD: float = 0.0  # Fixed fee for Online card issuance
    ONLINE_TOPUP_MARKUP_PERCENT: float = 3.8
    ONLINE_PLUS_ISSUE_FEE_USD: float = 0.0  # Fixed fee for Online + Pay card issuance
    ONLINE_PLUS_TOPUP_MARKUP_PERCENT: float = 4.0
    # SBP prices users actually pay for issuance (admin panel / DB overrides these)
    CARD_ISSUANCE_PRICE_RUB: float = 999.0
    CARD_ISSUANCE_PRICE_PAY_RUB: float = 1999.0

    # App exchange-rate formula: rate = [BB index] × bitbFee × myFee × clarusFee,
    # where each multiplier is (1 + percent/100). Percents are admin-editable.
    SBP_BITBANKER_FEE_PERCENT: float = 2.1
    SBP_OUR_FEE_PERCENT: float = 1.9
    SBP_CLARUS_FEE_PERCENT: float = 2.8
    # Fixed Bitbanker commission passed on to the user for small top-ups
    SBP_SMALL_PAYMENT_FEE_RUB: float = 210.0
    SBP_SMALL_PAYMENT_THRESHOLD_RUB: float = 10000.0

    # Billing address shown in card info (O-Plata API does not provide one —
    # set the issuer's address here via admin panel once known)
    CARD_BILLING_ADDRESS: str = ""
    ISSUE_APPLY_TOPUP_MARKUP: bool = False
    ONLINE_CARD_VALIDITY_TEXT: str = "1 год"
    ONLINE_PLUS_CARD_VALIDITY_TEXT: str = "1 год"
    ONLINE_OPERATION_FEE_USD: float = 0.4
    ONLINE_PLUS_OPERATION_FEE_USD: float = 0.4
    
    ADMIN_EMAIL: str = "exprontopay@gmail.com"
    ADMIN_PASSWORD: str = "exprontoPay2026."

    TELEGRAM_BOT_TOKEN: str = ""  # Required for Telegram WebApp initData verification

    # Public app URL used for external OAuth callbacks (e.g. https://prontopay.pro)
    PUBLIC_BASE_URL: str = ""

    # Gmail API OAuth2 for Apple Pay codes
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""

    # O-Plata API
    OPLATA_BASE_URL: str = "https://int.o-plata.com:443"
    OPLATA_PRODUCT_ID: str = ""
    OPLATA_PRIVATE_KEY: str = ""  # Ed25519 seed in hex (32 bytes / 64 hex chars)
    OPLATA_PUBLIC_KEY: str = ""
    OPLATA_CALLBACK_PUBLIC_KEY: str = ""
    OPLATA_TEST_CLIENT_ID: str = "Developer"  # clientId used for fetching card types/offers
    OPLATA_PARENT_CLIENT_ID: str = "Developer"  # Funded parent client used to transfer funds to per-user clients
    OPLATA_USER_CLIENT_PREFIX: str = "tg_"  # Prefix for per-user O-Plata clientId derived from telegram_user_id

    # NeuroVision KYC
    NV_API_TOKEN: str = ""           # JWT token from NeuroVision LK (раздел Доступ)
    NV_SCHEMA_ID: str = ""           # KYC schema ID from NeuroVision LK
    NV_SCENARIO_SECRET: str = ""     # Scenario secret key (for clientKey encryption + webhook verification)

    # Bitbanker SBP gateway
    BITBANKER_API_KEY: str = ""
    BITBANKER_API_SECRET: str = ""
    BITBANKER_BASE_URL: str = "https://api.aws.dev.bitbanker.org/latest"  # DEV; swap to prod
    USD_TO_RUB_RATE: float = 95.0  # Admin-configurable USD to RUB exchange rate

    # Test KYC data for Bitbanker (temporary until NeuroVision integration)
    BB_TEST_FIRST_NAME: str = "Иван"
    BB_TEST_LAST_NAME: str = "Иванов"
    BB_TEST_PATRONYMIC: str = "Иванович"
    BB_TEST_BIRTH_DATE: str = "01.01.1990"
    BB_TEST_PASSPORT: str = "1234567890"
    BB_TEST_PASSPORT_ISSUE_DATE: str = "01.01.2018"
    BB_TEST_PHONE: str = "+79991234567"

    class Config:
        env_file = ".env"
        case_sensitive = False  # Allow lowercase env vars


settings = Settings()
