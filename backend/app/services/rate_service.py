"""App exchange rate (RUB per USD) shared by the SBP router and the
balance-payment paths.

rate = [Bitbanker index] x (1 + SBP %) x (1 + top-up fee of the card type)

The top-up fee per card type is set directly in the admin panel ("Витрина
карт"): ONLINE_TOPUP_MARKUP_PERCENT for O-Plata cards, UNIV_TOPUP_MARKUP_PERCENT
for Rocketpay "Pay" cards. The cost settings (our %, Bitbanker conversion,
Clarus, Rocketpay pool) don't change the price any more — they only describe
what a top-up costs us.

The same number the user sees in the app: SBP payments and internal-balance
prices (card issuance = RUB price / rate) must agree, so both use this helper.
Cached for a short while so a burst of quotes doesn't hammer Bitbanker.
"""
import logging
import time

from app.core.config import settings
from app.integrations.bitbanker_client import bitbanker_client

logger = logging.getLogger(__name__)

_cache = {"at": 0.0, "index": 0.0}
_TTL_S = 60.0


class RateUnavailable(Exception):
    pass


PROVIDERS = ("oplata", "rocketpay")


def provider_fee_percent(provider: str = "oplata") -> float:
    """The partner leg of the route: Clarus for O-Plata cards, Rocketpay's
    USDT pool top-up price for Rocketpay ("Pay") cards."""
    if provider == "rocketpay":
        return float(settings.ROCKETPAY_POOL_FEE_PERCENT or 0)
    return float(settings.SBP_CLARUS_FEE_PERCENT or 0)


def topup_fee_percent(provider: str = "oplata") -> float:
    """"Комиссия за пополнение" (everything after the SBP fee) of a card type,
    straight from the admin panel."""
    if provider == "rocketpay":
        return round(float(settings.UNIV_TOPUP_MARKUP_PERCENT or 0), 2)
    return round(float(settings.ONLINE_TOPUP_MARKUP_PERCENT or 0), 2)


def apply_multipliers(index: float, provider: str = "oplata") -> float:
    return (
        index
        * (1 + settings.SBP_BITBANKER_FEE_PERCENT / 100)
        * (1 + topup_fee_percent(provider) / 100)
    )


async def get_bb_index(force: bool = False) -> float:
    """Bitbanker's approximate USDT->RUB index for a 10 000 RUB exchange."""
    now = time.time()
    if not force and _cache["index"] > 0 and now - _cache["at"] < _TTL_S:
        return _cache["index"]
    try:
        pred = await bitbanker_client.get_exchange_prediction(10000)
        index = float(pred.get("approximate_rate") or 0)
    except Exception as exc:
        logger.warning("[RATE] exchange prediction failed: %s", str(exc)[:200])
        index = 0.0
    if index <= 0:
        if _cache["index"] > 0 and now - _cache["at"] < 15 * 60:
            return _cache["index"]  # short-lived stale fallback
        raise RateUnavailable("Курс временно недоступен. Попробуйте позже.")
    _cache.update(at=now, index=index)
    return index


async def get_app_rate(force: bool = False, provider: str = "oplata") -> float:
    """RUB per 1 USD as charged in the app (4-decimal precision)."""
    return round(apply_multipliers(await get_bb_index(force), provider), 4)
