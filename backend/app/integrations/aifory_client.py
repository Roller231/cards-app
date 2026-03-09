import httpx
from typing import Optional, Dict, Any
from app.core.config import settings


class AiforyClient:
    """HTTP client for Aifory Virtual Cards API."""
    
    def __init__(self):
        self.base_url = settings.AIFORY_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {settings.AIFORY_TOKEN}",
            "Content-Type": "application/json",
        }
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to Aifory API."""
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data or {},
            )
            response.raise_for_status()
            return response.json()
    
    # ==================== ACCOUNTS ====================
    
    async def get_accounts(self) -> Dict[str, Any]:
        """Get accounts to retrieve accountID for operations."""
        return await self._request("POST", "/v1/accounts")
    
    # ==================== CARD OFFERS ====================
    
    async def get_card_offers(self) -> Dict[str, Any]:
        """Get available card offers (bins)."""
        return await self._request("POST", "/v1/virtual-cards/cards/offers")
    
    # ==================== CARD ISSUANCE ====================
    
    async def calculate_card_order(
        self,
        bin: str,
        amount: str,
        account_id: str,
        account_id_to_exchange: Optional[str] = None,
        validate_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate fees for card issuance."""
        data = {
            "bin": bin,
            "amount": amount,
            "accountID": account_id,
        }
        if account_id_to_exchange:
            data["accountIDToExchange"] = account_id_to_exchange
        if validate_key:
            data["validateKey"] = validate_key
        return await self._request("POST", "/v1/virtual-cards/calculate-order", data)
    
    async def create_card_order(
        self,
        bin: str,
        amount: str,
        email: str,
        account_id: str,
        account_id_to_exchange: Optional[str] = None,
        validate_key: Optional[str] = None,
        code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create order to issue a new card."""
        data = {
            "bin": bin,
            "amount": amount,
            "email": email,
            "accountID": account_id,
        }
        if account_id_to_exchange:
            data["accountIDToExchange"] = account_id_to_exchange
        if validate_key:
            data["validateKey"] = validate_key
        if code:
            data["code"] = code
        return await self._request("POST", "/v1/virtual-cards/order", data)
    
    # ==================== CARDS ====================
    
    async def get_cards(self) -> Dict[str, Any]:
        """Get all cards."""
        return await self._request("POST", "/v1/virtual-cards/cards/get")
    
    async def get_card_requisites(self, card_id: str) -> Dict[str, Any]:
        """Get card requisites (number, CVV, holder). DO NOT STORE!"""
        return await self._request("POST", "/v1/virtual-cards/cards/requisites", {"cardID": card_id})
    
    # ==================== DEPOSIT ====================
    
    async def get_deposit_offer(self, card_id: str) -> Dict[str, Any]:
        """Get deposit offer for a card (min/max amounts, fee)."""
        return await self._request("POST", "/v1/virtual-cards/deposit/offer", {"cardID": card_id})
    
    async def calculate_deposit_order(
        self,
        card_id: str,
        amount: str,
        account_id: str,
        account_id_to_exchange: Optional[str] = None,
        validate_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate fees for card deposit."""
        data = {
            "cardID": card_id,
            "amount": amount,
            "accountID": account_id,
        }
        if account_id_to_exchange:
            data["accountIDToExchange"] = account_id_to_exchange
        if validate_key:
            data["validateKey"] = validate_key
        return await self._request("POST", "/v1/virtual-cards/deposit/calculate-order", data)
    
    async def create_deposit_order(
        self,
        card_id: str,
        amount: str,
        account_id: str,
        account_id_to_exchange: Optional[str] = None,
        validate_key: Optional[str] = None,
        code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create deposit order to top up a card."""
        data = {
            "cardID": card_id,
            "amount": amount,
            "accountID": account_id,
        }
        if account_id_to_exchange:
            data["accountIDToExchange"] = account_id_to_exchange
        if validate_key:
            data["validateKey"] = validate_key
        if code:
            data["code"] = code
        return await self._request("POST", "/v1/virtual-cards/deposit/order", data)
    
    # ==================== ORDERS ====================
    
    async def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """Get order status and details (for polling)."""
        return await self._request("POST", "/v1/virtual-cards/common/details", {"orderID": order_id})
    
    # ==================== TRANSACTIONS ====================
    
    async def get_card_transactions(
        self,
        card_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get transactions for a card."""
        return await self._request(
            "POST",
            "/v1/virtual-cards/common/card-transactions",
            {"cardID": card_id, "limit": limit, "offset": offset},
        )
    
    async def get_transaction_details(self, card_id: str, transaction_id: str) -> Dict[str, Any]:
        """Get transaction details."""
        return await self._request(
            "POST",
            "/v1/virtual-cards/common/card-transaction-details",
            {"cardID": card_id, "transactionID": transaction_id},
        )
    
    # ==================== COMMON ====================
    
    async def get_payment_systems(self) -> Dict[str, Any]:
        """Get payment systems."""
        return await self._request("POST", "/v1/virtual-cards/common/payment-systems")
    
    async def get_countries(self) -> Dict[str, Any]:
        """Get countries."""
        return await self._request("POST", "/v1/virtual-cards/common/countries")


aifory_client = AiforyClient()
