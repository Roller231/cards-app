"""Real SQL ledger checks; provider calls and notifications never leave tests."""
from contextlib import ExitStack
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
import httpx
from sqlalchemy import BigInteger, create_engine, func, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers import cards, services, sbp
from app.api.routers.crypto_payments import QuoteRequest
from app.core.config import settings
from app.core.database import Base, get_db
from app.models.user import User
from app.models.card import Card
from app.models.order import Order
from app.models.service_request import ServiceRequest
from app.models.crypto_payment import CryptoPayment
from app.models.balance_tx import BalanceTransaction
from app.services import crypto_payment_service as crypto, wallet_service
from app.services.card_service import card_service, ONLINE_OFFER_ID
from app.services.card_kyc import card_provider_identity
from test_china_crypto import AsyncDb
from test_cryptoway import invoice, FakeSession
from test_card_kyc import unverified_user


@compiles(BigInteger, 'sqlite')
def sqlite_integer(type_, compiler, **kwargs):
    return 'INTEGER'


class TransactionDb(AsyncDb):
    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            self.session.rollback()


class WalletPaymentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.engine = create_engine('sqlite://'); self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine, tables=[model.__table__ for model in
            (User, Card, Order, ServiceRequest, CryptoPayment, BalanceTransaction)])
        self.session = Session(self.engine, expire_on_commit=False); self.addCleanup(self.session.close)
        self.db = TransactionDb(self.session)
        self.user = User(id=11, username='wallet_unit', balance=Decimal('400'), is_active=True,
                         email='unit@prontopay.pro', phone='+12025550123',
                         kyc_status='pending', kyc_session_id='real-unit-session')
        self.session.add(self.user); self.session.commit()
        self.stack.enter_context(patch.object(crypto, 'enabled', return_value=True))
        self.stack.enter_context(patch.object(crypto, 'AsyncSessionLocal', return_value=self.db))
        self.stack.enter_context(patch.object(settings, 'SBP_DISABLED', True))
        self.stack.enter_context(patch.object(settings, 'CHINA_CNY_DIVISOR', 6.54))
        self.notify = self.stack.enter_context(patch.object(services, 'send_to_managers', AsyncMock(return_value={'unit': 1})))
        self.stack.enter_context(patch.object(services, '_notify_user', AsyncMock()))

    def ledger(self):
        return self.session.scalars(select(BalanceTransaction)).all()

    async def quote(self, **changes):
        body = dict(request_id='wallet-request-0123456789', purpose='balance_deposit', amount_usd='100.00')
        body.update(changes)
        return await crypto.create_quote(self.db, self.user, QuoteRequest(**body))

    async def test_crypto_wallet_quote_is_one_to_one_and_needs_no_kyc_or_fx(self):
        with patch('app.services.rate_service.get_bb_index', AsyncMock(side_effect=AssertionError('No FX for wallet'))):
            row = await self.quote()
        self.assertEqual(row.charge_usdt, Decimal('100'))
        self.assertEqual(row.fee_percent, 0)
        self.assertIsNone(row.card_id)
        self.assertFalse(crypto.payment_view(row, self.user)['kyc_required'])
        self.assertFalse(crypto.payment_view(row, self.user)['contact_required'])
        self.assertEqual(self.user.kyc_session_id, 'real-unit-session')
        self.assertEqual(self.user.kyc_status, 'pending')
        self.assertIsNone(self.user.kyc_passport)
        same = await self.quote()
        self.assertEqual(same.id, row.id)
        with self.assertRaises(HTTPException): await self.quote(amount_usd='101')
        with self.assertRaises(HTTPException): await self.quote(request_id='wallet-other-0123456789', card_id=1)
        with self.assertRaises(HTTPException): await self.quote(request_id='wallet-small-0123456789', amount_usd='0.99')

    async def test_crypto_wallet_invoice_does_not_require_contacts_or_neurovision(self):
        row = await self.quote()
        row.provider_invoice_id = '11111111-1111-4111-8111-111111111111'
        self.user.email = self.user.phone = None
        self.session.commit()
        provider = AsyncMock(return_value=invoice(row, status='active', target_value_symbol='100', payer_amount='100'))
        with patch.object(crypto, 'networks', AsyncMock(return_value=[{'symbol_id':'USDTBEP20','name':'Binance','min_amount':'1'}])), \
             patch.object(crypto.cryptoway_client, 'create_invoice', provider):
            await crypto.create_invoice(self.db, self.user, row.id, 'USDTBEP20')
            await crypto.create_invoice(self.db, self.user, row.id, 'USDTBEP20')
        provider.assert_awaited_once()
        self.assertEqual(row.status, 'active')

    async def test_crypto_wallet_credit_happens_once_and_creates_no_card_order(self):
        row = await self.quote(); row.status = 'paid'; self.session.commit()
        await crypto.fulfill_payment(row.id)
        await crypto.fulfill_payment(row.id)
        await crypto.reconcile_payment(self.db, self.user, row.id)
        self.assertEqual(self.user.balance, Decimal('500.00'))
        self.assertEqual(row.fulfillment_status, 'completed')
        self.assertEqual(len(self.ledger()), 1)
        self.assertEqual(self.ledger()[0].type, 'crypto_deposit')
        self.assertEqual(self.session.scalar(select(func.count(Order.id))), 0)

    async def test_credit_and_completion_roll_back_together_and_retry_once(self):
        row = await self.quote(); row.status = 'paid'; self.session.commit()
        real_credit = wallet_service.credit
        async def interrupted(*args, **kwargs):
            await real_credit(*args, **kwargs)
            raise RuntimeError('simulated crash before commit')
        with patch.object(wallet_service, 'credit', interrupted):
            with self.assertRaisesRegex(RuntimeError, 'simulated crash'):
                await crypto.fulfill_payment(row.id)
        self.assertEqual(self.user.balance, Decimal('400.00'))
        self.assertEqual(row.fulfillment_status, 'not_started')
        self.assertEqual(len(self.ledger()), 0)
        await crypto.fulfill_payment(row.id)
        self.assertEqual(self.user.balance, Decimal('500.00'))
        self.assertEqual(len(self.ledger()), 1)

    async def test_unconfirmed_crypto_never_credits_balance(self):
        row = await self.quote()
        for status in ('quoted', 'active', 'review', 'expired', 'cancelled'):
            row.status = status; self.session.commit()
            await crypto.fulfill_payment(row.id)
        self.assertEqual(self.user.balance, Decimal('400.00'))
        self.assertEqual(self.ledger(), [])

    def request(self, **changes):
        fields = dict(id=33, user_id=11, service='alipay', amount=Decimal('2000'), currency='CNY',
                      payment_method='balance', amount_usdt=Decimal('305.81'), cny_per_usdt=Decimal('6.54'),
                      status='awaiting_payment', created_at=datetime.utcnow(), recipient_type='phone',
                      recipient_phone='+12025550123', recipient_name='UNIT TEST')
        fields.update(changes)
        row = ServiceRequest(**fields)
        self.session.add(row); self.session.commit()
        return row

    async def test_china_balance_payment_and_repeat_are_one_debit_and_handoff(self):
        for index, service in enumerate(('alipay', 'wechat')):
            with self.subTest(service=service):
                self.user.balance = Decimal('400'); self.session.commit()
                row = self.request(id=33+index, service=service)
                result = await services.pay_from_balance(row.id, self.db, self.user)
                await services.pay_from_balance(row.id, self.db, self.user)
                self.assertEqual(result['status'], 'paid')
                self.assertEqual(self.user.balance, Decimal('94.19'))
        self.assertEqual(len(self.ledger()), 2)
        self.assertEqual(self.notify.await_count, 2)
        self.assertEqual(self.user.kyc_status, 'pending')
        self.assertEqual(self.user.kyc_session_id, 'real-unit-session')

    async def test_china_insufficient_foreign_expired_and_wrong_method_never_debit(self):
        row = self.request()
        for fields, code in (({'amount_usdt':Decimal('500')},400),
                             ({'user_id':12},404),
                             ({'created_at':datetime.utcnow()-timedelta(hours=3)},409),
                             ({'payment_method':'crypto'},409),
                             ({'status':'rejected'},409)):
            before = {key:getattr(row,key) for key in fields}
            for key,value in fields.items():setattr(row,key,value)
            self.session.commit()
            with self.subTest(fields=fields), self.assertRaises(HTTPException) as error:
                await services.pay_from_balance(row.id, self.db, self.user)
            self.assertEqual(error.exception.status_code, code)
            for key,value in before.items():setattr(row,key,value)
            self.session.commit()
        self.assertEqual(self.user.balance, Decimal('400.00'))
        self.assertEqual(self.ledger(), [])
        self.notify.assert_not_awaited()

    async def test_other_payment_callbacks_cannot_mark_balance_request_paid(self):
        row = self.request()
        for kwargs in ({'invoice_id':1}, {'crypto_payment_id':1}):
            with self.assertRaises(ValueError): await services.on_request_paid(self.db, row.id, **kwargs)
        self.assertEqual(row.status, 'awaiting_payment')
        self.assertEqual(self.ledger(), [])

    async def test_create_and_pay_both_china_services_without_sbp_crypto_or_kyc(self):
        app=FastAPI();app.include_router(services.router)
        async def db():yield self.db
        app.dependency_overrides[get_db]=db
        app.dependency_overrides[get_current_user]=lambda:self.user
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as temp, patch.object(services,'QR_DIR',Path(temp)), \
             patch.object(crypto,'enabled',return_value=False), \
             patch('app.services.rate_service.get_bb_index',AsyncMock(side_effect=AssertionError('No RUB rate'))):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://unit.test') as client:
                rate=await client.get('/services/rate?payment_method=balance')
                self.assertEqual(rate.status_code,200,rate.text)
                for index, service in enumerate(('alipay','wechat')):
                    self.user.balance=Decimal('400');self.session.commit()
                    response=await client.post('/services/requests',data={
                        'service':service,'amount':'2000','payment_method':'balance','recipient_type':'qr',
                    },files={'qr':('unit.png',b'\x89PNG\r\n\x1a\nunit','image/png')})
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['amount_usd'],'305.81')
                    paid=await client.post(f"/services/requests/{response.json()['id']}/pay-balance")
                    self.assertEqual(paid.status_code,200,paid.text)
                    self.assertEqual(self.user.balance,Decimal('94.19'))
                    saved=self.session.get(ServiceRequest,response.json()['id'])
                    saved.created_at=datetime.utcnow()-timedelta(minutes=1);self.session.commit()

    async def test_all_sbp_purposes_require_real_kyc_before_gateway_or_rates(self):
        app = FastAPI(); app.include_router(sbp.router)
        async def db(): yield self.db
        app.dependency_overrides[get_db] = db
        app.dependency_overrides[get_current_user] = lambda:self.user
        with patch.object(settings, 'SBP_DISABLED', False), \
             patch.object(sbp, '_get_bb_fee_params', AsyncMock()) as gateway:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://unit.test') as client:
                for purpose in ('card_issue','balance_topup','balance_deposit','china_payment'):
                    response = await client.post('/sbp/invoice', json={'purpose':purpose,'amount_rub':5000})
                    self.assertEqual(response.status_code,403,response.text)
        gateway.assert_not_awaited()


