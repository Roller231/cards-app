"""Payment invariants. All provider calls, notifications and credits are mocked."""
import asyncio
from contextlib import ExitStack
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
import httpx
from app.core.config import settings
from app.core.database import get_db
from app.api.deps import get_current_user
from app.api.routers.crypto_payments import router, QuoteRequest
from app.integrations.cryptoway_client import signature, verify_webhook, trusted_pay_url, CryptowayError
from app.models.crypto_payment import CryptoPayment
from app.models.user import User
from app.models.order import Order
from app.services import crypto_payment_service as service
from app.services import wallet_service
from app.services.card_service import card_service


def payment(**changes):
    values = dict(id=1, user_id=11, request_id='request-0123456789', external_id='pp-cw-unit-test',
        provider_invoice_id='11111111-1111-4111-8111-111111111111', purpose='card_topup',
        offer_id='ROCKETPAY', card_id=22, amount_usd=Decimal('100.00'), fee_percent=Decimal('3.6'),
        price_rub=None, base_rate=None, discount_percent=Decimal('0'),
        service_request_id=None, amount_cny=None, cny_per_usdt=None,
        charge_usdt=Decimal('103.60'), status='active', fulfillment_status='not_started', order_id=None,
        symbol_id='USDTBEP20', wallet_address='test-wallet', network_name='Binance', pay_url=None,
        expires_at=datetime.utcnow()+timedelta(minutes=30), created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        last_checked_at=None, creation_started_at=None, fulfillment_started_at=None, paid_at=None, received_usdt=Decimal('0'),
        refund_credited=False, paid_notified=False, review_notified=False, last_error=None)
    values.update(changes)
    return SimpleNamespace(**values)


def invoice(row, **changes):
    value = dict(id=row.provider_invoice_id, external_id=row.external_id, status='executed',
        target_wallet={'symbol_id':'USDTBEP20','value':'test-wallet'},
        target_value_symbol='103.60000000', payer_amount='103.60000000', merchant_amount='103.082',
        current_value='103.60000000', fee_split_percent='0', markup_percent='0',
        pay_url='https://pay.cryptoway.com/'+str(row.provider_invoice_id))
    value.update(changes)
    return value


def deposit(amount='103.60', status='executed', symbol='USDTBEP20'):
    return {'type':'deposit','status':status,'symbol_id':symbol,'net_amount':amount,
            'amount':str(Decimal(amount)*Decimal('.995')),'service_fee':str(Decimal(amount)*Decimal('.005'))}


class SignatureTests(unittest.TestCase):
    def test_request_matches_literal_canonical_contract(self):
        canonical = '1000{"body":{},"params":"","path":"/user/balance/"}'
        expected=hmac.new(b'test-secret',canonical.encode(),hashlib.sha256).hexdigest()
        self.assertEqual(signature('test-secret','1000',{'path':'/user/balance/','body':{},'params':''}),expected)

    def test_both_callback_envelopes_and_tampering(self):
        for payload in ({'type':'deposit','status':'executed'}, {'params':'','body':{'type':'invoice','id':'example','status':'executed'}}):
            data=payload if 'body' in payload else {'params':'','body':payload}
            supplied=signature('callback-test','1000',data)
            with patch.object(settings,'CRYPTOWAY_CALLBACK_KEY','callback-test'):
                self.assertTrue(verify_webhook(payload,'','1000',supplied,now=1000))
                self.assertFalse(verify_webhook(payload,'','1000',supplied,now=1016))
                self.assertFalse(verify_webhook(payload,'','1000','0'*64,now=1000))
                self.assertFalse(verify_webhook(payload,'','not-a-timestamp',supplied,now=1000))
                changed=json.loads(json.dumps(payload))
                (changed.get('body') or changed)['status']='cancelled'
                self.assertFalse(verify_webhook(changed,'','1000',supplied,now=1000))

    def test_provider_url_is_not_an_arbitrary_redirect(self):
        self.assertTrue(trusted_pay_url('https://pay.cryptoway.com/abc'))
        for url in ('http://pay.cryptoway.com/abc','https://pay.cryptoway.com.evil.test/abc','https://evil.test/','https://me@pay.cryptoway.com/abc','https://pay.cryptoway.com:bad/abc'):
            self.assertFalse(trusted_pay_url(url))


