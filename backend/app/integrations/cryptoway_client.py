"""Cryptoway signed API. Money-creating POST requests are never retried."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode, urlparse

import httpx
from app.core.config import settings


class CryptowayError(Exception):
    def __init__(self, status=0, message="Криптооплата временно недоступна. Попробуйте позже."):
        self.status = status
        super().__init__(message)


def signature(secret, timestamp, data):
    canonical = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return hmac.new(secret.encode(), f"{timestamp}{canonical}".encode(), hashlib.sha256).hexdigest()


def verify_webhook(payload, query, timestamp, supplied, now=None):
    if not settings.CRYPTOWAY_CALLBACK_KEY or not supplied:
        return False
    try:
        if abs((time.time() if now is None else now) - int(timestamp)) > 15:
            return False
    except (ValueError, TypeError):
        return False
    if isinstance(payload.get("body"), dict) and payload["body"].get("type") == "invoice":
        if payload.get("params") != query:
            return False
        data = payload  # Invoice callbacks already contain the signed envelope.
    else:
        data = {"params": query, "body": payload}
    return hmac.compare_digest(signature(settings.CRYPTOWAY_CALLBACK_KEY, timestamp, data), supplied)


def trusted_pay_url(value):
    try:
        parsed = urlparse(str(value or ""))
        return parsed.scheme == "https" and parsed.hostname == "pay.cryptoway.com" and parsed.port in (None, 443) and parsed.username is None
    except ValueError:
        return False


class CryptowayClient:
    def is_configured(self):
        return bool(settings.CRYPTOWAY_PROJECT_ID and settings.CRYPTOWAY_SECRET_KEY and settings.CRYPTOWAY_CALLBACK_KEY)

    async def request(self, method, path, body=None, params=None):
        if not self.is_configured():
            raise CryptowayError(503)
        query = urlencode(params or {})
        ts = str(int(time.time()))
        data = {"params": query, "body": body or {}, "path": path}
        headers = {
            "X-API-Key-ID": settings.CRYPTOWAY_PROJECT_ID,
            "X-Timestamp": ts,
            "X-Signature": signature(settings.CRYPTOWAY_SECRET_KEY, ts, data),
            "Content-Type": "application/json",
            "User-Agent": "ProntoPay/1.0",
        }
        url = settings.CRYPTOWAY_API_URL.rstrip("/") + path + ("?" + query if query else "")
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                response = await client.request(method, url, headers=headers,
                    content=json.dumps(body, separators=(",", ":"), sort_keys=True).encode() if body is not None else None)
            if response.status_code >= 300:
                raise CryptowayError(response.status_code)
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CryptowayError() from exc

    async def symbols(self, page=1):
        return await self.request("GET", "/symbol/", params={"search_query": "USDT", "per_page": 100, "page": page})

    async def fees(self):
        return await self.request("GET", "/setting/fees/my/")

    async def create_invoice(self, body):
        return await self.request("POST", "/invoice/", body=body)

    async def invoice(self, invoice_id):
        return await self.request("GET", f"/invoice/my/{invoice_id}/")

    async def transactions(self, invoice_id):
        return await self.request("GET", f"/invoice/{invoice_id}/transactions/")

    async def cancel(self, invoice_id):
        return await self.request("POST", f"/invoice/{invoice_id}/cancel/", body={})

    async def find_invoice(self, external_id):
        for page in range(1, 11):
            result = await self.request("GET", "/invoice/", params={"order_asc": "false", "per_page": 100, "page": page})
            for row in result.get("data") or []:
                if row.get("external_id") == external_id:
                    return row
            if page >= int(result.get("pages_count") or 1):
                break
        return None


cryptoway_client = CryptowayClient()
