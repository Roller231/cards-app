"""China/USDT pricing and durable handoff; all external effects are mocked."""
import asyncio
from contextlib import ExitStack
from datetime import datetime,timedelta
from decimal import Decimal
import math
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from unittest.mock import AsyncMock,patch

from fastapi import FastAPI,HTTPException
import httpx
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers import services,sbp
from app.api.routers.crypto_payments import QuoteRequest
from app.core.config import settings
from app.core.database import Base,get_db
from app.models.user import User
from app.models.card import Card
from app.models.order import Order
from app.models.service_request import ServiceRequest
from app.models.crypto_payment import CryptoPayment
from app.services import crypto_payment_service as crypto
from test_cryptoway import invoice


class AsyncDb:
    """Use actual SQL/constraints in SQLite without an extra async dependency."""
    def __init__(self,session):self.session=session
    async def execute(self,*a,**k):return self.session.execute(*a,**k)
    async def get(self,*a,**k):return self.session.get(*a,**k)
    def add(self,*a,**k):return self.session.add(*a,**k)
    async def flush(self):self.session.flush()
    async def commit(self):self.session.commit()
    async def rollback(self):self.session.rollback()
    async def refresh(self,row,*args,**kwargs):self.session.refresh(row,*args,**kwargs)
    async def __aenter__(self):return self
    async def __aexit__(self,*a):pass


class ChinaCryptoTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.engine=create_engine('sqlite://')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine,tables=[User.__table__,Card.__table__,Order.__table__,ServiceRequest.__table__,CryptoPayment.__table__])
        self.session=Session(self.engine,expire_on_commit=False);self.addCleanup(self.session.close)
        self.db=AsyncDb(self.session)
        self.user=User(id=11,username='china_unit',is_active=True,kyc_status=None)
        self.request=ServiceRequest(id=33,user_id=11,service='alipay',amount=Decimal('2000'),currency='CNY',
            payment_method='crypto',amount_usdt=Decimal('305.81'),cny_per_usdt=Decimal('6.54'),
            status='awaiting_payment',recipient_type='phone',recipient_phone='+12025550123',recipient_name='UNIT TEST')
        self.session.add_all([self.user,self.request]);self.session.commit()
        for key,value in {'CHINA_CNY_DIVISOR':6.54,'SBP_BITBANKER_FEE_PERCENT':2.1,'SBP_DISABLED':False}.items():
            self.stack.enter_context(patch.object(settings,key,value))
        self.stack.enter_context(patch.object(crypto,'enabled',return_value=True))
        self.stack.enter_context(patch.object(crypto,'networks',AsyncMock(return_value=[{'symbol_id':'USDTBEP20','name':'Binance','min_amount':'1'}])))

    async def quote(self,**changes):
        body={'request_id':'china-quote-0123456789','purpose':'china_payment','service_request_id':33}
        body.update(changes)
        return await crypto.create_quote(self.db,self.user,QuoteRequest(**body))

    def test_requested_rounding_example(self):
        self.assertEqual(services.usdt_for_cny(Decimal('2000'),Decimal('6.54')),Decimal('305.81'))
        self.assertEqual(services.usdt_for_cny(Decimal('2000'),Decimal('6.6')),Decimal('303.03'))

    def test_invalid_configured_rate_cannot_create_a_zero_or_nan_price(self):
        for value in (0,-1,1e-10,float('nan'),float('inf')):
            with self.subTest(value=value),patch.object(settings,'CHINA_CNY_DIVISOR',value):
                with self.assertRaises(HTTPException):services.cny_per_usdt()

    async def test_crypto_rate_has_no_sbp_or_bitbanker_dependency(self):
        with patch('app.services.rate_service.get_bb_index',AsyncMock(side_effect=AssertionError('No FX API for USDT'))):
            data=await services.cny_quote('crypto')
        self.assertEqual(Decimal(data['cny_per_usdt']),Decimal('6.54'))

    async def test_sbp_formula_is_index_divisor_plus_2_1_percent_without_fixed_fee(self):
        with patch('app.services.rate_service.get_bb_index',AsyncMock(return_value=87)), \
             patch.object(sbp,'_get_bb_fee_params',AsyncMock(return_value=(.021,0))):
            q=await services.cny_quote('sbp')
        base,fee,total=services.rub_for_cny(Decimal('2000'),q['rate'])
        self.assertEqual(total,math.ceil(2000/6.54*87*1.021))
        self.assertEqual(fee,0)
        self.assertEqual(q['small_payment_fee_rub'],0)

    async def test_quote_uses_owned_request_not_client_supplied_amount_and_freezes_rate(self):
        row=await self.quote(amount_usd='1')
        self.assertEqual(row.charge_usdt,Decimal('305.81'))
        self.assertEqual(row.fee_percent,0)
        self.assertEqual(row.amount_cny,Decimal('2000'))
        with patch.object(settings,'CHINA_CNY_DIVISOR',7):
            same=await self.quote()
        self.assertEqual(same.id,row.id)
        self.assertEqual(same.cny_per_usdt,Decimal('6.54'))
        self.assertFalse(crypto.payment_view(row,self.user)['kyc_required'])

    async def test_foreign_or_sbp_service_request_cannot_create_crypto_quote(self):
        with self.assertRaises(HTTPException) as exc:await self.quote(service_request_id=999)
        self.assertEqual(exc.exception.status_code,404)
        self.request.payment_method='sbp';self.session.commit()
        with self.assertRaises(HTTPException) as exc:await self.quote()
        self.assertEqual(exc.exception.status_code,409)

    async def test_one_external_invoice_for_a_service_request(self):
        row=await self.quote()
        response=invoice(row,id='11111111-1111-4111-8111-111111111111',status='active',
            target_value_symbol='305.81',payer_amount='305.81')
        with patch.object(crypto.cryptoway_client,'create_invoice',AsyncMock(return_value=response)) as provider:
            await crypto.create_invoice(self.db,self.user,row.id,'USDTBEP20')
            again=await self.quote(request_id='another-quote-0123456789')
            self.assertEqual(again.id,row.id)
            other=CryptoPayment(user_id=11,request_id='competing-quote-0123456789',external_id='competing-unit',
                purpose='china_payment',service_request_id=33,amount_usd=Decimal('305.81'),charge_usdt=Decimal('305.81'),
                amount_cny=Decimal('2000'),cny_per_usdt=Decimal('6.54'),status='quoted',expires_at=datetime.utcnow()+timedelta(minutes=10))
            self.session.add(other);self.session.commit()
            with self.assertRaises(HTTPException) as exc:
                await crypto.create_invoice(self.db,self.user,other.id,'USDTBEP20')
            self.assertEqual(exc.exception.status_code,409)
        provider.assert_awaited_once()

    async def test_paid_crypto_handoff_runs_once_and_never_creates_card_orders(self):
        row=await self.quote();row.status='paid';row.received_usdt=row.charge_usdt;self.session.commit()
        with patch.object(crypto,'AsyncSessionLocal',return_value=self.db), \
             patch.object(services,'send_to_managers',AsyncMock(return_value={'test_manager':123})) as send:
            await asyncio.gather(crypto.fulfill_payment(row.id),crypto.fulfill_payment(row.id))
        self.assertEqual(self.request.status,'paid')
        self.assertEqual(self.request.crypto_payment_id,row.id)
        self.assertIsNone(self.request.invoice_id)
        self.assertEqual(row.fulfillment_status,'completed')
        send.assert_awaited_once()
        self.assertIn('305.81 USDT',send.call_args.args[0])
        self.assertEqual(self.session.scalar(select(func.count(Order.id))),0)

    async def test_handoff_recovers_after_request_paid_but_before_crypto_commit(self):
        row=await self.quote();row.status='paid';row.fulfillment_status='processing'
        self.request.status='paid';self.request.crypto_payment_id=row.id;self.session.commit()
        await crypto.update_order_outcome(self.db,row)
        self.assertEqual(row.fulfillment_status,'completed')

    async def test_closed_request_or_second_payment_cannot_be_handed_off(self):
        self.request.status='rejected';self.session.commit()
        with self.assertRaises(ValueError):
            await services.on_request_paid(self.db,33,crypto_payment_id=1)
        self.request.status='paid';self.request.crypto_payment_id=1;self.session.commit()
        with self.assertRaises(ValueError):
            await services.on_request_paid(self.db,33,crypto_payment_id=2)

    async def test_sbp_cannot_pay_crypto_request(self):
        app=FastAPI();app.include_router(sbp.router)
        self.user.kyc_status='success';self.user.kyc_first_name='Unit';self.user.kyc_last_name='Test'
        self.user.kyc_birth_date='01.01.1990';self.user.kyc_passport='unit-test-only';self.session.commit()
        async def db():yield self.db
        app.dependency_overrides[get_db]=db
        app.dependency_overrides[get_current_user]=lambda:self.user
        with patch.object(sbp,'_get_bb_fee_params',AsyncMock(return_value=(.021,0))), \
             patch.object(sbp.bitbanker_client,'create_invoice',AsyncMock()) as gateway:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://unit.test') as client:
                response=await client.post('/sbp/invoice',json={'purpose':'china_payment','service_request_id':33,'amount_rub':30000})
        self.assertEqual(response.status_code,409,response.text)
        gateway.assert_not_awaited()

    async def test_create_alipay_and_wechat_crypto_requests_while_sbp_disabled(self):
        app=FastAPI();app.include_router(services.router)
        async def db():yield self.db
        app.dependency_overrides[get_db]=db
        app.dependency_overrides[get_current_user]=lambda:self.user
        # The seed request should not trigger the public form's rate limiter.
        self.session.delete(self.request);self.session.commit()
        with patch.object(settings,'SBP_DISABLED',True),TemporaryDirectory() as temp,patch.object(services,'QR_DIR',Path(temp)):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://unit.test') as client:
                for index,service in enumerate(['alipay','wechat']):
                    fields={'service':service,'amount':'2000','payment_method':'crypto','recipient_type':'qr'}
                    response=await client.post('/services/requests',data=fields,files={'qr':('unit.png',b'\x89PNG\r\n\x1a\nunit','image/png')})
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['amount_usdt'],'305.81')
                    self.assertIsNone(response.json()['amount_rub'])
                    saved=self.session.get(ServiceRequest,response.json()['id']);saved.created_at=datetime.utcnow()-timedelta(minutes=1);self.session.commit()


if __name__=='__main__':unittest.main()
