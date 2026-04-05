"""
Aifory API client with cookie-based auth, TOTP 2FA, PIN finalize, and auto-relogin on 401.
All requests go through the single parent Aifory account configured in .env.
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from curl_cffi import requests
import pyotp

from app.core.config import settings

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
        self._cookie_jar: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._cookie_file = settings.AIFORY_COOKIE_FILE
        self._load_cookies()
        # TLS/browser fingerprint impersonation (curl_cffi)
        # Can be configured via env AIFORY_IMPERSONATE; when empty => no impersonation
        self._impersonate: Optional[str] = (settings.AIFORY_IMPERSONATE or None)
        self._impersonate_candidates: List[str] = [
            "chrome124",
            "chrome123",
            "chrome110",
            "chrome120",
            "edge101",
            "safari17_0",
        ]

    def _default_headers(self) -> Dict[str, str]:
        """Minimal Postman-like headers to avoid WAF heuristics."""
        return {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "ru,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Host": "srv.aifory.pro",
            "Origin": "https://srv.aifory.pro",
            "Referer": "https://srv.aifory.pro/lk/",
        }

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self, code_override: Optional[str] = None) -> None:
        """Full cookie-based login flow using v1/auth/client endpoints with curl_cffi."""
        # Create session with existing cookies
        session = requests.Session()
        
        # Set cookies from jar
        for name, value in self._cookie_jar.items():
            session.cookies.set(name, value)
        # На время логина не отправляем старые access/refresh, чтобы не ломать новую сессию входа
        session.cookies.pop("access", None)
        session.cookies.pop("refresh", None)
        # Также удалим потенциально протухший signInToken, чтобы получить свежий на request
        session.cookies.pop("signInToken", None)
        
        try:
            # Warm-up: GET base page to obtain anti-bot/session cookies (like CF/WAF)
            try:
                _ = self._session_request(session, "GET", f"{self._base_url}/", headers=self._default_headers(), timeout=30)
                self._update_cookies_from_session(session)
                # No raise_for_status here; some WAF pages may respond 403/200 with HTML – we just want cookies
            except Exception:
                pass
            # Warm-up 2: GET /lk/ explicitly
            try:
                _ = self._session_request(session, "GET", f"{self._base_url}", headers=self._default_headers(), timeout=30)
                self._update_cookies_from_session(session)
            except Exception:
                pass

            # Step 1 – request
            base_headers = self._default_headers()
            r1 = self._session_request(
                session,
                "POST",
                f"{self._base_url}/v1/auth/client/sign-in/request",
                headers=base_headers,
                timeout=30,
                json={"login": self._email, "password": self._password},
            )
            if r1.status_code == 403:
                raise AiforyAuthError(
                    "403 Forbidden on sign-in/request. Check AIFORY_BASE_URL, network/WAF, "
                    "and that required headers are accepted from this host."
                )
            self._update_cookies_from_session(session)
            self._update_cookies_from_headers(r1)
            self._log_resp("sign-in/request", r1)
            r1.raise_for_status()

            # Debug: log cookie names after request
            try:
                cookie_names = [c.name for c in session.cookies]
                logger.info("Aifory cookies after request: %s", cookie_names)
            except Exception:
                pass

            # Step 2 – confirm with TOTP (confirmationCode + login)
            totp_code = (code_override or (pyotp.TOTP(self._totp_secret).now() if self._totp_secret else "000000"))
            base_headers = self._default_headers()
            r2 = self._session_request(
                session,
                "POST",
                f"{self._base_url}/v1/auth/client/sign-in/confirm",
                headers=base_headers,
                timeout=30,
                json={"confirmationCode": totp_code, "login": self._email},
            )
            self._update_cookies_from_session(session)
            self._update_cookies_from_headers(r2)
            self._log_resp("sign-in/confirm", r2)
            if r2.status_code == 400:
                # Try to detect session expired and redo request->confirm quickly
                try:
                    data = r2.json()
                except Exception:
                    data = None
                if isinstance(data, dict) and data.get("message") == "LOG_IN_SESSION_EXPIRED":
                    logger.info("Aifory: login session expired on confirm, retrying request->confirm once")
                    # redo request step to refresh temporary sign-in session cookies
                    base_headers = self._default_headers()
                    r1b = self._session_request(
                        session,
                        "POST",
                        f"{self._base_url}/v1/auth/client/sign-in/request",
                        headers=base_headers,
                        timeout=30,
                        json={"login": self._email, "password": self._password},
                    )
                    self._update_cookies_from_session(session)
                    self._update_cookies_from_headers(r1b)
                    self._log_resp("sign-in/request(retry)", r1b)
                    r1b.raise_for_status()
                    # confirm again with the same code
                    r2b = self._session_request(
                        session,
                        "POST",
                        f"{self._base_url}/v1/auth/client/sign-in/confirm",
                        headers=base_headers,
                        timeout=30,
                        json={"confirmationCode": totp_code, "login": self._email},
                    )
                    self._update_cookies_from_session(session)
                    self._update_cookies_from_headers(r2b)
                    self._log_resp("sign-in/confirm(retry)", r2b)
                    r2b.raise_for_status()
                else:
                    r2.raise_for_status()
            else:
                r2.raise_for_status()

            # Step 3 – finalize with PIN (PIN only)
            base_headers = self._default_headers()
            r3 = self._session_request(
                session,
                "POST",
                f"{self._base_url}/v1/auth/client/sign-in/finalize",
                headers=base_headers,
                timeout=30,
                json={"PIN": self._pin},
            )
            self._update_cookies_from_session(session)
            self._update_cookies_from_headers(r3)
            self._log_resp("sign-in/finalize", r3, log_headers=True)
            r3.raise_for_status()

        finally:
            session.close()

        if not (self._cookie_jar.get("access") or self._access_cookie):
            # As a fallback, inspect headers (not ideal but helpful for debugging)
            raise AiforyAuthError("Login succeeded but no 'access' cookie found in response")

        logger.info("Aifory login successful (cookies acquired)")

    async def _refresh_access_token(self) -> None:
        """Perform full login again to refresh cookies."""
        await self.login()

    async def _ensure_authenticated(self) -> None:
        async with self._lock:
            if not (self._cookie_jar.get("access") or self._access_cookie):
                await self.login()

    def _cookie_headers(self) -> Dict[str, str]:
        # Prefer full cookie jar (access/refresh/sse/others). Fallback to legacy fields.
        parts: List[str] = []
        if self._cookie_jar:
            for k, v in self._cookie_jar.items():
                parts.append(f"{k}={v}")
        else:
            if self._access_cookie:
                parts.append(f"access={self._access_cookie}")
            if self._refresh_cookie:
                parts.append(f"refresh={self._refresh_cookie}")
        return {"Cookie": "; ".join(parts)} if parts else {}

    def _update_cookies_from_session(self, session: requests.Session) -> None:
        """Merge cookies from curl_cffi session into our in-memory jar."""
        try:
            for cookie in session.cookies:
                if cookie.value is None:
                    continue
                self._cookie_jar[cookie.name] = cookie.value
                if cookie.name == "access":
                    self._access_cookie = cookie.value
                elif cookie.name == "refresh":
                    self._refresh_cookie = cookie.value
        except Exception:
            # Be resilient to any cookie parsing issues
            pass
        # Persist to disk after each update
        self._save_cookies()

    # -------------------------
    # Debug helpers
    # -------------------------
    def _resp_preview(self, response) -> str:
        try:
            j = response.json()
            return json.dumps(j)[:500]
        except Exception:
            try:
                return (response.text or "")[:500]
            except Exception:
                return "<no-preview>"

    def _log_resp(self, label: str, response, *, log_headers: bool = False) -> None:
        try:
            preview = self._resp_preview(response)
            logger.info("Aifory %s response preview: %s", label, preview)
            # Log Set-Cookie lines explicitly if present
            try:
                for k, v in getattr(response, "headers", {}).items():
                    if str(k).lower() == "set-cookie":
                        logger.info("Aifory %s Set-Cookie: %s", label, v)
            except Exception:
                pass
            if log_headers:
                try:
                    headers_dict = {str(k): str(v) for k, v in getattr(response, "headers", {}).items()}
                    logger.info("Aifory %s headers: %s", label, headers_dict)
                except Exception:
                    pass
        except Exception:
            pass

    def _update_cookies_from_headers(self, response) -> None:
        """Parse Set-Cookie headers manually to capture access/refresh even if session jar missed them."""
        try:
            # Collect all set-cookie header values
            for k, v in getattr(response, "headers", {}).items():
                if str(k).lower() == "set-cookie":
                    # Parse multiple cookies in single Set-Cookie header (comma-separated)
                    cookie_parts = str(v).split(", ")
                    for part in cookie_parts:
                        # Each part is "name=value; attributes..."
                        if "=" in part:
                            cookie_def = part.split(";")[0].strip()  # Take only "name=value"
                            if "=" in cookie_def:
                                name, value = cookie_def.split("=", 1)
                                name = name.strip()
                                value = value.strip()
                                if name == "access":
                                    self._access_cookie = value
                                    self._cookie_jar["access"] = value
                                    logger.info("Aifory: extracted access cookie: %s", value[:20] + "...")
                                elif name == "refresh":
                                    self._refresh_cookie = value
                                    self._cookie_jar["refresh"] = value
                                    logger.info("Aifory: extracted refresh cookie: %s", value[:20] + "...")
                                elif name == "sse":
                                    self._cookie_jar["sse"] = value
                                    logger.info("Aifory: extracted sse cookie: %s", value)
        except Exception:
            pass
        self._save_cookies()

    def _select_impersonation(self, session: requests.Session) -> None:
        """If env set, keep it; otherwise try candidates until one works; if none, disable impersonation."""
        if self._impersonate:
            # Respect explicit config
            return
        for candidate in self._impersonate_candidates:
            try:
                _ = session.get(
                    f"{self._base_url}/",
                    headers=self._default_headers(),
                    timeout=10,
                    impersonate=candidate,
                )
                self._impersonate = candidate
                logger.info("Aifory: selected impersonation profile: %s", candidate)
                return
            except Exception:
                continue
        self._impersonate = None

    def _session_request(self, session: requests.Session, method: str, url: str, **kwargs):
        """Perform a request with optional impersonation; if unsupported, retry without it once."""
        # Clean kwargs: don't send json/params if None to avoid invalid bodies
        if kwargs.get("json", None) is None:
            kwargs.pop("json", None)
        if kwargs.get("params", None) is None:
            kwargs.pop("params", None)
        use_imp = self._impersonate
        if use_imp:
            try:
                kwargs["impersonate"] = use_imp
                resp = session.request(method, url, **kwargs)
                # Brief debug log
                logger.info("Aifory %s %s -> %s", method, url, resp.status_code)
                if resp.status_code >= 400:
                    preview = resp.text[:300] if isinstance(resp.text, str) else str(resp.text)[:300]
                    logger.error("Aifory error body preview: %s", preview)
                return resp
            except Exception as e:
                msg = str(e)
                if "Impersonating" in msg and "not supported" in msg:
                    logger.warning("Aifory: impersonation %s not supported, retrying without it", use_imp)
                    self._impersonate = None
                    kwargs.pop("impersonate", None)
                    resp = session.request(method, url, **kwargs)
                    logger.info("Aifory %s %s -> %s (no impersonation)", method, url, resp.status_code)
                    if resp.status_code >= 400:
                        preview = resp.text[:300] if isinstance(resp.text, str) else str(resp.text)[:300]
                        logger.error("Aifory error body preview: %s", preview)
                    return resp
                raise
        # No impersonation
        resp = session.request(method, url, **kwargs)
        logger.info("Aifory %s %s -> %s", method, url, resp.status_code)
        if resp.status_code >= 400:
            preview = resp.text[:300] if isinstance(resp.text, str) else str(resp.text)[:300]
            logger.error("Aifory error body preview: %s", preview)
        return resp

    def _update_cookies(self, response) -> None:
        """Legacy method - kept for compatibility but not used with curl_cffi."""
        pass

    def _load_cookies(self) -> None:
        try:
            if self._cookie_file and os.path.exists(self._cookie_file):
                with open(self._cookie_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._cookie_jar.update({str(k): str(v) for k, v in data.items()})
                    # Sync legacy fields for backward compatibility
                    if "access" in self._cookie_jar:
                        self._access_cookie = self._cookie_jar.get("access")
                    if "refresh" in self._cookie_jar:
                        self._refresh_cookie = self._cookie_jar.get("refresh")
        except Exception:
            # Ignore cookie load errors to avoid blocking startup
            pass

    def _save_cookies(self) -> None:
        try:
            if not self._cookie_file:
                return
            with open(self._cookie_file, "w", encoding="utf-8") as f:
                json.dump(self._cookie_jar, f, ensure_ascii=False, indent=2)
        except Exception:
            # Ignore save errors silently (non-critical)
            pass

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
        
        # Create session with cookies
        session = requests.Session()
        for name, value in self._cookie_jar.items():
            session.cookies.set(name, value)
        
        try:
            headers = self._default_headers()
            r = self._session_request(
                session,
                method,
                url,
                headers=headers,
                timeout=30,
                json=json,
                params=params,
            )
            
            # Update cookies from response
            self._update_cookies_from_session(session)

            if r.status_code == 401 and not retried:
                logger.info("Received 401, attempting re-login")
                async with self._lock:
                    self._access_cookie = None
                    self._cookie_jar.pop("access", None)
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
            
        finally:
            session.close()

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
        """List parent account wallets.
        Порядок попыток:
        1) POST /accounts (без client)
        2) POST /client/accounts
        3) GET  /accounts
        """
        # Try POST /accounts first (as per latest hint)
        try:
            result = await self._request("POST", "/accounts", json={})
        except Exception:
            # Fallback to POST /client/accounts
            try:
                result = await self._request("POST", "/client/accounts", json={})
            except Exception:
                # Final fallback: GET /accounts
                result = await self._request("GET", "/accounts")

        if isinstance(result, list):
            return result
        # Aifory returns {ungroupedWallets: [...], groups: [...]} в некоторых версиях
        wallets = result.get("ungroupedWallets", [])
        accounts: List[Dict] = []
        for wallet in wallets:
            wallet_accounts = wallet.get("accounts", [])
            if wallet_accounts:
                accounts.extend(wallet_accounts)
            else:
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
        """POST /virtual-cards/calculate-order – fee preview for card issuance."""
        return await self._request(
            "POST",
            "/virtual-cards/calculate-order",
            json={
                "bin": offer_id,
                "amount": str(amount),
                "accountID": account_id,
                "accountIDToExchange": account_id_to_exchange,
                "validateKey": validate_key,
            },
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
        logger.info("Aifory create_card_order payload: %s", {k: v for k, v in payload.items() if k != "code"})
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
