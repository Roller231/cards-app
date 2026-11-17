"""Payment activity must preserve the customer's real KYC session and data."""
from datetime import datetime
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch
from contextlib import ExitStack

from fastapi import FastAPI, HTTPException
import httpx
from decimal import Decimal
from types import SimpleNamespace

from app.api.deps import get_current_user
from app.api.routers import sbp
from app.core.config import settings
from app.core.database import get_db
from app.services import card_kyc, crypto_payment_service as crypto
from app.services.card_service import ONLINE_OFFER_ID, card_service
from app.integrations.oplata_client import oplata_client
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
    async def test_online_topup_uses_provider_view_through_real_registration(self):
        # The top-up branch must use the same provider view as issuance.
        # Keep _ensure_client real so its KYC guard is part of the regression.
        for mode in ('crypto', 'balance'):
            for status in ('pending', 'failed', 'success'):
                with self.subTest(mode=mode, status=status):
                    owner = unverified_user()
                    owner.kyc_status = status
                    owner.kyc_session_id = 'unit-real-session'
                    owner.email = 'unit@prontopay.pro'
                    owner.phone = '+79991234567'
                    before = vars(owner).copy()
                    card = SimpleNamespace(id=22, offer_id='RAVANA:RT-prod', aifory_card_id='unit-card')
                    row = payment(status='paid', purpose='card_topup', offer_id=card.offer_id)
                    kwargs = {'crypto_payment_id': 1, 'allow_synthetic_kyc': True} if mode == 'crypto' else {'balance_charge_usd': Decimal('103.60')}
                    with ExitStack() as stack:
                        stack.enter_context(patch.object(card_service, '_resolve_card', AsyncMock(return_value=card)))
                        stack.enter_context(patch.object(card_service, '_provider_balance_currency', AsyncMock(return_value='USDT')))
                        stack.enter_context(patch.object(oplata_client, 'register_client', AsyncMock(return_value={'clientWalletId': 'unit-wallet'})))
                        for name in ('kyc_verify_email', 'kyc_verify_person', 'kyc_verify_country', 'kyc_verify_home'):
                            stack.enter_context(patch.object(oplata_client, name, AsyncMock(return_value={})))
                        stack.enter_context(patch.object(oplata_client, 'kyc_info', AsyncMock(return_value={
                            'checksVerified': ['PARTNER'],
                            'orderResponses': [{'orderType': 'PARTNER', 'orderState': 'COMPLETED'}]})))
                        partner = stack.enter_context(patch.object(oplata_client, 'kyc_verify_partner_start', AsyncMock(return_value={})))
                        topup = stack.enter_context(patch.object(oplata_client, 'topup_card', AsyncMock(side_effect=RuntimeError('PAST_REGISTRATION'))))
                        with self.assertRaisesRegex(RuntimeError, 'PAST_REGISTRATION'):
                            await card_service.deposit_card(FakeSession(row=row, user=owner), owner, '22', 100,
                                                            skip_balance_check=True, **kwargs)
                    topup.assert_awaited_once()
                    partner.assert_awaited_once()
                    self.assertEqual(vars(owner), before)

    async def test_topup_without_allowed_payment_still_requires_verified_identity(self):
        owner = unverified_user()
        owner.kyc_status = 'pending'
        owner.kyc_session_id = 'unit-real-session'
        owner.email = 'unit@prontopay.pro'
        owner.phone = '+79991234567'
        before = vars(owner).copy()
        card = SimpleNamespace(id=22, offer_id='RAVANA:RT-prod', aifory_card_id='unit-card')
        with patch.object(card_service, '_resolve_card', AsyncMock(return_value=card)), \
             patch.object(oplata_client, 'register_client', AsyncMock()) as register, \
             patch.object(oplata_client, 'topup_card', AsyncMock()) as topup:
            with self.assertRaisesRegex(ValueError, 'KYC'):
                await card_service.deposit_card(FakeSession(), owner, '22', 100, skip_balance_check=True)
        register.assert_not_awaited()
        topup.assert_not_awaited()
        self.assertEqual(vars(owner), before)

    async def test_provider_view_reaches_registration_with_pending_real_session_intact(self):
        # Exercise the real consumer of the view: mocking _ensure_client hid
        # its direct access to kyc_status and missed the production crash.
        for status in ('pending', 'failed', 'success'):
            with self.subTest(status=status):
                owner = unverified_user()
                owner.kyc_status = status
                owner.kyc_session_id = 'unit-real-session'
                owner.email = 'unit@prontopay.pro'
                owner.phone = '+79991234567'
                before = vars(owner).copy()
                identity = card_kyc.card_provider_identity(owner)
                self.assertIsNone(identity.kyc_status)
                self.assertTrue(card_kyc.synthetic_ready(identity))
                self.assertFalse(card_kyc.kyc_ready(identity))
                with ExitStack() as stack:
                    register = stack.enter_context(patch.object(oplata_client, 'register_client',
                        AsyncMock(return_value={'clientWalletId': 'unit-wallet'})))
                    for name in ('kyc_verify_email', 'kyc_verify_person', 'kyc_verify_country', 'kyc_verify_home'):
                        stack.enter_context(patch.object(oplata_client, name, AsyncMock(return_value={})))
                    stack.enter_context(patch.object(oplata_client, 'kyc_info', AsyncMock(return_value={
                        'checksVerified': ['PARTNER'],
                        'orderResponses': [{'orderType': 'PARTNER', 'orderState': 'COMPLETED'}]})))
                    partner = stack.enter_context(patch.object(oplata_client, 'kyc_verify_partner_start',
                        AsyncMock(return_value={})))
                    result = await card_service._ensure_client('unit-client', identity)
                self.assertEqual(result, 'unit-wallet')
                register.assert_awaited_once()
                partner.assert_awaited_once()
                self.assertEqual(vars(owner), before)

    def test_verified_provider_identity_stays_the_original_user(self):
        owner = user()
        before = vars(owner).copy()
        self.assertIs(card_kyc.card_provider_identity(owner), owner)
        self.assertEqual(vars(owner), before)

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
