"""App exchange rate (RUB per USD) shared by the SBP router and the
balance-payment paths.

rate = [Bitbanker index] x (1 + %BB) x (1 + %ours) x (1 + %Clarus)

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


def apply_multipliers(index: float) -> float:
    return (
        index
        * (1 + settings.SBP_BITBANKER_FEE_PERCENT / 100)
        * (1 + settings.SBP_OUR_FEE_PERCENT / 100)
        * (1 + settings.SBP_CLARUS_FEE_PERCENT / 100)
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


async def get_app_rate(force: bool = False) -> float:
    """RUB per 1 USD as charged in the app (4-decimal precision)."""
    return round(apply_multipliers(await get_bb_index(force)), 4)
