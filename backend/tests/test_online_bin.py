"""Offline regression checks for the 2026-11-02 Online type replacement.

Run from backend: venv/Scripts/python.exe -m unittest discover -s tests -v
No database, provider writes, or Telegram calls are used.
"""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from app.models.card import Card, _set_billing_identity
from app.services import billing_identity
from app.services import card_service as module


CURRENT = "RAVANA:RT-prod:f5d8ea65-6c55-43e6-b7a1-19e103be42ce"
RETIRED = (
    "RAVANA:RT-prod:faa1988b-a467-4397-85c7-ab380fea7bb4",
    "RAVANA:RT-prod:747f2774-646e-4901-a8ce-c79a185fab74",
    "RAVANA:RT-prod:6704da1b-7850-46ad-837a-c06336ccbfa5",
)
# Relevant cardTypesList fields from the read-only live API inspection.
PROVIDERS = [{
    "ravanaServerId": "RAVANA:RT-prod", "cardCurrency": "USD",
    "minimumCardBalance": "1", "maxIssuedCount": 10, "cardsList": [],
    "cardTypesList": [
        {"uuid": CURRENT.rsplit(":", 1)[1], "paymentSystem": "MASTERCARD",
         "readOnly": False, "validityPeriod": 24, "transactionConstantFee": "0.8"},
        *[{"uuid": offer.rsplit(":", 1)[1], "paymentSystem": "MASTERCARD", "readOnly": True}
          for offer in RETIRED],
    ],
}]


class OnlineOffersTests(unittest.IsolatedAsyncioTestCase):
    async def offers(self, providers):
        with patch.object(module.oplata_client, "get_virtual_card_list", AsyncMock(return_value=providers)), \
             patch.object(module.settings, "CARD_ONLINE_ENABLED", True):
            return await module.CardService()._get_oplata_offers()

    async def test_only_current_online_is_offered(self):
        offers = await self.offers(deepcopy(PROVIDERS))
        self.assertEqual([(o["id"], o["name"], o["payment_system"]) for o in offers],
                         [(CURRENT, "Online", "MASTERCARD")])

    async def test_readonly_replacement_is_not_sold(self):
        providers = deepcopy(PROVIDERS)
        providers[0]["cardTypesList"][0]["readOnly"] = True
        self.assertEqual(await self.offers(providers), [])

    async def test_retired_types_stay_hidden_if_provider_reenables_them(self):
        providers = deepcopy(PROVIDERS)
        for card_type in providers[0]["cardTypesList"]:
            card_type["readOnly"] = False
        self.assertEqual([o["id"] for o in await self.offers(providers)], [CURRENT])

    async def test_paid_old_offers_resolve_before_provider_calls(self):
        class StopBeforeKyc(Exception):
            pass

        service = module.CardService()
        user = SimpleNamespace(id=123, telegram_user_id="123", client_seq=0, username="test")
        for offer in (*RETIRED, CURRENT):
            with self.subTest(offer=offer), \
                 patch.object(service, "_ensure_client", AsyncMock(side_effect=StopBeforeKyc)), \
                 patch.object(module, "_parse_offer_id", wraps=module._parse_offer_id) as parse:
                with self.assertRaises(StopBeforeKyc):
                    await service.issue_card(None, user, offer, "Example", "User",
                                             skip_balance_check=True, sbp_invoice_id=999)
                parse.assert_called_once_with(CURRENT)


class BillingIdentityTests(unittest.TestCase):
    def test_new_online_identities_are_singapore_with_matching_postal_code(self):
        for offer in (CURRENT, "RAVANA:RT-prod", None):
            for _ in range(20):
                identity = billing_identity.generate(offer)
                self.assertEqual(identity["billing_country"], "Singapore")
                self.assertRegex(identity["billing_postal"], r"^\d{6}$")
                matches = [(block, street, postal) for block, street, postal in billing_identity._ADDRESSES
                           if identity["billing_address"].startswith(f"{block} {street} #")]
                self.assertEqual(len(matches), 1)
                self.assertEqual(identity["billing_postal"], matches[0][2])

    def test_pay_and_explicit_old_hk_offer_remain_hong_kong(self):
        for offer in ("ROCKETPAY", "ROCKETPAY:pay", RETIRED[1]):
            identity = billing_identity.generate(offer)
            self.assertEqual(identity["billing_country"], "Hong Kong")
            self.assertEqual(identity["billing_postal"], "000000")

    def test_card_insert_hook_generates_sg_for_new_online(self):
        card = Card(user_id=123, offer_id="RAVANA:RT-prod", balance=Decimal("0"))
        _set_billing_identity(None, None, card)
        self.assertEqual(card.billing_country, "Singapore")
        self.assertRegex(card.billing_postal, r"^\d{6}$")

    def test_existing_identity_is_not_replaced(self):
        card = Card(user_id=123, offer_id="RAVANA:RT-prod", billing_name="Existing Name",
                    billing_address="Existing HK address", billing_country="Hong Kong")
        with patch.object(billing_identity, "generate") as generate:
            _set_billing_identity(None, None, card)
        generate.assert_not_called()
        self.assertEqual(card.billing_country, "Hong Kong")
        self.assertEqual(card.billing_address, "Existing HK address")


if __name__ == "__main__":
    unittest.main()
