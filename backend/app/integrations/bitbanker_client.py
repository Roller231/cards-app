"""Bitbanker SBP gateway client.

Handles HMAC-signed requests, partner-client registration/KYC,
exchange prediction, invoice creation, and webhook signature verification.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _canonical_json(payload: Dict[str, Any]) -> str:
    """Build canonical JSON: sorted keys, no spaces, ensure_ascii=False,
    without sign/sign_2/full_sign fields."""
    clean = {k: v for k, v in payload.items() if k not in ("sign", "sign_2", "full_sign")}
    return json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _compute_full_sign(payload: Dict[str, Any], api_secret: str) -> str:
    """Compute HMAC-SHA256 over canonical JSON of the payload."""
    canonical = _canonical_json(payload)
    return hmac.new(api_secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _base_fields() -> Dict[str, Any]:
    """Return timestamp and nonce required in every signed request."""
    return {
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
        "nonce": str(_uuid.uuid4()),
    }


def verify_webhook_signature(payload: Dict[str, Any], api_secret: str) -> bool:
    """Verify full_sign in a received webhook/response payload."""
    received = payload.get("full_sign", "")
    if not received:
        return False
    expected = _compute_full_sign(payload, api_secret)
    return hmac.compare_digest(expected, received)


class BitbankerClient:
    def __init__(self) -> None:
        self._base = settings.BITBANKER_BASE_URL.rstrip("/")
        self._api_key = settings.BITBANKER_API_KEY
        self._api_secret = settings.BITBANKER_API_SECRET

    def _is_configured(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-KEY": self._api_key,
        }

    def _signed_body(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Add timestamp, nonce, and full_sign to payload."""
        body = {**_base_fields(), **payload}
        body["full_sign"] = _compute_full_sign(body, self._api_secret)
        return body

    async def _post(self, path: str, payload: Dict[str, Any], idempotency_key: Optional[str] = None) -> Any:
        if not self._is_configured():
            raise RuntimeError("Bitbanker API key/secret not configured (BITBANKER_API_KEY, BITBANKER_API_SECRET)")
        body = self._signed_body(payload)
        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        url = f"{self._base}{path}"
        logger.debug("Bitbanker POST %s | nonce=%s", url, body.get("nonce"))
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, content=json.dumps(body, ensure_ascii=False))
            if resp.status_code >= 400:
                preview = resp.text[:500]
                logger.error("Bitbanker %s -> %s | %s", path, resp.status_code, preview)
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code} from Bitbanker {path}: {preview}",
                    request=resp.request, response=resp,
                )
            return resp.json() if resp.content else {}

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self._is_configured():
            raise RuntimeError("Bitbanker API key/secret not configured")
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers(), params=params or {})
            if resp.status_code >= 400:
                logger.error("Bitbanker GET %s -> %s | %s", path, resp.status_code, resp.text[:300])
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code} from Bitbanker {path}: {resp.text[:300]}",
                    request=resp.request, response=resp,
                )
            return resp.json() if resp.content else {}

    # ------------------------------------------------------------------
    # KYC
    # ------------------------------------------------------------------

    async def create_kyc_session(self, external_client_ref: str) -> Dict[str, Any]:
        """POST /api/v1/kyc-request — returns kyc_url and partner_client_id."""
        body = {**_base_fields(), "external_client_ref": external_client_ref}
        body["full_sign"] = _compute_full_sign(body, self._api_secret)
        headers = self._headers()
        url = f"{self._base}/api/v1/kyc-request"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, content=json.dumps(body, ensure_ascii=False))
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}: {resp.text[:300]}", request=resp.request, response=resp,
                )
            return resp.json()

    async def register_partner_client(self, client_id: str, **kyc_data) -> Dict[str, Any]:
        """POST /api/v2/partner-clients — register/update a partner client with KYC data."""
        payload = {"client_id": client_id, **kyc_data}
        return await self._post("/api/v2/partner-clients", payload, idempotency_key=f"pc-{client_id}")

    async def get_partner_client(self, external_id: str) -> Dict[str, Any]:
        """GET /api/v2/partner-clients?external_id=... — check is_verified_for_sbp."""
        return await self._get("/api/v2/partner-clients", {"external_id": external_id})

    # ------------------------------------------------------------------
    # Prediction / rates
    # ------------------------------------------------------------------

    async def get_sbp_prediction(self) -> Dict[str, Any]:
        """GET /api/v2/prediction-sbp — limits and fee info, no signing required."""
        return await self._get("/api/v2/prediction-sbp")

    async def get_exchange_prediction(self, volume: float, give_currency: str = "RUBR", take_currency: str = "USDT") -> Dict[str, Any]:
        """POST /api/v2/exchange_prediction — calculate rates before invoice."""
        payload = {
            "volume": f"{volume:.3f}",
            "give_currency": give_currency,
            "take_currency": take_currency,
        }
        return await self._post("/api/v2/exchange_prediction", payload)

    # ------------------------------------------------------------------
    # Invoice
    # ------------------------------------------------------------------

    async def create_invoice(
        self,
        amount_rub: float,
        partner_client_external_id: str,
        idempotency_key: str,
        take_currency: str = "USDT",
    ) -> Dict[str, Any]:
        """POST /api/v2/invoices — create SBP payment invoice, returns qr image."""
        payload = {
            "amount": f"{amount_rub:.2f}",  # Bitbanker expects string format
            "currency": "RUBR",
            "sbp_payment": True,
            "is_convert_payments": True,
            "take_currency": take_currency,
            "payment_currencies": ["RUBR"],
            "partner_client_external_id": partner_client_external_id,
        }
        return await self._post("/api/v2/invoices", payload, idempotency_key=idempotency_key)

    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """GET /api/v2/invoices/{id} — poll payment status."""
        return await self._get(f"/api/v2/invoices/{invoice_id}")


bitbanker_client = BitbankerClient()
