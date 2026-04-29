import json
import logging
import os
from typing import Any, Dict

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import settings

logger = logging.getLogger(__name__)


class OPlataClient:
    def __init__(self) -> None:
        self._base_url = settings.OPLATA_BASE_URL.rstrip("/")
        self._product_id = (settings.OPLATA_PRODUCT_ID or "").strip()
        self._private_key_hex = (settings.OPLATA_PRIVATE_KEY or "").strip().lower()

    def _body_bytes(self, body: Dict[str, Any]) -> bytes:
        return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _make_signature_headers(self, body_bytes: bytes) -> Dict[str, str]:
        if not self._product_id:
            raise ValueError("OPLATA_PRODUCT_ID is not configured")
        if len(self._private_key_hex) != 64:
            raise ValueError("OPLATA_PRIVATE_KEY must be a 32-byte hex seed (64 hex chars)")

        try:
            seed = bytes.fromhex(self._private_key_hex)
        except ValueError as exc:
            raise ValueError("OPLATA_PRIVATE_KEY is not valid hex") from exc

        prefix = os.urandom(64)
        postfix = os.urandom(64)
        message = prefix + body_bytes + postfix

        private_key = Ed25519PrivateKey.from_private_bytes(seed)
        signature = private_key.sign(message)

        return {
            "NaClSignature_USER_ID": self._product_id,
            "NaClSignature_PREFIX": prefix.hex(),
            "NaClSignature_POSTFIX": postfix.hex(),
            "NaClSignature_SIGNATURE": signature.hex(),
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, body: Dict[str, Any]) -> Any:
        body_bytes = self._body_bytes(body)
        headers = self._make_signature_headers(body_bytes)
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, content=body_bytes)
            if response.status_code >= 400:
                logger.error("O-Plata POST %s -> %s | %s", url, response.status_code, response.text[:1000])
                response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

    async def register_client(self, client_id: str) -> Dict[str, Any]:
        return await self._post("/product/rest/client/register", {"clientId": client_id})


oplata_client = OPlataClient()
