"""Admin recovery must never replay an unpaid, refunded or in-flight operation."""
import asyncio
from decimal import Decimal
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException

from app.api.deps import get_admin
from app.api.routers.crypto_payments import router
from app.core.database import get_db
from app.models.card import Card
from app.models.crypto_payment import CryptoPayment
from app.models.order import Order
from app.models.service_request import ServiceRequest
from app.models.user import User
from app.services import crypto_payment_service as service
from app.services.card_service import card_service
from test_cryptoway import FakeSession, Result, payment, user


REQUEST = 'admin-retry-request-0123456789'


class RetrySession(FakeSession):
    def __init__(self, row, order=None, card=None, request=None):
        if not hasattr(row, 'provider_payload'):
            row.provider_payload = None
        u = user()
        u.is_active = True
        super().__init__(row=row, user=u, order=order, card=card)
        self.request = request

    async def execute(self, query):
        entity = query.column_descriptions[0].get('entity')
        if entity is Order:
            self.queries.append(query)
            return Result(self.order)
        return await super().execute(query)

    async def get(self, model, pk):
        if model is ServiceRequest:
            return self.request
        if model is Card:
            return self.card
        return await super().get(model, pk)


class AdminRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, db, checked=False, request_id=REQUEST):
        with patch.object(service, 'fulfill_payment', AsyncMock()) as fulfill:
            result = await service.retry_paid_payment(db, 1, request_id, checked)
            await asyncio.sleep(0)
            return result, fulfill

    async def test_review_requires_explicit_provider_check_before_retry(self):
        row = payment(status='paid', fulfillment_status='review', received_usdt=Decimal('103.60'))
        db = RetrySession(row)
        with self.assertRaises(HTTPException) as error:
            await self.call(db)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(row.fulfillment_status, 'review')
        self.assertEqual(db.commits, 0)

    async def test_checked_retry_is_durable_and_preserves_frozen_price_and_error_audit(self):
        row = payment(status='paid', fulfillment_status='review', received_usdt=Decimal('103.60'),
                      provider_payload='{"id":"original-invoice"}', last_error='previous failure')
        db = RetrySession(row)
        result, fulfill = await self.call(db, checked=True)
        self.assertTrue(result['ok'])
        self.assertEqual(db.commits, 1)
        self.assertEqual(row.fulfillment_status, 'retry_queued')
        self.assertEqual(row.amount_usd, Decimal('100'))
        self.assertEqual(row.charge_usdt, Decimal('103.60'))
        self.assertEqual(row.status, 'paid')
        payload = json.loads(row.provider_payload)
        self.assertEqual(payload['id'], 'original-invoice')
        self.assertEqual(payload['admin_retries'][0]['previous_error'], 'previous failure')
        fulfill.assert_awaited_once_with(1)
        self.assertIsNotNone(db.queries[0]._for_update_arg)

    async def test_repeated_same_request_after_failure_cannot_schedule_again(self):
        row = payment(status='paid', fulfillment_status='review', received_usdt=Decimal('103.60'))
        db = RetrySession(row)
        await self.call(db, checked=True)
        row.fulfillment_status = 'review'
        result, fulfill = await self.call(db, checked=True)
        self.assertIn('уже принят', result['message'])
        fulfill.assert_not_awaited()

    async def test_double_click_and_processing_do_not_schedule_another_attempt(self):
        for state in ('processing', 'retry_queued', 'completed'):
            row = payment(status='paid', fulfillment_status=state, received_usdt=Decimal('103.60'))
            result, fulfill = await self.call(RetrySession(row), checked=True)
            self.assertTrue(result['ok'])
            fulfill.assert_not_awaited()

    async def test_unpaid_shortfall_and_refunded_payments_are_rejected(self):
        for changes in ({'status': 'active'}, {'received_usdt': Decimal('103.59999999')}, {'refund_credited': True}):
            row = payment(status='paid', fulfillment_status='review', received_usdt=Decimal('103.60'))
            for key, value in changes.items():
                setattr(row, key, value)
            with self.assertRaises(HTTPException) as error:
                await self.call(RetrySession(row), checked=True)
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(row.fulfillment_status, 'review')

    async def test_linked_completed_order_only_repairs_status(self):
        row = payment(status='paid', fulfillment_status='review', order_id=99, received_usdt=Decimal('103.60'))
        db = RetrySession(row, order=SimpleNamespace(id=99, user_id=11, status='completed'))
        _, fulfill = await self.call(db)
        fulfill.assert_not_awaited()
        self.assertEqual(row.fulfillment_status, 'completed')
        self.assertEqual(row.order_id, 99)

    async def test_pending_and_processing_orders_are_never_reset(self):
        for state in ('pending', 'processing'):
            row = payment(status='paid', fulfillment_status='review', order_id=99, received_usdt=Decimal('103.60'))
            order = SimpleNamespace(id=99, user_id=11, status=state)
            with self.assertRaises(HTTPException):
                await self.call(RetrySession(row, order=order), checked=True)
            self.assertEqual(order.status, state)
            self.assertEqual(row.order_id, 99)

    async def test_failed_order_retained_in_audit_but_unlinked_for_new_attempt(self):
        row = payment(status='paid', fulfillment_status='review', order_id=99, received_usdt=Decimal('103.60'))
        order = SimpleNamespace(id=99, user_id=11, status='failed', type='topup')
        _, fulfill = await self.call(RetrySession(row, order=order), checked=True)
        fulfill.assert_awaited_once()
        self.assertIsNone(row.order_id)
        self.assertEqual(order.status, 'failed')
        self.assertEqual(json.loads(row.provider_payload)['admin_retries'][0]['previous_order_id'], 99)

    async def test_issue_order_with_existing_active_card_cannot_be_replayed(self):
        row = payment(status='paid', fulfillment_status='review', order_id=99, received_usdt=Decimal('103.60'))
        order = SimpleNamespace(id=99, user_id=11, status='failed', type='issue', card_id=22)
        with self.assertRaises(HTTPException):
            await self.call(RetrySession(row, order=order, card=SimpleNamespace(status='active')), checked=True)

    async def test_paid_china_request_is_not_reopened_and_closed_request_is_rejected(self):
        for state, linked in (('paid', 1), ('done', 1), ('rejected', 1), ('cancelled', None)):
            row = payment(status='paid', purpose='china_payment', fulfillment_status='review',
                          service_request_id=7, received_usdt=Decimal('103.60'))
            req = SimpleNamespace(user_id=11, payment_method='crypto', crypto_payment_id=linked, status=state)
            db = RetrySession(row, request=req)
            if linked:
                _, fulfill = await self.call(db)
                self.assertEqual(row.fulfillment_status, 'completed')
                fulfill.assert_not_awaited()
            else:
                with self.assertRaises(HTTPException):
                    await self.call(db)
            self.assertEqual(req.status, state)

    async def test_queued_attempt_resumes_once_after_restart(self):
        row = payment(status='paid', fulfillment_status='retry_queued')
        db = RetrySession(row)
        with patch.object(service, 'AsyncSessionLocal', return_value=db), \
             patch.object(card_service, 'deposit_card', AsyncMock(return_value={'local_order_id': 99})) as deposit:
            await asyncio.gather(service.fulfill_payment(1), service.fulfill_payment(1))
        deposit.assert_awaited_once()
        self.assertEqual(row.order_id, 99)

    async def test_refunded_queue_cannot_fulfill(self):
        row = payment(status='paid', fulfillment_status='retry_queued', refund_credited=True)
        with patch.object(service, 'AsyncSessionLocal', return_value=RetrySession(row)), \
             patch.object(card_service, 'deposit_card', AsyncMock()) as deposit:
            await service.fulfill_payment(1)
        deposit.assert_not_awaited()

    async def test_endpoint_requires_admin_and_valid_request_id(self):
        app = FastAPI()
        app.include_router(router)
        db = RetrySession(payment(status='paid', received_usdt=Decimal('103.60')))
        async def test_db():
            yield db
        app.dependency_overrides[get_db] = test_db
        with patch.object(service, 'retry_paid_payment', AsyncMock(return_value={'ok': True})) as retry:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://unit.test') as client:
                response = await client.post('/admin/cryptoway/payments/1/retry', json={'request_id': REQUEST})
                self.assertIn(response.status_code, (401, 403))
                retry.assert_not_awaited()
                app.dependency_overrides[get_admin] = lambda: 'admin'
                response = await client.post('/admin/cryptoway/payments/1/retry', json={'request_id': 'short'})
                self.assertEqual(response.status_code, 422)
                retry.assert_not_awaited()
                response = await client.post('/admin/cryptoway/payments/1/retry', json={'request_id': REQUEST, 'provider_checked': True})
                self.assertEqual(response.status_code, 200)
                retry.assert_awaited_once_with(db, 1, REQUEST, True)
