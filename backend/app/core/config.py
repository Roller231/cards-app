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
    AIFORY_ACCESS_COOKIE: str = "dIGWxRgXSj7b6MZqy1BziEehUF_LKr49ciKsBKMT6RuO5y3HfAG0nsvBnVD_ubUE2t_xWiyvSaHgW3VKpP4rxFdQIhM_9g16xw0HNd4UgJxLflszSmBtz_Ob0TYx"
    AIFORY_REFRESH_COOKIE: str = "PVx0wXNJv0qoT3ZnFWUXb5Ixcau26g9yiWJuSBZRl5bw_d0ee8yR0TJKWJY_tbKH7az_glqvEJIA7TphCsqpIiI0jV9QbC3cSF_vDkpMilAOzlKlWmNisMOaNJ1H"
    AIFORY_EXTRA_COOKIES: str = "sse=d30dee19-efe8-470b-b034-7d9c96c5f655; spid=1773565218774_30458c2d9978729217cf85165287a4e2_koefp1ukwj6ogw8d; spsc=1773777536373_463f58f171e00a0275e708421e777598_WVpSAeiIeGHBHhv9x2h85Q15inwuZFOJWlZrJ.FmZY8Z; _ym_visorc=w; signInToken=be23cf02-5bce-41c0-b440-b7ec42f127b1;"
    # Optional: set the ENTIRE Cookie header value from Postman here to bypass WAF (overrides the 3 above)
    AIFORY_RAW_COOKIE: str = "access=dIGWxRgXSj7b6MZqy1BziEehUF_LKr49ciKsBKMT6RuO5y3HfAG0nsvBnVD_ubUE2t_xWiyvSaHgW3VKpP4rxFdQIhM_9g16xw0HNd4UgJxLflszSmBtz_Ob0TYx; refresh=PVx0wXNJv0qoT3ZnFWUXb5Ixcau26g9yiWJuSBZRl5bw_d0ee8yR0TJKWJY_tbKH7az_glqvEJIA7TphCsqpIiI0jV9QbC3cSF_vDkpMilAOzlKlWmNisMOaNJ1H;; spid=1773695097082_c88c08f9d815436afff01669be3352d3_fv0outk9gmm2boko; spsc=1773778614796_5cba730e6eece71bd492e1a476ae1047_RfTORy1yB1lHO3xWOEhmQJCWpID-kAlA5TNUM.7kxeAZ"

    CARD_ISSUE_MARKUP_PERCENT: float = 0.0
    CARD_TOPUP_MARKUP_PERCENT: float = 0.0

    class Config:
        env_file = ".env"


settings = Settings()
