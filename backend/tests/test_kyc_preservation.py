"""Payment activity must preserve the customer's real KYC session and data."""
from datetime import datetime
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
import httpx

from app.api.deps import get_current_user
from app.api.routers import sbp
from app.core.config import settings
from app.core.database import get_db
from app.services import card_kyc, crypto_payment_service as crypto
from app.services.card_service import ONLINE_OFFER_ID
from test_card_kyc import unverified_user
from test_cryptoway import FakeSession, invoice, payment, user


class IdentityPreservationTests(TestCase):
    def test_real_kyc_states_are_never_overwritten(self):
        for status in ('pending', 'success', 'failed'):
            with self.subTest(status=status):
                owner = unverified_user()
                owner.kyc_status = status
                owner.kyc_session_id = 'unit-real-session'
                before = vars(owner).copy()
                with patch.object(card_kyc, '_synthetic_identity') as generator:
                    self.assertFalse(card_kyc.ensure_synthetic_identity(owner))
                generator.assert_not_called()
                self.assertEqual(vars(owner), before)

    def test_real_session_is_preserved_even_without_a_status(self):
        owner = unverified_user()
        owner.kyc_session_id = 'unit-real-session'
        before = vars(owner).copy()
        with patch.object(card_kyc, '_synthetic_identity') as generator:
            self.assertFalse(card_kyc.ensure_synthetic_identity(owner))
        generator.assert_not_called()
        self.assertEqual(vars(owner), before)

    def test_partial_identity_is_not_replaced(self):
        fields = ('kyc_first_name', 'kyc_last_name', 'kyc_patronymic',
                  'kyc_birth_date', 'kyc_passport', 'kyc_passport_issue_date')
        for field in fields:
            with self.subTest(field=field):
                owner = unverified_user()
                owner.kyc_session_id = None
                setattr(owner, field, 'unit-existing-value')
                before = vars(owner).copy()
                with patch.object(card_kyc, '_synthetic_identity') as generator:
                    self.assertFalse(card_kyc.ensure_synthetic_identity(owner))
                generator.assert_not_called()
                self.assertEqual(vars(owner), before)

    def test_synthetic_marker_does_not_override_a_real_kyc_status(self):
        for status in ('pending', 'failed', 'success'):
            with self.subTest(status=status):
                owner = unverified_user()
                owner.kyc_status = status
                owner.kyc_session_id = card_kyc.SYNTHETIC_KYC_SESSION
                for field in ('kyc_first_name', 'kyc_last_name', 'kyc_birth_date', 'kyc_passport'):
                    setattr(owner, field, 'unit-fixture')
                self.assertFalse(card_kyc.synthetic_ready(owner))


