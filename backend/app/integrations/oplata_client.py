import json
import logging
import os
from typing import Any, Dict, List, Optional

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
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=headers, content=body_bytes)
                if response.status_code >= 400:
                    body_preview = response.text[:500]
                    logger.error("O-Plata POST %s -> %s | %s", url, response.status_code, body_preview)
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code} from {path}: {body_preview}",
                        request=response.request,
                        response=response,
                    )
                if not response.content:
                    return {}
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("O-Plata request failed %s | %s: %s", url, exc.__class__.__name__, exc)
            raise

    # ====== CLIENT ======

    async def register_client(self, client_id: str) -> Dict[str, Any]:
        """Register or get existing client. Idempotent."""
        return await self._post("/product/rest/client/register", {"clientId": client_id})

    async def get_client_info(self, client_id: str) -> Dict[str, Any]:
        return await self._post("/product/rest/client/info", {"clientId": client_id})

    # ====== KYC (client verification — required before card issuance) ======

    async def kyc_info(self, client_id: str) -> Dict[str, Any]:
        """Get current KYC verification status for a client."""
        return await self._post("/product/rest/kyc/info", {"clientId": client_id})

    async def kyc_verify_email(self, client_id: str, email: str) -> Any:
        """Complete email KYC verification (sets EMAIL MDM data)."""
        return await self._post("/product/rest/kyc/verify/email/complete", {
            "clientId": client_id, "email": email,
        })

    async def kyc_verify_person(self, client_id: str, first_name: str, last_name: str,
                                 date_of_birth: str, middle_name: Optional[str] = None,
                                 country: str = "RU") -> Any:
        """Complete person KYC verification."""
        body: Dict[str, Any] = {
            "clientId": client_id,
            "firstName": first_name,
            "lastName": last_name,
            "dateOfBirth": date_of_birth,
            "country": country,
        }
        if middle_name:
            body["middleName"] = middle_name
        return await self._post("/product/rest/kyc/verify/person/complete", body)

    async def kyc_verify_country(self, client_id: str, country_code: str) -> Any:
        """Complete country KYC verification."""
        return await self._post("/product/rest/kyc/verify/country/complete", {
            "clientId": client_id, "countryCode": country_code,
        })

    async def kyc_verify_home(
        self,
        client_id: str,
        address: str,
        city: str,
        country_code: str,
        state: str,
        street: str,
    ) -> Any:
        """Complete home address verification."""
        return await self._post("/product/rest/kyc/verify/home/complete", {
            "clientId": client_id,
            "address": address,
            "city": city,
            "countryCode": country_code,
            "state": state,
            "street": street,
        })

    async def kyc_verify_partner_start(
        self,
        client_id: str,
        first_name: str = "Test",
        last_name: str = "Testov",
        middle_name: str = "Testovich",
        date_of_birth: str = "1980-01-01",
        email: str = "test@test.com",
        phone_number: str = "+71234567890",
        gender: str = "MALE",
        document_number: str = "1234567890",
        document_type: str = "CITIZEN_PASSPORT",
        issue_date: str = "2025-01-01",
        valid_until_date: str = "2035-01-01",
        country: str = "RU",
        pep: bool = False,
    ) -> Any:
        """Start partner KYC verification — completes IDENTIFICATION_DOCUMENT for card issuance.

        Body matches O-Plata doc example exactly. CITIZEN_PASSPORT requires 10-digit Russian
        passport number; middleName must not be null.
        """
        return await self._post("/product/rest/kyc/verify/partner/start", {
            "clientId": client_id,
            "firstName": first_name,
            "lastName": last_name,
            "middleName": middle_name,
            "dateOfBirth": date_of_birth,
            "email": email or f"{client_id}@oplata.test",
            "phoneNumber": phone_number,
            "gender": gender,
            "number": document_number,
            "type": document_type,
            "issueDate": issue_date,
            "validUntilDate": valid_until_date,
            "country": country,
            "pep": pep,
        })

    async def set_identification_document(self, client_id: str, document_number: str) -> Any:
        """Best-effort submission of identification document for card issuance.

        O-Plata test environments appear to differ in which endpoint/body shape they accept,
        so we try several known/likely variants until one succeeds.
        """
        candidates = [
            (
                "/product/rest/client/mdm/set",
                {"clientId": client_id, "type": "IDENTIFICATION_DOCUMENT", "value": document_number},
            ),
            (
                "/product/rest/client/mdm",
                {"clientId": client_id, "type": "IDENTIFICATION_DOCUMENT", "value": document_number},
            ),
            (
                "/product/rest/client/mdm/set",
                {
                    "clientId": client_id,
                    "type": "IDENTIFICATION_DOCUMENT",
                    "value": document_number,
                    "documentType": "PASSPORT",
                },
            ),
            (
                "/product/rest/client/update",
                {"clientId": client_id, "documentNumber": document_number},
            ),
            (
                "/product/rest/client/update",
                {"clientId": client_id, "identificationDocument": document_number},
            ),
            (
                "/product/rest/client/register",
                {"clientId": client_id, "identificationDocument": document_number},
            ),
        ]

        last_exc: Optional[Exception] = None
        for path, body in candidates:
            try:
                result = await self._post(path, body)
                logger.info("O-Plata identification document accepted via %s", path)
                return result
            except Exception as exc:
                last_exc = exc
                logger.warning("O-Plata identification document attempt failed via %s: %s", path, exc)
                continue

        if last_exc:
            raise last_exc
        return {}

    async def raw_post(self, path: str, body: Dict[str, Any]) -> Any:
        """Send a raw signed POST to any O-Plata path (for debugging)."""
        return await self._post(path, body)

    # ====== BALANCE ======

    async def get_balance_all(self, client_id: str) -> Dict[str, Any]:
        return await self._post("/product/rest/balance/all", {"clientId": client_id})

    async def get_balance_currency(self, client_id: str, currency_code: str) -> Dict[str, Any]:
        return await self._post("/product/rest/balance/currency", {"clientId": client_id, "currencyCode": currency_code})

    # ====== VIRTUAL CARDS ======

    async def get_virtual_card_list(self, client_id: str) -> List[Dict]:
        """Returns providers with cardTypesList and cardsList."""
        result = await self._post("/product/rest/card/virtual/list", {"clientId": client_id})
        return result if isinstance(result, list) else []

    async def get_virtual_card_history(
        self, client_id: str, ravana_server_id: Optional[str] = None,
        page_number: int = 0, page_size: int = 50,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"clientId": client_id, "pageNumber": page_number, "pageSize": page_size}
        if ravana_server_id:
            body["ravanaServerId"] = ravana_server_id
        return await self._post("/product/rest/card/virtual/history", body)

    async def issue_virtual_card(
        self, client_id: str, name: str, ravana_server_id: str, type_uuid: str,
    ) -> Dict[str, Any]:
        return await self._post("/product/rest/card/virtual/issue", {
            "clientId": client_id,
            "name": name,
            "ravanaServerId": ravana_server_id,
            "typeUuid": type_uuid,
        })

    async def close_virtual_card(self, client_id: str, card_id: str, ravana_server_id: str) -> Dict[str, Any]:
        return await self._post("/product/rest/card/virtual/close", {
            "clientId": client_id, "cardId": card_id, "ravanaServerId": ravana_server_id,
        })

    async def get_card_funds_balance(self, client_id: str, card_id: str, ravana_server_id: str) -> Dict[str, Any]:
        return await self._post("/product/rest/card/virtual/funds/balance", {
            "clientId": client_id, "cardId": card_id, "ravanaServerId": ravana_server_id,
        })

    async def topup_card(
        self, client_id: str, card_id: str, ravana_server_id: str, amount: float,
    ) -> Dict[str, Any]:
        return await self._post("/product/rest/card/virtual/funds/topup", {
            "clientId": client_id, "cardId": card_id,
            "ravanaServerId": ravana_server_id, "amount": amount,
        })

    async def cashout_card(
        self, client_id: str, card_id: str, ravana_server_id: str, amount: float,
    ) -> Any:
        return await self._post("/product/rest/card/virtual/funds/cashout", {
            "clientId": client_id, "cardId": card_id,
            "ravanaServerId": ravana_server_id, "amount": amount,
        })

    async def get_card_secret(self, client_id: str, card_id: str, ravana_server_id: str) -> Dict[str, Any]:
        return await self._post("/product/rest/card/virtual/secret", {
            "clientId": client_id, "cardId": card_id, "ravanaServerId": ravana_server_id,
        })

    async def get_card_transaction_list(
        self, client_id: str, card_id: str, ravana_server_id: str,
        page_number: int = 0, page_size: int = 20,
        period_start: Optional[int] = None, period_end: Optional[int] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "clientId": client_id, "cardId": card_id,
            "ravanaServerId": ravana_server_id,
            "pageNumber": page_number, "pageSize": page_size,
        }
        if period_start is not None:
            body["periodStart"] = period_start
        if period_end is not None:
            body["periodEnd"] = period_end
        return await self._post("/product/rest/card/virtual/transaction/list", body)

    async def get_card_transaction_details(
        self,
        client_id: str,
        card_id: str,
        ravana_server_id: str,
        transaction_id: str,
    ) -> Dict[str, Any]:
        return await self._post("/product/rest/card/virtual/transaction/details", {
            "clientId": client_id,
            "cardId": card_id,
            "ravanaServerId": ravana_server_id,
            "transactionId": transaction_id,
        })

    async def validate_card_registration(self, client_id: str, ravana_server_id: str) -> Dict[str, Any]:
        """Check what is missing before card issuance. Returns status like EMAIL_ABSENT."""
        return await self._post("/product/rest/card/virtual/validate", {
            "clientId": client_id, "ravanaServerId": ravana_server_id,
        })

    # ====== COMMON ======

    async def get_currencies(self, is_crypto_currency: Optional[bool] = None) -> List[Dict]:
        body: Dict[str, Any] = {}
        if is_crypto_currency is not None:
            body["isCryptoCurrency"] = is_crypto_currency
        result = await self._post("/product/rest/common/currencies", body)
        return result if isinstance(result, list) else []

    async def get_currency(self, currency_code: str) -> Dict[str, Any]:
        return await self._post("/product/rest/common/currency", {"currencyCode": currency_code})

    async def get_transports(
        self, currency_code: Optional[str] = None, is_crypto_currency: Optional[bool] = None,
    ) -> List[Dict]:
        body: Dict[str, Any] = {}
        if currency_code:
            body["currencyCode"] = currency_code
        if is_crypto_currency is not None:
            body["isCryptoCurrency"] = is_crypto_currency
        try:
            result = await self._post("/product/rest/common/transports", body)
            return result if isinstance(result, list) else []
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text if exc.response is not None else ""
            if (
                exc.response is None
                or exc.response.status_code != 500
                or "Property or field 'clientId' cannot be found on object of type 'com.exscudo.vishnu.product.request.TransportsRequest'" not in response_text
            ):
                raise
            logger.warning("O-Plata common/transports is broken on this environment, falling back to common/currencies")
            currencies = await self.get_currencies(is_crypto_currency=is_crypto_currency)
            normalized_currency_code = (currency_code or "").upper()
            transports: List[Dict[str, Any]] = []
            for currency in currencies:
                currency_value = str(currency.get("currency") or "").upper()
                if normalized_currency_code and currency_value != normalized_currency_code:
                    continue
                for transport in currency.get("transports") or []:
                    if isinstance(transport, dict):
                        transports.append(transport)
            return transports

    async def get_limits(self, client_id: str, currency_code: str) -> Dict[str, Any]:
        return await self._post("/product/rest/common/limits", {"clientId": client_id, "currencyCode": currency_code})

    # ====== TRANSACTIONS ======

    async def get_transaction_list(
        self, client_id: str, page_number: int = 0, page_size: int = 20,
        currencies: Optional[List[str]] = None, states: Optional[List[str]] = None,
        period_start: Optional[int] = None, period_end: Optional[int] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"clientId": client_id, "pageNumber": page_number, "pageSize": page_size}
        if currencies:
            body["currencies"] = currencies
        if states:
            body["states"] = states
        if period_start is not None:
            body["periodStart"] = period_start
        if period_end is not None:
            body["periodEnd"] = period_end
        return await self._post("/product/rest/transaction/list", body)

    async def get_transaction_payment(self, client_id: str, uuid: str) -> Dict[str, Any]:
        return await self._post("/product/rest/transaction/payment", {"clientId": client_id, "uuid": uuid})

    async def confirm_payment(self, client_id: str, uuid: str) -> Dict[str, Any]:
        return await self._post("/product/rest/payment/confirm", {"clientId": client_id, "uuid": uuid})

    async def cancel_payment(self, client_id: str, uuid: str) -> Dict[str, Any]:
        return await self._post("/product/rest/payment/cancel", {"clientId": client_id, "uuid": uuid})

    # ====== DEPOSITS ======

    async def get_deposit_transports(self, client_id: str, credit_amount: float, currency_code: str) -> List[Dict]:
        result = await self._post("/product/rest/payment/deposit/transport", {
            "clientId": client_id, "creditAmount": credit_amount, "currencyCode": currency_code,
        })
        return result if isinstance(result, list) else []

    async def calculate_deposit(
        self, client_id: str, transport_id: str, credit_amount: Optional[float] = None, debit_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"clientId": client_id, "transportId": transport_id}
        if credit_amount is not None:
            body["creditAmount"] = credit_amount
        if debit_amount is not None:
            body["debitAmount"] = debit_amount
        return await self._post("/product/rest/payment/deposit/calculate", body)

    async def create_deposit(
        self, client_id: str, transport_id: str, credit_amount: Optional[float] = None, debit_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"clientId": client_id, "transportId": transport_id}
        if credit_amount is not None:
            body["creditAmount"] = credit_amount
        if debit_amount is not None:
            body["debitAmount"] = debit_amount
        return await self._post("/product/rest/payment/deposit/create", body)

    # ====== WITHDRAWALS ======

    async def get_withdrawal_transports(self, client_id: str, currency_code: str, debit_amount: float) -> List[Dict]:
        result = await self._post("/product/rest/payment/withdrawal/transport", {
            "clientId": client_id, "currencyCode": currency_code, "debitAmount": debit_amount,
        })
        return result if isinstance(result, list) else []

    async def calculate_withdrawal(
        self, client_id: str, transport_id: str, debit_amount: Optional[float] = None, credit_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"clientId": client_id, "transportId": transport_id}
        if debit_amount is not None:
            body["debitAmount"] = debit_amount
        if credit_amount is not None:
            body["creditAmount"] = credit_amount
        return await self._post("/product/rest/payment/withdrawal/calculate", body)

    async def create_withdrawal(
        self, client_id: str, transport_id: str, wallet_id: str,
        debit_amount: Optional[float] = None, credit_amount: Optional[float] = None,
        wallet_tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"clientId": client_id, "transportId": transport_id, "walletId": wallet_id}
        if debit_amount is not None:
            body["debitAmount"] = debit_amount
        if credit_amount is not None:
            body["creditAmount"] = credit_amount
        if wallet_tag:
            body["walletTag"] = wallet_tag
        return await self._post("/product/rest/payment/withdrawal/create", body)

    # ====== RATIOS ======

    async def get_rate(self, of_currency_code: str, for_currency_code: str) -> Dict[str, Any]:
        return await self._post("/product/rest/ratio/rate", {
            "ofCurrencyCode": of_currency_code, "forCurrencyCode": for_currency_code,
        })

    async def get_rates(self, of_currency_code: str) -> List[Dict]:
        result = await self._post("/product/rest/ratio/rates", {"ofCurrencyCode": of_currency_code})
        return result if isinstance(result, list) else []

    # ====== TRANSFER ======

    async def create_transfer(
        self, client_id: str, currency_code: str, amount: float, wallet_id: str,
    ) -> Dict[str, Any]:
        return await self._post("/product/rest/payment/transfer/create", {
            "clientId": client_id, "currencyCode": currency_code,
            "amount": amount, "walletId": wallet_id,
        })


oplata_client = OPlataClient()
