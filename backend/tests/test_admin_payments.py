"""Real SQL checks for the complete admin journal, linkage and pagination."""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.deps import get_admin
from app.api.routers.admin_payments import router, payments, payment_detail
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.balance_tx import BalanceTransaction
from app.models.bb_invoice import BbInvoice
from app.models.card import Card
from app.models.crypto_payment import CryptoPayment
from app.models.order import Order
from app.models.service_request import ServiceRequest
from app.models.topup import BalanceTopUpRequest
from app.models.user import User
from test_wallet_payments import TransactionDb


class AdminPaymentHistoryTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine, tables=[m.__table__ for m in (
            User, Card, Order, BbInvoice, ServiceRequest, CryptoPayment,
            BalanceTransaction, BalanceTopUpRequest)])
        self.session = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.session.close)
        self.db = TransactionDb(self.session)
        self.now = datetime(2026, 11, 16, 19, 17, 33)
        self.session.add_all([User(id=576, username='Jekamamka', balance=Decimal('11')),
                              User(id=577, username='other_user', balance=Decimal('0'))])
        self.session.add_all([
            BbInvoice(id=207, user_id=576, idempotency_key='unit-207', external_client_ref='unit-576',
                      purpose='card_issue', amount_rub=Decimal('1349'), status='captured',
                      recover_attempts=2, created_at=self.now),
            BbInvoice(id=208, user_id=576, idempotency_key='unit-208', external_client_ref='unit-576',
                      purpose='balance_deposit', amount_rub=Decimal('1226'), amount_usd=Decimal('11'),
                      status='captured', created_at=self.now + timedelta(minutes=10)),
            BalanceTransaction(id=35, user_id=576, type='deposit', amount=Decimal('11'),
                               balance_after=Decimal('11'), ref_invoice_id=208, created_at=self.now + timedelta(minutes=11)),
        ])
        self.session.commit()

    async def history(self, **kwargs):
        args = dict(source=None, search='', status='', purpose='', user_id=None,
                    date_from=None, date_to=None, limit=50, offset=0, db=self.db, _='admin')
        args.update(kwargs)
        return await payments(**args)

    async def test_paid_invoice_without_order_and_balance_deposit_are_visible(self):
        result = await self.history()
        self.assertEqual(result['total'], 3)
        rows = {r['key']: r for r in result['items']}
        self.assertEqual(rows['sbp:207']['execution_status'], 'missing_order')
        self.assertEqual(rows['sbp:208']['execution_status'], 'completed')
        self.assertEqual(Decimal(rows['balance:35']['amount']), Decimal('11'))
        self.assertEqual(rows['sbp:207']['created_at'], '2026-11-16T19:17:33Z')
        self.assertEqual(self.session.get(User, 576).balance, Decimal('11'))

    async def test_invoice_token_is_exact_and_related_events_have_the_same_owner(self):
        self.session.add_all([
            Order(id=203, user_id=576, type='issue', amount=0, fee=30, status='completed',
                  description='Card issuance sbp_invoice:207', created_at=self.now),
            Order(id=204, user_id=576, type='issue', amount=0, fee=30, status='failed',
                  description='Card issuance sbp_invoice:2070', created_at=self.now),
            Order(id=205, user_id=577, type='issue', amount=0, fee=30, status='failed',
                  description='Card issuance sbp_invoice:207', created_at=self.now),
        ])
        self.session.commit()
        result = await self.history(source='sbp', search='207')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['execution_status'], 'completed')
        self.assertEqual(result['items'][0]['order_id'], 203)
        detail = await payment_detail('sbp', 207, self.db, 'admin')
        self.assertEqual([r['key'] for r in detail['related']], ['order:203'])
        detail = await payment_detail('sbp', 208, self.db, 'admin')
        self.assertEqual([r['key'] for r in detail['related']], ['balance:35'])

    async def test_pagination_reaches_the_oldest_event_past_the_old_100_limit(self):
        self.session.add_all([Order(id=i, user_id=576, type='topup', amount=1, fee=0,
                                   status='completed', created_at=self.now - timedelta(days=30)) for i in range(1, 141)])
        self.session.commit()
        all_keys = []
        for offset in range(0, 143, 25):
            result = await self.history(limit=25, offset=offset)
            self.assertEqual(result['total'], 143)
            all_keys.extend(r['key'] for r in result['items'])
        self.assertEqual(len(all_keys), 143)
        self.assertEqual(len(set(all_keys)), 143)
        self.assertIn('order:1', all_keys)
        self.assertEqual((await self.history(offset=143))['items'], [])

    async def test_crypto_china_and_legacy_events_are_preserved(self):
        self.session.add(ServiceRequest(id=47, user_id=576, service='alipay', amount=200,
            currency='CNY', payment_method='crypto', status='done', created_at=self.now))
        self.session.add(CryptoPayment(id=34, user_id=576, request_id='unit-request', external_id='unit-crypto',
            provider_invoice_id='unit-provider', purpose='china_payment', service_request_id=47,
            amount_usd=Decimal('30.58'), charge_usdt=Decimal('30.58123456'), status='paid',
            fulfillment_status='completed', paid_at=self.now, expires_at=self.now + timedelta(days=1),
            created_at=self.now))
        self.session.add(BalanceTopUpRequest(id=1, user_id=576, amount=20, status='confirmed'))
        self.session.commit()
        result = await self.history()
        rows = {r['key']: r for r in result['items']}
        self.assertEqual(Decimal(rows['crypto:34']['amount']), Decimal('30.58123456'))
        self.assertEqual(rows['china:47']['currency'], 'CNY')
        self.assertIsNone(rows['legacy:1']['created_at'])
        detail = await payment_detail('crypto', 34, self.db, 'admin')
        self.assertEqual([r['key'] for r in detail['related']], ['china:47'])
        self.assertNotIn('provider_payload', str(detail))
        self.assertNotIn('kyc_passport', str(detail))

    async def test_search_status_source_and_dates_apply_before_count_and_pagination(self):
        result = await self.history(search='@JEKAMAMKA', source='sbp', status='captured',
                                    purpose='balance_deposit', limit=1)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['key'], 'sbp:208')
        result = await self.history(date_from=self.now, date_to=self.now + timedelta(minutes=1))
        self.assertEqual([r['key'] for r in result['items']], ['sbp:207'])
        self.assertEqual((await self.history(user_id=577))['total'], 0)
        self.assertEqual((await self.history(search='%'))['total'], 0)

    async def test_routes_require_admin_and_validate_filters(self):
        app = FastAPI(); app.include_router(router, prefix='/admin')
        async def db():
            yield self.db
        app.dependency_overrides[get_db] = db
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://unit.test') as client:
            self.assertIn((await client.get('/admin/payments')).status_code, (401, 403))
            self.assertIn((await client.get('/admin/payments/sbp/207')).status_code, (401, 403))
            self.assertEqual((await client.get('/admin/payments', headers={
                'Authorization': 'Bearer ' + create_access_token('576')})).status_code, 403)
            app.dependency_overrides[get_admin] = lambda: 'admin'
            self.assertEqual((await client.get('/admin/payments')).status_code, 200)
            for query in ('limit=0', 'limit=201', 'offset=-1', 'source=invalid',
                          'date_from=2026-11-17T00:00:00Z&date_to=2026-11-16T00:00:00Z'):
                self.assertEqual((await client.get('/admin/payments?' + query)).status_code, 422)
            self.assertEqual((await client.get('/admin/payments/sbp/999')).status_code, 404)
            self.assertEqual((await client.get('/admin/payments/invalid/207')).status_code, 422)
