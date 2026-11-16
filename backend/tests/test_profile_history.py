"""Historical wallet entries and direct crypto payments retain distinct dates."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from fastapi import FastAPI
import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.profile import router
from app.core.database import Base, get_db
from app.models.user import User
from app.models.card import Card
from app.models.order import Order
from app.models.service_request import ServiceRequest
from app.models.crypto_payment import CryptoPayment
from app.models.balance_tx import BalanceTransaction
from app.services import wallet_service as wallet
from test_wallet_payments import TransactionDb


class ProfileHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine, tables=[m.__table__ for m in (
            User, Card, Order, ServiceRequest, CryptoPayment, BalanceTransaction)])
        self.session = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.session.close)
        self.db = TransactionDb(self.session)
        self.owner = User(id=11, username='history_owner', balance=Decimal('20'), is_active=True)
        self.other = User(id=22, username='history_other', balance=Decimal('0'), is_active=True)
        self.session.add_all([self.owner, self.other])
        self.session.commit()

    def payment(self, pk=1, **changes):
        values = dict(id=pk, user_id=11, request_id=f'history-{pk:016}', external_id=f'history-{pk}',
                      provider_invoice_id=f'unit-invoice-{pk}', purpose='card_topup',
                      amount_usd=Decimal('100'), charge_usdt=Decimal('103.60'),
                      received_usdt=Decimal('103.60'), status='paid', fulfillment_status='completed',
                      created_at=datetime(2026, 11, 11, 11, 8), paid_at=datetime(2026, 11, 11, 11, 13),
                      expires_at=datetime(2026, 11, 12), refund_credited=False)
        values.update(changes)
        row = CryptoPayment(**values)
        self.session.add(row)
        return row

    async def test_october_wallet_debit_and_november_crypto_payment_have_their_own_dates(self):
        self.session.add(BalanceTransaction(user_id=11, type='card_topup', amount=Decimal('-103.60'),
            balance_after=Decimal('12.96'), created_at=datetime(2026, 10, 28, 19, 58, 47)))
        self.payment()
        self.session.commit()
        ledger = await wallet.history(self.db, 11)
        payments = await wallet.crypto_history(self.db, 11)
        self.assertEqual(ledger[0]['created_at'], '2026-10-28T19:58:47Z')
        self.assertEqual(payments[0]['paid_at'], '2026-11-11T11:13:00Z')
        self.assertEqual(Decimal(payments[0]['amount_usdt']), Decimal('103.60'))
        self.assertEqual(self.owner.balance, Decimal('20'))
        self.assertEqual(len(self.session.scalars(select(BalanceTransaction)).all()), 1)

    async def test_only_owned_confirmed_direct_payments_are_shown(self):
        self.payment()
        self.payment(2, status='quoted', paid_at=None)
        self.payment(3, status='cancelled')
        self.payment(4, status='active')
        self.payment(5, user_id=22)
        self.payment(6, purpose='balance_deposit')
        self.payment(7, received_usdt=Decimal('103.59999999'))
        self.payment(8, provider_invoice_id=None)
        self.payment(9, paid_at=None)
        self.session.commit()
        self.assertEqual([r['id'] for r in await wallet.crypto_history(self.db, 11)], [1])

    async def test_crypto_history_sorts_by_payment_time_and_paginates(self):
        self.payment(30, paid_at=datetime(2026, 11, 10))
        self.payment(20, paid_at=datetime(2026, 11, 12))
        self.payment(10, paid_at=datetime(2026, 11, 13))
        self.session.commit()
        self.assertEqual([r['id'] for r in await wallet.crypto_history(self.db, 11)], [10, 20, 30])
        self.assertEqual([r['id'] for r in await wallet.crypto_history(self.db, 11, limit=1, offset=1)], [20])

    async def test_migration_is_labelled_without_rewriting_financial_records(self):
        original = 'Сброс фантомного баланса (миграция внутреннего баланса)'
        self.session.add_all([
            BalanceTransaction(id=1, user_id=11, type='admin_adjust', amount=Decimal('-1576.95'),
                balance_after=Decimal('0'), description=original, created_at=datetime(2026, 9, 21)),
            BalanceTransaction(id=2, user_id=11, type='admin_adjust', amount=Decimal('20'),
                balance_after=Decimal('20'), description='Ручная корректировка', created_at=datetime(2026, 10, 28)),
        ])
        self.session.commit()
        result = await wallet.history(self.db, 11)
        self.assertEqual([r['id'] for r in result], [2, 1])
        self.assertFalse(result[0]['is_system'])
        self.assertTrue(result[1]['is_system'])
        self.assertIn('Не банковское списание', result[1]['description'])
        self.assertEqual(result[1]['amount'], -1576.95)
        self.assertEqual(self.session.get(BalanceTransaction, 1).description, original)

    async def test_new_credit_and_debit_have_current_utc_dates_and_correct_balances(self):
        before = datetime.utcnow()
        credit = await wallet.credit(self.db, self.owner, 5, 'deposit')
        debit = await wallet.debit(self.db, self.owner, 3, 'card_topup')
        after = datetime.utcnow()
        self.assertEqual(self.owner.balance, Decimal('22'))
        self.assertEqual(credit.balance_after, Decimal('25'))
        self.assertEqual(debit.balance_after, Decimal('22'))
        for row in (credit, debit):
            self.assertLessEqual(before, row.created_at)
            self.assertLessEqual(row.created_at, after)
        history = await wallet.history(self.db, 11)
        self.assertTrue(all(r['created_at'].endswith('Z') for r in history))

    async def test_api_uses_authenticated_account_and_validates_pagination(self):
        self.payment()
        self.payment(2, user_id=22)
        self.session.commit()
        app = FastAPI()
        app.include_router(router)
        async def db():
            yield self.db
        app.dependency_overrides[get_db] = db
        app.dependency_overrides[get_current_user] = lambda: self.owner
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://unit.test') as client:
            response = await client.get('/profile/crypto/history?user_id=22')
            invalid = await client.get('/profile/crypto/history?limit=0')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['id'] for r in response.json()['items']], [1])
        self.assertNotIn('provider_invoice_id', response.json()['items'][0])
        self.assertEqual(invalid.status_code, 422)

    def test_utc_serialization_normalizes_explicit_offsets(self):
        value = datetime(2026, 11, 13, 0, 30, tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(wallet.utc_timestamp(value), '2026-11-12T21:30:00Z')
        self.assertIsNone(wallet.utc_timestamp(None))

    def test_legacy_provider_names_are_not_exposed_in_user_errors(self):
        from app.services.crypto_payment_service import payment_view
        from test_cryptoway import payment, user
        row = payment(status='error', last_error='Cryptoway не создал счёт. Попробуйте позже.')
        public_error = payment_view(row, user())['last_error']
        self.assertNotIn('cryptoway', public_error.lower())
        self.assertIn('платёжный сервис', public_error)
        self.assertIn('Cryptoway', row.last_error)