class PaymentKycPreservationTests(IsolatedAsyncioTestCase):
    async def test_pay_crypto_does_not_depend_on_neurovision_status(self):
        for purpose, offer in (('card_issue', 'ROCKETPAY:pay'), ('card_topup', 'ROCKETPAY')):
            for status in (None, 'pending', 'failed', 'success'):
                with self.subTest(purpose=purpose, status=status):
                    owner = unverified_user()
                    owner.kyc_status = status
                    owner.kyc_session_id = 'unit-real-session'
                    before = vars(owner).copy()
                    row = payment(purpose=purpose, offer_id=offer, status='quoted')
                    with patch.object(settings, 'CRYPTOWAY_PAY_WITHOUT_KYC', True), \
                         patch.object(crypto, 'enabled'), \
                         patch.object(crypto, 'networks', AsyncMock(return_value=[
                             {'symbol_id': 'USDTBEP20', 'name': 'Binance', 'min_amount': '1'}])), \
                         patch.object(crypto.cryptoway_client, 'create_invoice',
                                      AsyncMock(return_value=invoice(row, status='active'))) as provider:
                        await crypto.create_invoice(FakeSession(row=row), owner, row.id, 'USDTBEP20')
                    provider.assert_awaited_once()
                    self.assertEqual(row.status, 'active')
                    self.assertEqual(vars(owner), before)

    async def test_verified_online_crypto_preserves_real_identity(self):
        for purpose in ('card_issue', 'card_topup'):
            with self.subTest(purpose=purpose):
                owner = user()
                owner.email = 'unit@prontopay.pro'
                owner.phone = '+12025550123'
                owner.kyc_session_id = 'unit-real-session'
                before = vars(owner).copy()
                row = payment(purpose=purpose, offer_id=ONLINE_OFFER_ID, status='quoted')
                with patch.object(crypto, 'enabled'), \
                     patch.object(crypto, 'networks', AsyncMock(return_value=[
                         {'symbol_id': 'USDTBEP20', 'name': 'Binance', 'min_amount': '1'}])), \
                     patch.object(card_kyc, '_synthetic_identity') as generator, \
                     patch.object(crypto.cryptoway_client, 'create_invoice',
                                  AsyncMock(return_value=invoice(row, status='active'))) as provider:
                    await crypto.create_invoice(FakeSession(row=row), owner, row.id, 'USDTBEP20')
                generator.assert_not_called()
                provider.assert_awaited_once()
                self.assertEqual(vars(owner), before)

    async def test_sbp_rejects_unverified_identity_before_calling_gateway(self):
        app = FastAPI()
        app.include_router(sbp.router)
        owner = user()
        async def fake_db():
            yield FakeSession()
        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: owner
        with patch.object(settings, 'SBP_DISABLED', False), \
             patch.object(sbp, '_get_bb_fee_params', AsyncMock()) as gateway:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://unit.test') as client:
                for status in (None, 'pending', 'failed'):
                    owner.kyc_status = status
                    owner.kyc_session_id = card_kyc.SYNTHETIC_KYC_SESSION
                    for offer in (ONLINE_OFFER_ID, 'ROCKETPAY:pay'):
                        for purpose in ('card_issue', 'balance_topup'):
                            with self.subTest(status=status, offer=offer, purpose=purpose):
                                response = await client.post('/sbp/invoice', json={
                                    'purpose': purpose, 'offer_id': offer, 'card_id': 'unit-card',
                                    'amount_usd_requested': 100, 'amount_rub': 1499,
                                })
                                self.assertEqual(response.status_code, 403, response.text)
                                self.assertIn('KYC', response.json()['detail'])
        gateway.assert_not_awaited()

    async def test_status_reads_do_not_change_identity(self):
        for purpose in ('card_issue', 'card_topup'):
            for status in (None, 'pending', 'failed', 'success'):
                for payment_status in ('quoted', 'error', 'active', 'paid', 'review', 'expired', 'cancelled'):
                    with self.subTest(purpose=purpose, kyc=status, payment=payment_status):
                        owner = unverified_user()
                        owner.kyc_status = status
                        owner.kyc_session_id = 'unit-real-session' if status else None
                        before = vars(owner).copy()
                        row = payment(purpose=purpose, offer_id=ONLINE_OFFER_ID,
                                      status=payment_status, fulfillment_status='completed',
                                      last_checked_at=datetime.utcnow())
                        db = FakeSession(row=row, user=owner)
                        with patch.object(card_kyc, '_synthetic_identity') as generator, \
                             patch.object(crypto, 'update_order_outcome', AsyncMock()), \
                             patch.object(crypto.cryptoway_client, 'invoice', AsyncMock()) as provider:
                            result = await crypto.reconcile_payment(db, owner, row.id)
                        self.assertIs(result, row)
                        generator.assert_not_called()
                        provider.assert_not_awaited()
                        self.assertEqual(vars(owner), before)

    async def test_pending_or_failed_kyc_allows_crypto_without_replacing_identity(self):
        for purpose in ('card_issue', 'card_topup'):
            for status in ('pending', 'failed'):
                with self.subTest(purpose=purpose, status=status):
                    owner = unverified_user()
                    owner.kyc_status = status
                    owner.kyc_session_id = 'unit-real-session'
                    owner.email = 'unit@prontopay.pro'
                    owner.phone = '+12025550123'
                    before = vars(owner).copy()
                    row = payment(purpose=purpose, offer_id=ONLINE_OFFER_ID, status='quoted')
                    with patch.object(crypto, 'enabled'), \
                         patch.object(crypto, 'networks', AsyncMock(return_value=[
                             {'symbol_id': 'USDTBEP20', 'name': 'Binance', 'min_amount': '1'}])), \
                         patch.object(card_kyc, '_synthetic_identity') as generator, \
                         patch.object(crypto.cryptoway_client, 'create_invoice', AsyncMock(return_value=invoice(row, status='active'))) as provider:
                        await crypto.create_invoice(FakeSession(row=row), owner, row.id, 'USDTBEP20')
                    self.assertEqual(row.status, 'active')
                    generator.assert_not_called()
                    provider.assert_awaited_once()
                    self.assertEqual(vars(owner), before)
