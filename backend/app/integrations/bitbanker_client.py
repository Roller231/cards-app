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


# ---------------------------------------------------------------------------
# Human-readable messages for known Bitbanker API error codes.
# Matched by substring against the raw error text (Bitbanker returns
# {"code": "..."} in the body, which our exceptions embed as a preview).
# Order matters: more specific codes must come before their prefixes.
# ---------------------------------------------------------------------------

SUPPORT_HINT = "Обратитесь в службу поддержки."

BB_ERROR_MESSAGES: Dict[str, str] = {
    # --- partner-clients (KYC) ---
    "PhoneNumberFailed": "Номер телефона не прошёл проверку. Убедитесь, что указан российский номер в формате +7XXXXXXXXXX, и попробуйте снова. Если ошибка повторяется — обратитесь в поддержку.",
    "PassportFailed": "Паспортные данные не прошли проверку. Проверьте серию, номер, дату выдачи и ФИО (без лишних пробелов) и попробуйте снова. Если ошибка повторяется — обратитесь в поддержку.",
    "SecurityFailed": "Ваш доступ к сервису был ограничен. Пожалуйста, обратитесь в службу поддержки.",
    "INNFailed": f"Не удалось подтвердить ваши данные. {SUPPORT_HINT}",
    "NeedCompleteKYC": "Верификация не пройдена. Проверьте свои данные и попробуйте снова, либо обратитесь в поддержку.",
    # Typo is intentional — this is the exact code Bitbanker sends.
    "ParnersClientPasportNumberAlreadyOccupied": "На данный номер паспорта уже зарегистрирован аккаунт в системе. Используйте другой аккаунт с данным паспортом.",
    "PartnerClientPublicApiUpdateForbidden": f"Ваши данные не совпадают с зарегистрированными ранее. {SUPPORT_HINT}",
    "PartnerIsNotFound": f"Сервис оплаты временно недоступен. {SUPPORT_HINT}",
    # --- invoices / SBP ---
    "CanNotPayInvoiceBySBP": f"Оплата по СБП сейчас недоступна. {SUPPORT_HINT}",
    "PartnerClientRequiredForSbpInvoice": f"Профиль не зарегистрирован в платёжной системе. {SUPPORT_HINT}",
    "PartnerClientDoesNotExist": f"Профиль не найден в платёжной системе. {SUPPORT_HINT}",
    "SbpInvoiceCurrencyError": f"Оплата по СБП недоступна для этой валюты. {SUPPORT_HINT}",
    "TooMuchInvoices": "Слишком много неоплаченных счетов. Попробуйте позже.",
    "MinInvoiceAmount": "Минимальная сумма перевода по СБП — 1 000 ₽. Увеличьте сумму и попробуйте снова.",
    "BadRequestParameters": f"Некорректные параметры платежа. Попробуйте ещё раз. Если ошибка повторяется — {SUPPORT_HINT.lower()}",
    "UserForbiddenError": f"Сервис СБП временно недоступен. {SUPPORT_HINT}",
    "UserNotFound": f"Сервис СБП временно недоступен. {SUPPORT_HINT}",
    "SbpPredictionLimitsNotAvailable": f"Сервис СБП временно недоступен. Попробуйте позже. {SUPPORT_HINT}",
    "WLForbiddenError": f"Пополнение по СБП отключено. {SUPPORT_HINT}",
    "SbpTransferNotAllowedError": "Ваш доступ к сервису был ограничен. Пожалуйста, обратитесь в службу поддержки.",
    "BankNotFoundError": "Не можем найти ваш банк. Пожалуйста, обратитесь в службу поддержки.",
    "CurrencyNotFound": "Измените сумму пополнения или обратитесь в службу поддержки.",
    "SbpBankCostLimitsNotFound": "Попробуйте изменить сумму пополнения или обратитесь в службу поддержки.",
    "NotEnoughMoneyOnBalance": "Попробуйте уменьшить сумму пополнения или обратитесь в службу поддержки.",
    "UnknownSbpPlatform": "Не можем провести операцию с этим банком. Пожалуйста, обратитесь в службу поддержки.",
    "ProviderDailyCompletedQrlimitReached": "Достигнут суточный лимит оплаченных QR-кодов. Лимит сбросится в 00:00 по Москве — повторите пополнение завтра.",
    "ProviderDailyQrlimitReached": "Достигнут суточный лимит по созданию QR-кодов. Лимит сбросится в 00:00 по Москве — повторите пополнение завтра.",
    "DailyCompletedQrlimitReached": "Достигнут суточный лимит оплаченных QR-кодов. Лимит сбросится в 00:00 по Москве — повторите пополнение завтра.",
    "DailyQrlimitReached": "Достигнут суточный лимит по созданию QR-кодов. Лимит сбросится в 00:00 по Москве — повторите пополнение завтра.",
    "ProviderGetQrCodeError": "Технические проблемы с созданием QR-кода. Попробуйте позже или обратитесь в поддержку.",
    "SbpPhoneNumberRequired": "Не заполнен номер телефона для пополнения по СБП. Обратитесь в службу поддержки и сообщите свой номер.",
    "ExceededMaxPendingQrCodesError": "Превышен лимит неоплаченных QR-кодов, пополнение по СБП временно недоступно. Дождитесь автоматического сброса лимита или обратитесь в поддержку.",
}

BB_GENERIC_ERROR = "Платёжный сервис временно недоступен. Попробуйте позже или обратитесь в поддержку."


