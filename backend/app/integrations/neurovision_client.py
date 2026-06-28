"""NeuroVision KYC integration client.

Flow:
1. Backend generates encrypted clientKey (AES-256-CBC) and returns it to frontend.
2. Frontend opens KYC widget with schemaId + clientKey.
3. On successCb, frontend polls GET /kyc/status until status = 'success'.
4. Backend fetches session from NeuroVision, extracts OCR passport data, saves to User.
5. Passport data is used for Bitbanker partner-client registration.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, Optional

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from app.core.config import settings

logger = logging.getLogger(__name__)

NV_BASE_URL = "https://api.neuro-vision.ru/v1"


def _encrypt_client_key(raw_key: str, scenario_secret: str) -> str:
    """Encrypt clientKeyRaw with AES-256-CBC using scenarioSecretKey.

    The scenarioSecretKey is taken from NeuroVision LK scenario settings.
    Key is derived as SHA-256 hex of the scenario secret, first 32 chars.
    IV is random 16 bytes, prepended to the encrypted result.
    Result is Base64-encoded.
    
    Algorithm (from NeuroVision docs):
    1. key = sha256(password).hex().substr(0, 32)
    2. iv = random 16 bytes
    3. encrypted = iv + aes256cbc(clientKey, key, iv)
    4. result = base64(encrypted)
    """
    # Key derivation: SHA-256 hex, first 32 chars (= 16 bytes when decoded from hex)
    key_hex = hashlib.sha256(scenario_secret.encode()).hexdigest()[:32]
    key = bytes.fromhex(key_hex)  # 16 bytes
    
    # Generate random IV (16 bytes)
    iv = os.urandom(16)
    
    # Encrypt with AES-256-CBC (but key is only 16 bytes, so it's AES-128-CBC)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(raw_key.encode("utf-8"), AES.block_size))
    
    # Prepend IV to encrypted data
    result = iv + encrypted
    
    return base64.b64encode(result).decode("utf-8")


class NeuroVisionClient:
    def __init__(self):
        self._api_token = settings.NV_API_TOKEN
        self._schema_id = settings.NV_SCHEMA_ID
        self._scenario_secret = settings.NV_SCENARIO_SECRET

    def _is_configured(self) -> bool:
        return bool(self._api_token and self._schema_id and self._scenario_secret)

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_token}",
        }

    def generate_client_key(self, user_id: int) -> Dict[str, str]:
        """Generate raw and encrypted clientKey for a user.

        Returns dict with:
          - client_key_raw: str (save this to DB for later lookup)
          - client_key_encrypted: str (pass this to frontend/widget)
          - schema_id: str
        """
        if not self._is_configured():
            raise RuntimeError("NeuroVision not configured (NV_API_TOKEN, NV_SCHEMA_ID, NV_SCENARIO_SECRET)")
        raw = f"u{user_id}"
        encrypted = _encrypt_client_key(raw, self._scenario_secret)
        return {
            "client_key_raw": raw,
            "client_key_encrypted": encrypted,
            "schema_id": self._schema_id,
        }

    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """Fetch KYC session status from NeuroVision API."""
        if not self._is_configured():
            raise RuntimeError("NeuroVision not configured")
        url = f"{NV_BASE_URL}/kyc/session/status"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                headers=self._headers(),
                params={"sessionId": session_id},
            )
            if resp.status_code >= 400:
                logger.error("NeuroVision GET /kyc/session/status -> %s | %s", resp.status_code, resp.text[:300])
                raise httpx.HTTPStatusError(
                    f"NeuroVision status error {resp.status_code}: {resp.text[:200]}",
                    request=resp.request, response=resp,
                )
            return resp.json()

    async def find_session_by_client_key(self, client_key_raw: str) -> Optional[Dict[str, Any]]:
        """Find latest KYC session by clientKey (raw, unencrypted)."""
        if not self._is_configured():
            raise RuntimeError("NeuroVision not configured")
        url = f"{NV_BASE_URL}/kyc/sessions/filter"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers=self._headers(),
                json={"clientKey": client_key_raw, "limit": 1},
            )
            if resp.status_code >= 400:
                logger.error("NeuroVision POST /kyc/sessions/filter -> %s | %s", resp.status_code, resp.text[:300])
                return None
            data = resp.json()
            sessions = data if isinstance(data, list) else data.get("sessions", [])
            return sessions[0] if sessions else None


def extract_passport_data(session: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Extract passport OCR data from a NeuroVision KYC session response.

    Returns dict with keys matching Bitbanker partner-client fields,
    or None if no document result found.
    """
    results = session.get("results", [])
    for task in results:
        if task.get("type") != "document":
            continue
        if task.get("status") != "success":
            continue
        ocr = task.get("ocr", {})
        if not ocr:
            continue

        # Parse OCR fields array: [{"title": "Surname", "value": "DOE", "conf": "high"}, ...]
        fields_map = {}
        if "fields" in ocr and isinstance(ocr["fields"], list):
            for field in ocr["fields"]:
                title = field.get("title", "").lower()
                value = field.get("value", "").strip()
                if value:
                    fields_map[title] = value
        
        # Extract data from fields_map
        # Common titles: "Surname", "Given name(s)", "Patronymic", "Date of birth", "Document number", "Date of issue"
        last_name = (
            fields_map.get("surname") or 
            fields_map.get("фамилия") or 
            ocr.get("surname") or 
            ""
        ).strip()
        
        first_name = (
            fields_map.get("given name(s)") or 
            fields_map.get("name") or
            fields_map.get("имя") or 
            ocr.get("name") or 
            ""
        ).strip()
        
        patronymic = (
            fields_map.get("patronymic") or 
            fields_map.get("отчество") or 
            ocr.get("patronymic") or 
            ""
        ).strip()
        
        birth_date = (
            fields_map.get("date of birth") or 
            fields_map.get("дата рождения") or 
            ocr.get("birthDate") or 
            ""
        ).strip()
        
        passport = (
            fields_map.get("document number") or 
            fields_map.get("номер документа") or 
            ocr.get("passportNumber") or 
            ocr.get("documentNumber") or 
            ""
        ).replace(" ", "").strip()
        
        issue_date = (
            fields_map.get("date of issue") or 
            fields_map.get("дата выдачи") or 
            ocr.get("issueDate") or 
            ""
        ).strip()

        if not (last_name and first_name and passport):
            logger.warning("NeuroVision OCR incomplete. fields_map=%s, ocr=%s", fields_map, ocr)
            return None

        return {
            "first_name": first_name,
            "last_name": last_name,
            "patronymic": patronymic,
            "birth_date": birth_date,
            "passport": passport,
            "passport_issue_date": issue_date,
        }
    return None


neurovision_client = NeuroVisionClient()