class BalanceCardTests(unittest.IsolatedAsyncioTestCase):
    async def test_online_balance_issue_uses_provider_view_and_preserves_real_session(self):
        for status in ('pending', 'failed', 'success'):
            owner = unverified_user(); owner.kyc_status = status; owner.kyc_session_id = 'real-unit-session'
            owner.email='unit@prontopay.pro'; owner.phone='+12025550123'
            before = vars(owner).copy()
            with patch.object(card_service,'_ensure_client', AsyncMock(side_effect=RuntimeError('PAST_GATE'))) as provider:
                with self.assertRaisesRegex(RuntimeError,'PAST_GATE'):
                    await card_service.issue_card(FakeSession(), owner, ONLINE_OFFER_ID, 'Unit', 'Test',
                                                  skip_balance_check=True, balance_charge_usd=Decimal('20'))
            identity = provider.call_args.kwargs['user']
            self.assertTrue(identity.kyc_first_name)
            self.assertEqual(vars(owner), before)

    async def test_balance_card_routes_accept_unverified_owners_before_scheduling(self):
        owner=unverified_user(); owner.email='unit@prontopay.pro'; owner.phone='+12025550123'
        app=FastAPI(); app.include_router(cards.router)
        async def db():yield FakeSession()
        app.dependency_overrides[get_db]=db
        app.dependency_overrides[get_current_user]=lambda:owner
        card=SimpleNamespace(offer_id=ONLINE_OFFER_ID,aifory_card_id='unit-card',last4='1234')
        with patch.object(settings,'CARD_ONLINE_ENABLED',True), \
             patch.object(cards,'_balance_issue_quote',AsyncMock(return_value={'price_usd':Decimal('20'),'price_rub':1499,'rate':75})), \
             patch.object(card_service,'_resolve_card',AsyncMock(return_value=card)), \
             patch.object(wallet_service,'debit',AsyncMock()) as debit, \
             patch.object(card_service,'schedule_issue_in_background') as issue, \
             patch.object(card_service,'schedule_deposit_in_background') as deposit:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://unit.test') as client:
                response=await client.post('/cards/issue',json={'offer_id':ONLINE_OFFER_ID,'holder_first_name':'Unit','holder_last_name':'Test','payment_method':'balance'})
                self.assertEqual(response.status_code,200,response.text)
                response=await client.post('/cards/unit-card/deposit',json={'amount':100,'payment_method':'balance'})
                self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(debit.await_count,2)
        issue.assert_called_once();deposit.assert_called_once()
        self.assertIsNone(owner.kyc_status)
