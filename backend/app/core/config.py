from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/cards_app"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    DETAILED_DEV_LOGS: bool = False  # Enable verbose development logging
    # Browser access without Telegram (POST /auth/dev-browser). MUST stay False
    # in production so the app is reachable only from inside Telegram.
    ALLOW_DEV_BROWSER_LOGIN: bool = False
    LOCAL_DEV_CLIENT_SUFFIX: str = ""  # Override fallback tg_dev_<suffix> for dev/testing

    # Card type availability toggles (admin panel)
    CARD_ONLINE_ENABLED: bool = True
    CARD_ONLINE_PLUS_ENABLED: bool = True
    CARD_PAY_ENABLED: bool = True

    # "Pay" (universal) cards live on a separate O-Plata provider and are issued
    # under a SEPARATE per-user client (tg_univ_*) with US identity data,
    # funded from a dedicated parent.
    OPLATA_UNIV_PARENT_CLIENT_ID: str = "PRONTOPAY_UNIV"
    OPLATA_UNIV_RAVANA_IDS: str = "RAVANA:RT-8-prod"  # comma-separated providers

    # Per-card-type commission settings
    ONLINE_ISSUE_FEE_USD: float = 0.0  # Fixed fee for Online card issuance
    ONLINE_TOPUP_MARKUP_PERCENT: float = 3.8
    ONLINE_PLUS_ISSUE_FEE_USD: float = 0.0  # Fixed fee for Online + Pay card issuance
    ONLINE_PLUS_TOPUP_MARKUP_PERCENT: float = 4.0
    # SBP prices users actually pay for issuance (admin panel / DB overrides these)
    CARD_ISSUANCE_PRICE_RUB: float = 999.0
    CARD_ISSUANCE_PRICE_PAY_RUB: float = 1999.0
    CARD_ISSUANCE_PRICE_UNIV_RUB: float = 1999.0  # "Pay" (universal) card

    # App exchange-rate formula: rate = [BB index] × bitbFee × myFee × clarusFee,
    # where each multiplier is (1 + percent/100). Percents are admin-editable.
    SBP_BITBANKER_FEE_PERCENT: float = 2.1
    # Bitbanker QR commission = max(pct × QR, this absolute minimum). Live values
    # come from BB's prediction-sbp; these are fallbacks when it's unavailable.
    # Prod is 21 ₽ today, BB plans to raise it to 210 ₽.
    SBP_BB_MIN_FEE_RUB: float = 21.0
    SBP_OUR_FEE_PERCENT: float = 1.9
    SBP_CLARUS_FEE_PERCENT: float = 2.8
    # Bitbanker RUB->USDT conversion fee (we pay it), part of the app rate
    SBP_BB_CONVERSION_FEE_PERCENT: float = 0.1
    # Fixed Bitbanker commission passed on to the user for small top-ups
    SBP_SMALL_PAYMENT_FEE_RUB: float = 210.0

    # Auto-recovery of paid invoices whose card issue / deposit failed
    # (provider 500s, timeouts, deploy restarts): retry up to 3 times.
    AUTO_RECOVER_ENABLED: bool = True
    # Telegram chat_id for admin alerts (auto-recovery attempts/failures).
    ADMIN_ALERT_CHAT_ID: str = ""
    SBP_SMALL_PAYMENT_THRESHOLD_RUB: float = 10000.0

    # Referral program: the invited user gets a discount on their FIRST card
    # issuance; the inviter gets a fixed bonus on the internal balance once
    # BOTH of them have issued a card.
    REFERRAL_INVITEE_DISCOUNT_PERCENT: float = 10.0
    REFERRAL_INVITER_BONUS_USD: float = 3.0

    # Telegram chat ids of managers who receive Alipay / WeChat Pay requests
    # (comma-separated). Editable in the admin panel.
    SERVICE_REQUEST_MANAGER_IDS: str = ""
    # Yuan rate = Bitbanker exchange rate (RUB/USDT) / this divisor
    CHINA_CNY_DIVISOR: float = 6.6
    # Minimum transfer in yuan per service
    CHINA_MIN_CNY_ALIPAY: float = 150.0
    CHINA_MIN_CNY_WECHAT: float = 150.0
    # Support contact the user is sent to from the managers' "В поддержку" button
    SUPPORT_CONTACT: str = "@exprontopay1"

    # Maintenance switches (admin panel):
    # MAINTENANCE_MODE — the whole app is closed (user API answers 503, the app
    #   shows a maintenance screen, the bot answers any message with the text);
    # SBP_DISABLED — no new SBP invoices (Bitbanker maintenance); cards and the
    #   internal balance keep working.
    # How often the background watcher checks cards for new transactions (sec)
    TX_WATCH_INTERVAL_SEC: int = 300
    MAINTENANCE_MODE: bool = False
    MAINTENANCE_TEXT: str = "Ведутся технические работы. Приложение временно недоступно — скоро всё заработает. Приносим извинения за неудобства."
    SBP_DISABLED: bool = False
    SBP_DISABLED_TEXT: str = "Оплата по СБП временно недоступна: у платёжного партнёра ведутся технические работы. Приносим свои извинения. Карты работают как обычно."
    # Optional separate bot for managers' notifications about paid China
    # requests (managers must /start it). Empty = the main bot is used.
    CHINA_BOT_TOKEN: str = ""

    # Names of the fees that turn the exchange (Bitbanker) rate into the rate
    # the user actually pays — shown as a breakdown before every payment.
    SBP_BITBANKER_FEE_LABEL: str = "Комиссия платёжной системы СБП"
    SBP_OUR_FEE_LABEL: str = "Сервисный сбор"
    SBP_CLARUS_FEE_LABEL: str = "Комиссия банка-партнёра за конвертацию"
    # Our fee + Clarus are shown to users as ONE line with this name; its
    # percent is computed from the two settings (compounded).
    SBP_TOPUP_FEE_LABEL: str = "Комиссия за пополнение"
    # Bot / mini-app names used to build the invite deep link
    # (https://t.me/<bot>/<app>?startapp=<code>).
    TELEGRAM_BOT_USERNAME: str = "exprontopay_bot"
    TELEGRAM_MINIAPP_SHORT_NAME: str = "exprontopay"

    # Billing address shown in card info (O-Plata API does not provide one —
    # set the issuer's address here via admin panel once known)
    CARD_BILLING_ADDRESS: str = ""
    ISSUE_APPLY_TOPUP_MARKUP: bool = False
    ONLINE_CARD_VALIDITY_TEXT: str = "1 год"
    ONLINE_PLUS_CARD_VALIDITY_TEXT: str = "1 год"
    ONLINE_OPERATION_FEE_USD: float = 0.4
    ONLINE_PLUS_OPERATION_FEE_USD: float = 0.4
    UNIV_CARD_VALIDITY_TEXT: str = "1 год"
    UNIV_OPERATION_FEE_USD: float = 0.4
    UNIV_TOPUP_MARKUP_PERCENT: float = 4.0

    # Promo cards on the home screen — every visible field is admin-editable
    CARD_ONLINE_PROMO_TITLE: str = "Online"
    CARD_ONLINE_PROMO_DESC: str = "Для оплаты покупок и сервисов в интернете"
    CARD_ONLINE_PROMO_BADGE: str = "Бесплатное обслуживание"
    CARD_ONLINE_PROMO_PAYS: str = "Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр."
    CARD_ONLINE_PROMO_BIN: str = "Гонконг"
    CARD_ONLINE_PLUS_PROMO_TITLE: str = "Online + Pay"
    CARD_ONLINE_PLUS_PROMO_DESC: str = "Оплата в магазинах через Apple Pay, Google Pay и онлайн-сервисов на сайтах"
    CARD_ONLINE_PLUS_PROMO_BADGE: str = "Бесплатное обслуживание"
    CARD_ONLINE_PLUS_PROMO_PAYS: str = "Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр."
    CARD_ONLINE_PLUS_PROMO_BIN: str = "США"
    CARD_PAY_PROMO_TITLE: str = "Pay"
    CARD_PAY_PROMO_DESC: str = "Универсальная карта для международных оплат и подписок"
    CARD_PAY_PROMO_BADGE: str = "Бесплатное обслуживание"
    CARD_PAY_PROMO_PAYS: str = "Booking, Airbnb, Zoom, Google One, Spotify, YouTube, покупки в магазинах и пр."
    CARD_PAY_PROMO_BIN: str = "США"

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
    # Funded parent client used to transfer funds to per-user clients.
    # Empty default on purpose: falls back to OPLATA_TEST_CLIENT_ID, then "Developer"
    # (see _parent_client_id) — a non-empty default here silently shadowed the .env value.
    OPLATA_PARENT_CLIENT_ID: str = ""
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
