"""Rocketpay API client (virtual cards, Apple Pay capable).

Docs: openapi.json from Rocketpay ("Rocketpay API 1.0.0").
- Base URL: ROCKETPAY_API_URL, e.g. https://<address>/api/v1 (sandbox and
  production are different addresses with different keys: rpk_test_… / rpk_…).
- Auth: `Authorization: Bearer <ROCKETPAY_API_KEY>`.
- Amounts are decimal STRINGS ("12.00"), never numbers.
- Writes that move money or act at the card issuer REQUIRE an
  `Idempotency-Key`; a repeat with the same key + same body within 24h
  returns the first answer (`Idempotent-Replayed: true`).
- Errors: {"error": {"code", "message", "request_id", "bank"}}.
- No webhooks: transactions are polled.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Error codes after which repeating the same request (same Idempotency-Key)
# later can succeed — per Rocketpay's ErrorCode table.
RETRYABLE_CODES = {
    "request_in_progress", "operation_in_progress", "card_not_issued",
    "card_has_pending_transactions", "account_not_ready", "export_not_ready",
    "internal_error", "bank_server_error", "bank_no_response", "bank_unreachable",
}


class RocketpayError(Exception):
    def __init__(self, status: int, code: str, message: str, request_id: str = "", bank: Any = None):
        self.status = status
        self.code = code or "unknown"
        self.message = message or ""
        self.request_id = request_id or ""
        self.bank = bank
        super().__init__(f"Rocketpay {status} {self.code}: {self.message} (request_id={self.request_id})")

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_CODES or self.status >= 500


def money(value: Any) -> str:
    """Decimal string with two decimals, as Rocketpay requires."""
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def is_configured() -> bool:
    return bool((settings.ROCKETPAY_API_URL or "").strip() and (settings.ROCKETPAY_API_KEY or "").strip())


class RocketpayClient:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    @property
    def base(self) -> str:
        return (settings.ROCKETPAY_API_URL or "").strip().rstrip("/")

    def _headers(self, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        key = (settings.ROCKETPAY_API_KEY or "").strip()
        h = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key[:255]
        return h

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Returns the JSON body plus `_status` (HTTP code) for async flows."""
        if not is_configured():
            raise RocketpayError(0, "not_configured", "ROCKETPAY_API_URL / ROCKETPAY_API_KEY are not set")
        url = f"{self.base}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.request(
                method, url, params=params, json=body,
                headers=self._headers(idempotency_key),
            )
        try:
            data = r.json() if r.content else {}
        except Exception:
            data = {"raw": r.text[:2000]}
        if r.status_code >= 400:
            err = (data or {}).get("error") or {}
            exc = RocketpayError(
                r.status_code, err.get("code") or "", err.get("message") or r.text[:300],
                err.get("request_id") or r.headers.get("X-Request-Id", ""), err.get("bank"),
            )
            logger.warning("[RP] %s %s -> %s", method, path, exc)
            raise exc
        if not isinstance(data, dict):
            data = {"items": data}
        data["_status"] = r.status_code
        if r.headers.get("Idempotent-Replayed"):
            data["_replayed"] = True
        logger.info("[RP] %s %s -> %s", method, path, r.status_code)
        return data

    @staticmethod
    def new_key(prefix: str = "pp") -> str:
        return f"{prefix}-{uuid.uuid4().hex}"

    # ---------------------------------------------------------------- account
    async def me(self) -> Dict[str, Any]:
        return await self._request("GET", "/auth/me")

    async def accounts(self) -> List[Dict[str, Any]]:
        return (await self._request("GET", "/issuer/accounts")).get("items") or []

    async def capacity(self) -> Dict[str, Any]:
        return await self._request("GET", "/clients/capacity")

    async def card_programs(self) -> List[Dict[str, Any]]:
        return (await self._request("GET", "/card-programs")).get("items") or []

    async def program_fees(self, program_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/card-programs/{program_id}/fees")

    async def deposit_address(self, account_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/issuer/accounts/{account_id}/deposit-address")

    # ---------------------------------------------------------------- cards
    async def issue_card(self, *, external_id: str, limits: Optional[Dict[str, Any]], metadata: Dict[str, str],
                         idempotency_key: str) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "external_id": external_id,
            "metadata": {k: str(v)[:500] for k, v in metadata.items()},
        }
        # some card programs reject limits altogether ("leave limits out")
        if limits:
            body["limits"] = {k: money(v) for k, v in limits.items()}
        return await self._request("POST", "/cards", body=body, idempotency_key=idempotency_key)

    async def get_card(self, card_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/cards/{card_id}")

    async def sync_card(self, card_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/cards/{card_id}/sync", idempotency_key=self.new_key("sync"))

    async def find_card_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        items = (await self._request("GET", "/cards", params={"external_id": external_id})).get("items") or []
        return items[0] if items else None

    async def fund_card(self, card_id: str, amount: Any, *, external_id: str, idempotency_key: str,
                        metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        body = {"amount": money(amount), "external_id": external_id}
        if metadata:
            body["metadata"] = metadata
        return await self._request("POST", f"/cards/{card_id}/fund", body=body, idempotency_key=idempotency_key)

    async def withdraw_card(self, card_id: str, amount: Any, *, external_id: str, idempotency_key: str) -> Dict[str, Any]:
        body = {"amount": money(amount), "external_id": external_id}
        return await self._request("POST", f"/cards/{card_id}/withdraw", body=body, idempotency_key=idempotency_key)

    async def get_movement(self, movement_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/issuer/movements/{movement_id}")

    async def card_transactions(self, card_id: str, limit: int = 50, cursor: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": max(1, min(int(limit), 200))}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", f"/cards/{card_id}/transactions", params=params)

    async def closure_preview(self, card_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/cards/{card_id}/closure-preview")

    async def close_card(self, card_id: str, reason: str, *, idempotency_key: str) -> Dict[str, Any]:
        body = {"reason": reason[:200], "refund_remaining_balance": True}
        return await self._request("POST", f"/cards/{card_id}/close", body=body, idempotency_key=idempotency_key)

    async def get_closure(self, closure_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/card-closures/{closure_id}")

    async def card_details(self, card_id: str) -> Dict[str, Any]:
        """Full card number / CVV / expiry / holder: POST /cards/{id}/pan-reveal
        -> {card_id, pan, cvv, expiry: {month, year}, holder}. PCI: fetched on
        every call, never stored or logged (the response body isn't logged)."""
        path = (settings.ROCKETPAY_CARD_DETAILS_PATH or "/cards/{card_id}/pan-reveal").format(card_id=card_id)
        return await self._request("POST", path)


rocketpay_client = RocketpayClient()