class SettlementTests(unittest.TestCase):
    def setUp(self):self.row=payment()

    def state(self, fresh=None, txs=None):
        return service.invoice_payment_state(self.row,fresh or invoice(self.row),[deposit()] if txs is None else txs)[0]

    def test_full_payment_uses_gross_deposit_not_merchant_net(self):
        self.assertEqual(self.state(),'paid')

    def test_multiple_transfers_cover_one_invoice(self):
        self.assertEqual(self.state(txs=[deposit('50'),deposit('53.60')]),'paid')

    def test_shortfall_of_one_atomic_unit_is_not_rounded_away(self):
        self.assertEqual(self.state(txs=[deposit('103.59999999')]),'review')

    def test_closed_invoice_without_confirmed_money_is_not_payment(self):
        self.assertEqual(self.state(txs=[]),'review')
        self.assertEqual(self.state(txs=[deposit(status='pending')]),'review')

    def test_active_invoice_is_not_paid_even_with_money(self):
        self.assertEqual(self.state(invoice(self.row,status='active')),'active')

    def test_expired_or_cancelled_money_needs_manual_review(self):
        for status in ('expired','cancelled'):
            self.assertEqual(self.state(invoice(self.row,status=status),[deposit('10')]),'review')
            self.assertEqual(self.state(invoice(self.row,status=status),[]),status)

    def test_aml_lock_cannot_release_a_card(self):
        self.assertEqual(self.state(txs=[deposit(status='dirty_lock')]),'review')

    def test_replaced_currency_or_invoice_rejected(self):
        for fresh in (invoice(self.row,external_id='someone-else'),invoice(self.row,payer_amount='104'),
                invoice(self.row,target_value_symbol='100'),invoice(self.row,fee_split_percent='100'),
                invoice(self.row,markup_percent='1'),invoice(self.row,target_wallet={'symbol_id':'BTC','value':'addr'})):
            with self.assertRaises(ValueError):self.state(fresh)
        with self.assertRaises(ValueError):self.state(txs=[deposit(symbol='BTC')])


class Result:
    def __init__(self,value=None,items=None):self.value=value;self.items=items or []
    def scalar_one(self):return self.value
    def scalar_one_or_none(self):return self.value
    def scalars(self):return self
    def all(self):return self.items


class FakeSession:
    def __init__(self,row=None,user=None,card=None,order=None):
        self.row,self.user,self.card,self.order=row,user,card,order
        self.queries=[];self.commits=0
    async def execute(self,query):
        self.queries.append(query)
        entity=query.column_descriptions[0].get('entity')
        if entity is CryptoPayment:return Result(self.row)
        from app.models.card import Card
        if entity is Card:return Result(self.card)
        return Result()
    async def get(self,model,pk):
        return self.user if model is User else self.order if model is Order else self.row
    def add(self,row):self.row=row;row.id=1
    async def flush(self):pass
    async def commit(self):self.commits+=1
    async def rollback(self):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass


def user():
    return SimpleNamespace(id=11,username='test',email='unit@example.test',kyc_status='success',
        kyc_first_name='Test',kyc_last_name='User',kyc_birth_date='01.01.1990',kyc_passport='unit-test-only')


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(service,'enabled',return_value=True))
        self.stack.enter_context(patch.object(settings,'CRYPTOWAY_TOPUP_MARKUP_PERCENT',3.6))
        self.stack.enter_context(patch.object(settings,'PUBLIC_BASE_URL','https://prontopay.pro'))
        self.stack.enter_context(patch.object(settings,'CRYPTOWAY_PAY_WITHOUT_KYC',False))

    async def test_topup_quote_has_no_bitbanker_dependency(self):
        card=SimpleNamespace(id=22,status='active',aifory_card_id='test-card',currency='USD',offer_id='ROCKETPAY')
        db=FakeSession(user=user(),card=card)
        with patch('app.services.rate_service.get_bb_index',AsyncMock(side_effect=AssertionError('BB must not be used'))) as rate:
            row=await service.create_quote(db,user(),QuoteRequest(request_id='request-0123456789',purpose='card_topup',card_id=22,amount_usd='100'))
        self.assertEqual(row.amount_usd,Decimal('100'))
        self.assertEqual(row.charge_usdt,Decimal('103.60'))
        rate.assert_not_awaited()

    async def test_issue_quote_uses_raw_index_and_rounds_up(self):
        db=FakeSession(user=user())
        with patch.object(card_service,'get_offers',AsyncMock(return_value=[{'id':'ROCKETPAY:pay'}])), \
             patch('app.api.routers.cards._issue_price_rub',AsyncMock(return_value=1499)), \
             patch.object(wallet_service,'invitee_discount_percent',AsyncMock(return_value=0)), \
             patch('app.services.rate_service.get_bb_index',AsyncMock(return_value=90)):
            row=await service.create_quote(db,user(),QuoteRequest(request_id='request-0123456789',purpose='card_issue',offer_id='ROCKETPAY:pay'))
        self.assertEqual(row.charge_usdt,Decimal('16.66'))
        self.assertEqual(row.fee_percent,0)
        self.assertEqual(row.base_rate,90)

    async def create_invoice(self,row,api):
        db=FakeSession(row=row,user=user())
        with patch.object(service,'networks',AsyncMock(return_value=[{'symbol_id':'USDTBEP20','name':'Binance','min_amount':'1'}])), \
             patch.object(service.cryptoway_client,'create_invoice',api):
            await service.create_invoice(db,user(),row.id,'USDTBEP20')
            await service.create_invoice(db,user(),row.id,'USDTBEP20')

    async def test_repeated_create_uses_one_provider_invoice(self):
        row=payment(status='quoted',provider_invoice_id=None)
        response=invoice(row,id='11111111-1111-4111-8111-111111111111',status='active')
        api=AsyncMock(return_value=response)
        await self.create_invoice(row,api)
        api.assert_awaited_once()
        self.assertEqual(api.call_args.args[0]['target_value_symbol'],'103.60')
        self.assertIs(api.call_args.args[0]['is_payer_fee'],False)
        self.assertEqual(row.status,'active')

    async def test_uncertain_create_is_not_repeated_after_timeout(self):
        row=payment(status='quoted',provider_invoice_id=None)
        api=AsyncMock(side_effect=CryptowayError())
        await self.create_invoice(row,api)
        api.assert_awaited_once()
        self.assertEqual(row.status,'creating')

    async def test_two_paid_callbacks_do_not_fulfill_twice(self):
        row=payment(status='paid',purpose='card_issue',offer_id='ROCKETPAY:pay')
        db=FakeSession(row=row,user=user())
        async def issue(*args,**kwargs):
            await asyncio.sleep(.01)
            return {'local_order_id':99}
        with patch.object(service,'AsyncSessionLocal',return_value=db),patch.object(card_service,'issue_card',AsyncMock(side_effect=issue)) as api:
            await asyncio.gather(service.fulfill_payment(row.id),service.fulfill_payment(row.id))
        api.assert_awaited_once()
        self.assertEqual(row.order_id,99)
        self.assertTrue(any(q._for_update_arg is not None for q in db.queries))

    async def test_definitive_failure_returns_funds_once(self):
        row=payment(status='paid',fulfillment_status='processing',order_id=99)
        db=FakeSession(row=row,user=user(),order=SimpleNamespace(id=99,status='failed'))
        with patch.object(wallet_service,'credit',AsyncMock()) as credit:
            await service.update_order_outcome(db,row)
            await service.update_order_outcome(db,row)
        credit.assert_awaited_once()
        self.assertTrue(row.refund_credited)

    async def test_unknown_provider_result_never_auto_refunds(self):
        row=payment(status='paid',fulfillment_status='review',order_id=99)
        db=FakeSession(row=row,user=user(),order=SimpleNamespace(id=99,status='failed'))
        with patch.object(wallet_service,'credit',AsyncMock()) as credit:
            await service.update_order_outcome(db,row)
        credit.assert_not_awaited()

    async def test_status_polling_cannot_reset_stuck_fulfillment_timeout(self):
        row=payment(status='paid',fulfillment_status='processing',
            fulfillment_started_at=datetime.utcnow()-timedelta(minutes=16))
        with patch.object(service,'alert_review',AsyncMock()) as alert:
            await service.update_order_outcome(FakeSession(row=row),row)
        self.assertEqual(row.fulfillment_status,'review')
        alert.assert_awaited_once()

    async def test_retryable_bank_rejection_never_auto_refunds(self):
        from app.integrations.rocketpay_client import RocketpayError
        row=payment(status='paid',order_id=99)
        db=FakeSession(row=row,user=user(),order=SimpleNamespace(id=99,status='failed'))
        async def topup(*args,**kwargs):
            raise ValueError('Unknown bank result') from RocketpayError(409,'request_in_progress','pending')
        with patch.object(service,'AsyncSessionLocal',return_value=db), \
             patch.object(card_service,'deposit_card',AsyncMock(side_effect=topup)), \
             patch.object(service,'alert_review',AsyncMock()), \
             patch.object(wallet_service,'credit',AsyncMock()) as credit:
            await service.fulfill_payment(row.id)
            await service.update_order_outcome(db,row)
        self.assertEqual(row.fulfillment_status,'review')
        credit.assert_not_awaited()


class ApiSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def manual_check(self, row, provider, transactions):
        app=FastAPI();app.include_router(router)
        db=FakeSession(row=row,user=user())
        async def get_test_db():yield db
        app.dependency_overrides[get_db]=get_test_db
        app.dependency_overrides[get_current_user]=user
        with patch.object(service.cryptoway_client,'invoice',provider), \
             patch.object(service.cryptoway_client,'transactions',transactions), \
             patch.object(service,'fulfill_payment',AsyncMock()) as fulfill:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://unit.test') as client:
                response=await client.post('/crypto/payments/1/refresh')
            await asyncio.sleep(0)
        return response,fulfill

    async def test_manual_check_bypasses_poll_cache_and_confirms_full_payment(self):
        row=payment(last_checked_at=datetime.utcnow())
        provider=AsyncMock(return_value=invoice(row))
        transactions=AsyncMock(return_value=[deposit()])
        response,fulfill=await self.manual_check(row,provider,transactions)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'paid')
        provider.assert_awaited_once();transactions.assert_awaited_once()
        fulfill.assert_awaited_once()

    async def test_background_poll_keeps_its_throttle(self):
        row=payment(last_checked_at=datetime.utcnow())
        with patch.object(service.cryptoway_client,'invoice',AsyncMock()) as provider:
            await service.reconcile_payment(FakeSession(row=row),user(),row.id)
        provider.assert_not_awaited()
        self.assertEqual(row.status,'active')

    async def test_background_provider_failure_keeps_retryable_payment(self):
        row=payment()
        with patch.object(service.cryptoway_client,'invoice',AsyncMock(side_effect=CryptowayError())):
            result=await service.reconcile_payment(FakeSession(row=row),user(),row.id)
        self.assertIs(result,row)
        self.assertEqual(row.status,'active')
        self.assertEqual(row.fulfillment_status,'not_started')

    async def test_manual_check_reports_provider_failure_without_changing_payment(self):
        row=payment(last_checked_at=datetime.utcnow())
        provider=AsyncMock(side_effect=CryptowayError())
        transactions=AsyncMock()
        response,fulfill=await self.manual_check(row,provider,transactions)
        self.assertEqual(response.status_code,502,response.text)
        self.assertIn('повторно',response.json()['detail'].lower())
        self.assertEqual(row.status,'active')
        self.assertEqual(row.fulfillment_status,'not_started')
        transactions.assert_not_awaited();fulfill.assert_not_awaited()

    async def test_manual_check_cannot_treat_unconfirmed_deposit_as_payment(self):
        row=payment()
        response,fulfill=await self.manual_check(row,AsyncMock(return_value=invoice(row,status='active')),
                                                AsyncMock(return_value=[deposit(status='pending')]))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'active')
        fulfill.assert_not_awaited()

    async def test_completed_payment_check_is_immediate_without_provider_or_repeat_fulfillment(self):
        row=payment(status='paid',fulfillment_status='completed',order_id=99)
        provider=AsyncMock(side_effect=AssertionError('Already confirmed'))
        transactions=AsyncMock(side_effect=AssertionError('Already confirmed'))
        response,fulfill=await self.manual_check(row,provider,transactions)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'paid')
        provider.assert_not_awaited();transactions.assert_not_awaited();fulfill.assert_not_awaited()

    async def test_foreign_manual_check_never_calls_provider_or_fulfills(self):
        provider=AsyncMock();transactions=AsyncMock()
        response,fulfill=await self.manual_check(None,provider,transactions)
        self.assertEqual(response.status_code,404)
        provider.assert_not_awaited();transactions.assert_not_awaited();fulfill.assert_not_awaited()

    async def test_invalid_webhook_does_not_reach_money_or_provider(self):
        app=FastAPI();app.include_router(router)
        db=FakeSession()
        async def get_test_db():yield db
        app.dependency_overrides[get_db]=get_test_db
        with patch.object(settings,'CRYPTOWAY_CALLBACK_KEY','unit-callback'),patch.object(service,'reconcile_payment',AsyncMock()) as reconcile:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://unit.test') as client:
                response=await client.post('/webhooks/cryptoway',json={'params':'','body':{'type':'invoice','id':'fake','status':'executed'}})
        self.assertEqual(response.status_code,401)
        self.assertEqual(db.queries,[])
        reconcile.assert_not_awaited()

    async def test_foreign_payment_not_accessible(self):
        app=FastAPI();app.include_router(router)
        async def get_test_db():yield FakeSession()
        app.dependency_overrides[get_db]=get_test_db
        app.dependency_overrides[get_current_user]=user
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://unit.test') as client:
            response=await client.get('/crypto/payments/1')
        self.assertEqual(response.status_code,404)


if __name__=='__main__':unittest.main()
