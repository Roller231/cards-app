"""Real SQL regressions for poll-before-webhook, retries, and China handoff."""
from contextlib import ExitStack
from datetime import datetime, timedelta
from decimal import Decimal
import json
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.core.database import Base
from app.api.routers import sbp, services
from app.services import recovery_service as recovery
from app.models.user import User
from app.models.bb_invoice import BbInvoice
from app.models.service_request import ServiceRequest
from app.models.balance_tx import BalanceTransaction
from app.models.promo import PromoCode, PromoRedemption
from test_wallet_payments import TransactionDb


class SbpReconciliationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.engine = create_engine('sqlite://'); self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine, tables=[m.__table__ for m in (
            User, BbInvoice, ServiceRequest, BalanceTransaction, PromoCode, PromoRedemption)])
        self.session = Session(self.engine, expire_on_commit=False); self.addCleanup(self.session.close)
        self.db = TransactionDb(self.session)
        self.owner = User(id=11, username='sbp_unit', balance=Decimal('10'))
        self.req = ServiceRequest(id=47, user_id=11, service='alipay', amount=Decimal('200'),
            currency='CNY', payment_method='sbp', amount_rub=Decimal('2697'), status='awaiting_payment')
        self.inv = BbInvoice(id=203, user_id=11, bb_invoice_id='test-bb', idempotency_key='unit-sbp',
            external_client_ref='u11', purpose='china_payment', service_request_id=47,
            amount_rub=Decimal('2697'), status='pending', created_at=datetime.utcnow()-timedelta(minutes=20))
        self.session.add_all([self.owner, self.req, self.inv]); self.session.commit()
        self.payload = {'id':'test-bb', 'sbp_info':{'status':'captured'},
            'exchange_deal':[{'take_currency':'USDT','volume_take_final':'28.76'}]}
        self.stack.enter_context(patch.object(sbp, 'AsyncSessionLocal', return_value=self.db))
        self.stack.enter_context(patch.object(sbp, 'verify_webhook_signature', return_value=True))
        self.stack.enter_context(patch.object(sbp.bitbanker_client, 'get_invoice', AsyncMock(return_value=self.payload)))
        self.notify = self.stack.enter_context(patch.object(sbp, 'notify_sbp_payment', AsyncMock()))
        self.managers = self.stack.enter_context(patch.object(services, 'send_to_managers', AsyncMock(return_value={'unit':123})))
        self.post = self.stack.enter_context(patch.object(sbp, '_trigger_post_payment', AsyncMock()))
        self.stack.enter_context(patch('app.services.rate_service.get_app_rate', AsyncMock(return_value=90)))
        self.jobs = []
        self.stack.enter_context(patch.object(sbp, '_schedule_paid_booking', side_effect=lambda i,p:self.jobs.append((i,p))))

    async def webhook(self, payload=None):
        request = AsyncMock(); request.json.return_value = payload or self.payload
        return await sbp.bitbanker_webhook(request)

    async def drain(self):
        jobs, self.jobs = self.jobs, []
        for invoice_id, payload in jobs:
            await sbp._credit_and_trigger(invoice_id, payload)

    async def test_poll_before_webhook_completes_china_once(self):
        await sbp.get_invoice_status(203,self.db,self.owner)
        self.assertEqual(self.inv.status,'captured')
        self.assertIsNone(self.inv.amount_usd)
        await self.webhook()
        await self.drain()
        self.assertEqual(self.req.status,'paid')
        self.assertEqual(self.req.invoice_id,203)
        self.assertIsNotNone(self.req.paid_at)
        self.assertEqual(self.inv.amount_usd,Decimal('28.76'))
        self.managers.assert_awaited_once()
        self.notify.assert_awaited_once()
        self.assertEqual(self.owner.balance,Decimal('10'))

    async def test_webhook_before_poll_and_duplicate_webhooks_do_not_repeat(self):
        await self.webhook(); await self.drain()
        await sbp.get_invoice_status(203,self.db,self.owner)
        await self.webhook(); await self.drain()
        self.managers.assert_awaited_once(); self.notify.assert_awaited_once()

    async def test_poll_can_finish_payment_without_webhook(self):
        await sbp.get_invoice_status(203,self.db,self.owner)
        await self.drain()
        self.assertEqual(self.req.status,'paid')
        self.managers.assert_awaited_once()

    async def test_handoff_failure_rolls_back_marker_and_retry_works(self):
        self.inv.status='captured';self.session.commit()
        with patch.object(services,'on_request_paid',AsyncMock(side_effect=RuntimeError('unit failure'))):
            await sbp._credit_and_trigger(203,self.payload)
        self.session.refresh(self.inv)
        self.assertIsNone(self.inv.amount_usd)
        self.post.assert_not_awaited()
        await sbp._credit_and_trigger(203,self.payload)
        self.assertEqual(self.req.status,'paid')

    async def test_late_failure_webhook_does_not_undo_paid_status(self):
        await self.webhook(); await self.drain()
        await self.webhook({'id':'test-bb','sbp_info':{'status':'pending'}})
        self.assertEqual(self.inv.status,'captured')
        self.assertEqual(self.req.status,'paid')

    async def test_stale_poll_cannot_overwrite_webhook_payment(self):
        async def webhook_wins(_):
            self.inv.status='captured';self.inv.amount_usd=Decimal('28.76')
            self.req.status='paid';self.session.commit()
            return {'id':'test-bb','sbp_info':{'status':'pending'}}
        with patch.object(sbp.bitbanker_client,'get_invoice',AsyncMock(side_effect=webhook_wins)):
            result=await sbp.get_invoice_status(203,self.db,self.owner)
        self.assertEqual(result['status'],'captured')
        self.assertEqual(self.jobs,[])

    async def test_balance_credit_and_promo_are_applied_once(self):
        self.inv.purpose='balance_deposit';self.inv.service_request_id=None
        self.inv.amount_usd_requested=Decimal('30')
        promo=PromoCode(id=1,code='UNIT',type='rate_discount',used_count=0)
        redemption=PromoRedemption(id=1,promo_id=1,user_id=11,invoice_id=203,status='pending')
        self.session.add_all([promo,redemption]);self.session.commit()
        with patch('app.services.telegram_bot_service.notify_balance_deposit',AsyncMock()):
            await sbp.get_invoice_status(203,self.db,self.owner)
            await self.webhook();await self.drain()
            await self.webhook();await self.drain()
        self.assertEqual(self.owner.balance,Decimal('40'))
        self.assertEqual(self.session.scalar(select(func.count(BalanceTransaction.id))),1)
        self.assertEqual(promo.used_count,1)
        self.assertEqual(redemption.status,'applied')

    async def test_recovery_books_china_and_does_not_reopen_manual_done(self):
        self.inv.status='captured';self.inv.raw_response=json.dumps(self.payload);self.session.commit()
        with patch.object(recovery,'AsyncSessionLocal',return_value=self.db), \
             patch.object(recovery.settings,'AUTO_RECOVER_ENABLED',True), \
             patch.object(recovery,'_alert',AsyncMock()):
            await recovery.scan_and_recover()
            self.assertEqual(self.req.status,'paid')
            self.req.status='done';self.inv.amount_usd=None;self.session.commit()
            await recovery.scan_and_recover()
        self.assertEqual(self.req.status,'done')
        self.managers.assert_awaited_once()

    async def test_cached_status_with_truncated_old_payload_is_retriable(self):
        self.inv.status='captured';self.inv.raw_response='{"truncated":';self.session.commit()
        data=await sbp.get_invoice_status(203,self.db,self.owner)
        self.assertEqual(data['status'],'captured')
        self.assertEqual(len(self.jobs),1)
