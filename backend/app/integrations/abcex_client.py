import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://gateway.abcex.io"

# Maps frontend network label → ABCEX networkId
_NETWORK_ID = {
    "TRC-20": "TRX",
    "ERC-20": "ETH",
}

# Single USDT wallet — same walletId used for all networks, only networkId varies
_usdt_wallet_id: Optional[str] = None


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.ABCEX_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _get(path: str, params: Optional[Dict] = None) -> Any:
    url = f"{_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=_headers(), params=params)
        if r.status_code >= 400:
            logger.error("ABCEX GET %s -> %s | %s", url, r.status_code, r.text[:500])
            r.raise_for_status()
        return r.json()


async def get_wallets() -> List[Dict]:
    """Return all user wallets from ABCEX."""
    data = await _get("/api/v1/wallets/balances")
    if isinstance(data, list):
        return data
    # Some APIs wrap in data/items
    return data.get("data") or data.get("items") or data.get("wallets") or []


async def get_usdt_wallet_id() -> str:
    """Find and cache the single USDT wallet ID used for address generation."""
    global _usdt_wallet_id
    if _usdt_wallet_id:
        return _usdt_wallet_id

    wallets = await get_wallets()
    logger.info(
        "ABCEX wallets: %s",
        [{k: w.get(k) for k in ("id", "currencyId", "networkId", "type")} for w in wallets[:10]],
    )

    # Primary: prefer type=user USDT wallet
    for w in wallets:
        w_type = (w.get("type") or "").lower()
        currency = (w.get("currencyId") or w.get("currency") or "").upper()
        if w_type == "user" and currency == "USDT":
            _usdt_wallet_id = str(w["id"])
            logger.info("Found USDT user wallet: %s", _usdt_wallet_id)
            return _usdt_wallet_id

    # Fallback: any USDT wallet regardless of type
    for w in wallets:
        currency = (w.get("currencyId") or w.get("currency") or "").upper()
        if currency == "USDT":
            _usdt_wallet_id = str(w["id"])
            logger.warning("Using fallback USDT wallet (type=%s): %s", w.get("type"), _usdt_wallet_id)
            return _usdt_wallet_id

    raise ValueError("USDT wallet not found in ABCEX account")


async def generate_address(network_label: str = "TRC-20") -> str:
    """Generate a new USDT deposit address for the given network (TRC-20/ERC-20)."""
    network_id = _NETWORK_ID.get(network_label, "TRX")
    wallet_id = await get_usdt_wallet_id()
    data = await _get(
        "/api/v1/wallet/get-new-crypto-address",
        params={"walletId": wallet_id, "networkId": network_id},
    )
    if isinstance(data, list):
        for item in data:
            if item.get("network", "").upper() == network_id:
                return item["address"]
        if data:
            return data[0]["address"]
    if isinstance(data, dict):
        return data.get("address") or data.get("data", {}).get("address") or ""
    raise ValueError(f"Unexpected address response for {network_label}: {data}")


async def generate_trc_address() -> str:
    """Backwards-compatible wrapper — generates TRC-20 address."""
    return await generate_address("TRC-20")


async def get_transactions(limit: int = 200, page: int = 1) -> List[Dict]:
    """Fetch incoming transactions from ABCEX."""
    data = await _get(
        "/api/v1/wallet/transactions/list/my",
        params={"page": page, "limit": limit},
    )
    if isinstance(data, list):
        return data
    return data.get("data") or []
