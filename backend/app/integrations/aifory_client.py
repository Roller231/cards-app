"""
Aifory API client with cookie-based auth, TOTP 2FA, PIN finalize, and auto-relogin on 401.
All requests go through the single parent Aifory account configured in .env.
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
import pyotp

from app.core.config import settings

_COOKIE_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".aifory_session.json")

logger = logging.getLogger(__name__)


class AiforyAuthError(Exception):
    pass


class AiforyClient:
    def __init__(self):
        self._base_url = settings.AIFORY_BASE_URL.rstrip("/")
        # Ensure API prefix starts with a single leading slash, empty if not provided
        api_prefix = (settings.AIFORY_API_PREFIX or "").strip()
        if api_prefix and not api_prefix.startswith("/"):
            api_prefix = "/" + api_prefix
        self._api_prefix = api_prefix.rstrip("/")
        self._email = settings.AIFORY_EMAIL
        self._password = settings.AIFORY_PASSWORD
        self._pin = settings.AIFORY_PIN
        self._totp_secret = settings.AIFORY_TOTP_SECRET
        # Cookies set by Aifory (from Set-Cookie headers)
        self._access_cookie: Optional[str] = None
        self._refresh_cookie: Optional[str] = None
        self._lock = asyncio.Lock()
        # Try to restore cookies from last session to avoid re-login on restart
        self._load_cookies_from_disk()
        # If developer provided cookies via environment, prefer them
        if settings.AIFORY_ACCESS_COOKIE:
            self._access_cookie = settings.AIFORY_ACCESS_COOKIE
        if settings.AIFORY_REFRESH_COOKIE:
            self._refresh_cookie = settings.AIFORY_REFRESH_COOKIE
        if self._access_cookie:
            logger.info("Aifory: using pre-configured cookies from env/disk")

    def _load_cookies_from_disk(self) -> None:
        """Load cached cookies from disk to survive server restarts."""
        try:
            if os.path.exists(_COOKIE_CACHE_FILE):
                with open(_COOKIE_CACHE_FILE, "r") as f:
                    data = json.load(f)
                self._access_cookie = data.get("access")
                self._refresh_cookie = data.get("refresh")
                if self._access_cookie:
                    logger.info("Aifory: restored session cookies from disk cache")
        except Exception:
            pass

    def _save_cookies_to_disk(self) -> None:
        """Persist cookies to disk so restarts don't trigger a new login."""
        try:
            with open(_COOKIE_CACHE_FILE, "w") as f:
                json.dump({"access": self._access_cookie, "refresh": self._refresh_cookie}, f)
        except Exception:
            pass

    def _default_headers(self) -> Dict[str, str]:
        """Headers to mimic browser requests and pass common WAF checks."""
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://srv.aifory.pro",
            "Referer": "https://srv.aifory.pro/lk/",
            "X-Requested-With": "XMLHttpRequest",
            # Hints some WAFs expect from browsers
            "sec-ch-ua": '"Chromium";v="122", "Google Chrome";v="122", "Not.A/Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            # Redundant but sometimes validated by strict WAFs
            "Host": "srv.aifory.pro",
        }

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self) -> None:
        """Full cookie-based login flow using v1/auth/client endpoints."""
        # If manual cookies are configured (via env), skip login entirely
        manual_mode = bool(getattr(settings, "AIFORY_ACCESS_COOKIE", "") or getattr(settings, "AIFORY_REFRESH_COOKIE", ""))
        if manual_mode and self._access_cookie:
            logger.info("Aifory: manual-cookie mode active, skipping login()")
            return
        async with httpx.AsyncClient(headers=self._default_headers(), timeout=30, http2=True) as client:
            # Step 1 – request
            r1 = await client.post(
                f"{self._base_url}/v1/auth/client/sign-in/request",
                json={"login": self._email, "password": self._password},
            )
            if r1.status_code == 403:
                raise AiforyAuthError(
                    "403 Forbidden on sign-in/request. Check AIFORY_BASE_URL, network/WAF, "
                    "and that required headers are accepted from this host."
                )
            r1.raise_for_status()

            # Step 2 – confirm with TOTP (confirmationCode + login)
            totp_code = pyotp.TOTP(self._totp_secret).now() if self._totp_secret else "000000"
            r2 = await client.post(
                f"{self._base_url}/v1/auth/client/sign-in/confirm",
                json={"confirmationCode": totp_code, "login": self._email},
            )
            r2.raise_for_status()

            # Step 3 – finalize with PIN (PIN only)
            r3 = await client.post(
                f"{self._base_url}/v1/auth/client/sign-in/finalize",
                json={"PIN": self._pin},
            )
            r3.raise_for_status()

            # Extract cookies (access, refresh) from Set-Cookie
            self._access_cookie = r3.cookies.get("access") or client.cookies.get("access")
            self._refresh_cookie = r3.cookies.get("refresh") or client.cookies.get("refresh")

        if not self._access_cookie:
            # As a fallback, inspect headers (not ideal but helpful for debugging)
            raise AiforyAuthError("Login succeeded but no 'access' cookie found in response")

        logger.info("Aifory login successful (cookies acquired)")
        self._save_cookies_to_disk()

    async def _refresh_access_token(self) -> None:
        """Perform full login again to refresh cookies."""
        await self.login()

    async def _ensure_authenticated(self) -> None:
        async with self._lock:
            if not self._access_cookie:
                await self.login()

    def _cookie_headers(self) -> Dict[str, str]:
        # If the developer provided the full Cookie header, use it verbatim
        raw_cookie = (getattr(settings, "AIFORY_RAW_COOKIE", "") or "").strip()
        if raw_cookie:
            return {"Cookie": raw_cookie}
        cookies: List[str] = []
        if self._access_cookie:
            cookies.append(f"access={self._access_cookie}")
        if self._refresh_cookie:
            cookies.append(f"refresh={self._refresh_cookie}")
        extra = getattr(settings, "AIFORY_EXTRA_COOKIES", "") or ""
        extra = extra.strip()
        if extra:
            # Expecting format like: "sse=...; spid=...; spsc=..."
            cookies.append(extra)
        return {"Cookie": "; ".join(cookies)} if cookies else {}

    # ------------------------------------------------------------------
    # Generic request with auto-relogin on 401
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Any = None,
        retried: bool = False,
    ) -> Any:
        await self._ensure_authenticated()
        # Prefix with /v1 (or configured) for all non-auth API calls
        url = f"{self._base_url}{self._api_prefix}{path}"
        async with httpx.AsyncClient(timeout=30, headers=self._default_headers(), http2=True) as client:
            r = await client.request(
                method,
                url,
                headers={**self._default_headers(), **self._cookie_headers()},
                json=json,
                params=params,
            )
        if r.status_code == 401 and not retried:
            # If manual cookies are configured, do NOT attempt login to avoid WAF blocks.
            manual_mode = bool(getattr(settings, "AIFORY_ACCESS_COOKIE", "") or getattr(settings, "AIFORY_REFRESH_COOKIE", ""))
            if manual_mode:
                logger.error("Aifory 401 with manual cookies: please update AIFORY_*_COOKIE values from Postman")
                r.raise_for_status()
            logger.info("Received 401, attempting re-login")
            async with self._lock:
                self._access_cookie = None
                await self._refresh_access_token()
            return await self._request(method, path, json=json, params=params, retried=True)
        if r.status_code >= 400:
            try:
                err_payload = r.json()
            except Exception:
                err_payload = r.text
            logger.error("Aifory error %s %s -> %s | payload=%s", r.status_code, method, url, err_payload)
            r.raise_for_status()
        
        if r.content:
            return r.json()
        return {}

    async def _request_multi(
        self,
        method: str,
        paths: List[str],
        *,
        json: Any = None,
        params: Any = None,
    ) -> Any:
        """Try multiple endpoint paths until one succeeds.
        Primarily used to switch between '/client/...'
        and non-client variants depending on deployment.
        """
        last_exc: Optional[Exception] = None
        for idx, path in enumerate(paths):
            try:
                return await self._request(method, path, json=json, params=params)
            except httpx.HTTPStatusError as e:  # type: ignore[name-defined]
                status = e.response.status_code if e.response is not None else None
                # Try next path on 404/405
                if status in (404, 405) and idx < len(paths) - 1:
                    last_exc = e
                    continue
                raise
            except Exception as e:
                last_exc = e
                if idx < len(paths) - 1:
                    continue
                raise last_exc
        # Should not reach here
        raise last_exc or RuntimeError("All endpoint variants failed")

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    async def get_accounts(self) -> List[Dict]:
        """POST /accounts – list parent account wallets (requires POST with empty JSON)."""
        result = await self._request_multi("POST", ["/client/accounts", "/accounts"], json={})
        if isinstance(result, list):
            return result
        # Aifory returns {ungroupedWallets: [...], groups: [...]}
        wallets = result.get("ungroupedWallets", [])
        # Flatten: extract accounts from each wallet
        accounts = []
        for wallet in wallets:
            wallet_accounts = wallet.get("accounts", [])
            if wallet_accounts:
                accounts.extend(wallet_accounts)
            else:
                # If no sub-accounts, use the wallet itself as an account
                accounts.append({
                    "id": wallet.get("id"),
                    "currencyID": wallet.get("currencyID"),
                    "currencyName": wallet.get("currencyName"),
                    "balance": wallet.get("balance"),
                })
        return accounts

    # ------------------------------------------------------------------
    # Card Offers
    # ------------------------------------------------------------------

    async def get_card_offers_simple(self) -> List[Dict]:
        """POST /virtual-cards/cards/offers – available card products."""
        result = await self._request("POST", "/virtual-cards/cards/offers", json={})
        if isinstance(result, list):
            return result
        return result.get("offers") or result.get("data") or []

    async def get_card_offers(self, account_id: str) -> List[Dict]:
        """POST /virtual-cards/cards/offers – available card products."""
        # The API doesn't seem to need account_id for offers, just call simple version
        return await self.get_card_offers_simple()

    # ------------------------------------------------------------------
    # Card Orders
    # ------------------------------------------------------------------

    async def calculate_card_order(
        self,
        account_id: str,
        offer_id: str,
        amount: float,
        *,
        account_id_to_exchange: str,
        validate_key: str,
    ) -> Dict:
        """POST /virtual-cards/calculate-order – fee preview."""
        payload: Dict[str, Any] = {
            "bin": offer_id,
            "amount": str(amount),
            "accountID": account_id,
            "accountIDToExchange": account_id_to_exchange,
            "validateKey": validate_key,
        }
        return await self._request(
            "POST",
            "/virtual-cards/calculate-order",
            json=payload,
        )

    async def create_card_order(
        self,
        account_id: str,
        offer_id: str,
        amount: float,
        *,
        account_id_to_exchange: str,
        validate_key: str,
    ) -> Dict:
        """POST /virtual-cards/order – issue a new virtual card."""
        payload: Dict[str, Any] = {
            "bin": offer_id,
            "accountID": account_id,
            "accountIDToExchange": account_id_to_exchange,
            "validateKey": validate_key,
            "amount": str(amount),
            "email": self._email,
            "code": (pyotp.TOTP(self._totp_secret).now() if self._totp_secret else "000000"),
        }
        return await self._request(
            "POST",
            "/virtual-cards/order",
            json=payload,
        )

    # ------------------------------------------------------------------
    # Cards
    # ------------------------------------------------------------------

    async def get_cards(self, account_id: str) -> List[Dict]:
        """POST /virtual-cards/cards/get – list all cards on the parent account."""
        result = await self._request("POST", "/virtual-cards/cards/get", json={})
        if isinstance(result, list):
            return result
        return result.get("cards") or result.get("data") or []

    async def get_card_requisites(self, card_id: str) -> Dict:
        """POST /virtual-cards/cards/requisites – PAN, expiry, CVV."""
        return await self._request("POST", "/virtual-cards/cards/requisites", json={"cardID": card_id})

    # ------------------------------------------------------------------
    # Deposit (top-up card balance)
    # ------------------------------------------------------------------

    async def get_deposit_offers(self, account_id: str, card_id: str) -> List[Dict]:
        """POST /virtual-cards/deposit/offer – deposit methods for a card."""
        result = await self._request(
            "POST",
            "/virtual-cards/deposit/offer",
            json={"cardID": card_id},
        )
        if isinstance(result, list):
            return result
        return result.get("offers") or result.get("data") or [result]  # Single offer response

    async def calculate_deposit_order(
        self,
        account_id: str,
        card_id: str,
        amount: float,
        *,
        account_id_to_exchange: str,
        validate_key: str,
    ) -> Dict:
        """POST /virtual-cards/deposit/calculate-order – fee preview for deposit."""
        return await self._request(
            "POST",
            "/virtual-cards/deposit/calculate-order",
            json={
                "cardID": card_id,
                "amount": str(amount),
                "accountID": account_id,
                "accountIDToExchange": account_id_to_exchange,
                "validateKey": validate_key,
            },
        )

    async def create_deposit_order(
        self,
        account_id: str,
        card_id: str,
        amount: float,
        *,
        account_id_to_exchange: str,
        validate_key: str,
    ) -> Dict:
        """POST /virtual-cards/deposit/order – create a card top-up order."""
        return await self._request(
            "POST",
            "/virtual-cards/deposit/order",
            json={
                "cardID": card_id,
                "amount": str(amount),
                "accountID": account_id,
                "accountIDToExchange": account_id_to_exchange,
                "validateKey": validate_key,
                "code": (pyotp.TOTP(self._totp_secret).now() if self._totp_secret else "000000"),
            },
        )

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def get_order_details(self, order_id: str) -> Dict:
        """POST /virtual-cards/common/details – order status and details."""
        return await self._request("POST", "/virtual-cards/common/details", json={"orderID": order_id})

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    async def get_card_transactions(self, card_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        """POST /virtual-cards/common/card-transactions – transaction history for a card."""
        result = await self._request(
            "POST",
            "/virtual-cards/common/card-transactions",
            json={"cardID": card_id, "limit": limit, "offset": offset},
        )
        if isinstance(result, list):
            return result
        return result.get("transactions") or result.get("data") or []

    async def get_card_transaction_details(self, card_id: str, transaction_id: str) -> Dict:
        """POST /virtual-cards/common/card-transaction-details."""
        return await self._request(
            "POST",
            "/virtual-cards/common/card-transaction-details",
            json={"cardID": card_id, "transactionID": transaction_id},
        )

    # ------------------------------------------------------------------
    # Payment systems / countries
    # ------------------------------------------------------------------

    async def get_payment_systems(self) -> List[Dict]:
        result = await self._request("POST", "/virtual-cards/common/payment-systems", json={})
        if isinstance(result, list):
            return result
        return result.get("systems") or result.get("data") or []

    async def get_countries(self) -> List[Dict]:
        result = await self._request("POST", "/virtual-cards/common/countries", json={})
        if isinstance(result, list):
            return result
        return result.get("countries") or result.get("data") or []


# Singleton instance used across the app
aifory_client = AiforyClient()