def humanize_bb_error(raw: Any) -> str:
    """Map a raw Bitbanker error (exception text / response body) to a
    user-facing Russian message. Falls back to a generic message."""
    text = str(raw or "")
    for code, message in BB_ERROR_MESSAGES.items():
        if code in text:
            return message
    return BB_GENERIC_ERROR


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
        # Log full request body for debugging (without sensitive data in production)
        logger.info("Bitbanker POST %s | payload keys: %s", path, list(body.keys()))
        logger.info("Bitbanker POST %s | Idempotency-Key: %s | full_sign: %s...", 
                   path, headers.get("Idempotency-Key", "N/A"), body.get("full_sign", "N/A")[:16])
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, content=json.dumps(body, ensure_ascii=False))
            if resp.status_code >= 400:
                preview = resp.text[:500]
                logger.error("Bitbanker %s -> %s | %s", path, resp.status_code, preview)
                logger.error("Request payload (without full_sign): %s", {k: v for k, v in body.items() if k != "full_sign"})
                # Log canonical JSON for debugging signature
                canonical = _canonical_json({k: v for k, v in body.items() if k != "full_sign"})
                logger.error("Canonical JSON: %s", canonical[:200])
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code} from Bitbanker {path}: {preview}",
                    request=resp.request, response=resp,
                )
            return resp.json() if resp.content else {}

    async def _post_unsigned(self, path: str, payload: Dict[str, Any]) -> Any:
        """POST without timestamp/nonce/full_sign (for endpoints that don't require signing)."""
        if not self._is_configured():
            raise RuntimeError("Bitbanker API key/secret not configured")
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers(), content=json.dumps(payload, ensure_ascii=False))
            if resp.status_code >= 400:
                preview = resp.text[:500]
                logger.error("Bitbanker POST %s -> %s | %s", path, resp.status_code, preview)
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code} from Bitbanker {path}: {preview}",
                    request=resp.request, response=resp,
                )
            return resp.json() if resp.content else {}

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False) -> Any:
        """GET request. If signed=True, adds timestamp/nonce/full_sign to query params."""
        if not self._is_configured():
            raise RuntimeError("Bitbanker API key/secret not configured")
        url = f"{self._base}{path}"
        query_params = params or {}
        if signed:
            query_params = {**_base_fields(), **query_params}
            query_params["full_sign"] = _compute_full_sign(query_params, self._api_secret)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=self._headers(), params=query_params)
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
        """POST /api/v1/kyc-request — returns kyc_url and partner_client_id (no signing required)."""
        payload = {"external_client_ref": external_client_ref}
        url = f"{self._base}/api/v1/kyc-request"
        headers = self._headers()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, content=json.dumps(payload, ensure_ascii=False))
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}: {resp.text[:300]}", request=resp.request, response=resp,
                )
            return resp.json()

    async def register_partner_client(self, client_id: str, **kyc_data) -> Dict[str, Any]:
        """POST /api/v2/partner-clients — register/update a partner client with KYC data."""
        payload = {"client_id": client_id, **kyc_data}
        return await self._post("/api/v2/partner-clients", payload, idempotency_key=f"pc-{client_id}")

    async def get_partner_client(self, client_id: str) -> Dict[str, Any]:
        """GET /api/v2/partner-clients?client_id=... — check is_verified_for_sbp (requires signing)."""
        return await self._get("/api/v2/partner-clients", {"client_id": client_id}, signed=True)

    # ------------------------------------------------------------------
    # Prediction / rates
    # ------------------------------------------------------------------

    async def get_sbp_prediction(self) -> Dict[str, Any]:
        """GET /api/v2/prediction-sbp — limits and fee info, no signing required."""
        return await self._get("/api/v2/prediction-sbp")

    async def get_exchange_prediction(self, volume: float, give_currency: str = "RUBR", take_currency: str = "USDT") -> Dict[str, Any]:
        """POST /api/v2/exchange-prediction — calculate rates before invoice (no signing required)."""
        payload = {
            "volume": volume,  # Numeric value, not string
            "give_currency": give_currency,
            "take_currency": take_currency,
        }
        return await self._post_unsigned("/api/v2/exchange-prediction", payload)

    # ------------------------------------------------------------------
    # Invoice
    # ------------------------------------------------------------------

    async def create_invoice(
        self,
        amount_rub: float,
        partner_client_external_id: str,
        idempotency_key: str,
        take_currency: str = "USDT",
        description: str = "",
        header: str = "ProntoPay",
    ) -> Dict[str, Any]:
        """POST /api/v2/invoices — create SBP payment invoice, returns qr image."""
        payload = {
            "payment_currencies": ["RUBR"],
            "payment_chains": [],
            "currency": "RUBR",
            "amount": int(amount_rub),  # Bitbanker expects integer for amount
            "header": header,
            "description": description or f"Оплата {int(amount_rub)} руб.",
            "language": "ru",
            "crypto_payment": False,
            "sbp_payment": True,
            "is_convert_payments": True,
            "take_currency": take_currency,
            "partner_client_external_id": partner_client_external_id,
        }
        return await self._post("/api/v2/invoices", payload, idempotency_key=idempotency_key)

    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """GET /api/v2/invoices?id=... — poll payment status."""
        return await self._get("/api/v2/invoices", params={"id": invoice_id})


bitbanker_client = BitbankerClient()
